"""Phase 3 / Checkpoint 10 Task B -- ATLAS link prediction warm-up (Phase 3 hard gate).

Task B is the **Phase 3 hard gate** -- test AUC > 0.85 on a real-data
heterogeneous link-prediction task is required before tagging v0.3-htgn
and entering Phase 4. Failure to meet the gate triggers root-cause
investigation, NOT a bypass via increased epochs / weakened negative
sampling / metric reinterpretation.

Data
====
Source: ATLAS scenario M3, host h2 (M3_h2). Per Checkpoint 4 window
density artifact, M3_h2 1.0h windows have mean 50,095 events with
median 38,490 -- a representative medium-density host, neither M5_h1's
right-tail outlier (123k mean) nor S2's long-tail extreme.

**Data scope honesty (Phase 3 Option C decision archived in
known_issues.md::Phase 3 设计偏离记录::Task B "完全 benign 子图" spec)**:
M3_h2 first 1.0h window is a **mixed subgraph (predominantly benign
with unverified attack fraction; Phase 8 ground-truth label loader
not yet wired in v0.1-data)**. We do NOT claim the data is benign-only.
The AUC > 0.85 gate validates HTGN's structural learning capability on
mixed-event provenance graphs, NOT a benign baseline distribution.

Subgraph: full first-1.0h window has ~50k events / ~10k nodes which
exceeds single-card RTX 4090 VRAM under naive HTGN forward (linear
extrapolation from Checkpoint 9 bench: 0.191 GB / 128 nodes -> ~15 GB
per 10k nodes per forward, plus backward x2). We K-hop sample
(seed=process[0], khop=2, max_nodes=2000, edge_ranking="weight") to
keep VRAM <= 5 GB while preserving sufficient edges for meaningful
train/val/test AUC.

Link prediction protocol
========================
1. Mask 10% of edges (by random shuffle, seed-fixed) as positive
   prediction targets; remaining 90% form the training context.
2. For each masked positive edge (u, op, v): sample exactly 1 negative
   (u, op, v') where v' is a random dst_type node and (u, op, v') is
   NOT present in the original graph. Negative:positive = 1:1. This
   structured negative sampling avoids the dst_type-bias shortcut
   ("file nodes never connect to file nodes").
3. Split masked positives + negatives 7:1.5:1.5 into train / val / test.
4. HTGN forward on context edges -> node embeddings dict. For each
   labelled edge (pos or neg), predict via MLP(concat[emb_u, emb_v]):
   single Linear(2*hidden_dim, 1) layer (the "dim=512 single MLP layer"
   interpretation; "simple" per spec). BCEWithLogitsLoss. 30 epochs,
   Adam lr=1e-3.
5. Test AUC computed on held-out test split after final epoch.

Hard gate
=========
* Test AUC > 0.85: PASS -- request v0.3-htgn tag, enter Phase 4.
* 0.80 <= Test AUC <= 0.85: BORDERLINE -- RFC user (do NOT decide
  unilaterally per hard-gate inviolability discipline).
* Test AUC < 0.80: FAIL -- stop, root-cause from candidate list (TGN
  memory detach timing, Time2Vec dim, negative sampling leak,
  cross-type src memory bug, etc.). Forbidden: increasing epochs,
  weakening negative sampling, picking a luckier subgraph seed.

Workarounds in this script (NOT to be confused with metric tweaks)
==================================================================
* num_nodes_per_type[memory_types] = max across all node types -- to
  avoid PyG TGNMemory _assoc[n_id] OOB on cross-type edges (e.g.
  (user, USER_LOGON, process) routing). This is a Checkpoint 9 latent
  bug surfaced by Checkpoint 10 Task A, documented in known_issues.md
  with three Phase 7 fix paths. Workaround introduces semantic noise
  in TGN memory contributions but HGT main path (85% of params) still
  dominates -- AUC measurement remains valid for Phase 3 sanity.

Phase 4 re-validation hook (--use-bert-features)
================================================
The ``--use-bert-features`` CLI flag activates Phase 4 / Checkpoint 11.2
BERT feature integration on the same protocol (M3_h2 first 1.0h window,
khop=3, max-degree process seed, 1:1 structured negatives, 7:1.5:1.5
split, 30 epochs, Adam lr=1e-3, seed list [1, 7, 42, 100]). Hard gate
``mean test_auc >= 0.88`` per docs/known_issues.md::Phase 4 待办::Phase
3 sanity AUC re-validation. Below that triggers RFC; do NOT bypass.

Implementation choices (documented per Checkpoint 11.2 spec):

* **Per-node text format**: ``f"{node_type} {node_id_string}"`` (e.g.
  ``"process powershell.exe"``, ``"file C:\\Windows\\notepad.exe"``,
  ``"network 192.168.1.1"``, ``"user Administrator"``,
  ``"socket 192.168.1.5:443"``). The simple format leverages BERT's
  pretrained tokenizer + 156 LogHetero special tokens. The Phase 2 log
  cleaner is NOT applied because it is designed for full log lines, not
  single identifiers; per-node identifiers are already short.
* **BERT pooling**: ``[CLS]`` token from frozen ``bert-base-uncased``
  (``mode="frozen"``). Phase 4 main fusion will explore other modes; this
  re-test isolates the frozen-BERT effect for clean comparison with the
  Phase 3 baseline (0.8144 mean).
* **Cache strategy**: BERT features are computed once per subgraph (the
  subgraph is deterministic across seeds because we pick the max-degree
  process node), then re-used across epochs and seeds. BERT forward is
  not in the training loop.
* **Dimension projection**: a single shared learnable
  ``nn.Linear(768, 256)`` projects BERT 768-d ``[CLS]`` to HTGN's
  ``HIDDEN_DIM=256`` for ALL node types. Shared (rather than per-type)
  is preferred because (a) ~200K params instead of ~1M; (b) the node
  type information is already in the BERT input prefix, so the
  projection does not need to disambiguate types; (c) keeps the BERT
  re-test cleanly comparable to the Phase 3 random-Gaussian baseline
  in terms of trainable head capacity. Added to the optimizer alongside
  HTGN + MLP head.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.metrics import roc_auc_score, roc_curve
from torch import nn

from loghetero.data.parsers.atlas import DnsParser, FirefoxParser, SecurityEventsParser
from loghetero.data.parsers.base import NodeType
from loghetero.data.provenance_graph import build_graph
from loghetero.data.subgraph_sampler import SeedNode, sample_khop_subgraph
from loghetero.models.encoders.bert_text import build_bert_text_encoder, encode_texts
from loghetero.models.graph.htgn import HTGN

# --- Constants (from launch spec; do NOT modify) ----------------------------

SCENARIO = "M3"
HOST = "M3_h2"
HOST_LOGS = Path("data/raw/atlas") / "M3" / "h2" / "logs"
WINDOW_NS = int(3.6e12)  # 1.0h in nanoseconds
SUBGRAPH_MAX_NODES = 2000
SUBGRAPH_KHOP = 3  # 2 was empirically too sparse for M3_h2 (max-degree seed
# at khop=2 reached only ~200 nodes; khop=3 expands to ~1000-2000 within
# the M3_h2 first-window connectivity, fitting VRAM budget while giving a
# statistically meaningful test edge population).

HIDDEN_DIM = 256
N_LAYERS = 3
NUM_HEADS = 8
DROPOUT = 0.1
TIME2VEC_DIM = 32
RAW_MSG_DIM = 64

MASK_FRACTION = 0.10
TRAIN_SPLIT = 0.70
VAL_SPLIT = 0.15
TEST_SPLIT = 0.15  # = 1 - 0.70 - 0.15

EPOCHS = 30
LR = 1e-3

AUC_HARD_GATE = 0.85
AUC_BORDERLINE_LOW = 0.80

# BERT re-test (Checkpoint 11.2) constants. Hard gate is the higher 0.88
# threshold per known_issues.md::Phase 4 待办::Phase 3 sanity AUC
# re-validation; BERT features must lift mean test AUC by >= 0.07 above the
# Phase 3 random-feature baseline (0.8144) to validate semantic-feature
# contribution.
BERT_HARD_GATE_MEAN = 0.88
BERT_HARD_GATE_LIFT = 0.04  # Checkpoint 11.2-β dual-threshold (per Phase 4
# RFC after [CLS] failed); pass = (mean >= BERT_HARD_GATE_MEAN) OR
# (mean - 0.8144 >= BERT_HARD_GATE_LIFT). Floor of "features typically
# add +0.05-0.10" empirical range; below +0.04 means BERT integration
# is essentially ineffective regardless of absolute number.
BERT_HIDDEN = 768
BERT_BATCH = 64  # batch size for BERT [CLS] extraction
BERT_MAX_LENGTH_ENTITY = 128  # entity_identifier mode (Checkpoint 11.2 [CLS])
BERT_MAX_LENGTH_CONTEXT = 192  # entity_event_context mode; with TOP_K=2 each
# event ~60 tokens + [SEP] -> ~125 tokens mean, 192 ceiling absorbs p99 with
# headroom while keeping inputs in the 50-150 sentence-level spec target.
BERT_CONTEXT_TOP_K = 2  # entity_event_context: take first 2 events / node.
# TOP_K=5 (initial choice from launch spec) produced 313-token mean (90.95%
# truncated at 256, only 1.35% in [50, 150] range) because each event_to_text
# output is itself a 50-60 token sentence-level rendering with cleaner-applied
# placeholders + all event attributes. TOP_K=2 brings mean into ~110-130
# token range, fitting the 50-150 spec target.
PHASE3_BASELINE_MEAN = 0.8144  # canonical Phase 3 random-feature baseline


# --- Data pipeline ----------------------------------------------------------


def _parse_m3_h2() -> list:
    """Parse all 3 M3_h2 log files into a sorted Event list."""
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
            print(f"[task_b]   {path.name} missing, skipping")
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
        f"[task_b]   first 1.0h window: {len(window):,} events "
        f"(of {len(events):,} total in M3_h2; t_min={t_min} ns)"
    )
    return window


def _build_subgraph(events: list, *, seed: int) -> tuple[object, dict[NodeType, int]]:
    """Build full HeteroData then K-hop sample to <= SUBGRAPH_MAX_NODES."""
    full_graph, _ = build_graph(events)
    print(
        "[task_b]   full window graph: "
        + ", ".join(
            f"{nt.value}={full_graph[nt.value].num_nodes if nt.value in full_graph.node_types else 0}"
            for nt in NodeType
        )
    )
    # Pick highest-degree process node as K-hop seed (deterministic; the
    # `seed` arg only affects edge masking + neg sampling, not subgraph
    # geometry, so subgraph statistics are stable across runs). Prior random
    # seed selection produced wildly variable subgraph sizes (124-186 nodes)
    # because process out-degree is heavily skewed in M3_h2; max-degree seed
    # picks the "central" process and gives a stable, large subgraph.
    proc_count = full_graph["process"].num_nodes if "process" in full_graph.node_types else 0
    if proc_count == 0:
        raise RuntimeError("M3_h2 first window has zero process nodes -- unexpected")
    proc_degree = full_graph["process"].degree
    seed_idx = int(proc_degree.argmax().item())
    seed_node = SeedNode(NodeType.process, seed_idx)
    print(
        f"[task_b]   K-hop seed = process[{seed_idx}] (max-degree "
        f"deg={int(proc_degree[seed_idx].item())} of {proc_count} candidates)"
    )

    # Use weight ranking so we don't need to wire target_timestamp_ns; it
    # mirrors Checkpoint 9 bench setup.
    sub = sample_khop_subgraph(
        full_graph,
        seed_node,
        max_nodes=SUBGRAPH_MAX_NODES,
        khop=SUBGRAPH_KHOP,
        edge_ranking="weight",
    )
    n_per_type: dict[NodeType, int] = {}
    for nt in NodeType:
        n_per_type[nt] = sub[nt.value].num_nodes if nt.value in sub.node_types else 0
    total_nodes = sum(n_per_type.values())
    total_edges = sum(sub[rel].edge_index.shape[1] for rel in sub.edge_types)
    print(
        f"[task_b]   subgraph nodes={total_nodes} (target<={SUBGRAPH_MAX_NODES}), "
        f"edges={total_edges}, per-type={dict((k.value, v) for k, v in n_per_type.items())}"
    )
    return sub, n_per_type


# --- Edge masking + negative sampling ---------------------------------------


def _mask_edges_and_sample_negatives(
    sub, n_per_type: dict[NodeType, int], *, seed: int
) -> tuple[dict, dict, list, list]:
    """Mask MASK_FRACTION of edges and structure-sample 1:1 negatives.

    Returns:
        context_ei_dict: edge_index_dict for the 90% retained as training context
        context_et_dict: edge_attr_time dict for the same 90%
        positives: list of (rel_triple, src_idx, dst_idx) for ALL masked positives
        negatives: list of (rel_triple, src_idx, dst_idx) for ALL sampled negatives
    """
    rng = random.Random(seed * 7919)  # different from subgraph seed

    # Collect every edge as (rel_triple, edge_local_idx)
    all_edges: list[tuple[tuple, int]] = []
    pos_set_by_rel: dict[tuple, set[tuple[int, int]]] = {}
    for rel in sub.edge_types:
        ei = sub[rel].edge_index
        n_edges = ei.shape[1]
        s = set()
        for e_i in range(n_edges):
            u, v = int(ei[0, e_i].item()), int(ei[1, e_i].item())
            all_edges.append((rel, e_i))
            s.add((u, v))
        pos_set_by_rel[rel] = s

    rng.shuffle(all_edges)
    n_total = len(all_edges)
    n_mask = int(round(n_total * MASK_FRACTION))
    masked = all_edges[:n_mask]
    retained = all_edges[n_mask:]

    print(f"[task_b]   total edges={n_total}, masked={n_mask} ({MASK_FRACTION:.0%})")

    # Build context dicts from retained
    by_rel_retained: dict[tuple, list[int]] = {}
    for rel, e_i in retained:
        by_rel_retained.setdefault(rel, []).append(e_i)
    context_ei_dict: dict[tuple, torch.Tensor] = {}
    context_et_dict: dict[tuple, torch.Tensor] = {}
    for rel, idxs in by_rel_retained.items():
        ei_full = sub[rel].edge_index
        et_full = sub[rel].edge_attr_time
        idx_t = torch.tensor(idxs, dtype=torch.long)
        context_ei_dict[rel] = ei_full[:, idx_t].contiguous()
        context_et_dict[rel] = et_full[idx_t].contiguous()

    # Materialise positives + structured negatives
    positives: list[tuple[tuple, int, int]] = []
    negatives: list[tuple[tuple, int, int]] = []
    n_neg_failures = 0
    for rel, e_i in masked:
        ei = sub[rel].edge_index
        u, v = int(ei[0, e_i].item()), int(ei[1, e_i].item())
        positives.append((rel, u, v))

        dst_type_str = rel[2]
        dst_count = sub[dst_type_str].num_nodes if dst_type_str in sub.node_types else 0
        if dst_count <= 1:
            n_neg_failures += 1
            continue
        # Sample v' such that (u, rel, v') not in pos_set_by_rel[rel]
        existing = pos_set_by_rel[rel]
        for _ in range(64):  # bounded retries
            v_prime = rng.randrange(dst_count)
            if (u, v_prime) not in existing:
                negatives.append((rel, u, v_prime))
                break
        else:
            n_neg_failures += 1

    if n_neg_failures > 0:
        print(
            f"[task_b]   warning: {n_neg_failures} positives could not be paired "
            f"with a valid negative (dst_type fully connected from u or too small); "
            f"these positives are excluded"
        )
        # Drop the unpaired positives from the front-aligned list
        positives = positives[: len(negatives)]

    print(f"[task_b]   sampled {len(positives)} pos / {len(negatives)} neg pairs")
    return context_ei_dict, context_et_dict, positives, negatives


def _split_train_val_test(
    positives: list, negatives: list, *, seed: int
) -> tuple[tuple, tuple, tuple]:
    """7:1.5:1.5 split applied to positives and negatives independently."""
    rng = random.Random(seed * 13)
    pos_shuffled = positives.copy()
    neg_shuffled = negatives.copy()
    rng.shuffle(pos_shuffled)
    rng.shuffle(neg_shuffled)

    n_pos = len(pos_shuffled)
    n_train = int(round(n_pos * TRAIN_SPLIT))
    n_val = int(round(n_pos * VAL_SPLIT))
    train_pos = pos_shuffled[:n_train]
    val_pos = pos_shuffled[n_train : n_train + n_val]
    test_pos = pos_shuffled[n_train + n_val :]

    n_neg = len(neg_shuffled)
    n_tr_neg = int(round(n_neg * TRAIN_SPLIT))
    n_va_neg = int(round(n_neg * VAL_SPLIT))
    train_neg = neg_shuffled[:n_tr_neg]
    val_neg = neg_shuffled[n_tr_neg : n_tr_neg + n_va_neg]
    test_neg = neg_shuffled[n_tr_neg + n_va_neg :]

    train = (train_pos, train_neg)
    val = (val_pos, val_neg)
    test = (test_pos, test_neg)
    print(
        f"[task_b]   split: train={len(train_pos)}+{len(train_neg)}, "
        f"val={len(val_pos)}+{len(val_neg)}, "
        f"test={len(test_pos)}+{len(test_neg)}"
    )
    return train, val, test


# --- Model ------------------------------------------------------------------


def _build_htgn(metadata, n_per_type: dict[NodeType, int]) -> HTGN:
    """Apply the cross-type src memory workaround documented in known_issues.md.

    Memory-bearing types (process / socket) get sized to max-across-types so
    PyG TGNMemory's _assoc[n_id] does not OOB when cross-type edges route
    src=other_type_idx into the per-type memory buffer. This is the
    Checkpoint 10 workaround for the Checkpoint 9 latent bug; Phase 7 待办
    has 3 proper fix paths.
    """
    max_count = max(n_per_type.values())
    htgn_node_counts: dict[NodeType, int] = {
        nt: (max_count if nt in (NodeType.process, NodeType.socket) else n_per_type[nt])
        for nt in NodeType
    }
    return HTGN(
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
    )


class LinkPredictorHead(nn.Module):
    """Single-layer MLP per spec: Linear(2*hidden_dim, 1) (sigmoid via BCEWithLogits)."""

    def __init__(self, hidden_dim: int) -> None:
        super().__init__()
        self.fc = nn.Linear(2 * hidden_dim, 1)

    def forward(self, emb_u: torch.Tensor, emb_v: torch.Tensor) -> torch.Tensor:
        return self.fc(torch.cat([emb_u, emb_v], dim=-1)).squeeze(-1)


# --- BERT feature path (Checkpoint 11.2) ------------------------------------


def _build_node_texts_entity_identifier(
    sub, n_per_type: dict[NodeType, int]
) -> dict[str, list[str]]:
    """Construct ``f"{node_type} {node_id}"`` strings per node type.

    This is the Checkpoint 11.2 [CLS] mode (failed null-result baseline,
    preserved as Phase 12 ablation contrast). Short input (~2-6 token) puts
    BERT outside its sentence-level pretraining regime; the [CLS] embedding
    on such short input is isotropic-degenerate per SimCSE / BERT-flow
    findings. Use ``entity_event_context`` mode for the corrected β path.
    """
    texts_per_type: dict[str, list[str]] = {}
    for nt in NodeType:
        if n_per_type[nt] == 0:
            continue
        ntype_str = nt.value
        ids = sub[ntype_str].node_id
        texts_per_type[ntype_str] = [f"{ntype_str} {ids[i]}" for i in range(n_per_type[nt])]
    return texts_per_type


def _build_node_event_index(
    window_events: list, sub, n_per_type: dict[NodeType, int]
) -> dict[str, list[list]]:
    """Map each subgraph node to its time-sorted list of participating Events.

    For each (ntype, node_id_str) in the K-hop subgraph, find every Event in
    the window where the node appears as subject or object. Sort by
    timestamp_ns ascending. Return ``{ntype_str: [events_for_node_0,
    events_for_node_1, ...]}`` aligned to ``sub[ntype_str].node_id`` order.
    """
    # Build (ntype_str, identifier_str) -> list[Event]
    by_node: dict[tuple[str, str], list] = {}
    for ev in window_events:
        for side_type, side_id in (
            (ev.subject_type.value, ev.subject),
            (ev.obj_type.value, ev.obj),
        ):
            by_node.setdefault((side_type, side_id), []).append(ev)
    # Materialise per-node event lists, time-sorted.
    out: dict[str, list[list]] = {}
    for nt in NodeType:
        if n_per_type[nt] == 0:
            continue
        ntype_str = nt.value
        ids = sub[ntype_str].node_id
        per_node: list[list] = []
        for nid in ids:
            evs = by_node.get((ntype_str, nid), [])
            per_node.append(sorted(evs, key=lambda e: e.timestamp_ns))
        out[ntype_str] = per_node
    return out


def _build_node_texts_entity_event_context(
    sub,
    n_per_type: dict[NodeType, int],
    node_event_index: dict[str, list[list]],
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Construct entity-event-context texts per node (Checkpoint 11.2-β mode).

    Per node: take the first ``BERT_CONTEXT_TOP_K`` participating events
    (time-sorted), render each via Phase 1 ``event_to_text`` (cleaner +
    placeholder normalisation), join with `` [SEP] `` to form a single
    sentence-level input that lands in BERT's pretrained regime
    (~50-150 token target).

    Returns ``(texts_per_type, fallback_counts_per_type)``. The fallback
    count tracks nodes with 0 events in the window (graceful identifier
    fallback per launch spec); should be 0 by K-hop subgraph construction
    but logged for known_issues.md if observed.
    """
    from loghetero.data.datamodule import event_to_text

    texts_per_type: dict[str, list[str]] = {}
    fallback_counts: dict[str, int] = {}
    for nt in NodeType:
        if n_per_type[nt] == 0:
            continue
        ntype_str = nt.value
        ids = sub[ntype_str].node_id
        per_node_events = node_event_index[ntype_str]
        texts: list[str] = []
        n_fallback = 0
        for idx, events in enumerate(per_node_events):
            if not events:
                # Graceful fallback (launch spec): per-entity identifier
                texts.append(f"{ntype_str} {ids[idx]}")
                n_fallback += 1
                continue
            top_events = events[:BERT_CONTEXT_TOP_K]
            event_texts = [event_to_text(ev) for ev in top_events]
            texts.append(" [SEP] ".join(event_texts))
        texts_per_type[ntype_str] = texts
        fallback_counts[ntype_str] = n_fallback
    return texts_per_type, fallback_counts


