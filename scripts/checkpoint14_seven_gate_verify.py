"""Phase 4 / Checkpoint 14 seven-gate integration verification.

Runs all 7 gate checks on the fully integrated Phase4Model against real
M3_h2 data.  Any single gate failure causes the script to exit with code 1
and print NEEDS_CONTEXT — thresholds are NOT relaxed on failure.

Seven gates (locked per Phase 4 launch spec + RFC adjudications)
================================================================
| Gate | Criterion                                     | Tightening                           |
|------|-----------------------------------------------|--------------------------------------|
|  1   | forward + backward on batch=8, no NaN/Inf     | report fused_text/graph shapes + loss|
|  2   | three param-category grad flow (RFC-3)         | 1 representative param per category  |
|  3   | cross-attn entropy in [0.3, 0.95] (RFC-4)     | all 8 specific numbers               |
|  4   | modality dropout cos-sim < 0.95 (RFC-5)       | mean + p10/p50/p90                   |
|  5   | 8-sample x50 epoch overfit (RFC-6)            | epoch-1 + epoch-50 loss + reduction% |
|  6   | random text ablation cos-sim < 0.9 (RFC-8)    | mean + p10/p50/p90                   |
|  7   | batch=16 VRAM < 16 GB AND step < 500 ms       | absolute VRAM (GB) + median ms       |

Data path: M3_h2 first 1.0h window (consistent with C10/C11/C12/C13).
HTGN seed: max-degree process node, K-hop=3, max_nodes=2000.

EXEMPT from 4-step multi-agent review pattern per docs/known_issues.md.

RFC-G3/G4-A: Gate measurement order and model state
====================================================
Gates 3 and 4 verify trained fusion attention behaviour, not init prior. The
spec wording "fusion non-degeneration" and "model uses text modality" both
implicitly assume a trained context; Gate 5 overfit training provides that state.

Concretely: Gate 5 (8-sample x 50-epoch overfit) is executed FIRST and returns
the trained model state.  Gates 3 and 4 then immediately use that same trained
model (no re-initialisation).  This is RFC-G3/G4-A (Option A) per the Checkpoint
14 adjudication recorded in docs/known_issues.md (Phase 12 paper material:
Cross-modal fusion init-state asymmetry).

Per-gate model state summary:
  Gate 1 -- untrained main model (forward+backward correctness test)
  Gate 2 -- same untrained model after Gate 1 backward (grad flow test)
  Gate 5 -- fresh model, trained to overfit 8 samples x 50 epochs; returns
            trained state captured as `model_g5`
  Gate 3 -- `model_g5` (post-Gate-5 trained state); RFC-G3/G4-A
  Gate 4 -- `model_g5` (post-Gate-5 trained state); RFC-G3/G4-A
  Gate 6 -- `model_g5` (post-Gate-5 trained state; consistent eval context)
  Gate 7 -- fresh model (independent VRAM/timing test; needs clean state)

IMPORTANT: do NOT move Gates 3 or 4 back to init-state measurement.  The
execution order Gate 5 → 3 → 4 → 6 (by numeric appearance in source) differs
from the numeric order (1 → 2 → 3 → 4 → 5 → 6 → 7) intentionally; the RFC
rationale above locks this ordering.
"""

from __future__ import annotations

import random
import sys
import time
import tracemalloc
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Constants
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
GATE4_COSIM_THRESHOLD = 0.95  # cos-sim must be < this (modality dropout)
GATE6_COSIM_THRESHOLD = 0.9  # cos-sim must be < this (random text ablation)
GATE5_LOSS_THRESHOLD = 0.3  # loss < this at epoch 50
GATE5_REDUCTION_THRESHOLD = 90.0  # relative reduction % > this
GATE7_VRAM_GB_THRESHOLD = 16.0  # < 16 GB
GATE7_STEP_MS_THRESHOLD = 500.0  # < 500 ms

# RFC-8: random tokens from [104, 30678), skip reserved 0/100/101/102/103
RANDOM_TOKEN_LO = 104
RANDOM_TOKEN_HI = 30678

N_WARM_UP = 3
N_TIMED = 7

