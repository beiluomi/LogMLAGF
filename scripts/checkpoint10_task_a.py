"""Phase 3 / Checkpoint 10 Task A — HTGN sanity-check node classification.

Task A is a sanity check (NOT the Phase 3 hard gate). Goal: verify the
3-layer HTGN encoder (HGT + Option-C temporal residual + HeteroTGNMemory)
can learn a simple structural signal end-to-end on a tiny synthetic
heterogeneous graph that mirrors the production 5-node-type / multi-edge
schema.

Toy graph spec
==============
* 5 production node types (process / file / socket / network / user) with
  ~50 nodes total: 15 process, 15 file, 8 socket, 7 network, 5 user.
* 7 edge types (all valid EdgeType enum values from
  ``src/loghetero/data/parsers/base.py``):
    1. (process, FILE_READ, file)         -- file-read access pattern
    2. (process, FILE_WRITE, file)        -- file-write access pattern
    3. (process, NET_CONNECT, network)    -- outbound network connect
    4. (process, NET_SEND_SOCKET, socket) -- IPC send to socket
    5. (process, NET_RECV_SOCKET, socket) -- IPC recv from socket
    6. (process, PROCESS_FORK, process)   -- process forking another
    7. (user,    USER_LOGON, process)     -- user logging on a process
* ~3 * num_nodes = ~150 edges total, distributed across the 7 types.
* Random initial node features per type (dim 64), fixed seed.
* Random ns timestamps within a 1-hour window, monotone-sorted globally
  before being split per relation.

Label rule (process nodes only)
================================
For each process node ``v``, label = 1 if ``v`` has at least 2 INCOMING
USER_LOGON edges from user nodes (i.e. count of edges in
``(user, USER_LOGON, process)`` with ``dst == v`` is >= 2); else 0.

We use an INCOMING-edge rule rather than an outgoing-edge rule because
PyG ``HGTConv`` propagates messages from src to dst -- so a node's
representation is naturally updated by its INCOMING edges, not its
outgoing ones. Using outgoing-FILE_WRITE counts would require either
manually reversing edges or relying on multi-hop indirection (which
this 5-node-types-with-no-file-to-process-edge schema does not provide
through any single edge triple). The launch spec explicitly authorises
choosing the label rule per "Anything HTGN can plausibly learn from
neighborhood structure"; we select an incoming-edge structural property
of degree-2 to keep the task non-trivial yet directly aggregable.

Hard targets (Task A pass criteria)
====================================
* Final training loss < 0.05 at epoch 50
* Final training accuracy >= 0.95
If either misses, we DO NOT bypass by tweaking epochs / label rule /
weakening the task — we stop, document, return.
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
from torch import nn

from loghetero.data.parsers.base import EdgeType, NodeType
from loghetero.models.graph.htgn import HTGN

# --- Spec constants (from launch spec; do NOT edit) -------------------------

NODE_COUNTS: dict[NodeType, int] = {
    NodeType.process: 15,
    NodeType.file: 15,
    NodeType.socket: 8,
    NodeType.network: 7,
    NodeType.user: 5,
}
IN_DIM = 64
EDGE_TRIPLES: list[tuple[str, str, str]] = [
    (NodeType.process.value, EdgeType.FILE_READ.value, NodeType.file.value),
    (NodeType.process.value, EdgeType.FILE_WRITE.value, NodeType.file.value),
    (NodeType.process.value, EdgeType.NET_CONNECT.value, NodeType.network.value),
    (NodeType.process.value, EdgeType.NET_SEND_SOCKET.value, NodeType.socket.value),
    (NodeType.process.value, EdgeType.NET_RECV_SOCKET.value, NodeType.socket.value),
    (NodeType.process.value, EdgeType.PROCESS_FORK.value, NodeType.process.value),
    (NodeType.user.value, EdgeType.USER_LOGON.value, NodeType.process.value),
]

# Production HTGN hyperparams from configs/model/graph/htgn.yaml.
HIDDEN_DIM = 256
N_LAYERS = 3
NUM_HEADS = 8
DROPOUT = 0.1
TIME2VEC_DIM = 32
RESIDUAL_ALPHA = 0.5
LAYER_DECAY_GAMMA: tuple[float, ...] = (1.0, 0.7, 0.4)
RAW_MSG_DIM = 64

# Hard gates.
LOSS_TARGET = 0.05
ACC_TARGET = 0.95

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "data"
DEFAULT_SUMMARY = DEFAULT_OUT_DIR / "checkpoint10_taskA_summary.json"
DEFAULT_PNG = DEFAULT_OUT_DIR / "processed" / "checkpoint10_taskA_loss.png"


def _set_seeds(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def _build_toy_graph(
    seed: int,
) -> tuple[
    dict[str, torch.Tensor],
    dict[tuple[str, str, str], torch.Tensor],
    dict[tuple[str, str, str], torch.Tensor],
]:
    """Build the toy heterogeneous graph per the launch spec.

    Edge counts per relation are fixed to sum to ~3 * num_nodes = ~150,
    deliberately weighting FILE_WRITE so the binary label has both
    classes present (not all-0 / all-1).
    """
    g = torch.Generator().manual_seed(seed)

    # --- Per-type node features ------------------------------------------
    x_dict: dict[str, torch.Tensor] = {}
    for nt in NodeType:
        x_dict[nt.value] = torch.randn(NODE_COUNTS[nt], IN_DIM, generator=g)

    # --- Edge counts per relation (sum ~150) -----------------------------
    # Bias FILE_WRITE high enough to ensure both labels exist.
    edges_per_relation = {
        EDGE_TRIPLES[0]: 25,  # FILE_READ
        EDGE_TRIPLES[1]: 35,  # FILE_WRITE  (label-bearing relation, weighted heavier)
        EDGE_TRIPLES[2]: 18,  # NET_CONNECT
        EDGE_TRIPLES[3]: 18,  # NET_SEND_SOCKET
        EDGE_TRIPLES[4]: 18,  # NET_RECV_SOCKET
        EDGE_TRIPLES[5]: 18,  # PROCESS_FORK
        EDGE_TRIPLES[6]: 18,  # USER_LOGON
    }
    total_edges = sum(edges_per_relation.values())
    assert total_edges == 150, f"edge count drift: {total_edges}"

    # --- Build a global event timeline so timestamps are monotone -------
    # 1-hour window in ns.
    base_ns = 1_541_213_032_292_203_000  # 2018-11-03 02:43:52.292203 UTC
    one_hour_ns = 3_600 * 1_000_000_000
    # Sample `total_edges` ns offsets uniformly in [0, one_hour_ns), sorted.
    # (randperm over the full hour-of-ns range would allocate ~29 TB; use
    # float sampling + cast to int64.)
    offsets_float = torch.rand(total_edges, generator=g) * float(one_hour_ns)
    offsets, _ = torch.sort(offsets_float.to(torch.int64))
    # Distribute timestamps to each relation in declaration order (round-robin
    # by simply slicing — order doesn't affect monotonicity per relation as
    # long as the global slice stays sorted, which it is).

    edge_index_dict: dict[tuple[str, str, str], torch.Tensor] = {}
    edge_time_dict_ns: dict[tuple[str, str, str], torch.Tensor] = {}
    cursor = 0
    for triple, n_edges in edges_per_relation.items():
        src_t, _e_t, dst_t = triple
        n_src = NODE_COUNTS[NodeType(src_t)]
        n_dst = NODE_COUNTS[NodeType(dst_t)]
        src_idx = torch.randint(0, n_src, (n_edges,), generator=g, dtype=torch.long)
        dst_idx = torch.randint(0, n_dst, (n_edges,), generator=g, dtype=torch.long)
        edge_index_dict[triple] = torch.stack([src_idx, dst_idx], dim=0)
        # Pull this relation's timestamp slice from the sorted global pool.
        rel_offsets = offsets[cursor : cursor + n_edges]
        edge_time_dict_ns[triple] = (rel_offsets + base_ns).to(torch.int64)
        cursor += n_edges
    return x_dict, edge_index_dict, edge_time_dict_ns


def _compute_process_labels(
    edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
) -> torch.Tensor:
    """Label each process node 1 iff it has >= 2 incoming USER_LOGON edges.

    Counts edges in (user, USER_LOGON, process) where dst == process_idx.
    PyG HGTConv flows messages src->dst, so this incoming-edge property
    is directly aggregable at the process node.
    """
    logon_triple = (
        NodeType.user.value,
        EdgeType.USER_LOGON.value,
        NodeType.process.value,
    )
    dst = edge_index_dict[logon_triple][1]  # (E,) dst process indices
    n_proc = NODE_COUNTS[NodeType.process]
    counts = torch.bincount(dst, minlength=n_proc)
    return (counts >= 2).long()


def train(
    seed: int,
    epochs: int,
    output_dir: Path,
) -> dict:
    _set_seeds(seed)

    metadata: tuple[list[str], list[tuple[str, str, str]]] = (
        [nt.value for nt in NodeType],
        EDGE_TRIPLES,
    )
    x_dict, edge_index_dict, edge_time_dict_ns = _build_toy_graph(seed)
    labels = _compute_process_labels(edge_index_dict)
    n_pos = int(labels.sum().item())
    n_neg = int((labels == 0).sum().item())
    print(
        f"[task-a] process labels: pos={n_pos} neg={n_neg} "
        f"(label rule: >=2 incoming USER_LOGON edges)"
    )
    if n_pos == 0 or n_neg == 0:
        raise RuntimeError(
            f"Degenerate label distribution (pos={n_pos}, neg={n_neg}); "
            "structural label rule produced single class. Stopping per spec."
        )

    # PyG TGNMemory's internal `_assoc` buffer is sized to the dst type's
    # node count, BUT in HTGN.forward both src and dst tensors are indexed
    # into that single buffer (PyG TGN was authored for homogeneous graphs).
    # For (process, NET_*_SOCKET, socket) edges, src=process_idx can exceed
    # socket count; we therefore size each memory-bearing type's `num_nodes`
    # to the max node count across types so PyG's `_assoc[n_id]` does not
    # OOB. Real-data graphs (Phase 7) sidestep this when socket count >=
    # process count or via batch-level renumbering; for the toy graph we
    # take the simpler upper-bound approach.
    max_count = max(NODE_COUNTS.values())
    htgn_node_counts: dict[NodeType, int] = {
        nt: (max_count if nt in (NodeType.process, NodeType.socket) else NODE_COUNTS[nt])
        for nt in NodeType
    }

    htgn = HTGN(
        in_channels=IN_DIM,
        metadata=metadata,
        num_nodes_per_type=htgn_node_counts,
        hidden_dim=HIDDEN_DIM,
        n_layers=N_LAYERS,
        num_heads=NUM_HEADS,
        dropout=DROPOUT,
        time2vec_dim=TIME2VEC_DIM,
        residual_alpha=RESIDUAL_ALPHA,
        layer_decay_gamma=LAYER_DECAY_GAMMA,
        memory_node_types=(NodeType.process, NodeType.socket),
        raw_msg_dim=RAW_MSG_DIM,
    )
    classifier = nn.Linear(HIDDEN_DIM, 2)

    params = list(htgn.parameters()) + list(classifier.parameters())
    optimizer = torch.optim.Adam(params, lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    breakdown = htgn.parameter_breakdown()
    total_params = breakdown["total"] + sum(p.numel() for p in classifier.parameters())
    print(
        f"[task-a] HTGN params: {breakdown['total']:,} "
        f"(+ classifier {sum(p.numel() for p in classifier.parameters()):,}) "
        f"= {total_params:,} total trainable"
    )

    loss_curve: list[float] = []
    acc_curve: list[float] = []

    htgn.train()
    classifier.train()

    t_start = time.perf_counter()
    for epoch in range(epochs):
        # Reset TGN memory at epoch boundary per yaml spec
        # (tgn_memory.reset_on_epoch_boundary: true).
        htgn.tgn_memory.reset_state()

        optimizer.zero_grad()
        out = htgn(x_dict, edge_index_dict, edge_time_dict_ns)
        proc_repr = out[NodeType.process.value]  # (15, hidden_dim)
        logits = classifier(proc_repr)  # (15, 2)
        loss = loss_fn(logits, labels)

        loss.backward()
        optimizer.step()

        # Detach TGN memory between epochs (avoid graph carry-over).
        htgn.tgn_memory.detach()

        with torch.no_grad():
            preds = logits.argmax(dim=-1)
            acc = (preds == labels).float().mean().item()
        loss_val = float(loss.item())
        loss_curve.append(loss_val)
        acc_curve.append(acc)
        print(f"[task-a] epoch {epoch + 1:02d}/{epochs} " f"loss={loss_val:.6f} acc={acc:.4f}")

    wall_seconds = time.perf_counter() - t_start

    final_loss = loss_curve[-1]
    final_acc = acc_curve[-1]
    passed_loss = final_loss < LOSS_TARGET
    passed_acc = final_acc >= ACC_TARGET

    print()
    print(f"[task-a] DONE: final loss={final_loss:.6f} " f"(<{LOSS_TARGET}? {passed_loss})")
    print(f"[task-a] DONE: final acc={final_acc:.4f} " f"(>={ACC_TARGET}? {passed_acc})")
    print(f"[task-a] wall_seconds={wall_seconds:.2f}")

    # --- Visualization ---------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / "processed" / "checkpoint10_taskA_loss.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(range(1, epochs + 1), loss_curve, marker="o", markersize=3, linewidth=1.4)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Cross-entropy loss")
    ax.set_yscale("log")
    ax.set_title("Checkpoint 10 Task A - Toy Heterogeneous Node Classification")
    ax.axhline(
        LOSS_TARGET, color="red", linestyle="--", linewidth=0.8, label=f"target {LOSS_TARGET}"
    )
    ax.grid(True, alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    print(f"[task-a] loss curve png -> {png_path}")

    # --- Reproducibility summary JSON ------------------------------------
    summary_path = output_dir / "checkpoint10_taskA_summary.json"
    summary = {
        "spec": {
            "node_counts_per_type": {nt.value: NODE_COUNTS[nt] for nt in NodeType},
            "edge_types_used": [list(t) for t in EDGE_TRIPLES],
            "label_rule": (
                "process node label = 1 iff incoming USER_LOGON edge count >= 2; "
                "else 0 (15 process nodes labeled total)"
            ),
            "epochs": epochs,
            "seed": seed,
        },
        "result": {
            "final_loss": final_loss,
            "final_train_accuracy": final_acc,
            "loss_curve": [float(v) for v in loss_curve],
            "accuracy_curve": [float(v) for v in acc_curve],
            "passed_loss_target": passed_loss,
            "passed_acc_target": passed_acc,
        },
        "model_params": int(breakdown["total"]),
        "wall_seconds": float(wall_seconds),
    }
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2)
    print(f"[task-a] summary json -> {summary_path}")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Checkpoint 10 Task A driver")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Root output directory (defaults to <repo>/data)",
    )
    args = parser.parse_args()

    summary = train(args.seed, args.epochs, args.output_dir)

    passed_both = summary["result"]["passed_loss_target"] and summary["result"]["passed_acc_target"]
    if not passed_both:
        print("[task-a] HARD-GATE FAIL: did NOT meet both targets at 50 epochs.")
        return 1
    print("[task-a] HARD-GATE PASS: both loss and accuracy targets met.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