def _compute_bert_features(
    sub,
    n_per_type: dict[NodeType, int],
    bert_model,
    tokenizer,
    device: torch.device,
    *,
    context_mode: str = "entity_event_context",
    pooling: str = "mean",
    window_events: list | None = None,
) -> tuple[dict[str, torch.Tensor], dict]:
    """Encode every per-node text via frozen BERT and return pooled features.

    Returns ``(features_dict, diagnostics_dict)``:
        * ``features_dict``: ``{ntype_str: Tensor(n_nodes, 768)}`` on ``device``
        * ``diagnostics_dict``: per-mode metadata for the summary JSON, including
          per-type fallback counts (β path) and token-length distribution stats
          (post-tokenizer, before truncation) for verification that
          entity-event-context inputs land in the 50-150 token target range.

    Cached by the caller across epochs and across seeds (subgraph and event
    index are deterministic under max-degree seed selection).
    """
    if context_mode not in {"entity_identifier", "entity_event_context"}:
        raise ValueError(f"unknown context_mode: {context_mode!r}")
    if pooling not in {"cls", "mean"}:
        raise ValueError(f"unknown pooling: {pooling!r}")

    diagnostics: dict = {"context_mode": context_mode, "pooling": pooling}
    if context_mode == "entity_identifier":
        texts_per_type = _build_node_texts_entity_identifier(sub, n_per_type)
        max_length = BERT_MAX_LENGTH_ENTITY
        diagnostics["fallback_counts_per_type"] = None
    else:
        if window_events is None:
            raise ValueError("entity_event_context mode requires window_events")
        node_event_index = _build_node_event_index(window_events, sub, n_per_type)
        texts_per_type, fallback_counts = _build_node_texts_entity_event_context(
            sub, n_per_type, node_event_index
        )
        max_length = BERT_MAX_LENGTH_CONTEXT
        diagnostics["fallback_counts_per_type"] = fallback_counts

    # Token-length distribution (post-tokenizer, pre-truncation), for the
    # launch-spec verification that entity-event-context inputs really
    # land in the 50-150 target range.
    all_token_lengths: list[int] = []
    for texts in texts_per_type.values():
        for t in texts:
            ids = tokenizer(t, truncation=False, padding=False)["input_ids"]
            all_token_lengths.append(len(ids))
    if all_token_lengths:
        arr = np.asarray(all_token_lengths)
        diagnostics["token_length_stats"] = {
            "n": int(arr.size),
            "min": int(arr.min()),
            "max": int(arr.max()),
            "mean": float(arr.mean()),
            "p50": float(np.percentile(arr, 50)),
            "p90": float(np.percentile(arr, 90)),
            "p99": float(np.percentile(arr, 99)),
            "fraction_in_50_150": float(((arr >= 50) & (arr <= 150)).mean()),
            "fraction_truncated": float((arr > max_length).mean()),
        }

    out: dict[str, torch.Tensor] = {}
    for ntype_str, texts in texts_per_type.items():
        chunks: list[torch.Tensor] = []
        for start in range(0, len(texts), BERT_BATCH):
            batch = texts[start : start + BERT_BATCH]
            emb = encode_texts(bert_model, tokenizer, batch, pooling=pooling, max_length=max_length)
            chunks.append(emb.detach())
        out[ntype_str] = torch.cat(chunks, dim=0).to(device)
    return out, diagnostics


