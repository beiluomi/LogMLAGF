"""Phase 4 / Checkpoint 13 perplexity comparison driver.

Validates the modified MLM (post-fusion hidden states) vs traditional MLM (raw
BERT hidden states) on M3_h2 first 1.0h window, per Q3 RFC Option A protocol.

Protocol (locked)
==================
* Data: M3_h2 first 1.0h window events (consistent with Checkpoint 10/11/12).
* 80/20 event-level split: 80% train, 20% test.
* Two configurations:
  - **Modified MLM**: frozen BERT + frozen HTGN → CrossModalAttention →
    ``fused_text`` → ``ModifiedMLMHead`` (trained).
  - **Traditional MLM**: frozen BERT → raw ``last_hidden_state`` →
    ``ModifiedMLMHead`` (separate, freshly initialised, also trained).
* Both configurations share the **same token-level masking** strategy (BERT
  standard 15% token-mask, 替換 semantics only) across both configs so the
  only variable is the hidden state backbone (fused vs raw BERT).
* 4 random seeds: [1, 7, 42, 100].  Each seed controls: (a) 80/20 split
  shuffle, (b) masking RNG, (c) head parameter init.
* 5 epochs of training per configuration per seed.
* Metric: perplexity = exp(mean token-level cross-entropy loss on test set).
* Report: mean ± std perplexity for each config + relative difference %
  + structured JSON output.

Hypothesis (NOT a hard gate; user adjudicates after seeing numbers)
===================================================================
Modified MLM perplexity < Traditional MLM perplexity, indicating that the
fused hidden states carry graph information that helps recover masked tokens.

If modified MLM perplexity >= traditional MLM, the script prints
``RESULT: NULL_FINDING`` and does NOT make a unilateral pass/fail decision
(per Q3 RFC — null finding triggers user RFC).

BERT + HTGN frozen note
========================
Both BERT and HTGN are run in eval mode with ``torch.no_grad()`` during their
forward pass; only the ``ModifiedMLMHead`` parameters are trained.  For the
modified config, ``CrossModalAttention`` is ALSO trainable (it is the only
non-frozen component besides the head), to allow it to learn to route graph
information into the fused text representation.

For the traditional config, only the ``ModifiedMLMHead`` is trained (BERT is
fully frozen; there is no cross-attention component).

Masking choice (token-level for this comparison)
=================================================
Both configs use token-level masking (``build_token_level_mask`` with
mask_prob=0.15).  This isolates the backbone effect (fused vs raw BERT) from
the masking mechanism effect.  Field-level masking is NOT used in this
comparison because the 替換/删除 operations produce different sequence shapes
across samples, complicating the per-token perplexity calculation.  The
comparison is deliberately kept clean: same masking → different backbone.

EXEMPT from 4-step multi-agent review pattern per docs/known_issues.md
("例外情况: verification scripts").
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from loghetero.models.objectives.modified_mlm import BERT_HIDDEN_DIM  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (must match checkpoint10_task_b.py / checkpoint12_real_data_smoke.py)
# ---------------------------------------------------------------------------

SCENARIO = "M3"
HOST = "M3_h2"
HOST_LOGS = PROJECT_ROOT / "data" / "raw" / "atlas" / "M3" / "h2" / "logs"
WINDOW_NS = int(3.6e12)  # 1.0h in nanoseconds
SUBGRAPH_MAX_NODES = 2000
SUBGRAPH_KHOP = 3
HIDDEN_DIM = 256
N_LAYERS = 3
NUM_HEADS = 8
DROPOUT = 0.1
TIME2VEC_DIM = 32
RAW_MSG_DIM = 64

BERT_MODEL = "bert-base-uncased"
BERT_MAX_LENGTH = 128  # per-event text; shorter than smoke12 (192) to keep
# batch processing fast; 128 tokens is sufficient for most event_to_text outputs.

# CrossModalAttention constants (locked per Phase 4 launch spec)
GRAPH_DIM = 256
ATTN_DIM = 256
ATTN_HEADS = 8
ATTN_DROPOUT = 0.1

TRAIN_FRAC = 0.80
N_SEEDS = 4
SEEDS = [1, 7, 42, 100]
EPOCHS = 5
LR = 1e-3
BATCH_SIZE = 16
MASK_PROB = 0.15

# Event count cap: the M3_h2 first window has ~74k events, but BERT forward on
# every event for 5 epochs x 4 seeds would require millions of GPU calls.  We
# cap at 500 events (randomly sampled from the first window, seeded=0 so the
# sample is reproducible across runs).  500 events gives a statistically
# meaningful 80/20 split (400 train / 100 test) and completes in a practical
# wall-clock time (~minutes on GPU).  The comparison remains valid because both
# configs see the same events; the only variable is fused vs raw BERT hidden.
MAX_EVENTS: int = 500


# ---------------------------------------------------------------------------
# Data loading (identical to checkpoint10_task_b.py / checkpoint12_real_data_smoke.py)
# ---------------------------------------------------------------------------


def _parse_m3_h2() -> list:
    """Parse all 3 M3_h2 log files into a sorted Event list."""
    from loghetero.data.parsers.atlas import DnsParser, FirefoxParser, SecurityEventsParser

    if not HOST_LOGS.is_dir():
        raise FileNotFoundError(f"{HOST_LOGS} missing; run scripts/download_atlas.sh first.")
    events = []
    for fname, parser in [
        ("dns", DnsParser()),
        ("firefox.txt", FirefoxParser()),
        ("security_events.txt", SecurityEventsParser()),
    ]:
        path = HOST_LOGS / fname
        if not path.is_file():
            print(f"[cp13]   {path.name} missing, skipping")
            continue
        events.extend(parser.parse_file(path, scenario_id=SCENARIO, host_id=HOST))
    events.sort(key=lambda e: e.timestamp_ns)
    return events


def _select_first_window(events: list) -> list:
    """Slice events to those falling in [t_min, t_min + 1.0h)."""
    if not events:
        raise RuntimeError("Empty event stream from M3_h2 -- parser misfire?")
    t_min = events[0].timestamp_ns
    window = [e for e in events if e.timestamp_ns < t_min + WINDOW_NS]
    print(f"[cp13]   first 1.0h window: {len(window):,} events (of {len(events):,} total)")
    return window


def _build_subgraph(events: list) -> tuple[Any, dict]:
    """Build full HeteroData then K-hop sample; identical to prior checkpoints."""
    from loghetero.data.parsers.base import NodeType
    from loghetero.data.provenance_graph import build_graph
    from loghetero.data.subgraph_sampler import SeedNode, sample_khop_subgraph

    full_graph, _ = build_graph(events)
    proc_count = full_graph["process"].num_nodes if "process" in full_graph.node_types else 0
    if proc_count == 0:
        raise RuntimeError("M3_h2 first window has zero process nodes")
    proc_degree = full_graph["process"].degree
    seed_idx = int(proc_degree.argmax().item())
    seed_node = SeedNode(NodeType.process, seed_idx)
    print(
        f"[cp13]   K-hop seed = process[{seed_idx}] "
        f"(deg={int(proc_degree[seed_idx].item())} of {proc_count})"
    )

    sub = sample_khop_subgraph(
        full_graph,
        seed_node,
        max_nodes=SUBGRAPH_MAX_NODES,
        khop=SUBGRAPH_KHOP,
        edge_ranking="weight",
    )
    n_per_type: dict = {}
    for nt in NodeType:
        n_per_type[nt] = sub[nt.value].num_nodes if nt.value in sub.node_types else 0
    total_nodes = sum(n_per_type.values())
    print(f"[cp13]   subgraph nodes={total_nodes}")
    return sub, n_per_type


# ---------------------------------------------------------------------------
# Event texts → tokenized batches
# ---------------------------------------------------------------------------


def _tokenize_events(
    events: list,
    tokenizer: Any,
    device: torch.device,
) -> list[torch.Tensor]:
    """Convert a list of events to token-id tensors.

    Batch-tokenizes for speed (one tokenizer call per TOKENIZE_CHUNK events).

    Returns a list of (T_i,) long tensors, one per event.
    """
    from loghetero.data.datamodule import event_to_text

    texts = [event_to_text(ev) for ev in events]
    token_lists: list[torch.Tensor] = []
    chunk_size = 64
    for i in range(0, len(texts), chunk_size):
        chunk = texts[i : i + chunk_size]
        enc = tokenizer(
            chunk,
            max_length=BERT_MAX_LENGTH,
            truncation=True,
            padding=False,
            return_tensors=None,  # plain python lists — different lengths
        )
        for ids in enc["input_ids"]:
            token_lists.append(torch.tensor(ids, dtype=torch.long, device=device))
    return token_lists


# ---------------------------------------------------------------------------
# HTGN graph embeddings: build stacked (1, N_total, 256) tensor
# ---------------------------------------------------------------------------


def _build_graph_embeddings(
    sub: Any,
    device: torch.device,
) -> tuple[torch.Tensor, dict[str, int]]:
    """Run HTGN forward on the subgraph and stack all node embeddings.

    Returns:
        graph_hidden: ``(1, N_total, 256)`` float tensor.
        ntype_sizes: dict mapping node type string to node count.
    """
    from loghetero.data.parsers.base import NodeType
    from loghetero.models.graph.htgn import HTGN

    # Build HTGN.
    node_type_names = [nt.value for nt in NodeType if nt.value in sub.node_types]
    in_channels: dict[str, int] = {}
    for nt_name in node_type_names:
        feat = getattr(sub[nt_name], "x", None)
        if feat is not None and feat.ndim == 2:
            in_channels[nt_name] = feat.shape[1]
        else:
            in_channels[nt_name] = HIDDEN_DIM

    # num_nodes_per_type (workaround from Checkpoint 10 — use max across types).
    max_nodes = max(
        (sub[nt].num_nodes for nt in node_type_names if nt in sub.node_types),
        default=1,
    )
    from loghetero.data.parsers.base import NodeType as NodeTypeEnum

    num_nodes_per_type: dict[NodeTypeEnum, int] = {
        nt: max_nodes for nt in NodeTypeEnum if nt.value in node_type_names
    }

    metadata = (
        node_type_names,
        [tuple(rel) for rel in sub.edge_types],  # type: ignore[misc]
    )

    htgn = HTGN(
        in_channels=in_channels,  # type: ignore[arg-type]
        metadata=metadata,  # type: ignore[arg-type]
        num_nodes_per_type=num_nodes_per_type,
        hidden_dim=HIDDEN_DIM,
        n_layers=N_LAYERS,
        num_heads=NUM_HEADS,
        dropout=DROPOUT,
        time2vec_dim=TIME2VEC_DIM,
        raw_msg_dim=RAW_MSG_DIM,
    ).to(device)

    # Freeze HTGN.
    for p in htgn.parameters():
        p.requires_grad = False
    htgn.eval()

    # Build x_dict and edge dicts.
    x_dict: dict[str, torch.Tensor] = {}
    for nt_name in node_type_names:
        feat = getattr(sub[nt_name], "x", None)
        if feat is not None and feat.ndim == 2:
            x_dict[nt_name] = feat.float().to(device)
        else:
            # Random Gaussian initialisation (no BERT features for this test;
            # following Checkpoint 10 approach for simplicity).
            n = sub[nt_name].num_nodes
            x_dict[nt_name] = torch.randn(n, HIDDEN_DIM, device=device)

    edge_index_dict: dict[tuple, torch.Tensor] = {}
    edge_time_dict_ns: dict[tuple, torch.Tensor] = {}
    for rel in sub.edge_types:
        rel_t = tuple(rel)
        edge_index_dict[rel_t] = sub[rel].edge_index.to(device)
        # edge_attr_time stores nanosecond timestamps.
        edge_time_dict_ns[rel_t] = sub[rel].edge_attr_time.to(device)

    with torch.no_grad():
        htgn.tgn_memory.reset_state()
        node_embs = htgn(x_dict, edge_index_dict, edge_time_dict_ns)

    # Stack embeddings in deterministic order.
    parts: list[torch.Tensor] = []
    ntype_sizes: dict[str, int] = {}
    for nt_name in sorted(node_embs.keys()):
        emb = node_embs[nt_name]  # (n_i, 256)
        parts.append(emb)
        ntype_sizes[nt_name] = emb.shape[0]

    graph_hidden = torch.cat(parts, dim=0).unsqueeze(0)  # (1, N_total, 256)
    print(f"[cp13]   graph_hidden shape: {graph_hidden.shape}")
    return graph_hidden, ntype_sizes


# ---------------------------------------------------------------------------
# BERT forward: last-layer hidden states for a batch of token-id tensors
# ---------------------------------------------------------------------------


def _bert_last_hidden(
    token_ids: torch.Tensor,  # (B, T)
    bert_model: Any,
    device: torch.device,
) -> torch.Tensor:
    """Return BERT last hidden states for a batch.

    Args:
        token_ids: (B, T) long tensor (padded).
        bert_model: frozen BERT model.
        device: computation device.

    Returns:
        (B, T, 768) float tensor.
    """
    attn_mask = (token_ids != 0).long()
    with torch.no_grad():
        out = bert_model(input_ids=token_ids, attention_mask=attn_mask)
    return out.last_hidden_state  # (B, T, 768)


# ---------------------------------------------------------------------------
# Padding utility
# ---------------------------------------------------------------------------


def _pad_batch(
    token_list: list[torch.Tensor],
    pad_id: int = 0,
) -> torch.Tensor:
    """Pad a list of (T_i,) tensors to the same length and stack."""
    max_len = max(t.shape[0] for t in token_list)
    result = torch.full(
        (len(token_list), max_len), pad_id, dtype=torch.long, device=token_list[0].device
    )
    for i, t in enumerate(token_list):
        result[i, : t.shape[0]] = t
    return result


# ---------------------------------------------------------------------------
# Training and evaluation utilities
# ---------------------------------------------------------------------------


def _apply_token_mask(
    token_ids: torch.Tensor,  # (B, T)
    mask_prob: float,
    rng: torch.Generator,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Apply token-level masking to a padded batch.

    Delegates per-sample masking to ``build_token_level_mask`` from the module
    (module utility is per-sample only; batched iteration is kept here and will
    be refactored when the module gains a batched API).

    Returns:
        masked_ids: (B, T) with MASK_TOKEN_ID at masked positions.
        labels: (B, T) with original ids at masked positions, -100 elsewhere.
    """
    from loghetero.models.objectives.modified_mlm import IGNORE_INDEX, build_token_level_mask

    b, t = token_ids.shape
    masked_rows: list[torch.Tensor] = []
    label_rows: list[torch.Tensor] = []
    for i in range(b):
        out = build_token_level_mask(token_ids[i].cpu(), mask_prob=mask_prob, rng=rng)
        masked_rows.append(out.input_ids)
        label_rows.append(out.labels)

    masked_ids = torch.stack(masked_rows, dim=0).to(token_ids.device)
    labels = torch.stack(label_rows, dim=0).to(token_ids.device)
    # Ensure IGNORE_INDEX fill value at padding positions beyond original length.
    _ = IGNORE_INDEX  # confirms import used; padding already handled by build_token_level_mask
    return masked_ids, labels