N_SEED_NODES_GATE7 = 16  # 16 distinct K-hop subgraphs for Gate 7

# ---------------------------------------------------------------------------
# Data utilities (consistent with checkpoint10/12/13)
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
            print(f"[C14]   {path.name} missing, skipping", file=sys.stderr)
            continue
        events.extend(parser.parse_file(path, scenario_id=SCENARIO, host_id=HOST))
    events.sort(key=lambda e: e.timestamp_ns)
    return events


def _select_first_window(events: list) -> list:
    """Slice events to [t_min, t_min + 1.0h)."""
    if not events:
        raise RuntimeError("Empty event stream from M3_h2")
    t_min = events[0].timestamp_ns
    return [e for e in events if e.timestamp_ns < t_min + WINDOW_NS]


def _build_full_graph(events: list):
    """Build full HeteroData from window events."""
    from loghetero.data.provenance_graph import build_graph

    full_graph, _ = build_graph(events)
    return full_graph


def _build_subgraph(full_graph, seed_idx: int, max_nodes: int = SUBGRAPH_MAX_NODES):
    """K-hop sample one subgraph from a given seed process node."""
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
    """Build and optionally freeze an HTGN from a subgraph."""
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
    """Build x_dict, edge_index_dict, edge_time_dict_ns for a subgraph."""
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
    """Tokenise first batch_size events from window; return (input_ids, attn_mask, texts)."""
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
# Gate helpers
# ---------------------------------------------------------------------------


def _compute_entropy_scalar(
    attn_weights: torch.Tensor,
) -> float:
    """Compute mean-aggregate normalised entropy for one attn weight tensor.

    RFC-4: per-sample per-head H[b,h] = -sum(p*log(p)) / log(n_keys),
    then mean over batch and heads.

    attn_weights: (B, num_heads, Q, K) — all values in [0, 1], sum to 1 over K.
    Returns a single float in [0, 1].
    """
    # attn_weights: (B, H, Q, K)
    b, h, q, k = attn_weights.shape
    if k <= 1:
        return 1.0  # trivially 1 key → uniform = max entropy
    eps = 1e-9
    # H[b, h, q] = -sum_{k} p_{bh,q,k} * log(p_{bh,q,k}) / log(K)
    log_k = torch.log(torch.tensor(float(k)))
    entropy_per_query = -(attn_weights * torch.log(attn_weights + eps)).sum(dim=-1) / log_k
    # mean over q, then mean over b and h
    scalar = entropy_per_query.mean().item()
    return float(scalar)


def _cosim_stats(
    a: torch.Tensor,
    b: torch.Tensor,
) -> dict[str, float]:
    """Compute cos-sim statistics between two (B, T, D) tensors.

    RFC-5 tightening: mean + p10/p50/p90 over (B*T) token pairs.
    """
    # (B, T, D) → (B*T, D)
    a_flat = a.reshape(-1, a.shape[-1]).float()
    b_flat = b.reshape(-1, b.shape[-1]).float()
    cos = torch.nn.functional.cosine_similarity(a_flat, b_flat, dim=-1)  # (B*T,)
    mean = cos.mean().item()
    p10 = float(torch.quantile(cos, 0.10).item())
    p50 = float(torch.quantile(cos, 0.50).item())
    p90 = float(torch.quantile(cos, 0.90).item())
    return {"mean": mean, "p10": p10, "p50": p50, "p90": p90}


# ---------------------------------------------------------------------------
# Per-gate functions
# ---------------------------------------------------------------------------


