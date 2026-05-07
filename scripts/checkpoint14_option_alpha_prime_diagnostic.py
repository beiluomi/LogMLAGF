"""Phase 4 / Checkpoint 14 supplementary diagnostic: Option alpha-prime (pretrained MLMHead).

Background
==========
Option alpha (commit ``1b16d25``) used **random-init frozen ModifiedMLMHead**.
Gate 5 failed (loss reduction 64.6% < 90% threshold, epoch-50 loss 3.6 > 0.3
threshold), attributed to gradient-noise pathology: a 30,678-class projection
initialised from random Gaussian has no semantic anchor, so gradient signal
back to CrossModalAttention is uniformly random direction — 50 epochs cannot
converge regardless of fusion capacity.

Option alpha-prime (alpha') fix
===========================
Load pretrained ``BertForMaskedLM`` weights into ``ModifiedMLMHead``, then
freeze.  This removes the gradient-noise confound while keeping the
"MLMHead frozen pressure forces fusion to engage" semantics intact.

Loading protocol (user-prescribed, LOCKED)
==========================================
Source: ``BertForMaskedLM.from_pretrained("bert-base-uncased")``.

  ModifiedMLMHead param          Source
  dense.weight                   cls.predictions.transform.dense.weight
  dense.bias                     cls.predictions.transform.dense.bias
  layer_norm.weight              cls.predictions.transform.LayerNorm.weight
  layer_norm.bias                cls.predictions.transform.LayerNorm.bias
  decoder.weight rows 0..30521   cls.predictions.decoder.weight (30522 rows)
  decoder.weight rows 30522+     Phase 2 synonym-mean init (existing utility)
  decoder.bias dims 0..30521     cls.predictions.bias (30522 dims)
  decoder.bias dims 30522+       zero init

Phase 2 special token init re-use
==================================
``loghetero.data.tokenizer.init_special_token_embeddings`` initialises newly
added token rows in an embedding matrix via the synonym-mean protocol.  It
operates through ``model.get_input_embeddings().weight.data``.  We wrap the
decoder.weight tensor in a thin shim so the existing utility can operate on
it without modification, satisfying the "no reinvention" constraint.

Pre-decided interpretation framework (LOCKED — apply directly, no RFC)
=======================================================================

Category 1: Gate 5 still fails
  → real fusion incapacity strong signal; 14.5 fail 时直接进架构级 RFC 评估
    Option gamma (可学习 scaling factor) 加入与其他架构修复路径,不需要再做
    root cause 回合。

Category 2: Gate 5 PASS but Gates 3/4 fail (entropy > 0.95 or cos-sim ≈ 1)
  → fusion engages but attention shape unhealthy; 14.5 解读时区分
    "fusion routes 但 attention 形态待优化" vs "fusion 完全不 engage" 两种状态:
    - 14.5 PASS → attention 形态优化推到 Phase 7 联合预训练阶段统一处理
    - 14.5 fail → 架构级 RFC 评估 attention 形态修复路径

Category 3: Gate 5 PASS AND Gates 3/4 PASS (entropy ∈ [0.3, 0.95] AND
  cos-sim < 0.95)
  → fusion fully functional 的明确证据; 14.5 解读时对融合机制健康度有确定
    prior; 14.5 fail 时其他根因优先于架构级 RFC 排查。

Scope
=====
Runs only Gates 5 / 3 / 4 (in that execution order).
Gates 1, 2, 6, 7 were already verified in the baseline run and are skipped here.

Exempt from 4-step multi-agent review pattern per
docs/known_issues.md::Phase 12 论文素材::multi-agent review pattern::"例外情况".
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Constants (identical to checkpoint14_option_alpha_diagnostic.py)
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
SEED = 42

BERT_MODEL = "bert-base-uncased"
BERT_MAX_LENGTH = 128

GATE3_ENTROPY_LO = 0.3
GATE3_ENTROPY_HI = 0.95
GATE4_COSIM_THRESHOLD = 0.95
GATE5_LOSS_THRESHOLD = 0.3
GATE5_REDUCTION_THRESHOLD = 90.0

# Number of BERT-native vocab tokens (before LogHetero special tokens).
BERT_VOCAB_SIZE: int = 30_522
# Number of LogHetero special tokens added on top.
LOGHETERO_SPECIAL_COUNT: int = 156  # == len(SPECIAL_TOKENS) from tokenizer.py


# ---------------------------------------------------------------------------
# Data utilities (mirrors checkpoint14_option_alpha_diagnostic.py)
# ---------------------------------------------------------------------------


def _parse_m3_h2() -> list:
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
            print(f"[alpha']   {path.name} missing, skipping", file=sys.stderr)
            continue
        events.extend(parser.parse_file(path, scenario_id=SCENARIO, host_id=HOST))
    events.sort(key=lambda e: e.timestamp_ns)
    return events


def _select_first_window(events: list) -> list:
    if not events:
        raise RuntimeError("Empty event stream from M3_h2")
    t_min = events[0].timestamp_ns
    return [e for e in events if e.timestamp_ns < t_min + WINDOW_NS]


def _build_full_graph(events: list):
    from loghetero.data.provenance_graph import build_graph

    full_graph, _ = build_graph(events)
    return full_graph


def _build_subgraph(full_graph, seed_idx: int, max_nodes: int = SUBGRAPH_MAX_NODES):
    from loghetero.data.parsers.base import NodeType
    from loghetero.data.subgraph_sampler import SeedNode, sample_khop_subgraph

    seed_node = SeedNode(NodeType.process, seed_idx)
    sub = sample_khop_subgraph(
        full_graph,
        seed_node,
        max_nodes=max_nodes,
        khop=SUBGRAPH_KHOP,
        edge_ranking="weight",
    )
    return sub


def _build_htgn(sub, device: torch.device, trainable: bool = True):
    from loghetero.data.parsers.base import NodeType
    from loghetero.models.graph.htgn import HTGN

    n_per_type: dict = {}
    for nt in NodeType:
        n = sub[nt.value].num_nodes if nt.value in sub.node_types else 0
        n_per_type[nt] = n

    max_count = max(n_per_type.values()) if n_per_type else 1
    htgn_node_counts = {
        nt: (max_count if nt in (NodeType.process, NodeType.socket) else n_per_type[nt])
        for nt in NodeType
    }

    metadata = sub.metadata()
    htgn = HTGN(
        in_channels=HIDDEN_DIM,
        metadata=metadata,
        num_nodes_per_type=htgn_node_counts,
        hidden_dim=HIDDEN_DIM,
        n_layers=N_LAYERS,
        num_heads=NUM_HEADS,
        dropout=DROPOUT,
        time2vec_dim=TIME2VEC_DIM,
        residual_alpha=0.5,
        layer_decay_gamma=(1.0, 0.7, 0.4),
        memory_node_types=(NodeType.process, NodeType.socket),
        raw_msg_dim=RAW_MSG_DIM,
    ).to(device)

    for p in htgn.parameters():
        p.requires_grad = trainable

    return htgn, n_per_type


def _build_x_edge_dicts(sub, n_per_type: dict, device: torch.device):
    from loghetero.data.parsers.base import NodeType

    torch.manual_seed(SEED)
    x_dict: dict[str, torch.Tensor] = {}
    for nt in NodeType:
        n = n_per_type[nt]
        if n > 0:
            x_dict[nt.value] = torch.randn(n, HIDDEN_DIM, device=device)

    edge_index_dict = {}
    edge_time_dict_ns = {}
    for rel in sub.edge_types:
        ei = sub[rel].edge_index.to(device)
        et = sub[rel].edge_attr_time.to(device)
        edge_index_dict[rel] = ei
        edge_time_dict_ns[rel] = et

    return x_dict, edge_index_dict, edge_time_dict_ns


def _build_text_batch(
    window_events: list,
    batch_size: int,
    tokenizer,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, list[str]]:
    from loghetero.data.datamodule import event_to_text

    texts = [event_to_text(e) for e in window_events[:batch_size]]
    enc = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=BERT_MAX_LENGTH,
        return_tensors="pt",
    )
    return (
        enc["input_ids"].to(device),
        enc["attention_mask"].to(device),
        texts,
    )


# ---------------------------------------------------------------------------
# Pretrained MLMHead loading (Option alpha-prime core: user-prescribed protocol)
# ---------------------------------------------------------------------------


class _EmbeddingWeightProxy:
    """Thin shim so ``init_special_token_embeddings`` can write to decoder.weight.

    ``init_special_token_embeddings(model, tokenizer)`` calls::

        embeddings = model.get_input_embeddings().weight.data

    The call chain is:
        model.get_input_embeddings()  →  an object with ``.weight``
        .weight                       →  an object with ``.data``
        .data                         →  the actual tensor

    ``_ModelProxyForSpecialTokenInit.get_input_embeddings()`` returns this
    class, whose ``.weight`` attribute IS this instance itself (so ``.weight.data``
    reaches the underlying decoder.weight tensor via the ``.data`` property).

    Redirect means the Phase 2 synonym-mean utility operates on the decoder
    output projection rows instead of an input embedding — same vocabulary
    layout, identical initialisation semantics — without reinventing any
    synonym-mean computation.
    """

    def __init__(self, weight_tensor: torch.Tensor) -> None:
        # ``self.weight = self`` so that ``.weight.data`` resolves correctly.
        self._weight_tensor = weight_tensor
        # The proxy acts as both the "embedding module" and its own ".weight".
        self.weight: _EmbeddingWeightProxy = self  # type: ignore[assignment]

    @property
    def data(self) -> torch.Tensor:
        return self._weight_tensor


class _ModelProxyForSpecialTokenInit:
    """Proxy model whose ``get_input_embeddings()`` returns the embedding proxy."""

    def __init__(self, decoder_weight: torch.Tensor) -> None:
        self._proxy = _EmbeddingWeightProxy(decoder_weight)

    def get_input_embeddings(self) -> _EmbeddingWeightProxy:  # type: ignore[override]
        return self._proxy


def load_pretrained_mlm_head(model, tokenizer) -> dict[str, int]:  # type: ignore[return]
    """Load pretrained BERT MLM head weights into ``model.mlm_head``.

    Implements the user-prescribed 8-tensor loading protocol exactly:

    1. dense.weight / dense.bias                 ← transform.dense
    2. layer_norm.weight / layer_norm.bias        ← transform.LayerNorm
    3. decoder.weight rows 0..30521              ← cls.predictions.decoder.weight
    4. decoder.weight rows 30522+               ← Phase 2 synonym-mean (re-used utility)
    5. decoder.bias dims 0..30521               ← cls.predictions.bias
    6. decoder.bias dims 30522+                 ← zero init

    Args:
        model: Phase4Model instance; ``model.mlm_head`` is a ModifiedMLMHead.
        tokenizer: the augmented BERT tokenizer already attached to the model
            (bert-base-uncased + 156 LogHetero special tokens).

    Returns:
        dict with counts: ``{"bert_rows_copied": 30522, "special_rows_initialised": N,
        "special_rows_random_unk": M}``.
    """
    from transformers import BertForMaskedLM

    from loghetero.data.tokenizer import init_special_token_embeddings

    print("[alpha'] Loading BertForMaskedLM (bert-base-uncased) weights ...")
    bfm = BertForMaskedLM.from_pretrained(BERT_MODEL)
    bfm.eval()

    mlm_head = model.mlm_head
    preds = bfm.cls.predictions

    with torch.no_grad():
        # ------------------------------------------------------------------
        # 1-2. Transform block: dense + LayerNorm
        # ------------------------------------------------------------------
        mlm_head.dense.weight.copy_(preds.transform.dense.weight)
        mlm_head.dense.bias.copy_(preds.transform.dense.bias)
        mlm_head.layer_norm.weight.copy_(preds.transform.LayerNorm.weight)
        mlm_head.layer_norm.bias.copy_(preds.transform.LayerNorm.bias)

        # ------------------------------------------------------------------
        # 3. decoder.weight rows 0..30521 ← BERT native vocab (30522 rows)
        # ------------------------------------------------------------------
        bert_decoder_w = preds.decoder.weight  # (30522, 768) — tied to embeddings
        assert bert_decoder_w.shape == (
            BERT_VOCAB_SIZE,
            768,
        ), f"Expected BERT decoder.weight (30522, 768), got {bert_decoder_w.shape}"
        mlm_head.decoder.weight.data[:BERT_VOCAB_SIZE, :].copy_(bert_decoder_w)

        # ------------------------------------------------------------------
        # 5. decoder.bias dims 0..30521 ← cls.predictions.bias (30522 dims)
        # ------------------------------------------------------------------
        bert_pred_bias = preds.bias  # (30522,) — same tensor as decoder.bias
        assert bert_pred_bias.shape == (
            BERT_VOCAB_SIZE,
        ), f"Expected BERT predictions.bias (30522,), got {bert_pred_bias.shape}"
        mlm_head.decoder.bias.data[:BERT_VOCAB_SIZE].copy_(bert_pred_bias)

        # ------------------------------------------------------------------
        # 6. decoder.bias dims 30522+ ← zero init (convention verified:
        #    Phase 2 init_special_token_embeddings only touches .weight rows,
        #    not bias; zero bias for special tokens is the correct convention)
        # ------------------------------------------------------------------
        mlm_head.decoder.bias.data[BERT_VOCAB_SIZE:].zero_()

    # ------------------------------------------------------------------------
    # 4. decoder.weight rows 30522+ ← Phase 2 synonym-mean utility (re-used)
    #
    # init_special_token_embeddings(model, tokenizer) writes synonym-mean
    # embeddings into model.get_input_embeddings().weight.data at the token
    # IDs corresponding to SPECIAL_TOKENS (which are 30522..30677).
    #
    # We proxy the decoder.weight tensor as if it were an input embedding so
    # the existing utility can operate on it without modification.
    # ------------------------------------------------------------------------
    decoder_weight = mlm_head.decoder.weight.data  # (30678, 768) in-place target
    proxy_model = _ModelProxyForSpecialTokenInit(decoder_weight)
    statuses = init_special_token_embeddings(proxy_model, tokenizer)  # type: ignore[arg-type]

    n_initialised = sum(1 for v in statuses.values() if v == "initialised")
    n_random_unk = sum(1 for v in statuses.values() if v == "random_unk_synonyms")
    n_missing = sum(1 for v in statuses.values() if v == "missing_in_vocab")

    print(
        f"[alpha']   decoder.weight special rows: "
        f"{n_initialised} initialised (synonym-mean), "
        f"{n_random_unk} random (unk synonyms), "
        f"{n_missing} missing in vocab"
    )

    del bfm  # free BertForMaskedLM memory after copy

    return {
        "bert_rows_copied": BERT_VOCAB_SIZE,
        "special_rows_initialised": n_initialised,
        "special_rows_random_unk": n_random_unk,
        "special_rows_missing": n_missing,
    }


def _freeze_mlm_head_pretrained(model) -> int:
    """Freeze all parameters of model.mlm_head (pretrained weights loaded).

    Returns the count of frozen parameters.
    """
    frozen = 0
    for p in model.mlm_head.parameters():
        p.requires_grad = False
        frozen += p.numel()
    return frozen


# ---------------------------------------------------------------------------
# Gate helpers (identical to baseline / alpha scripts)
# ---------------------------------------------------------------------------


def _compute_entropy_scalar(attn_weights: torch.Tensor) -> float:
    """Mean-aggregate normalised entropy; RFC-4."""
    b, h, q, k = attn_weights.shape
    if k <= 1:
        return 1.0
    eps = 1e-9
    log_k = torch.log(torch.tensor(float(k)))
    entropy_per_query = -(attn_weights * torch.log(attn_weights + eps)).sum(dim=-1) / log_k
    return float(entropy_per_query.mean().item())


def _cosim_stats(a: torch.Tensor, b: torch.Tensor) -> dict[str, float]:
    """Cos-sim statistics (B, T, D) → mean + p10/p50/p90; RFC-5."""
    a_flat = a.reshape(-1, a.shape[-1]).float()
    b_flat = b.reshape(-1, b.shape[-1]).float()
    cos = torch.nn.functional.cosine_similarity(a_flat, b_flat, dim=-1)
    return {
        "mean": float(cos.mean().item()),
        "p10": float(torch.quantile(cos, 0.10).item()),
        "p50": float(torch.quantile(cos, 0.50).item()),
        "p90": float(torch.quantile(cos, 0.90).item()),
    }


# ---------------------------------------------------------------------------
# Gate 5 (Option alpha-prime variant: pretrained + frozen MLMHead)
# ---------------------------------------------------------------------------


def run_gate5_alpha_prime(
    model_class,
    htgn_factory,
    window_events: list,
    tokenizer,
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[bool, dict, object]:
    """Gate 5 (alpha'): 8-sample x 50-epoch overfit with pretrained+frozen MLMHead.

    Trainable: HTGN + CrossModalAttention (4x).
    Frozen:    BERT (baseline) + MLMHead (pretrained, NOT random-init).

    The pretrained MLMHead removes the gradient-noise pathology of Option alpha
    while preserving the fusion-engagement pressure: the only way to reduce MLM
    loss is to route useful graph information through CrossModalAttention.

    Returns (passed, info_dict, trained_model).
    The trained model is left in eval mode for Gates 3 and 4.
    """
    print("[G5alpha']  running 8-sample x 50-epoch overfit (pretrained frozen MLMHead) ...")

    htgn, _ = htgn_factory()
    model_overfit = model_class(htgn=htgn).to(device)

    # Load pretrained BERT MLM head weights + freeze.
    load_info = load_pretrained_mlm_head(model_overfit, tokenizer)
    n_frozen = _freeze_mlm_head_pretrained(model_overfit)
    n_trainable = sum(p.numel() for p in model_overfit.parameters() if p.requires_grad)
    print(
        f"[G5alpha']    MLMHead frozen: {n_frozen:,} params (pretrained BERT weights); "
        f"BERT vocab rows copied: {load_info['bert_rows_copied']:,}; "
        f"special rows init: {load_info['special_rows_initialised']} synonym-mean + "
        f"{load_info['special_rows_random_unk']} random-unk"
    )
    print(f"[G5alpha']    trainable: {n_trainable:,} params (HTGN + CrossModalAttention only)")

    model_overfit.train()

    input_ids, attention_mask, _texts = _build_text_batch(window_events, 8, tokenizer, device)
    x_dict, edge_index_dict, edge_time_dict_ns = _build_x_edge_dicts(sub, n_per_type, device)

    # Fixed labels: mask every 5th token (same as baseline Gate 5 and alpha).
    batch_size, seq_len = input_ids.shape
    labels = torch.full((batch_size, seq_len), -100, dtype=torch.long, device=device)
    for pos in range(2, seq_len - 1, 5):
        labels[:, pos] = input_ids[:, pos]

    # Only trainable params (HTGN + CrossModalAttention).
    trainable_params = [p for p in model_overfit.parameters() if p.requires_grad]
    optimizer = torch.optim.Adam(trainable_params, lr=1e-3)

    losses: list[float] = []
    for epoch in range(50):
        model_overfit.htgn.tgn_memory.reset_state()
        model_overfit.htgn.tgn_memory.detach()
        optimizer.zero_grad()
        out = model_overfit(
            input_ids=input_ids,
            attention_mask=attention_mask,
            x_dict={k: v.clone() for k, v in x_dict.items()},
            edge_index_dict=edge_index_dict,
            edge_time_dict_ns=edge_time_dict_ns,
            labels=labels,
        )
        loss = out["loss"]
        assert loss is not None
        loss.backward()
        model_overfit.htgn.tgn_memory.detach()
        optimizer.step()
        losses.append(float(loss.item()))
        if (epoch + 1) % 10 == 0:
            print(f"[G5alpha']      epoch {epoch + 1}/50: loss={losses[-1]:.4f}")

    loss_e1 = losses[0]
    loss_e50 = losses[-1]
    reduction_pct = 100.0 * (loss_e1 - loss_e50) / max(abs(loss_e1), 1e-9)
    passed = (loss_e50 < GATE5_LOSS_THRESHOLD) and (reduction_pct > GATE5_REDUCTION_THRESHOLD)

    model_overfit.eval()
    return (
        passed,
        {
            "loss_epoch1": loss_e1,
            "loss_epoch50": loss_e50,
            "reduction_pct": reduction_pct,
        },
        model_overfit,
    )


# ---------------------------------------------------------------------------
# Gate 3 (post-G5alpha' trained state)
# ---------------------------------------------------------------------------


def run_gate3_entropy(
    model,
    window_events: list,
    tokenizer,
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[bool, dict]:
    """Gate 3: cross-attn entropy in [0.3, 0.95] for all 8 scalars."""
    print("[G3alpha']  computing cross-attention entropy (8 scalars) ...")

    model.eval()
    model.htgn.tgn_memory.reset_state()

    input_ids, attention_mask, _texts = _build_text_batch(window_events, 8, tokenizer, device)
    x_dict, edge_index_dict, edge_time_dict_ns = _build_x_edge_dicts(sub, n_per_type, device)

    with torch.no_grad():
        out = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            edge_time_dict_ns=edge_time_dict_ns,
        )

    attn_weights_list = out["attn_weights"]
    scalars: dict[str, float] = {}
    all_pass = True

    for k, w_dict in enumerate(attn_weights_list):
        for direction in ("text_to_graph", "graph_to_text"):
            weights = w_dict[direction]
            h = _compute_entropy_scalar(weights)
            label = f"fusion{k + 1}_{direction}"
            scalars[label] = h
            if not (GATE3_ENTROPY_LO <= h <= GATE3_ENTROPY_HI):
                all_pass = False

    return all_pass, scalars


# ---------------------------------------------------------------------------
# Gate 4 (post-G5alpha' trained state)
# ---------------------------------------------------------------------------


def run_gate4_modality_dropout(
    model,
    window_events: list,
    tokenizer,
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[bool, dict]:
    """Gate 4: modality dropout cos-sim < 0.95."""
    print("[G4alpha']  running modality dropout comparison ...")

    model.eval()

    input_ids, attention_mask, _texts = _build_text_batch(window_events, 8, tokenizer, device)
    x_dict, edge_index_dict, edge_time_dict_ns = _build_x_edge_dicts(sub, n_per_type, device)

    model.htgn.tgn_memory.reset_state()
    with torch.no_grad():
        out_normal = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            edge_time_dict_ns=edge_time_dict_ns,
        )

    x_dict_zeroed = {k: torch.zeros_like(v) for k, v in x_dict.items()}

    model.htgn.tgn_memory.reset_state()
    with torch.no_grad():
        out_dropped = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            x_dict=x_dict_zeroed,
            edge_index_dict=edge_index_dict,
            edge_time_dict_ns=edge_time_dict_ns,
        )

    stats = _cosim_stats(out_normal["fused_text"], out_dropped["fused_text"])
    passed = stats["mean"] < GATE4_COSIM_THRESHOLD
    return passed, stats


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


def _pass_str(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _sep() -> None:
    print("=" * 76)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run Option alpha-prime diagnostic (Gate 5 → Gate 3 → Gate 4). Return 0=all-pass."""
    random.seed(SEED)
    torch.manual_seed(SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("[alpha'] Checkpoint 14 Option alpha-prime diagnostic -- pretrained frozen MLMHead")
    print("[alpha'] alpha' rationale: pretrained head removes gradient-noise pathology of alpha")
    print(f"[alpha'] device = {device}")

    # ---- Load data ---------------------------------------------------------
    print("[alpha'] Loading M3_h2 first 1.0h window ...")
    all_events = _parse_m3_h2()
    window_events = _select_first_window(all_events)
    print(f"[alpha']   window: {len(window_events):,} events")

    full_graph = _build_full_graph(window_events)
    proc_degree = full_graph["process"].degree
    main_seed_idx = int(proc_degree.argmax().item())

    sub_main = _build_subgraph(full_graph, main_seed_idx)
    from loghetero.data.parsers.base import NodeType

    n_per_type_main: dict = {}
    for nt in NodeType:
        n = sub_main[nt.value].num_nodes if nt.value in sub_main.node_types else 0
        n_per_type_main[nt] = n
    total_nodes = sum(n_per_type_main.values())
    print(
        f"[alpha']   subgraph: {total_nodes} nodes "
        f"(seed=process[{main_seed_idx}], khop={SUBGRAPH_KHOP})"
    )

    # ---- Build model class + factory ---------------------------------------
    from loghetero.models.phase4_model import Phase4Model

    def _htgn_factory():
        return _build_htgn(sub_main, device, trainable=True)

    # Load tokenizer from a fresh model (don't keep this model for gates).
    _tmp_htgn, _ = _build_htgn(sub_main, device, trainable=True)
    _tmp_model = Phase4Model(htgn=_tmp_htgn).to(device)
    tokenizer = _tmp_model.tokenizer
    del _tmp_model, _tmp_htgn

    # ---- Gate 5 (alpha': pretrained frozen MLMHead) ----------------------------
    _sep()
    print("[G5alpha']  Gate 5: 8-sample x 50-epoch overfit (pretrained frozen MLMHead)")
    print("[G5alpha']  Execution order: G5 → G3 → G4  (RFC-G3/G4-A)")
    ok5, info5, model_g5 = run_gate5_alpha_prime(
        Phase4Model,
        _htgn_factory,
        window_events,
        tokenizer,
        sub_main,
        n_per_type_main,
        device,
    )
    print(f"[G5alpha']  epoch-1  loss: {info5['loss_epoch1']:.6f}")
    print(f"[G5alpha']  epoch-50 loss: {info5['loss_epoch50']:.6f}")
    print(f"[G5alpha']  reduction:     {info5['reduction_pct']:.1f}%")
    print(f"[G5alpha']  RESULT: {_pass_str(ok5)}")

    # ---- Category 1: Gate 5 fails → real fusion incapacity ----------------
    if not ok5:
        _sep()
        print()
        print("alpha-prime RESULT CATEGORY 1: Gate 5 FAIL")
        print()
        print(
            f"  Gate 5 FAIL: loss_epoch50={info5['loss_epoch50']:.4f} "
            f"(threshold < {GATE5_LOSS_THRESHOLD}), "
            f"reduction={info5['reduction_pct']:.1f}% "
            f"(threshold > {GATE5_REDUCTION_THRESHOLD}%)"
        )
        print()
        print("  alpha' interpretation (pre-decided Category 1):")
        print("  Gate 5 fail with PRETRAINED frozen MLMHead is strong signal of")
        print("  real fusion incapacity -- gradient-noise pathology of alpha has been")
        print("  eliminated, and HTGN + CrossModalAttention still cannot route")
        print("  useful graph information to reduce MLM loss.")
        print()
        print(
            "  14.5 implication: directly enter architectural RFC evaluating Option gamma (learnable scaling factor)"
        )
        print("  and other architectural fix paths. No additional root-cause rounds needed.")
        return 1

    print("[G5alpha']  Trained model state captured → will be used for Gates 3 and 4.")

    # ---- Gate 3 (post-G5alpha' trained state) ---------------------------------
    _sep()
    print("[G3alpha']  Gate 3: cross-attn entropy in [0.3, 0.95]")
    print("[G3alpha']  (measured on post-G5alpha' trained model; RFC-G3/G4-A)")
    ok3, scalars3 = run_gate3_entropy(
        model_g5, window_events, tokenizer, sub_main, n_per_type_main, device
    )
    print("[G3alpha']  All 8 entropy scalars (RFC-4 tightening):")
    for label, h in scalars3.items():
        in_range = GATE3_ENTROPY_LO <= h <= GATE3_ENTROPY_HI
        print(f"[G3alpha']    {label}: {h:.4f}  {'in-range' if in_range else 'OUT-OF-RANGE'}")
    print(f"[G3alpha']  RESULT: {_pass_str(ok3)}")

    # ---- Gate 4 (post-G5alpha' trained state) ---------------------------------
    _sep()
    print("[G4alpha']  Gate 4: modality dropout cos-sim < 0.95")
    print("[G4alpha']  (measured on post-G5alpha' trained model; RFC-G3/G4-A)")
    ok4, stats4 = run_gate4_modality_dropout(
        model_g5, window_events, tokenizer, sub_main, n_per_type_main, device
    )
    print(
        f"[G4alpha']  fused_text cos-sim (normal vs zeroed-graph): "
        f"mean={stats4['mean']:.4f}  p10={stats4['p10']:.4f}  "
        f"p50={stats4['p50']:.4f}  p90={stats4['p90']:.4f}"
    )
    print(f"[G4alpha']  RESULT: {_pass_str(ok4)}")

    # ---- Pre-decided interpretation framework -----------------------------
    _sep()

    in_range_count = sum(1 for h in scalars3.values() if GATE3_ENTROPY_LO <= h <= GATE3_ENTROPY_HI)

    all_three_pass = ok5 and ok3 and ok4
    gate5_only = ok5 and (not ok3 or not ok4)

    print()
    print("Checkpoint 14 Option alpha-prime Supplementary Diagnostic — Result Summary")
    print()
    print(f"{'Gate':<8} {'Result':<8} Detail")
    print("-" * 76)
    print(
        f"  G5alpha'  {_pass_str(ok5):<8} "
        f"epoch1={info5['loss_epoch1']:.4f}  epoch50={info5['loss_epoch50']:.4f}  "
        f"reduction={info5['reduction_pct']:.1f}%"
    )
    print(
        f"  G3alpha'  {_pass_str(ok3):<8} "
        f"{in_range_count}/8 scalars in [{GATE3_ENTROPY_LO}, {GATE3_ENTROPY_HI}]"
    )
    print(
        f"  G4alpha'  {_pass_str(ok4):<8} "
        f"cos-sim mean={stats4['mean']:.4f}  "
        f"(threshold < {GATE4_COSIM_THRESHOLD})"
    )
    print("-" * 76)
    print()
    print("Gate 3 entropy scalars (all 8):")
    for label, h in scalars3.items():
        in_r = GATE3_ENTROPY_LO <= h <= GATE3_ENTROPY_HI
        print(f"  {label}: {h:.4f}  {'[in-range]' if in_r else '[OUT-OF-RANGE]'}")
    print()
    print("Gate 4 cos-sim percentiles:")
    print(
        f"  mean={stats4['mean']:.4f}  p10={stats4['p10']:.4f}  "
        f"p50={stats4['p50']:.4f}  p90={stats4['p90']:.4f}"
    )
    print()

    # Pre-decided category verdict.
    if all_three_pass:
        category = "Category 3: Gate 5 PASS AND Gates 3/4 PASS"
        implication = (
            "alpha' three gates all PASS -> fusion fully functional, clear evidence.\n"
            "  14.5: prior on fusion health is strong.\n"
            "  14.5 fail: other root causes (anomaly task design or TTP template leakage)\n"
            "  prioritised over architectural RFC."
        )
    elif gate5_only:
        category = "Category 2: Gate 5 PASS but Gates 3/4 fail"
        implication = (
            "alpha' Gate 5 PASS Gates 3/4 fail -> fusion engages but attention shape unhealthy.\n"
            "  14.5 PASS -> defer attention shape optimisation to Phase 7 joint pretraining.\n"
            "  14.5 fail -> architectural RFC on attention shape fix path."
        )
    else:
        # Should not reach here (Gate 5 fail already returned early above).
        category = "Category 1: Gate 5 FAIL"
        implication = "See above early-exit report."

    print(f"PRE-DECIDED RESULT CATEGORY: {category}")
    print()
    print(f"14.5 implication: {implication}")
    print()

    return 0 if all_three_pass else 1


if __name__ == "__main__":
    sys.exit(main())