def _compute_perplexity_batch(
    logits: torch.Tensor,  # (B, T, V)
    labels: torch.Tensor,  # (B, T)
) -> float:
    """Compute perplexity = exp(mean CE loss) over all unignored positions."""
    import torch.nn.functional as func

    flat_logits = logits.view(-1, logits.shape[-1])
    flat_labels = labels.view(-1)
    ce = func.cross_entropy(flat_logits, flat_labels, ignore_index=-100, reduction="mean")
    return math.exp(ce.item())


# ---------------------------------------------------------------------------
# Config runners
# ---------------------------------------------------------------------------


class ModifiedMLMConfig:
    """Frozen BERT + frozen HTGN + CrossModalAttention + ModifiedMLMHead."""

    def __init__(
        self,
        graph_hidden: torch.Tensor,  # (1, N_total, 256) — shared across events
        bert_model: Any,
        device: torch.device,
        seed: int,
    ) -> None:
        from loghetero.models.fusion.cross_attention import CrossModalAttention
        from loghetero.models.objectives.modified_mlm import ModifiedMLMHead

        torch.manual_seed(seed)
        self.cross_attn = CrossModalAttention(
            text_dim=BERT_HIDDEN_DIM,
            graph_dim=GRAPH_DIM,
            attn_dim=ATTN_DIM,
            num_heads=ATTN_HEADS,
            dropout=ATTN_DROPOUT,
        ).to(device)
        self.head = ModifiedMLMHead(hidden_dim=BERT_HIDDEN_DIM).to(device)
        self.bert_model = bert_model
        self.graph_hidden = graph_hidden  # (1, N_total, 256)
        self.device = device

        # Only cross_attn and head are trainable.
        self.optimizer = torch.optim.Adam(
            list(self.cross_attn.parameters()) + list(self.head.parameters()),
            lr=LR,
        )

    def forward(
        self,
        token_ids: torch.Tensor,  # (B, T)
    ) -> torch.Tensor:
        """Compute logits via fused_text hidden states."""
        # BERT last hidden states (frozen).
        bert_hidden = _bert_last_hidden(token_ids, self.bert_model, self.device)  # (B, T, 768)

        # Expand graph_hidden to batch size.
        b = bert_hidden.shape[0]
        graph_exp = self.graph_hidden.expand(b, -1, -1)  # (B, N_total, 256)

        # CrossModalAttention fusion (trainable).
        fused_text, _fused_graph, _weights = self.cross_attn(bert_hidden, graph_exp)  # (B, T, 768)

        # ModifiedMLMHead (trainable).
        logits = self.head(fused_text)  # (B, T, vocab_size)
        return logits

    def train_step(
        self,
        masked_ids: torch.Tensor,
        labels: torch.Tensor,
    ) -> float:
        from loghetero.models.objectives.modified_mlm import compute_mlm_loss

        self.cross_attn.train()
        self.head.train()
        self.optimizer.zero_grad()
        logits = self.forward(masked_ids)
        loss = compute_mlm_loss(logits, labels)
        loss.backward()
        self.optimizer.step()
        return loss.item()

    def eval_perplexity(
        self,
        masked_ids: torch.Tensor,
        labels: torch.Tensor,
    ) -> float:
        self.cross_attn.eval()
        self.head.eval()
        with torch.no_grad():
            logits = self.forward(masked_ids)
        return _compute_perplexity_batch(logits, labels)