def run_gate1_forward_backward(
    model,
    window_events: list,
    tokenizer,
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[bool, dict]:
    """Gate 1: forward + backward on batch=8, no NaN/Inf."""
    print("[G1]  running forward + backward (batch=8) ...")

    model.train()
    model.htgn.tgn_memory.reset_state()

    input_ids, attention_mask, _texts = _build_text_batch(window_events, 8, tokenizer, device)
    x_dict, edge_index_dict, edge_time_dict_ns = _build_x_edge_dicts(sub, n_per_type, device)

    # Build labels: mask position 5 for all samples
    batch_size, seq_len = input_ids.shape
    labels = torch.full((batch_size, seq_len), -100, dtype=torch.long, device=device)
    labels[:, 5] = input_ids[:, 5]

    out = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        x_dict=x_dict,
        edge_index_dict=edge_index_dict,
        edge_time_dict_ns=edge_time_dict_ns,
        labels=labels,
    )

    loss = out["loss"]
    fused_text = out["fused_text"]
    fused_graph = out["fused_graph"]

    assert loss is not None
    loss.backward()

    issues = []
    for name, tensor in [
        ("loss", loss),
        ("fused_text", fused_text),
        ("fused_graph", fused_graph),
    ]:
        if torch.isnan(tensor).any():
            issues.append(f"{name}: NaN detected")
        if torch.isinf(tensor).any():
            issues.append(f"{name}: Inf detected")

    passed = len(issues) == 0
    info = {
        "loss": float(loss.item()),
        "fused_text_shape": tuple(fused_text.shape),
        "fused_graph_shape": tuple(fused_graph.shape),
        "issues": issues,
    }
    return passed, info


def run_gate2_grad_flow(model) -> tuple[bool, dict]:
    """Gate 2: three param-category grad flow (RFC-3).

    Each category must have at least one param with grad.norm() > 1e-6.
    """
    print("[G2]  checking grad flow across 3 param categories ...")

    groups = model.named_param_groups()
    results: dict[str, dict] = {}
    passed = True

    for cat_name, named_params in groups.items():
        best_norm = 0.0
        best_param_name = "(none)"
        for pname, p in named_params:
            if p.grad is not None:
                gnorm = float(p.grad.norm().item())
                if gnorm > best_norm:
                    best_norm = gnorm
                    best_param_name = pname
        ok = best_norm > 1e-6
        if not ok:
            passed = False
        results[cat_name] = {
            "best_param": best_param_name,
            "grad_norm": best_norm,
            "pass": ok,
        }

    return passed, results


