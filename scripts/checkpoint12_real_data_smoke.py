"""Phase 4 / Checkpoint 12 real-data smoke test — CrossModalAttention on M3_h2 first window.

PURPOSE
=======
Single-shot verification that the Checkpoint 12 ``CrossModalAttention`` module
works correctly on REAL ATLAS data (M3_h2 first 1.0h window K-hop subgraph),
as opposed to the synthetic unit-test inputs used in ``tests/test_cross_attention.py``.
This is the audit anchor bridging the synthetic-regime to the real-regime gap
before Checkpoint 13 (MLM integration) builds on top.

DATA PATH (consistent with Checkpoint 10/11 lineage)
=====================================================
* Parses M3_h2 logs (dns, firefox.txt, security_events.txt) via the same 3-parser
  pipeline used in ``checkpoint10_task_b.py``.
* Slices the first 1.0h window (t_min to t_min+3.6e12 ns).
* Builds the full HeteroData graph, selects the max-degree process node as K-hop
  seed, and samples the K-hop subgraph (khop=3, max_nodes=2000, edge_ranking="weight")
  — identical parameters to checkpoint10_task_b.py.

BERT WIRING (text path)
=======================
* Loads frozen ``bert-base-uncased`` (Phase 2 / decision 4.1).
* Takes the **first event by timestamp** from the M3_h2 first window and renders
  it via ``event_to_text`` (Phase 1 cleaner + placeholder normalisation).
  We use a single representative event (rather than per-node entity-context mode)
  because the smoke test's goal is to verify the SHAPE PIPELINE and
  NUMERICAL HEALTH of CrossModalAttention, not to evaluate retrieval quality.
  Real per-node context integration is Checkpoint 14's job.
* Calls BERT forward with ``output_hidden_states=True`` and uses the
  **layer-12 (last) hidden states** as text_hidden (shape ``(1, T, 768)``).
  Layer 12 is the final transformer output, matching the most information-rich
  hidden representation. Choice is explicit and documented here.

GRAPH WIRING
============
* Runs HTGN forward in eval mode (frozen for this test; only CrossModalAttention
  parameters receive gradients). HTGN TGN memory is reset before forward.
* Stacks all node embeddings from all node types in deterministic order
  (sorted by NodeType.value string, then by node index within type).
  Result: ``(1, N_total, 256)`` where N_total = sum of nodes across all types.
  ntype boundaries are printed but not used in the attention mask.

ATTENTION MASK SIMPLIFICATION
==============================
``attention_mask=None`` is passed to ``CrossModalAttention.forward``.
This exercises the **unmasked attention path** (every text token can attend
to every graph node and vice versa). The realistic per-event attention mask
(where token→node gating is event-id based) is Checkpoint 14's job
(``build_event_attention_mask`` utility is already implemented; wiring it
to the real data loader is Checkpoint 14 work). The simplification is
acceptable for this smoke test because the four numerical-health checks
(NaN/Inf, grad norms, VRAM, timing) are independent of mask correctness.

FOUR VERIFICATIONS
==================
1. No NaN/Inf in ``fused_text``, ``fused_graph``, and attention weight tensors.
2. Gradient norms for 6 CrossModalAttention parameter tensors in [1e-7, 1e3].
   (Tighter than unit-test [1e-8, 1e6]; real-data regime should give healthy norms.)
   BERT is frozen (no grads). HTGN is also frozen for this test (clean signal
   isolation: only Checkpoint 12 module under test receives gradients).
3. Peak GPU VRAM < 4 GB. CPU fallback: tracemalloc peak reported (partial verify).
4. Single forward+backward < 100 ms (median of 10 timed iterations after 5 warm-ups).

LOSS REDUCTION CHOICE (mean reduction rationale, 2026-05-06 RFC Option B)
=========================================================================
Smoke test uses mean reduction (``loss = fused_text.mean() + fused_graph.mean()``)
so gradient norm thresholds remain N-invariant; this differs from Checkpoint 12
unit tests (``tests/test_cross_attention.py``) which use sum reduction. The two
test purposes are complementary not contradictory: unit tests verify module
shape and gradient flow on synthetic tensors (small N where sum is fine and
the [1e-8, 1e6] bound covers the natural sqrt(B*T*D)-scaled gradient range);
smoke test verifies numerical health on real-data dimensions (N=2000 graph
nodes where sum reduction would inflate gradients ~125x relative to N=16
unit-test scale and break the [1e-7, 1e3] tight numerical-health bound).

The original [1e-7, 1e3] bound in the smoke test launch spec (2026-05-06)
was set without accounting for sum reduction's N-scaling. RFC Option B
diagnosis: changing to mean reduction is "fix the root cause" not "paper
over the symptom"; mean is the canonical PyTorch training-loss convention,
and the cap-around alternatives (relax bound to 1e5 / cap N at 128) either
hide the scale-coupling issue or defeat the real-data-regime intent of the
smoke test. See docs/known_issues.md::经验启发式校准记录::"Smoke test
阈值设计必须显式考虑 loss reduction 与 N 的交互" for full lesson narrative.

EXEMPT from 4-step multi-agent review pattern per docs/known_issues.md
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

# --- Constants (must match checkpoint10_task_b.py) --------------------------

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
SEED = 42  # deterministic seed for all RNG

# BERT constants
BERT_MODEL = "bert-base-uncased"
BERT_MAX_LENGTH = 192

# CrossModalAttention constants (locked per Phase 4 launch spec)
TEXT_DIM = 768
GRAPH_DIM = 256
ATTN_DIM = 256
ATTN_HEADS = 8
ATTN_DROPOUT = 0.1

N_WARM_UP = 5
N_TIMED = 10


# ---------------------------------------------------------------------------
# Step 1: Data loading (reuses checkpoint10_task_b.py logic)
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
            print(f"[smoke12]   {path.name} missing, skipping", file=sys.stderr)
            continue
        events.extend(parser.parse_file(path, scenario_id=SCENARIO, host_id=HOST))
    events.sort(key=lambda e: e.timestamp_ns)
    return events


def _select_first_window(events: list) -> list:
    """Slice events to those falling in [t_min, t_min + 1.0h)."""
    if not events:
        raise RuntimeError("Empty event stream from M3_h2 -- parser misfire?")
    t_min = events[0].timestamp_ns
    t_max_exclusive = t_min + WINDOW_NS
    window = [e for e in events if e.timestamp_ns < t_max_exclusive]
    print(
        f"[smoke12]   first 1.0h window: {len(window):,} events "
        f"(of {len(events):,} total; t_min={t_min} ns)"
    )
    return window


def _build_subgraph(events: list) -> tuple[object, dict]:
    """Build full HeteroData then K-hop sample (identical to checkpoint10_task_b.py)."""
    from loghetero.data.parsers.base import NodeType
    from loghetero.data.provenance_graph import build_graph
    from loghetero.data.subgraph_sampler import SeedNode, sample_khop_subgraph

    full_graph, _ = build_graph(events)
    node_type_summary = ", ".join(
        f"{nt.value}={full_graph[nt.value].num_nodes if nt.value in full_graph.node_types else 0}"
        for nt in NodeType
    )
    print(f"[smoke12]   full window graph: {node_type_summary}")

    proc_count = full_graph["process"].num_nodes if "process" in full_graph.node_types else 0
    if proc_count == 0:
        raise RuntimeError("M3_h2 first window has zero process nodes -- unexpected")
    proc_degree = full_graph["process"].degree
    seed_idx = int(proc_degree.argmax().item())
    seed_node = SeedNode(NodeType.process, seed_idx)
    print(
        f"[smoke12]   K-hop seed = process[{seed_idx}] (max-degree "
        f"deg={int(proc_degree[seed_idx].item())} of {proc_count} candidates)"
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
    total_edges = sum(sub[rel].edge_index.shape[1] for rel in sub.edge_types)
    print(
        f"[smoke12]   subgraph nodes={total_nodes} (target<={SUBGRAPH_MAX_NODES}), "
        f"edges={total_edges}"
    )
    print(
        "[smoke12]   per-type: "
        + ", ".join(f"{k.value}={v}" for k, v in n_per_type.items() if v > 0)
    )
    return sub, n_per_type


# ---------------------------------------------------------------------------
# Step 2: BERT forward → last hidden states (layer 12)
# ---------------------------------------------------------------------------


def _bert_forward_last_hidden(
    window_events: list,
    device: torch.device,
) -> tuple[torch.Tensor, str]:
    """Encode the first window event via BERT; return last-layer hidden states.

    Returns:
        text_hidden: (1, T, 768) — layer-12 (last) hidden states for the event text.
        event_text:  the rendered text string (for report).
    """
    from loghetero.data.datamodule import event_to_text
    from loghetero.models.encoders.bert_text import TrainMode, build_bert_text_encoder

    first_event = window_events[0]
    event_text = event_to_text(first_event)
    print(f"[smoke12]   BERT input text (first event): {event_text[:120]!r}")

    print(f"[smoke12]   building frozen {BERT_MODEL} ...")
    bert_model, tokenizer = build_bert_text_encoder(BERT_MODEL, mode=TrainMode.frozen)
    bert_model = bert_model.to(device)
    bert_model.eval()

    enc = tokenizer(
        [event_text],
        padding=True,
        truncation=True,
        max_length=BERT_MAX_LENGTH,
        return_tensors="pt",
    )
    enc = {k: v.to(device) for k, v in enc.items()}

    # Forward with output_hidden_states=True (already configured by build_bert_text_encoder).
    with torch.no_grad():
        bert_out = bert_model(**enc)

    # hidden_states is a tuple of (n_layers + 1) tensors, each (B, T, 768).
    # Index 0 = embedding layer, indices 1-12 = transformer layers.
    # We use index 12 (layer 12, the last transformer layer) = same as last_hidden_state.
    hidden_states = bert_out.hidden_states
    assert hidden_states is not None, "BERT did not return hidden_states"
    assert len(hidden_states) == 13, f"Expected 13 hidden state tensors, got {len(hidden_states)}"

    layer12_hidden = hidden_states[12]  # (1, T, 768), same as bert_out.last_hidden_state
    seq_len = layer12_hidden.shape[1]
    print(
        f"[smoke12]   BERT layer-12 hidden states shape: "
        f"{tuple(layer12_hidden.shape)} (T={seq_len})"
    )

    # Detach since BERT is frozen; we don't want BERT computations in the graph.
    return layer12_hidden.detach(), event_text


# ---------------------------------------------------------------------------
# Step 3: HTGN forward → flattened graph node embeddings
# ---------------------------------------------------------------------------


def _htgn_forward_and_flatten(
    sub,
    n_per_type: dict,
    device: torch.device,
) -> tuple[torch.Tensor, list[str]]:
    """Run HTGN forward and stack all node embeddings into (1, N_total, 256).

    HTGN is run in eval mode with frozen parameters (no gradients).
    This cleanly isolates Checkpoint 12 CrossModalAttention as the ONLY
    module under gradient test.

    Returns:
        graph_hidden: (1, N_total, 256)
        ntype_order: list of ntype strings in the order they were stacked
                     (sorted alphabetically for determinism).
    """
    from loghetero.data.parsers.base import NodeType
    from loghetero.models.graph.htgn import HTGN

    # Build x_dict with random Gaussian initial features (same as checkpoint10 Phase 3 baseline).
    torch.manual_seed(SEED)
    x_dict: dict[str, torch.Tensor] = {}
    for nt in NodeType:
        n = n_per_type[nt]
        if n > 0:
            x_dict[nt.value] = torch.randn(n, HIDDEN_DIM, device=device)

    # Build edge_index_dict and edge_time_dict_ns from subgraph.
    edge_index_dict: dict[tuple[str, str, str], torch.Tensor] = {}
    edge_time_dict_ns: dict[tuple[str, str, str], torch.Tensor] = {}
    for rel in sub.edge_types:
        ei = sub[rel].edge_index.to(device)
        et = sub[rel].edge_attr_time.to(device)
        edge_index_dict[rel] = ei
        edge_time_dict_ns[rel] = et

    metadata = sub.metadata()

    # Apply the same max-count workaround for TGN cross-type src memory
    # (documented in checkpoint10_task_b.py::_build_htgn).
    max_count = max(n_per_type.values())
    htgn_node_counts: dict[NodeType, int] = {
        nt: (max_count if nt in (NodeType.process, NodeType.socket) else n_per_type[nt])
        for nt in NodeType
    }

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

    # Freeze all HTGN parameters: only CrossModalAttention will receive grads.
    for p in htgn.parameters():
        p.requires_grad = False

    htgn.eval()
    htgn.tgn_memory.reset_state()

    with torch.no_grad():
        out_dict = htgn(x_dict, edge_index_dict, edge_time_dict_ns)

    # Stack in deterministic alphabetical order by ntype string.
    ntype_order = sorted(out_dict.keys())
    parts = [out_dict[nt] for nt in ntype_order]
    stacked = torch.cat(parts, dim=0)  # (n_total, 256)
    n_total = stacked.shape[0]

    print(
        "[smoke12]   HTGN out dict node types: "
        + ", ".join(f"{nt}={out_dict[nt].shape[0]}" for nt in ntype_order)
    )
    print(f"[smoke12]   Stacked graph_hidden shape: (1, {n_total}, {HIDDEN_DIM})")

    graph_hidden = stacked.unsqueeze(0).detach()  # (1, N_total, 256); detach HTGN graph
    return graph_hidden, ntype_order


# ---------------------------------------------------------------------------
# Step 4: CrossModalAttention forward + backward
# ---------------------------------------------------------------------------


def _run_cross_attention_forward_backward(
    text_hidden: torch.Tensor,
    graph_hidden: torch.Tensor,
    device: torch.device,
) -> tuple[object, torch.Tensor, torch.Tensor, dict[str, torch.Tensor]]:
    """Instantiate CrossModalAttention, run forward, backward, return results.

    Returns:
        model: the CrossModalAttention instance (for grad inspection)
        fused_text: (1, T, 768)
        fused_graph: (1, N, 256)
        attn_weights: dict with 'text_to_graph' and 'graph_to_text'
    """
    from loghetero.models.fusion.cross_attention import CrossModalAttention

    torch.manual_seed(SEED)
    model = CrossModalAttention(
        text_dim=TEXT_DIM,
        graph_dim=GRAPH_DIM,
        attn_dim=ATTN_DIM,
        num_heads=ATTN_HEADS,
        dropout=ATTN_DROPOUT,
    ).to(device)
    model.train()  # dropout active; gradients needed

    # attention_mask=None: unmasked path (documented simplification in module docstring).
    fused_text, fused_graph, attn_weights = model(
        text_hidden,
        graph_hidden,
        attention_mask=None,
        text_padding_mask=None,
        graph_padding_mask=None,
    )

    # mean reduction (RFC Option B 2026-05-06): keeps grad norms N-invariant so the
    # smoke test's tight [1e-7, 1e3] bound remains meaningful at real N=2000 scale.
    # Differs from unit tests (sum) on purpose; see module-level docstring rationale.
    loss = fused_text.mean() + fused_graph.mean()
    loss.backward()

    return model, fused_text, fused_graph, attn_weights


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------


def _check_no_nan_inf(
    fused_text: torch.Tensor,
    fused_graph: torch.Tensor,
    attn_weights: dict[str, torch.Tensor],
) -> tuple[bool, list[str]]:
    """Check 1: no NaN or Inf in any output tensor."""
    issues = []
    for name, tensor in [
        ("fused_text", fused_text),
        ("fused_graph", fused_graph),
        ("attn_weights[text_to_graph]", attn_weights["text_to_graph"]),
        ("attn_weights[graph_to_text]", attn_weights["graph_to_text"]),
    ]:
        if torch.isnan(tensor).any():
            issues.append(f"{name}: NaN detected")
        if torch.isinf(tensor).any():
            issues.append(f"{name}: Inf detected")
    return len(issues) == 0, issues


def _check_grad_norms(model: object) -> tuple[bool, dict[str, float]]:
    """Check 2: grad norms for 6 CrossModalAttention parameter tensors in [1e-7, 1e3]."""
    from loghetero.models.fusion.cross_attention import CrossModalAttention

    assert isinstance(model, CrossModalAttention)

    param_checks = [
        ("text_proj.weight", model.text_proj.weight),
        ("graph_proj.weight", model.graph_proj.weight),
        ("tg_attn.in_proj_weight", model.tg_attn.in_proj_weight),
        ("gt_attn.in_proj_weight", model.gt_attn.in_proj_weight),
        ("tg_out_proj.weight", model.tg_out_proj.weight),
        ("gt_out_proj.weight", model.gt_out_proj.weight),
    ]

    norms: dict[str, float] = {}
    issues = []
    lo, hi = 1e-7, 1e3

    for name, param in param_checks:
        if param.grad is None:
            issues.append(f"{name}: no gradient (grad is None)")
            norms[name] = float("nan")
            continue
        gn = float(param.grad.norm().item())
        norms[name] = gn
        if not (lo <= gn <= hi):
            issues.append(f"{name}: grad norm {gn:.3e} outside [{lo:.0e}, {hi:.0e}]")

    return len(issues) == 0, norms


def _check_vram(device: torch.device) -> tuple[bool, str]:
    """Check 3: peak VRAM < 4 GB (or tracemalloc on CPU)."""
    gb = 1024**3
    if device.type == "cuda":
        peak_bytes = torch.cuda.max_memory_allocated(device)
        peak_gb = peak_bytes / gb
        passed = peak_gb < 4.0
        report = f"{peak_gb:.3f} GB"
        return passed, report
    else:
        # CPU-only: tracemalloc was started in main(); stop and read peak.
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = peak_bytes / (1024**2)
        # No hard limit on CPU; partial verification.
        report = f"N/A (CPU-only); tracemalloc peak = {peak_mb:.1f} MB (partial verify)"
        return True, report  # Not a fail per spec


def _check_timing(
    text_hidden: torch.Tensor,
    graph_hidden: torch.Tensor,
    device: torch.device,
) -> tuple[bool, float]:
    """Check 4: forward+backward < 100 ms (median of 10 timed iters after 5 warm-ups).

    Uses torch.cuda.synchronize() on GPU; time.perf_counter() on CPU.
    """
    from loghetero.models.fusion.cross_attention import CrossModalAttention

    torch.manual_seed(SEED)
    model = CrossModalAttention(
        text_dim=TEXT_DIM,
        graph_dim=GRAPH_DIM,
        attn_dim=ATTN_DIM,
        num_heads=ATTN_HEADS,
        dropout=ATTN_DROPOUT,
    ).to(device)
    model.train()

    def _one_iter() -> None:
        if model.text_proj.weight.grad is not None:
            model.zero_grad()
        ft, fg, _ = model(text_hidden, graph_hidden, attention_mask=None)
        # mean reduction (matches main loss formulation; see module docstring).
        loss = ft.mean() + fg.mean()
        loss.backward()

    # Warm-up
    for _ in range(N_WARM_UP):
        _one_iter()

    # Timed
    times_ms: list[float] = []
    for _ in range(N_TIMED):
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        t0 = time.perf_counter()
        _one_iter()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        t1 = time.perf_counter()
        times_ms.append((t1 - t0) * 1000.0)

    times_ms.sort()
    median_ms = times_ms[N_TIMED // 2]
    passed = median_ms < 100.0
    return passed, median_ms


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the Checkpoint 12 real-data smoke test. Return 0=PASS, 1=FAIL."""
    # Seed for reproducibility.
    random.seed(SEED)
    torch.manual_seed(SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[smoke12] device = {device}")

    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    else:
        tracemalloc.start()

    # --- Step 1: load M3_h2 first 1.0h window --------------------------------
    print("[smoke12] Step 1: loading M3_h2 data ...")
    all_events = _parse_m3_h2()
    window_events = _select_first_window(all_events)
    sub, n_per_type = _build_subgraph(window_events)

    total_nodes = sum(n_per_type.values())

    # --- Step 2: BERT forward -------------------------------------------------
    print("[smoke12] Step 2: BERT forward (layer-12 hidden states) ...")
    text_hidden, event_text = _bert_forward_last_hidden(window_events, device)

    # --- Step 3: HTGN forward -------------------------------------------------
    print("[smoke12] Step 3: HTGN forward (frozen, eval mode) ...")
    graph_hidden, ntype_order = _htgn_forward_and_flatten(sub, n_per_type, device)

    seq_len = text_hidden.shape[1]
    n_nodes = graph_hidden.shape[1]
    print(
        f"[smoke12]   text_hidden: (1, {seq_len}, {TEXT_DIM}), "
        f"graph_hidden: (1, {n_nodes}, {GRAPH_DIM})"
    )

    # --- Step 4: CrossModalAttention forward + backward -----------------------
    print("[smoke12] Step 4: CrossModalAttention forward + backward ...")
    model, fused_text, fused_graph, attn_weights = _run_cross_attention_forward_backward(
        text_hidden, graph_hidden, device
    )

    # --- Verification ---------------------------------------------------------
    print("[smoke12] Running 4 verifications ...")

    ok1, issues1 = _check_no_nan_inf(fused_text, fused_graph, attn_weights)
    ok2, grad_norms = _check_grad_norms(model)
    ok3, vram_report = _check_vram(device)
    ok4, median_ms = _check_timing(text_hidden, graph_hidden, device)

    # --- Report ---------------------------------------------------------------
    pass_str = "PASS" if (ok1 and ok2 and ok3 and ok4) else "FAIL"

    print("\n" + "=" * 70)
    print("**Checkpoint 12 real-data smoke test report**\n")
    print(
        f"- Setup: M3_h2 first 1.0h window K-hop subgraph "
        f"(khop={SUBGRAPH_KHOP}, max_nodes={SUBGRAPH_MAX_NODES}, seed=max-degree process node), "
        f"total_nodes={total_nodes}, batch=1, frozen BERT + frozen HTGN, "
        f"attention_mask=None (unmasked path — real event-id mask is Checkpoint 14)"
    )
    print(
        f"- BERT text input: first window event (layer-12 / last hidden states, "
        f"T={seq_len} tokens)"
    )
    print(
        f"- Graph: {n_nodes} nodes stacked from {len(ntype_order)} types "
        f"({', '.join(ntype_order)})"
    )
    print(f"- Device: {device.type.upper()}")
    print()

    nan_inf_str = "✅" if ok1 else "❌"
    if ok1:
        print(
            f"- {nan_inf_str} NaN/Inf check: all clean (fused_text, fused_graph, both attn_weights)"
        )
    else:
        print(f"- {nan_inf_str} NaN/Inf check: FAILED — {'; '.join(issues1)}")
    print()

    grad_str = "✅" if ok2 else "❌"
    grad_lines = [f"    {n}: {v:.3e}" for n, v in grad_norms.items()]
    print(f"- {grad_str} Grad norms in [1e-7, 1e3]:")
    for line in grad_lines:
        print(line)
    print()

    vram_str = "✅" if ok3 else "❌"
    print(f"- {vram_str} Peak VRAM < 4 GB: {vram_report}")
    print()

    timing_str = "✅" if ok4 else "❌"
    print(
        f"- {timing_str} forward+backward < 100 ms: {median_ms:.1f} ms (median of {N_TIMED} iters)"
    )
    print()

    print(f"Overall: {pass_str}")
    print("=" * 70)

    if not (ok1 and ok2 and ok3 and ok4):
        print("\n[smoke12] FAIL — details above. Do NOT commit. Issue RFC.")
        return 1

    print("\n[smoke12] All 4 checks PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