class TraditionalMLMConfig:
    """Frozen BERT only → raw last_hidden_state → ModifiedMLMHead."""

    def __init__(
        self,
        bert_model: Any,
        device: torch.device,
        seed: int,
    ) -> None:
        from loghetero.models.objectives.modified_mlm import ModifiedMLMHead

        torch.manual_seed(seed)
        self.head = ModifiedMLMHead(hidden_dim=BERT_HIDDEN_DIM).to(device)
        self.bert_model = bert_model
        self.device = device

        # Only head is trainable.
        self.optimizer = torch.optim.Adam(self.head.parameters(), lr=LR)

    def forward(
        self,
        token_ids: torch.Tensor,  # (B, T)
    ) -> torch.Tensor:
        """Compute logits from raw BERT last hidden states."""
        bert_hidden = _bert_last_hidden(token_ids, self.bert_model, self.device)  # (B, T, 768)
        logits = self.head(bert_hidden)  # (B, T, vocab_size)
        return logits

    def train_step(
        self,
        masked_ids: torch.Tensor,
        labels: torch.Tensor,
    ) -> float:
        from loghetero.models.objectives.modified_mlm import compute_mlm_loss

        self.head.train()
        self.optimizer.zero_grad()
        logits = self.forward(masked_ids)
        loss = compute_mlm_loss(logits, labels)
        loss.backward()
        self.optimizer.step()
        return loss.item()

    def eval_perplexity(
        self,
        masked_ids: torch.Tensor,
        labels: torch.Tensor,
    ) -> float:
        self.head.eval()
        with torch.no_grad():
            logits = self.forward(masked_ids)
        return _compute_perplexity_batch(logits, labels)