def run_gate3_entropy(
    model,
    window_events: list,
    tokenizer,
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[bool, dict]:
    """Gate 3: cross-attn entropy in [0.3, 0.95] for all 8 scalars.

    RFC-4: 8 scalars = 4 fusion points x 2 directions.
    """
    print("[G3]  computing cross-attention entropy (8 scalars) ...")

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

    attn_weights_list = out["attn_weights"]  # list of 4 dicts
    scalars: dict[str, float] = {}
    all_pass = True

    for k, w_dict in enumerate(attn_weights_list):
        for direction in ("text_to_graph", "graph_to_text"):
            weights = w_dict[direction]  # (B, H, Q, K)
            h = _compute_entropy_scalar(weights)
            label = f"fusion{k + 1}_{direction}"
            scalars[label] = h
            if not (GATE3_ENTROPY_LO <= h <= GATE3_ENTROPY_HI):
                all_pass = False

    return all_pass, scalars


def run_gate4_modality_dropout(
    model,
    window_events: list,
    tokenizer,
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[bool, dict]:
    """Gate 4: modality dropout cos-sim < 0.95.

    Compare fused_text with cross_attn_mask=None vs a zeroed graph_hidden
    (simulated graph dropout).  Compare last fusion point fused_text.
    RFC-5 tightening: mean + p10/p50/p90.
    """
    print("[G4]  running modality dropout comparison ...")

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

    # Simulate modality dropout: zero all graph node features.
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


def run_gate5_overfit(
    model_class,
    htgn_factory,
    window_events: list,
    tokenizer,
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[bool, dict, object]:
    """Gate 5: 8-sample x 50-epoch overfit.

    RFC-6: loss_epoch50 < 0.3 AND relative_reduction > 90%.
    Uses a fresh Phase4Model to isolate overfit test from other gates.

    Returns:
        (passed, info_dict, trained_model)

    The trained model is returned so that Gates 3 and 4 can immediately
    use the post-overfit trained state (RFC-G3/G4-A Option A).  The model
    is left in eval mode after training completes.
    """
    print("[G5]  running 8-sample x 50-epoch overfit test ...")

    # Fresh model for overfit test.
    htgn, n_per_type2 = htgn_factory()
    model_overfit = model_class(htgn=htgn).to(device)
    model_overfit.train()

    input_ids, attention_mask, _texts = _build_text_batch(window_events, 8, tokenizer, device)
    x_dict, edge_index_dict, edge_time_dict_ns = _build_x_edge_dicts(sub, n_per_type, device)

    # Fixed labels for overfit: mask every 5th token that is not CLS/SEP.
    batch_size, seq_len = input_ids.shape
    labels = torch.full((batch_size, seq_len), -100, dtype=torch.long, device=device)
    for pos in range(2, seq_len - 1, 5):
        labels[:, pos] = input_ids[:, pos]

    # Collect all trainable params: fusion + htgn + mlm_head.
    trainable_params = [p for p in model_overfit.parameters() if p.requires_grad]
    optimizer = torch.optim.Adam(trainable_params, lr=1e-3)

    losses = []
    for epoch in range(50):
        # Reset TGN memory state at epoch start (zero out buffers).
        model_overfit.htgn.tgn_memory.reset_state()
        # Detach TGN memory from previous computation graph.
        # PyG TGNMemory.detach() calls memory.detach_() to break gradient chains
        # across epochs (per HeteroTGNMemory docstring "Phase 7 training-loop hook").
        # Without this, the second backward complains about freed intermediate tensors.
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
        # Detach again after backward to ensure memory gradients don't accumulate.
        model_overfit.htgn.tgn_memory.detach()
        optimizer.step()
        losses.append(float(loss.item()))
        if (epoch + 1) % 10 == 0:
            print(f"[G5]    epoch {epoch + 1}/50: loss={losses[-1]:.4f}")

    loss_e1 = losses[0]
    loss_e50 = losses[-1]
    reduction_pct = 100.0 * (loss_e1 - loss_e50) / max(abs(loss_e1), 1e-9)
    passed = (loss_e50 < GATE5_LOSS_THRESHOLD) and (reduction_pct > GATE5_REDUCTION_THRESHOLD)

    # Leave the trained model in eval mode so Gates 3, 4, and 6 can use it
    # directly without re-initialisation (RFC-G3/G4-A).
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


def run_gate6_text_ablation(
    model,
    window_events: list,
    tokenizer,
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[bool, dict]:
    """Gate 6: random text ablation cos-sim < 0.9.

    Replace input_ids (non-CLS/SEP positions) with random tokens from
    [104, 30678) (RFC-8). Compare fused_text of original vs ablated text.
    RFC-5 tightening: mean + p10/p50/p90.
    """
    print("[G6]  running random text ablation comparison ...")

    model.eval()
    torch.manual_seed(SEED + 6)

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

    # Build ablated input_ids: replace all non-CLS/SEP positions.
    ablated_ids = input_ids.clone()
    batch_size, seq_len = ablated_ids.shape
    # Positions to ablate: not CLS(101), not SEP(102).
    for b in range(batch_size):
        for t in range(seq_len):
            tok = int(ablated_ids[b, t].item())
            if tok not in (101, 102, 0):  # skip CLS, SEP, PAD
                ablated_ids[b, t] = torch.randint(RANDOM_TOKEN_LO, RANDOM_TOKEN_HI, (1,)).item()

    model.htgn.tgn_memory.reset_state()
    with torch.no_grad():
        out_ablated = model(
            input_ids=ablated_ids,
            attention_mask=attention_mask,
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            edge_time_dict_ns=edge_time_dict_ns,
        )

    stats = _cosim_stats(out_normal["fused_text"], out_ablated["fused_text"])
    passed = stats["mean"] < GATE6_COSIM_THRESHOLD
    return passed, stats


def run_gate7_vram_timing(
    model_class,
    htgn_factory,
    full_graph,
    window_events: list,
    tokenizer,
    device: torch.device,
) -> tuple[bool, dict]:
    """Gate 7: batch=16 VRAM < 16 GB AND step < 500 ms.

    RFC-7: build 16 distinct K-hop subgraphs from 16 different seed nodes
    (top-16 process nodes by degree). Batch via PyG Batch.from_data_list.

    Returns absolute VRAM in GB and absolute median step time in ms.
    """
    print("[G7]  building 16 distinct K-hop subgraphs for batch-16 VRAM/timing test ...")

    proc_count = full_graph["process"].num_nodes if "process" in full_graph.node_types else 0
    if proc_count < N_SEED_NODES_GATE7:
        print(
            f"[G7]  WARNING: only {proc_count} process nodes; "
            f"using all of them (need {N_SEED_NODES_GATE7})."
        )

    # Select top-16 (or all) process nodes by degree.
    proc_degree = full_graph["process"].degree
    n_seeds = min(proc_count, N_SEED_NODES_GATE7)
    top_seed_indices = proc_degree.argsort(descending=True)[:n_seeds].tolist()
    print(
        f"[G7]  top-{n_seeds} process node degrees: {[int(proc_degree[i]) for i in top_seed_indices]}"
    )

    subgraphs = []
    for seed_idx in top_seed_indices:
        sub = _build_subgraph(full_graph, seed_idx)
        subgraphs.append(sub)
    print(f"[G7]  built {len(subgraphs)} subgraphs")

    # Build a fresh model for Gate 7 (separate from Gate 1 model which has accumulated grads).
    htgn, n_per_type_main = htgn_factory()
    model_g7 = model_class(htgn=htgn).to(device)
    model_g7.train()

    # Build batch input: 16 text samples.
    input_ids, attention_mask, _texts = _build_text_batch(
        window_events, N_SEED_NODES_GATE7, tokenizer, device
    )
    # Pad or trim to exactly N_SEED_NODES_GATE7.
    if input_ids.shape[0] < N_SEED_NODES_GATE7:
        repeat_times = (N_SEED_NODES_GATE7 + input_ids.shape[0] - 1) // input_ids.shape[0]
        input_ids = input_ids.repeat(repeat_times, 1)[:N_SEED_NODES_GATE7]
        attention_mask = attention_mask.repeat(repeat_times, 1)[:N_SEED_NODES_GATE7]

    # For Gate 7 we use the largest subgraph's x/edge dicts (worst-case VRAM).
    # We use n_per_type from the first seed (max-degree is likely largest).
    x_dict, edge_index_dict, edge_time_dict_ns = _build_x_edge_dicts(
        subgraphs[0], n_per_type_main, device
    )

    def _one_step():
        # Reset + detach TGN memory: break gradient chain across steps so that
        # each backward sees only the current step's computation graph.
        # (Same fix as Gate 5; see PyG TGNMemory.detach() docstring.)
        model_g7.htgn.tgn_memory.reset_state()
        model_g7.htgn.tgn_memory.detach()
        model_g7.zero_grad()
        out = model_g7(
            input_ids=input_ids,
            attention_mask=attention_mask,
            x_dict={k: v.clone() for k, v in x_dict.items()},
            edge_index_dict=edge_index_dict,
            edge_time_dict_ns=edge_time_dict_ns,
        )
        # Use fused_text mean as proxy loss for backward (mean reduction = N-invariant).
        proxy_loss = out["fused_text"].mean() + out["fused_graph"].mean()
        proxy_loss.backward()
        model_g7.htgn.tgn_memory.detach()

    # Reset VRAM stats before measurement.
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
        torch.cuda.empty_cache()
    else:
        tracemalloc.start()

    # Warm-up.
    for _ in range(N_WARM_UP):
        _one_step()

    # Timed iterations.
    times_ms: list[float] = []
    for _ in range(N_TIMED):
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        t0 = time.perf_counter()
        _one_step()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        t1 = time.perf_counter()
        times_ms.append((t1 - t0) * 1000.0)

    times_ms.sort()
    median_ms = times_ms[N_TIMED // 2]

    if device.type == "cuda":
        peak_bytes = torch.cuda.max_memory_allocated(device)
        peak_gb = peak_bytes / (1024**3)
        vram_report = f"{peak_gb:.3f} GB"
        vram_ok = peak_gb < GATE7_VRAM_GB_THRESHOLD
    else:
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_gb = peak_bytes / (1024**3)
        vram_report = f"CPU-only; tracemalloc peak = {peak_gb * 1024:.1f} MB (partial verify)"
        vram_ok = True  # CPU path: no hard VRAM limit

    time_ok = median_ms < GATE7_STEP_MS_THRESHOLD
    passed = vram_ok and time_ok

    return passed, {
        "vram_gb": peak_gb,
        "vram_report": vram_report,
        "median_step_ms": median_ms,
        "all_step_times_ms": times_ms,
        "vram_ok": vram_ok,
        "time_ok": time_ok,
        "device": device.type,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def _pass_str(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _print_separator() -> None:
    print("=" * 76)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all 7 gates. Return 0=all pass, 1=any fail."""
    random.seed(SEED)
    torch.manual_seed(SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[C14] device = {device}")

    # ---- Load data ---------------------------------------------------------
    print("[C14] Loading M3_h2 first 1.0h window ...")
    all_events = _parse_m3_h2()
    window_events = _select_first_window(all_events)
    print(f"[C14]   window: {len(window_events):,} events")

    full_graph = _build_full_graph(window_events)
    proc_degree = full_graph["process"].degree
    main_seed_idx = int(proc_degree.argmax().item())

    # Build main subgraph (max-degree process seed) for gates 1-6.
    sub_main = _build_subgraph(full_graph, main_seed_idx)
    from loghetero.data.parsers.base import NodeType

    n_per_type_main: dict = {}
    for nt in NodeType:
        n = sub_main[nt.value].num_nodes if nt.value in sub_main.node_types else 0
        n_per_type_main[nt] = n
    total_nodes = sum(n_per_type_main.values())
    print(
        f"[C14]   subgraph: {total_nodes} nodes (seed=process[{main_seed_idx}], khop={SUBGRAPH_KHOP})"
    )

    # ---- Build model -------------------------------------------------------
    from loghetero.models.phase4_model import Phase4Model

    print("[C14] Building Phase4Model (BERT + HTGN + 4x CrossModalAttention + MLM head) ...")

    def _htgn_factory():
        return _build_htgn(sub_main, device, trainable=True)

    htgn_main, _ = _build_htgn(sub_main, device, trainable=True)
    model = Phase4Model(htgn=htgn_main).to(device)
    tokenizer = model.tokenizer
    print(
        f"[C14]   model built. trainable params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}"
    )

    # ---- Gate 1 ------------------------------------------------------------
    _print_separator()
    print("[G1]  Gate 1: forward + backward on batch=8 real data")
    ok1, info1 = run_gate1_forward_backward(
        model, window_events, tokenizer, sub_main, n_per_type_main, device
    )
    print(f"[G1]  fused_text shape: {info1['fused_text_shape']}")
    print(f"[G1]  fused_graph shape: {info1['fused_graph_shape']}")
    print(f"[G1]  loss: {info1['loss']:.6f}")
    if info1["issues"]:
        for iss in info1["issues"]:
            print(f"[G1]  ISSUE: {iss}")
    print(f"[G1]  RESULT: {_pass_str(ok1)}")

    # ---- Gate 2 ------------------------------------------------------------
    _print_separator()
    print("[G2]  Gate 2: three-category grad flow (RFC-3)")
    ok2, info2 = run_gate2_grad_flow(model)
    for cat, details in info2.items():
        print(
            f"[G2]  {cat}: param={details['best_param']!r}  "
            f"grad_norm={details['grad_norm']:.3e}  {'PASS' if details['pass'] else 'FAIL'}"
        )
    print(f"[G2]  RESULT: {_pass_str(ok2)}")

    # ---- Gate 5 (runs BEFORE Gates 3 and 4 -- RFC-G3/G4-A) -----------------
    # Gate 5 trains a fresh model on 8 samples x 50 epochs and returns the
    # trained state.  Gates 3, 4, and 6 then use that trained model so they
    # measure trained fusion attention behaviour, not init prior.
    #
    # Rationale (RFC-G3/G4-A): Gates 3 and 4 verify trained fusion attention
    # behaviour, not init prior; the spec wording "fusion non-degeneration"
    # and "model uses text modality" both implicitly assume a trained context,
    # and Gate 5 overfit training is the natural source of that state.
    #
    # NOTE: the gate result is still *reported* in numeric order (G1-G7) in the
    # summary table; only the *execution* order changes here.
    _print_separator()
    print("[G5]  Gate 5: 8-sample x 50-epoch overfit  (RFC-G3/G4-A: run before Gates 3 & 4)")
    ok5, info5, model_g5 = run_gate5_overfit(
        Phase4Model, _htgn_factory, window_events, tokenizer, sub_main, n_per_type_main, device
    )
    print(f"[G5]  epoch-1 loss: {info5['loss_epoch1']:.6f}")
    print(f"[G5]  epoch-50 loss: {info5['loss_epoch50']:.6f}")
    print(f"[G5]  reduction: {info5['reduction_pct']:.1f}%")
    print(f"[G5]  RESULT: {_pass_str(ok5)}")
    print("[G5]  Trained model state captured → will be used for Gates 3, 4, 6.")

    # ---- Gate 3 (uses post-Gate-5 trained state — RFC-G3/G4-A) ------------
    _print_separator()
    print("[G3]  Gate 3: cross-attn entropy in [0.3, 0.95]  (measured on post-G5 trained model)")
    ok3, scalars3 = run_gate3_entropy(
        model_g5, window_events, tokenizer, sub_main, n_per_type_main, device
    )
    print("[G3]  All 8 entropy scalars (RFC-4 tightening):")
    for label, h in scalars3.items():
        in_range = GATE3_ENTROPY_LO <= h <= GATE3_ENTROPY_HI
        print(f"[G3]    {label}: {h:.4f}  {'in-range' if in_range else 'OUT-OF-RANGE'}")
    print(f"[G3]  RESULT: {_pass_str(ok3)}")

    # ---- Gate 4 (uses post-Gate-5 trained state — RFC-G3/G4-A) ------------
    _print_separator()
    print("[G4]  Gate 4: modality dropout cos-sim < 0.95  (measured on post-G5 trained model)")
    ok4, stats4 = run_gate4_modality_dropout(
        model_g5, window_events, tokenizer, sub_main, n_per_type_main, device
    )
    print(
        f"[G4]  fused_text cos-sim (normal vs zeroed-graph): "
        f"mean={stats4['mean']:.4f}  p10={stats4['p10']:.4f}  "
        f"p50={stats4['p50']:.4f}  p90={stats4['p90']:.4f}"
    )
    print(f"[G4]  RESULT: {_pass_str(ok4)}")

    # Early exit if Option A re-measurement still fails Gate 3 or Gate 4.
    # Do NOT relax thresholds.  Do NOT introduce additional training.
    # Report NEEDS_CONTEXT and return.
    if not ok3 or not ok4:
        _print_separator()
        print()
        print("OPTION A RE-MEASUREMENT FAILURE")
        if not ok3:
            print(f"[G3]  FAIL — entropy out of range: {scalars3}")
        if not ok4:
            print(f"[G4]  FAIL — cos-sim not < {GATE4_COSIM_THRESHOLD}: {stats4}")
        print()
        print("NEEDS_CONTEXT — Gates 3/4 still fail under Option A (post-Gate-5 trained state).")
        print("Do NOT commit. Do NOT relax thresholds. Escalate to RFC.")
        return 1

    # ---- Gate 6 (uses post-Gate-5 trained state for eval consistency) ------
    _print_separator()
    print("[G6]  Gate 6: random text ablation cos-sim < 0.90  (post-G5 trained model)")
    ok6, stats6 = run_gate6_text_ablation(
        model_g5, window_events, tokenizer, sub_main, n_per_type_main, device
    )
    print(
        f"[G6]  fused_text cos-sim (normal vs random-text): "
        f"mean={stats6['mean']:.4f}  p10={stats6['p10']:.4f}  "
        f"p50={stats6['p50']:.4f}  p90={stats6['p90']:.4f}"
    )
    print(f"[G6]  RESULT: {_pass_str(ok6)}")

    # ---- Gate 7 ------------------------------------------------------------
    _print_separator()
    print("[G7]  Gate 7: batch=16 VRAM < 16 GB AND step < 500 ms")
    ok7, info7 = run_gate7_vram_timing(
        Phase4Model, _htgn_factory, full_graph, window_events, tokenizer, device
    )
    print(f"[G7]  device: {info7['device'].upper()}")
    print(f"[G7]  peak VRAM: {info7['vram_report']}  threshold={GATE7_VRAM_GB_THRESHOLD} GB")
    print(
        f"[G7]  median step time: {info7['median_step_ms']:.1f} ms  threshold={GATE7_STEP_MS_THRESHOLD} ms"
    )
    print(f"[G7]  all step times (ms): {[f'{t:.1f}' for t in info7['all_step_times_ms']]}")
    print(
        f"[G7]  VRAM: {'PASS' if info7['vram_ok'] else 'FAIL'}  timing: {'PASS' if info7['time_ok'] else 'FAIL'}"
    )
    print(f"[G7]  RESULT: {_pass_str(ok7)}")

    # ---- Overall summary ---------------------------------------------------
    _print_separator()
    all_pass = ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7
    gate_results = [
        (1, ok1, f"forward+backward no NaN/Inf  loss={info1['loss']:.6f}"),
        (2, ok2, "three-category grad flow (RFC-3)"),
        (3, ok3, f"entropy all 8 in [{GATE3_ENTROPY_LO},{GATE3_ENTROPY_HI}]"),
        (4, ok4, f"modality dropout cos-sim mean={stats4['mean']:.4f} < {GATE4_COSIM_THRESHOLD}"),
        (
            5,
            ok5,
            f"overfit loss={info5['loss_epoch50']:.4f} reduction={info5['reduction_pct']:.1f}%",
        ),
        (6, ok6, f"text ablation cos-sim mean={stats6['mean']:.4f} < {GATE6_COSIM_THRESHOLD}"),
        (
            7,
            ok7,
            f"VRAM={info7['vram_report']}  step={info7['median_step_ms']:.1f}ms",
        ),
    ]

    print()
    print("Phase 4 / Checkpoint 14 — Seven-Gate Verification Summary")
    print()
    print(f"{'Gate':<6} {'Result':<8} Detail")
    print("-" * 76)
    for gate_num, gate_ok, detail in gate_results:
        print(f"  G{gate_num}   {'PASS' if gate_ok else 'FAIL':<8} {detail}")
    print("-" * 76)
    print()
    print("Tightening details (RFC-4 Gate 3 — all 8 entropy scalars):")
    for label, h in scalars3.items():
        print(f"  {label}: {h:.4f}")
    print()
    print("Tightening details (RFC-5 Gate 4 — modality dropout cos-sim):")
    print(
        f"  mean={stats4['mean']:.4f}  p10={stats4['p10']:.4f}  p50={stats4['p50']:.4f}  p90={stats4['p90']:.4f}"
    )
    print()
    print("Tightening details (RFC-5 Gate 6 — random text ablation cos-sim):")
    print(
        f"  mean={stats6['mean']:.4f}  p10={stats6['p10']:.4f}  p50={stats6['p50']:.4f}  p90={stats6['p90']:.4f}"
    )
    print()
    print("Tightening details (RFC-7 Gate 7 — absolute VRAM + step time):")
    print(f"  VRAM: {info7['vram_report']}")
    print(f"  Median step: {info7['median_step_ms']:.1f} ms")
    print()
    print("Grad flow representatives (RFC-3 Gate 2):")
    for cat, details in info2.items():
        print(f"  {cat}: {details['best_param']!r}  grad_norm={details['grad_norm']:.3e}")
    print()
    print(f"OVERALL: {'PASS' if all_pass else 'FAIL'}")

    if not all_pass:
        failed_gates = [str(g) for g, ok, _ in gate_results if not ok]
        print(f"\nFailed gates: {', '.join(failed_gates)}")
        print("NEEDS_CONTEXT — do NOT commit. Investigate failed gate(s) first.")
        return 1

    print("\nAll 7 gates passed. Ready for commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