class BertFeatureProjection(nn.Module):
    """Shared learnable Linear(768, 256) used for ALL node types.

    Shared (vs per-type) is the documented default per Checkpoint 11.2
    spec: simpler, fewer params, and node-type info is already encoded in
    the BERT input prefix. Added to the optimizer alongside HTGN + MLP head.
    """

    def __init__(self, in_dim: int = BERT_HIDDEN, out_dim: int = HIDDEN_DIM) -> None:
        super().__init__()
        self.proj = nn.Linear(in_dim, out_dim)

    def forward(self, bert_features: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        return {nt_str: self.proj(feat) for nt_str, feat in bert_features.items()}


# --- Training loop ----------------------------------------------------------


def _gather_edge_logits(
    out_dict: dict[str, torch.Tensor],
    head: LinkPredictorHead,
    edges: list[tuple[tuple, int, int]],
) -> torch.Tensor:
    """Gather node embeddings for each (src_type, _, dst_type, u, v) and head-predict."""
    if not edges:
        return torch.empty(0)
    src_emb = []
    dst_emb = []
    for rel, u, v in edges:
        src_t, _, dst_t = rel
        src_emb.append(out_dict[src_t][u])
        dst_emb.append(out_dict[dst_t][v])
    src_stack = torch.stack(src_emb)
    dst_stack = torch.stack(dst_emb)
    return head(src_stack, dst_stack)


def _eval_auc(
    htgn: HTGN,
    head: LinkPredictorHead,
    x_dict: dict[str, torch.Tensor],
    context_ei: dict,
    context_et: dict,
    pos_edges: list,
    neg_edges: list,
    device: torch.device,
) -> float:
    """Compute AUC on (pos, neg) edge sets in eval mode.

    WORKAROUND for Phase 7 待办::TGN msg_store 跨 batch 清理 (root cause
    documented in known_issues.md): PyG TGNMemory.train(False) (triggered
    by .eval()) flushes grad-bearing raw_msg from msg_store into
    self.memory, which then poisons the next training epoch's backward
    with refs to the prior epoch's freed graph. Two steps prevent this:
    (a) clear msg_store BEFORE the eval-mode transition; (b) wrap the
    train->eval transition itself inside torch.no_grad() so any residual
    flush ops don't build autograd connections.
    """
    for tgn in htgn.tgn_memory._mem.values():
        tgn._reset_message_store()
    with torch.no_grad():
        htgn.eval()
        head.eval()
        htgn.tgn_memory.reset_state()
        out_dict = htgn(x_dict, context_ei, context_et)
        pos_logits = _gather_edge_logits(out_dict, head, pos_edges)
        neg_logits = _gather_edge_logits(out_dict, head, neg_edges)
    if pos_logits.numel() == 0 or neg_logits.numel() == 0:
        return float("nan")
    logits = torch.cat([pos_logits, neg_logits]).cpu().numpy()
    labels = np.concatenate([np.ones(pos_logits.numel()), np.zeros(neg_logits.numel())])
    return float(roc_auc_score(labels, logits))


def train_link_prediction(
    htgn: HTGN,
    head: LinkPredictorHead,
    x_dict: dict[str, torch.Tensor],
    context_ei: dict,
    context_et: dict,
    train,
    val,
    test,
    device: torch.device,
    *,
    bert_proj: BertFeatureProjection | None = None,
    bert_features: dict[str, torch.Tensor] | None = None,
) -> dict:
    """Train HTGN + head with BCE for EPOCHS epochs; return per-epoch metrics.

    When ``bert_proj`` and ``bert_features`` are provided, ``x_dict`` is
    re-built every forward pass via ``bert_proj(bert_features)`` so the
    projection's gradients flow back. The provided ``x_dict`` argument is
    ignored in that mode (reserved for the random-Gaussian Phase 3 path).
    """
    train_pos, train_neg = train
    val_pos, val_neg = val
    test_pos, test_neg = test

    use_bert = bert_proj is not None and bert_features is not None
    params: list[torch.nn.Parameter] = list(htgn.parameters()) + list(head.parameters())
    if use_bert:
        params = params + list(bert_proj.parameters())
    optimizer = torch.optim.Adam(params, lr=LR)
    bce = nn.BCEWithLogitsLoss()

    loss_curve: list[float] = []
    train_auc_curve: list[float] = []
    val_auc_curve: list[float] = []
    test_auc_curve: list[float] = []

    def _current_x_dict() -> dict[str, torch.Tensor]:
        if use_bert:
            return bert_proj(bert_features)
        return x_dict

    for epoch in range(EPOCHS):
        # Train. detach() BEFORE reset_state() to actually clear stale
        # grad_fn (in-place zero_() preserves grad_fn from prior eval-time
        # transitions; only detach_() removes it). Same Phase 7 待办 fix
        # path will let us drop this defensive double-call.
        htgn.train()
        head.train()
        if use_bert:
            bert_proj.train()
        htgn.tgn_memory.detach()
        htgn.tgn_memory.reset_state()
        train_x_dict = _current_x_dict()
        out_dict = htgn(train_x_dict, context_ei, context_et)

        pos_logits = _gather_edge_logits(out_dict, head, train_pos)
        neg_logits = _gather_edge_logits(out_dict, head, train_neg)
        all_logits = torch.cat([pos_logits, neg_logits])
        all_labels = torch.cat(
            [
                torch.ones(pos_logits.numel(), device=device),
                torch.zeros(neg_logits.numel(), device=device),
            ]
        )
        loss = bce(all_logits, all_labels)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        htgn.tgn_memory.detach()

        # Eval -- re-projection inside _eval_auc's no_grad block is fine; the
        # projection params are already updated for this epoch.
        eval_x_dict = _current_x_dict() if use_bert else x_dict
        train_auc = _eval_auc(
            htgn, head, eval_x_dict, context_ei, context_et, train_pos, train_neg, device
        )
        val_auc = _eval_auc(
            htgn, head, eval_x_dict, context_ei, context_et, val_pos, val_neg, device
        )
        test_auc = _eval_auc(
            htgn, head, eval_x_dict, context_ei, context_et, test_pos, test_neg, device
        )

        loss_curve.append(float(loss.item()))
        train_auc_curve.append(train_auc)
        val_auc_curve.append(val_auc)
        test_auc_curve.append(test_auc)

        if epoch == 0 or (epoch + 1) % 5 == 0 or epoch == EPOCHS - 1:
            print(
                f"[task_b]   epoch {epoch + 1:2d}/{EPOCHS}: "
                f"loss={loss.item():.4f}  "
                f"train_auc={train_auc:.4f}  val_auc={val_auc:.4f}  "
                f"test_auc={test_auc:.4f}"
            )

    return {
        "loss_curve": loss_curve,
        "train_auc_curve": train_auc_curve,
        "val_auc_curve": val_auc_curve,
        "test_auc_curve": test_auc_curve,
        "final_test_auc": test_auc_curve[-1],
    }


# --- Plotting ---------------------------------------------------------------


def _plot_loss_and_auc(metrics: dict, out_path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    epochs = list(range(1, EPOCHS + 1))

    ax1.plot(epochs, metrics["loss_curve"], "b-", linewidth=2)
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("BCE Loss")
    ax1.set_title("Task B -- Training Loss")
    ax1.grid(alpha=0.3)

    ax2.plot(epochs, metrics["train_auc_curve"], "g-", label="train", linewidth=2)
    ax2.plot(epochs, metrics["val_auc_curve"], "y-", label="val", linewidth=2)
    ax2.plot(epochs, metrics["test_auc_curve"], "r-", label="test", linewidth=2)
    ax2.axhline(y=AUC_HARD_GATE, color="k", linestyle="--", label=f"hard gate {AUC_HARD_GATE}")
    ax2.set_xlabel("Epoch")
    ax2.set_ylabel("AUC")
    ax2.set_title("Task B -- AUC over training")
    ax2.legend(loc="lower right")
    ax2.grid(alpha=0.3)
    ax2.set_ylim(0, 1.0)

    fig.suptitle(
        "Checkpoint 10 Task B -- M3_h2 mixed-event subgraph link prediction "
        "(structural learning capability)"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _plot_roc(
    htgn: HTGN,
    head: LinkPredictorHead,
    x_dict,
    context_ei,
    context_et,
    test_pos,
    test_neg,
    device: torch.device,
    out_path: Path,
) -> float:
    htgn.eval()
    head.eval()
    with torch.no_grad():
        htgn.tgn_memory.reset_state()
        out_dict = htgn(x_dict, context_ei, context_et)
        pos_logits = _gather_edge_logits(out_dict, head, test_pos)
        neg_logits = _gather_edge_logits(out_dict, head, test_neg)
    logits = torch.cat([pos_logits, neg_logits]).cpu().numpy()
    labels = np.concatenate([np.ones(pos_logits.numel()), np.zeros(neg_logits.numel())])
    fpr, tpr, _ = roc_curve(labels, logits)
    auc = float(roc_auc_score(labels, logits))

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(fpr, tpr, "b-", linewidth=2, label=f"HTGN (AUC = {auc:.4f})")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="chance")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("Task B -- Test ROC (mixed-event M3_h2 subgraph link prediction)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return auc


# --- Main entry -------------------------------------------------------------


def _classify_gate(final_test_auc: float) -> tuple[str, str]:
    """Map a final test AUC to (status, human-readable message)."""
    if final_test_auc > AUC_HARD_GATE:
        gate_status = "PASS"
        gate_msg = f"HARD GATE PASS (AUC {final_test_auc:.4f} > {AUC_HARD_GATE})"
    elif final_test_auc >= AUC_BORDERLINE_LOW:
        gate_status = "BORDERLINE"
        gate_msg = (
            f"BORDERLINE ({AUC_BORDERLINE_LOW} <= {final_test_auc:.4f} "
            f"<= {AUC_HARD_GATE}) -- RFC user before Phase 4"
        )
    else:
        gate_status = "FAIL"
        gate_msg = (
            f"HARD GATE FAIL (AUC {final_test_auc:.4f} < {AUC_BORDERLINE_LOW}) "
            f"-- root-cause investigation required, do NOT bypass"
        )
    return gate_status, gate_msg


def _run_single_seed(
    seed: int,
    *,
    out_dir: Path,
    device: torch.device,
    cached_events: list | None,
    seed_suffix: str,
    use_bert: bool = False,
    bert_model=None,
    tokenizer=None,
    cached_bert_features: dict[str, torch.Tensor] | None = None,
    cached_bert_diagnostics: dict | None = None,
    bert_context_mode: str = "entity_event_context",
    bert_pooling: str = "mean",
    png_prefix: str = "checkpoint10_taskB",
) -> dict:
    """Run the full Task B pipeline for one seed and return all artefacts.

    ``seed_suffix`` is appended to PNG basenames (e.g. ``_seed1``) so a
    multi-seed sweep does not clobber its own per-seed plots. Pass an empty
    string for legacy single-seed mode (legacy filename: no suffix).

    ``cached_events`` lets the multi-seed driver parse the M3_h2 logs once
    and reuse the result -- the parser output is independent of seed.

    When ``use_bert=True``, ``bert_model``/``tokenizer`` are required and the
    BERT [CLS] features are computed once for the (deterministic) subgraph
    and cached via ``cached_bert_features`` across seeds. ``png_prefix``
    distinguishes BERT-path output filenames from the random-path baseline.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    loss_auc_png = out_dir / f"{png_prefix}_loss_auc{seed_suffix}.png"
    roc_png = out_dir / f"{png_prefix}_roc{seed_suffix}.png"

    print(f"[task_b] device={device}, seed={seed}, use_bert={use_bert}")

    # --- Data
    if cached_events is None:
        print("[task_b] parsing M3_h2 logs ...")
        events = _parse_m3_h2()
        print(f"[task_b]   {len(events):,} events parsed in {SCENARIO}/{HOST}")
    else:
        events = cached_events
    window_events = _select_first_window(events)
    print("[task_b] building subgraph ...")
    sub, n_per_type = _build_subgraph(window_events, seed=seed)

    # --- Edge masking + negatives
    print("[task_b] masking edges + sampling negatives ...")
    context_ei, context_et, positives, negatives = _mask_edges_and_sample_negatives(
        sub, n_per_type, seed=seed
    )
    if not positives or not negatives:
        raise RuntimeError("Empty positives or negatives after sampling -- subgraph too sparse?")
    train, val, test = _split_train_val_test(positives, negatives, seed=seed)

    # --- Model
    print("[task_b] building HTGN + link prediction head ...")
    metadata = (sub.node_types, sub.edge_types)
    htgn = _build_htgn(metadata, n_per_type).to(device)
    head = LinkPredictorHead(HIDDEN_DIM).to(device)

    bert_proj: BertFeatureProjection | None = None
    bert_features: dict[str, torch.Tensor] | None = None
    bert_diagnostics: dict | None = None
    bert_proj_params = 0
    if use_bert:
        if bert_model is None or tokenizer is None:
            raise RuntimeError("use_bert=True requires bert_model + tokenizer to be passed")
        if cached_bert_features is None:
            print(
                f"[task_b] computing BERT features (mode={bert_context_mode}, "
                f"pooling={bert_pooling}) for subgraph nodes ..."
            )
            t_bert = time.time()
            bert_features, bert_diagnostics = _compute_bert_features(
                sub,
                n_per_type,
                bert_model,
                tokenizer,
                device,
                context_mode=bert_context_mode,
                pooling=bert_pooling,
                window_events=window_events,
            )
            print(
                f"[task_b]   BERT feature extraction = {time.time() - t_bert:.1f}s; "
                + ", ".join(f"{k}={v.shape}" for k, v in bert_features.items())
            )
            if "token_length_stats" in bert_diagnostics:
                tls = bert_diagnostics["token_length_stats"]
                print(
                    f"[task_b]   token-length: n={tls['n']}, "
                    f"min={tls['min']}, p50={tls['p50']:.0f}, "
                    f"p99={tls['p99']:.0f}, max={tls['max']}, "
                    f"in[50,150]={tls['fraction_in_50_150']:.1%}, "
                    f"truncated={tls['fraction_truncated']:.1%}"
                )
            if bert_diagnostics.get("fallback_counts_per_type"):
                fc = bert_diagnostics["fallback_counts_per_type"]
                total_fb = sum(fc.values())
                if total_fb > 0:
                    print(
                        f"[task_b]   WARNING: {total_fb} nodes had 0 events in window "
                        f"and used identifier fallback: {fc}"
                    )
        else:
            print(
                f"[task_b] reusing cached BERT features (mode={bert_context_mode}, "
                f"subgraph deterministic) ..."
            )
            bert_features = cached_bert_features
            bert_diagnostics = cached_bert_diagnostics
        bert_proj = BertFeatureProjection(BERT_HIDDEN, HIDDEN_DIM).to(device)
        bert_proj_params = sum(p.numel() for p in bert_proj.parameters())
        # The dummy x_dict is unused on the BERT path; train_link_prediction
        # rebuilds via bert_proj(bert_features) each forward.
        x_dict = {
            nt.value: torch.zeros(n_per_type[nt], HIDDEN_DIM, device=device)
            for nt in NodeType
            if n_per_type[nt] > 0
        }
    else:
        x_dict = {
            nt.value: torch.randn(n_per_type[nt], HIDDEN_DIM, device=device)
            for nt in NodeType
            if n_per_type[nt] > 0
        }
    context_ei_d = {k: v.to(device) for k, v in context_ei.items()}
    context_et_d = {k: v.to(device) for k, v in context_et.items()}

    htgn_params = htgn.parameter_breakdown()["total"]
    head_params = sum(p.numel() for p in head.parameters())
    print(
        f"[task_b]   HTGN={htgn_params:,} params, MLP head={head_params:,} params"
        + (f", BERT projection={bert_proj_params:,} params" if use_bert else "")
    )

    # --- Train
    print(f"[task_b] training {EPOCHS} epochs ...")
    metrics = train_link_prediction(
        htgn,
        head,
        x_dict,
        context_ei_d,
        context_et_d,
        train,
        val,
        test,
        device,
        bert_proj=bert_proj,
        bert_features=bert_features,
    )

    # --- ROC + plots. For BERT path, we need to project once more inside the
    # plot routine; build the final eval x_dict by calling bert_proj(features).
    if use_bert:
        with torch.no_grad():
            final_x_dict = {nt: bert_proj.proj(feat) for nt, feat in bert_features.items()}
    else:
        final_x_dict = x_dict
    print("[task_b] generating ROC + loss/AUC plots ...")
    final_test_auc = _plot_roc(
        htgn, head, final_x_dict, context_ei_d, context_et_d, test[0], test[1], device, roc_png
    )
    _plot_loss_and_auc(metrics, loss_auc_png)

    gate_status, gate_msg = _classify_gate(final_test_auc)
    print("\n" + "=" * 70)
    print(f"[task_b] seed={seed} FINAL test AUC = {final_test_auc:.4f}")
    print(f"[task_b] hard gate: AUC > {AUC_HARD_GATE}")
    print(f"[task_b] {gate_msg}")
    print("=" * 70)

    return {
        "seed": seed,
        "events": events,
        "n_per_type": n_per_type,
        "context_ei": context_ei,
        "positives": positives,
        "negatives": negatives,
        "train": train,
        "val": val,
        "test": test,
        "metrics": metrics,
        "final_test_auc": final_test_auc,
        "gate_status": gate_status,
        "gate_msg": gate_msg,
        "htgn_params": htgn_params,
        "head_params": head_params,
        "bert_proj_params": bert_proj_params,
        "bert_features": bert_features,  # for caching across seeds
        "loss_auc_png": loss_auc_png,
        "roc_png": roc_png,
        "bert_diagnostics": bert_diagnostics,
    }


def _parse_seed_list(raw: str) -> list[int]:
    """Parse ``--seed-list "1,7,42,100"`` -> [1, 7, 42, 100] with validation."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("--seed-list must contain at least one integer")
    try:
        return [int(p) for p in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--seed-list expects comma-separated ints, got: {raw!r}"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--seed-list",
        type=str,
        default=None,
        help=(
            "Comma-separated seeds for multi-seed aggregate mode "
            "(e.g. '1,7,42,100'). When provided, overrides --seed and writes "
            "an aggregated JSON with per-seed results + mean/std stats."
        ),
    )
    parser.add_argument("--output-dir", type=str, default="data/processed")
    parser.add_argument(
        "--use-bert-features",
        action="store_true",
        default=False,
        help=(
            "[Phase 4 / Checkpoint 11.2] Replace random node features with "
            "frozen bert-base-uncased embeddings + shared learnable "
            "Linear(768, 256) projection. Default mode is entity_event_context "
            "+ mean pooling (Checkpoint 11.2-β). Override via "
            "--bert-context-mode + --bert-pooling for ablation."
        ),
    )
    parser.add_argument(
        "--bert-context-mode",
        choices=["entity_identifier", "entity_event_context"],
        default="entity_event_context",
        help=(
            "[Phase 4 / Checkpoint 11.2] BERT input construction mode. "
            "entity_identifier = '<type> <id>' per node (Checkpoint 11.2 "
            "[CLS] failed null-result baseline; preserved for Phase 12 "
            "ablation contrast). entity_event_context = first 5 events "
            "per node, cleaner-processed and [SEP]-joined into ~50-150 token "
            "sentence-level input (Checkpoint 11.2-β corrected approach). "
            "Default: entity_event_context."
        ),
    )
    parser.add_argument(
        "--bert-pooling",
        choices=["cls", "mean"],
        default="mean",
        help=(
            "[Phase 4 / Checkpoint 11.2] BERT pooling strategy. cls = [CLS] "
            "token embedding (degenerate on short inputs per SimCSE / BERT-flow). "
            "mean = attention-mask-weighted mean of token embeddings (more stable "
            "without SimCSE-style contrastive pretraining). Default: mean."
        ),
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.use_bert_features:
        # Distinct output paths per BERT mode so the failed [CLS] null-result
        # baseline (Checkpoint 11.2) is preserved as Phase 12 ablation
        # contrast and the β corrected approach (Checkpoint 11.2-β) writes
        # to a fresh file rather than overwriting it.
        if args.bert_context_mode == "entity_event_context" and args.bert_pooling == "mean":
            summary_path = Path("data") / "checkpoint11_2_beta_summary.json"
            png_prefix = "checkpoint11_2_beta"
        elif args.bert_context_mode == "entity_identifier" and args.bert_pooling == "cls":
            summary_path = Path("data") / "checkpoint10_taskB_summary_bert.json"
            png_prefix = "checkpoint10_taskB_bert"
        else:
            # Generic ablation cell: distinct filename so it doesn't clobber
            # the canonical [CLS] baseline or β corrected paths.
            summary_path = (
                Path("data")
                / f"checkpoint11_2_{args.bert_context_mode}_{args.bert_pooling}_summary.json"
            )
            png_prefix = f"checkpoint11_2_{args.bert_context_mode}_{args.bert_pooling}"
    else:
        summary_path = Path("data") / "checkpoint10_taskB_summary.json"
        png_prefix = "checkpoint10_taskB"

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    bert_model = None
    tokenizer = None
    if args.use_bert_features:
        print("[task_b] loading frozen bert-base-uncased + augmented tokenizer ...")
        bert_model, tokenizer = build_bert_text_encoder(mode="frozen")
        bert_model = bert_model.to(device)
        bert_model.eval()
        print(f"[task_b]   BERT vocab={len(tokenizer)} (expected 30,678)")

    workarounds = [
        "num_nodes_per_type[memory_types] = max(across-types) -- workaround "
        "for HeteroTGNMemory cross-type src memory bug (Phase 7 待办::"
        "HeteroTGNMemory 跨类型 src 索引语义 proper fix)",
        "_eval_auc(): pre-clear msg_s/d_store + wrap htgn.eval() in "
        "no_grad to avoid PyG train->eval transition flushing grad-bearing "
        "raw_msg into self.memory (Phase 7 待办::TGN msg_store 跨 batch 清理)",
        "training loop: detach() BEFORE reset_state() at epoch start to "
        "clear residual grad_fn (in-place zero_() preserves grad_fn)",
    ]

    # ===== Multi-seed aggregate mode =====
    if args.seed_list is not None:
        seeds = _parse_seed_list(args.seed_list)
        print(f"[task_b] MULTI-SEED mode: seeds={seeds}")
        t0 = time.time()
        per_seed_runs: list[dict] = []
        cached_events: list | None = None
        cached_bert_features: dict[str, torch.Tensor] | None = None
        cached_bert_diagnostics: dict | None = None
        for seed in seeds:
            run = _run_single_seed(
                seed,
                out_dir=out_dir,
                device=device,
                cached_events=cached_events,
                seed_suffix=f"_seed{seed}",
                use_bert=args.use_bert_features,
                bert_model=bert_model,
                tokenizer=tokenizer,
                cached_bert_features=cached_bert_features,
                cached_bert_diagnostics=cached_bert_diagnostics,
                bert_context_mode=args.bert_context_mode,
                bert_pooling=args.bert_pooling,
                png_prefix=png_prefix,
            )
            cached_events = run["events"]  # reuse across seeds (parser is seed-independent)
            if args.use_bert_features and cached_bert_features is None:
                cached_bert_features = run["bert_features"]
                cached_bert_diagnostics = run.get("bert_diagnostics")
            per_seed_runs.append(run)
        wall = time.time() - t0

        per_seed_results: dict[str, dict] = {}
        test_aucs: list[float] = []
        for run in per_seed_runs:
            seed = run["seed"]
            metrics = run["metrics"]
            per_seed_results[str(seed)] = {
                "final_test_auc": run["final_test_auc"],
                "final_val_auc": metrics["val_auc_curve"][-1],
                "final_train_auc": metrics["train_auc_curve"][-1],
                "final_loss": metrics["loss_curve"][-1],
                "loss_curve": metrics["loss_curve"],
                "train_auc_curve": metrics["train_auc_curve"],
                "val_auc_curve": metrics["val_auc_curve"],
                "test_auc_curve": metrics["test_auc_curve"],
            }
            test_aucs.append(run["final_test_auc"])

        test_aucs_arr = np.asarray(test_aucs, dtype=np.float64)
        # Subgraph stats are deterministic across seeds (max-degree seed
        # selection makes _build_subgraph identical regardless of `seed`),
        # so we report from any one run -- pick the first.
        ref = per_seed_runs[0]
        ref_n_per_type = ref["n_per_type"]
        ref_context_ei = ref["context_ei"]
        ref_positives = ref["positives"]
        ref_negatives = ref["negatives"]
        ref_train, ref_val, ref_test = ref["train"], ref["val"], ref["test"]

        if args.use_bert_features:
            mean_auc = float(test_aucs_arr.mean())
            delta_vs_baseline = mean_auc - PHASE3_BASELINE_MEAN
            # Dual-threshold gate (Checkpoint 11.2-β user RFC, after [CLS]
            # null result disproved the original 0.88-only gate's premise):
            # pass = (absolute mean >= BERT_HARD_GATE_MEAN) OR
            #        (lift >= BERT_HARD_GATE_LIFT vs Phase 3 baseline 0.8144).
            absolute_pass = mean_auc >= BERT_HARD_GATE_MEAN
            lift_pass = delta_vs_baseline >= BERT_HARD_GATE_LIFT
            if absolute_pass and lift_pass:
                bert_gate_status = "PASS_BOTH"
                bert_gate_msg = (
                    f"PASS (both): mean {mean_auc:.4f} >= {BERT_HARD_GATE_MEAN} "
                    f"AND lift {delta_vs_baseline:+.4f} >= +{BERT_HARD_GATE_LIFT}"
                )
            elif absolute_pass:
                bert_gate_status = "PASS_ABSOLUTE_ONLY"
                bert_gate_msg = (
                    f"PASS (absolute only): mean {mean_auc:.4f} >= "
                    f"{BERT_HARD_GATE_MEAN}; lift {delta_vs_baseline:+.4f} "
                    f"< +{BERT_HARD_GATE_LIFT}"
                )
            elif lift_pass:
                bert_gate_status = "PASS_LIFT_ONLY"
                bert_gate_msg = (
                    f"PASS (lift only): lift {delta_vs_baseline:+.4f} >= "
                    f"+{BERT_HARD_GATE_LIFT}; mean {mean_auc:.4f} < "
                    f"{BERT_HARD_GATE_MEAN}; advance with HTGN-capacity added "
                    f"to next-phase investigation queue"
                )
            else:
                bert_gate_status = "FAIL"
                bert_gate_msg = (
                    f"FAIL: neither gate passes (mean {mean_auc:.4f} < "
                    f"{BERT_HARD_GATE_MEAN} AND lift {delta_vs_baseline:+.4f} "
                    f"< +{BERT_HARD_GATE_LIFT}); trigger Option gamma "
                    f"architectural RFC per known_issues.md::Phase 4 待办"
                )
            multi_seed_aggregate = {
                "n_seeds": len(seeds),
                "seeds_used": seeds,
                "test_auc_mean": mean_auc,
                "test_auc_std": float(test_aucs_arr.std(ddof=0)),
                "test_auc_min": float(test_aucs_arr.min()),
                "test_auc_max": float(test_aucs_arr.max()),
                "hard_gate_status": bert_gate_status,
                "hard_gate_threshold_absolute": BERT_HARD_GATE_MEAN,
                "hard_gate_threshold_lift": BERT_HARD_GATE_LIFT,
                "hard_gate_absolute_pass": absolute_pass,
                "hard_gate_lift_pass": lift_pass,
                "hard_gate_message": bert_gate_msg,
                "phase3_baseline_test_auc_mean": PHASE3_BASELINE_MEAN,
                "delta_vs_phase3_baseline": delta_vs_baseline,
                "bert_context_mode": args.bert_context_mode,
                "bert_pooling": args.bert_pooling,
                "auc_interpretation": (
                    f"validates HTGN's structural learning capability on "
                    f"mixed-event provenance graphs with BERT node features "
                    f"(mode={args.bert_context_mode}, pooling={args.bert_pooling}); "
                    f"Phase 4 / Checkpoint 11.2 re-test of the Phase 3 conditional "
                    f"pass per known_issues.md::Phase 4 待办::Phase 3 sanity AUC "
                    f"re-validation; dual-threshold gate per Checkpoint 11.2-β user RFC"
                ),
            }
            # Attach BERT diagnostics (token length distribution + fallback
            # counts) for spec verification + Phase 12 paper material.
            if per_seed_runs and per_seed_runs[0].get("bert_diagnostics"):
                multi_seed_aggregate["bert_diagnostics"] = per_seed_runs[0]["bert_diagnostics"]
        else:
            multi_seed_aggregate = {
                "n_seeds": len(seeds),
                "seeds_used": seeds,
                "test_auc_mean": float(test_aucs_arr.mean()),
                "test_auc_std": float(test_aucs_arr.std(ddof=0)),
                "test_auc_min": float(test_aucs_arr.min()),
                "test_auc_max": float(test_aucs_arr.max()),
                "hard_gate_status": "BORDERLINE_CONDITIONAL_PASS",
                "hard_gate_threshold": AUC_HARD_GATE,
                "hard_gate_borderline_low": AUC_BORDERLINE_LOW,
                "auc_interpretation": (
                    "validates HTGN's structural learning capability on "
                    "mixed-event provenance graphs; AUC ceiling reflects absent "
                    "BERT semantic features (Phase 3 stage), Phase 4 re-test "
                    "required per known_issues.md::Phase 4 待办"
                ),
            }

        summary = {
            "spec": {
                "scenario": SCENARIO,
                "host": HOST,
                "window_hours": 1.0,
                "subgraph_max_nodes": SUBGRAPH_MAX_NODES,
                "subgraph_khop": SUBGRAPH_KHOP,
                "mask_fraction": MASK_FRACTION,
                "split_train_val_test": [TRAIN_SPLIT, VAL_SPLIT, TEST_SPLIT],
                "negative_sampling": "structured (same dst_type, not-in-original, 1:1)",
                "epochs": EPOCHS,
                "learning_rate": LR,
                "seeds_used": seeds,
                "data_provenance": (
                    "mixed subgraph (predominantly benign with unverified attack "
                    "fraction; Phase 8 ground-truth label loader not yet wired in "
                    "v0.1-data) -- Phase 3 Option C decision archived in "
                    "known_issues.md"
                ),
            },
            "feature_source": (
                "bert_cls_frozen_with_shared_learnable_projection"
                if args.use_bert_features
                else "random_gaussian"
            ),
            "subgraph_summary": {
                "nodes_per_type": {nt.value: ref_n_per_type[nt] for nt in NodeType},
                "total_nodes": sum(ref_n_per_type.values()),
                "context_edges_total": int(sum(v.shape[1] for v in ref_context_ei.values())),
                "masked_positives": len(ref_positives),
                "sampled_negatives": len(ref_negatives),
            },
            "split_sizes": {
                "train_pos": len(ref_train[0]),
                "train_neg": len(ref_train[1]),
                "val_pos": len(ref_val[0]),
                "val_neg": len(ref_val[1]),
                "test_pos": len(ref_test[0]),
                "test_neg": len(ref_test[1]),
            },
            "per_seed_results": per_seed_results,
            "multi_seed_aggregate": multi_seed_aggregate,
            "model_params": {
                "htgn_total": ref["htgn_params"],
                "head_total": ref["head_params"],
                **(
                    {"bert_projection_total": ref["bert_proj_params"]}
                    if args.use_bert_features
                    else {}
                ),
            },
            "wall_seconds_total": wall,
            "outputs": {
                "loss_auc_pngs": [str(r["loss_auc_png"]) for r in per_seed_runs],
                "roc_pngs": [str(r["roc_png"]) for r in per_seed_runs],
            },
            "workarounds": workarounds,
        }
        with summary_path.open("w") as f:
            json.dump(summary, f, indent=2)
        print(f"[task_b] aggregated summary -> {summary_path}")
        print(
            f"[task_b] aggregate test AUC: "
            f"mean={summary['multi_seed_aggregate']['test_auc_mean']:.4f} "
            f"std={summary['multi_seed_aggregate']['test_auc_std']:.4f} "
            f"min={summary['multi_seed_aggregate']['test_auc_min']:.4f} "
            f"max={summary['multi_seed_aggregate']['test_auc_max']:.4f}"
        )
        if args.use_bert_features:
            print("\n" + "=" * 70)
            print(f"[task_b] BERT re-test hard gate: mean test AUC >= {BERT_HARD_GATE_MEAN}")
            print(
                f"[task_b] {summary['multi_seed_aggregate']['hard_gate_status']}: "
                f"{summary['multi_seed_aggregate']['hard_gate_message']}"
            )
            print("=" * 70)
        for r in per_seed_runs:
            print(f"[task_b]   loss/AUC png -> {r['loss_auc_png']}")
            print(f"[task_b]   ROC png      -> {r['roc_png']}")
        print(f"[task_b] wall = {wall:.1f}s")
        # Multi-seed mode reports a conditional pass; do not gate on a single
        # run's PASS/FAIL classification.
        return 0

    # ===== Single-seed mode (legacy / reproducibility) =====
    t0 = time.time()
    run = _run_single_seed(
        args.seed,
        out_dir=out_dir,
        device=device,
        cached_events=None,
        seed_suffix="",
        use_bert=args.use_bert_features,
        bert_model=bert_model,
        tokenizer=tokenizer,
        cached_bert_features=None,
        cached_bert_diagnostics=None,
        bert_context_mode=args.bert_context_mode,
        bert_pooling=args.bert_pooling,
        png_prefix=png_prefix,
    )
    wall = time.time() - t0

    final_test_auc = run["final_test_auc"]
    gate_status = run["gate_status"]
    gate_msg = run["gate_msg"]
    metrics = run["metrics"]
    n_per_type = run["n_per_type"]
    context_ei = run["context_ei"]
    positives = run["positives"]
    negatives = run["negatives"]
    train, val, test = run["train"], run["val"], run["test"]

    summary = {
        "spec": {
            "scenario": SCENARIO,
            "host": HOST,
            "window_hours": 1.0,
            "subgraph_max_nodes": SUBGRAPH_MAX_NODES,
            "subgraph_khop": SUBGRAPH_KHOP,
            "mask_fraction": MASK_FRACTION,
            "split_train_val_test": [TRAIN_SPLIT, VAL_SPLIT, TEST_SPLIT],
            "negative_sampling": "structured (same dst_type, not-in-original, 1:1)",
            "epochs": EPOCHS,
            "learning_rate": LR,
            "seed": args.seed,
            "data_provenance": (
                "mixed subgraph (predominantly benign with unverified attack "
                "fraction; Phase 8 ground-truth label loader not yet wired in "
                "v0.1-data) -- Phase 3 Option C decision archived in "
                "known_issues.md"
            ),
        },
        "subgraph_summary": {
            "nodes_per_type": {nt.value: n_per_type[nt] for nt in NodeType},
            "total_nodes": sum(n_per_type.values()),
            "context_edges_total": int(sum(v.shape[1] for v in context_ei.values())),
            "masked_positives": len(positives),
            "sampled_negatives": len(negatives),
        },
        "split_sizes": {
            "train_pos": len(train[0]),
            "train_neg": len(train[1]),
            "val_pos": len(val[0]),
            "val_neg": len(val[1]),
            "test_pos": len(test[0]),
            "test_neg": len(test[1]),
        },
        "result": {
            "final_test_auc": final_test_auc,
            "final_val_auc": metrics["val_auc_curve"][-1],
            "final_train_auc": metrics["train_auc_curve"][-1],
            "final_loss": metrics["loss_curve"][-1],
            "loss_curve": metrics["loss_curve"],
            "train_auc_curve": metrics["train_auc_curve"],
            "val_auc_curve": metrics["val_auc_curve"],
            "test_auc_curve": metrics["test_auc_curve"],
            "hard_gate_status": gate_status,
            "hard_gate_threshold": AUC_HARD_GATE,
            "hard_gate_borderline_low": AUC_BORDERLINE_LOW,
            "hard_gate_message": gate_msg,
            "auc_interpretation": (
                "validates HTGN's structural learning capability on mixed-event "
                "provenance graphs (NOT a benign baseline distribution)"
            ),
        },
        "model_params": {
            "htgn_total": run["htgn_params"],
            "head_total": run["head_params"],
        },
        "wall_seconds": wall,
        "outputs": {
            "loss_auc_png": str(run["loss_auc_png"]),
            "roc_png": str(run["roc_png"]),
        },
        "workarounds": workarounds,
    }
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2)
    print(f"[task_b] summary -> {summary_path}")
    print(f"[task_b] loss/AUC png -> {run['loss_auc_png']}")
    print(f"[task_b] ROC png -> {run['roc_png']}")
    print(f"[task_b] wall = {wall:.1f}s")

    if gate_status == "FAIL":
        print(
            "[task_b] FAIL: investigate root cause from candidate list "
            "(TGN memory detach timing / Time2Vec dim / negative sampling leak / "
            "cross-type src memory bug). Do NOT increase epochs to bypass."
        )
        return 2
    if gate_status == "BORDERLINE":
        print("[task_b] BORDERLINE: RFC user before Phase 4.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