# ---------------------------------------------------------------------------
# Single seed runner
# ---------------------------------------------------------------------------


def _run_one_seed(
    seed: int,
    all_token_ids: list[torch.Tensor],  # one per event in first window
    graph_hidden: torch.Tensor,
    bert_model: Any,
    device: torch.device,
) -> dict[str, float]:
    """Run both configs for one seed; return perplexity for each."""
    # 80/20 split.
    rng_split = random.Random(seed)
    indices = list(range(len(all_token_ids)))
    rng_split.shuffle(indices)
    n_train = int(len(indices) * TRAIN_FRAC)
    train_indices = indices[:n_train]
    test_indices = indices[n_train:]

    train_tokens = [all_token_ids[i] for i in train_indices]
    test_tokens = [all_token_ids[i] for i in test_indices]

    print(f"[cp13]   seed={seed}: train={len(train_tokens)}, test={len(test_tokens)}")

    # Torch RNG for masking (same for both configs).
    mask_rng = torch.Generator()
    mask_rng.manual_seed(
        seed + 31337
    )  # large fixed offset to decorrelate this RNG from the split RNG

    # Initialise both configs.
    mod_config = ModifiedMLMConfig(graph_hidden, bert_model, device, seed=seed)
    trad_config = TraditionalMLMConfig(bert_model, device, seed=seed)

    # Pre-build test batch with fixed masking (same mask for both configs).
    test_padded = _pad_batch(test_tokens)  # (N_test, T_max)
    test_mask_rng = torch.Generator()
    test_mask_rng.manual_seed(
        seed + 99999
    )  # large fixed offset to decorrelate this RNG from the train mask RNG
    test_masked, test_labels = _apply_token_mask(test_padded, MASK_PROB, test_mask_rng)

    # Training loop (5 epochs, same batches for both configs).
    for epoch in range(1, EPOCHS + 1):
        # Shuffle train batches each epoch.
        epoch_rng = random.Random(seed * 1000 + epoch)
        shuffled = list(train_tokens)
        epoch_rng.shuffle(shuffled)

        mod_losses: list[float] = []
        trad_losses: list[float] = []

        for batch_start in range(0, len(shuffled), BATCH_SIZE):
            batch_tokens = shuffled[batch_start : batch_start + BATCH_SIZE]
            if not batch_tokens:
                continue
            padded = _pad_batch(batch_tokens)  # (B, T_max)
            masked, labels = _apply_token_mask(padded, MASK_PROB, mask_rng)

            mod_loss = mod_config.train_step(masked, labels)
            trad_loss = trad_config.train_step(masked, labels)
            mod_losses.append(mod_loss)
            trad_losses.append(trad_loss)

        mean_mod = sum(mod_losses) / max(len(mod_losses), 1)
        mean_trad = sum(trad_losses) / max(len(trad_losses), 1)
        print(
            f"[cp13]   seed={seed} epoch={epoch}/{EPOCHS}  "
            f"mod_loss={mean_mod:.4f}  trad_loss={mean_trad:.4f}"
        )

    # Compute test perplexity.
    mod_ppl = mod_config.eval_perplexity(test_masked, test_labels)
    trad_ppl = trad_config.eval_perplexity(test_masked, test_labels)

    print(f"[cp13]   seed={seed} DONE  " f"mod_ppl={mod_ppl:.2f}  trad_ppl={trad_ppl:.2f}")
    return {"modified_ppl": mod_ppl, "traditional_ppl": trad_ppl}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Checkpoint 13 perplexity comparison")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/checkpoint13_perplexity.json"),
        help="Path for JSON output",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device: 'auto' / 'cuda' / 'cpu'",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=MAX_EVENTS,
        help=f"Cap event count for tractable runtime (default {MAX_EVENTS})",
    )
    args = parser.parse_args()

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"[cp13] using device: {device}")

    # --- Data loading -------------------------------------------------------
    t0 = time.time()
    print("[cp13] parsing M3_h2 logs ...")
    events = _parse_m3_h2()
    window_events = _select_first_window(events)

    print("[cp13] building K-hop subgraph ...")
    sub, _n_per_type = _build_subgraph(window_events)

    print("[cp13] building HTGN graph embeddings (frozen) ...")
    graph_hidden, _ntype_sizes = _build_graph_embeddings(sub, device)

    print(f"[cp13] loading frozen BERT {BERT_MODEL} ...")
    from loghetero.models.encoders.bert_text import TrainMode, build_bert_text_encoder

    bert_model, tokenizer = build_bert_text_encoder(BERT_MODEL, mode=TrainMode.frozen)
    bert_model = bert_model.to(device)
    bert_model.eval()

    # Cap events for tractable runtime (see MAX_EVENTS constant).
    max_ev = args.max_events
    if len(window_events) > max_ev:
        rng_cap = random.Random(0)  # fixed seed=0 for reproducibility across runs
        window_events_sample = rng_cap.sample(window_events, max_ev)
        print(f"[cp13] capping to {max_ev} events (from {len(window_events):,})")
    else:
        window_events_sample = window_events

    print(f"[cp13] tokenizing {len(window_events_sample)} events ...")
    all_token_ids = _tokenize_events(window_events_sample, tokenizer, device)
    print(
        f"[cp13] tokenized {len(all_token_ids)} events, data loading done in {time.time()-t0:.1f}s"
    )

    # --- Seed loop -----------------------------------------------------------
    results_by_seed: list[dict[str, float]] = []
    for seed in SEEDS:
        print(f"\n[cp13] === seed {seed} ===")
        seed_result = _run_one_seed(
            seed,
            all_token_ids,
            graph_hidden,
            bert_model,
            device,
        )
        results_by_seed.append(seed_result)

    # --- Aggregate statistics -----------------------------------------------
    import statistics

    mod_ppls = [r["modified_ppl"] for r in results_by_seed]
    trad_ppls = [r["traditional_ppl"] for r in results_by_seed]

    mod_mean = statistics.mean(mod_ppls)
    mod_std = statistics.stdev(mod_ppls) if len(mod_ppls) > 1 else 0.0
    trad_mean = statistics.mean(trad_ppls)
    trad_std = statistics.stdev(trad_ppls) if len(trad_ppls) > 1 else 0.0

    # Relative difference: (trad - mod) / trad * 100%
    # Positive = modified MLM is lower (better).
    rel_diff_pct = (trad_mean - mod_mean) / trad_mean * 100.0 if trad_mean != 0 else float("nan")

    # Hypothesis outcome.
    outcome = "PASS_HYPOTHESIS" if mod_mean < trad_mean else "NULL_FINDING"

    print("\n" + "=" * 70)
    print("CHECKPOINT 13 PERPLEXITY COMPARISON RESULTS")
    print("=" * 70)
    print(f"  Modified  MLM perplexity: {mod_mean:.2f} ± {mod_std:.2f}  (seeds={SEEDS})")
    print(f"  Traditional MLM perplexity: {trad_mean:.2f} ± {trad_std:.2f}")
    print(f"  Relative difference (trad-mod)/trad: {rel_diff_pct:+.1f}%")
    print(f"  Per-seed modified:    {[f'{p:.2f}' for p in mod_ppls]}")
    print(f"  Per-seed traditional: {[f'{p:.2f}' for p in trad_ppls]}")
    print(f"\n  RESULT: {outcome}")
    if outcome == "NULL_FINDING":
        print(
            "  WARNING: Modified MLM perplexity >= Traditional MLM perplexity.\n"
            "  This is a NULL FINDING. Do NOT unilaterally call it a pass or fail.\n"
            "  Report to user via RFC before making any decisions."
        )
    print("=" * 70)

    # --- JSON output --------------------------------------------------------
    report = {
        "checkpoint": 13,
        "protocol": {
            "data": "M3_h2 first 1.0h window",
            "split": f"{int(TRAIN_FRAC*100)}/{int((1-TRAIN_FRAC)*100)} train/test",
            "epochs": EPOCHS,
            "seeds": SEEDS,
            "mask_strategy": "token_level_15pct",
            "modified_config": "frozen_BERT + frozen_HTGN + trainable_CrossModalAttention + ModifiedMLMHead",
            "traditional_config": "frozen_BERT + trainable_ModifiedMLMHead",
        },
        "results": {
            "modified_mean": mod_mean,
            "modified_std": mod_std,
            "traditional_mean": trad_mean,
            "traditional_std": trad_std,
            "relative_diff_pct": rel_diff_pct,
            "per_seed": [
                {
                    "seed": s,
                    "modified_ppl": r["modified_ppl"],
                    "traditional_ppl": r["traditional_ppl"],
                }
                for s, r in zip(SEEDS, results_by_seed, strict=True)
            ],
        },
        "outcome": outcome,
        "note": (
            "NULL_FINDING requires RFC with user before any pass/fail decision."
            if outcome == "NULL_FINDING"
            else "Hypothesis confirmed: fused hidden states lower perplexity vs raw BERT."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[cp13] JSON report written to {args.output}")


if __name__ == "__main__":
    main()
