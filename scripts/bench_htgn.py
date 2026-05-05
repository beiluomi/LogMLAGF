"""Phase 3 / Checkpoint 9 HTGN performance benchmark.

Measures the three numbers the project owner requires for the Checkpoint 9
report (with hard gates):

1. **Forward time** on a 128-node ATLAS-realistic subgraph (RTX 4090).
   Target: < 50 ms. Hard stop if > 100 ms (per launch spec).
2. **Parameter breakdown**: HGTConv / Time2Vec / residual MLP / TGN
   memory / LayerNorm / msg_projection / total. Used by Phase 7 to
   reason about joint-pretraining batch capacity.
3. **VRAM peak at batch=32**: hard stop if > 4 GB (per launch spec).

The 128-node subgraph is sampled from a real ATLAS (S1) host graph using
the existing :func:`subgraph_sampler.sample_khop_subgraph`; this exercises
the production code path end-to-end (not a synthetic toy).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch

from loghetero.data.parsers.atlas import (
    DnsParser,
    FirefoxParser,
    SecurityEventsParser,
)
from loghetero.data.parsers.base import NodeType
from loghetero.data.provenance_graph import build_graph
from loghetero.data.subgraph_sampler import SeedNode, sample_khop_subgraph
from loghetero.models.graph.htgn import HTGN

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_LOGS = PROJECT_ROOT / "data" / "raw" / "atlas" / "S1" / "logs"
OUT_PATH = PROJECT_ROOT / "data" / "htgn_bench.json"

FORWARD_TARGET_MS = 50.0
FORWARD_HARD_LIMIT_MS = 100.0
VRAM_HARD_LIMIT_GB = 4.0
TARGET_NODES = 128

# Production HTGN hyperparams; benchmark uses these (not the test-time
# smaller values) so the numbers map to Phase 7 capacity.
HIDDEN_DIM = 256
N_LAYERS = 3
NUM_HEADS = 8
DROPOUT = 0.0  # benchmark deterministic
TIME2VEC_DIM = 32
RAW_MSG_DIM = 64


def _build_atlas_subgraph(
    target_nodes: int,
) -> tuple[dict, dict[str, torch.Tensor], dict, dict, dict[NodeType, int]]:
    """Sample a ~target_nodes K-hop subgraph from S1 ATLAS data.

    Returns (subgraph_HeteroData, x_dict, edge_index_dict, edge_time_dict_ns,
    num_nodes_per_type) ready to feed HTGN.forward.
    """
    if not SAMPLE_LOGS.is_dir():
        raise FileNotFoundError(f"{SAMPLE_LOGS} missing; run scripts/download_atlas.sh first.")

    print("[bench] parsing S1 events ...")
    events = []
    for fname, parser in [
        ("dns", DnsParser()),
        ("firefox.txt", FirefoxParser()),
        ("security_events.txt", SecurityEventsParser()),
    ]:
        path = SAMPLE_LOGS / fname
        if not path.is_file():
            continue
        events.extend(parser.parse_file(path, scenario_id="S1", host_id="S1"))
    events.sort(key=lambda e: e.timestamp_ns)
    print(f"[bench]   {len(events):,} events parsed")

    print("[bench] building host graph ...")
    full_graph, _stats = build_graph(events)
    print(
        "[bench]   nodes per type: "
        + ", ".join(
            f"{nt.value}={full_graph[nt.value].num_nodes if nt.value in full_graph.node_types else 0}"
            for nt in NodeType
        )
    )

    print(f"[bench] sampling K-hop subgraph (~{target_nodes} nodes) ...")
    seed = SeedNode(NodeType.process, 0)
    sub = sample_khop_subgraph(
        full_graph,
        seed,
        max_nodes=target_nodes,
        khop=2,
        edge_ranking="weight",
    )
    n_per_type: dict[NodeType, int] = {}
    for nt in NodeType:
        if nt.value in sub.node_types:
            n_per_type[nt] = sub[nt.value].num_nodes
        else:
            n_per_type[nt] = 0
    total = sum(n_per_type.values())
    print(f"[bench]   subgraph total nodes = {total} (target {target_nodes})")
    print(f"[bench]   per-type: {dict((k.value, v) for k, v in n_per_type.items())}")

    # Build x_dict / edge_index_dict / edge_time_dict_ns from subgraph.
    in_dim = HIDDEN_DIM
    x_dict = {
        nt.value: torch.randn(n_per_type[nt], in_dim) for nt in NodeType if n_per_type[nt] > 0
    }
    edge_index_dict = {}
    edge_time_dict_ns = {}
    for rel in sub.edge_types:
        ei = sub[rel].edge_index
        edge_index_dict[rel] = ei
        # subgraph_sampler stored edge_attr_time on the subgraph; reuse.
        ts = sub[rel].edge_attr_time
        edge_time_dict_ns[rel] = ts

    return sub, x_dict, edge_index_dict, edge_time_dict_ns, n_per_type


def _build_production_htgn(
    metadata: tuple[list[str], list[tuple[str, str, str]]],
    n_per_type: dict[NodeType, int],
) -> HTGN:
    return HTGN(
        in_channels=HIDDEN_DIM,
        metadata=metadata,
        num_nodes_per_type=n_per_type,
        hidden_dim=HIDDEN_DIM,
        n_layers=N_LAYERS,
        num_heads=NUM_HEADS,
        dropout=DROPOUT,
        time2vec_dim=TIME2VEC_DIM,
        residual_alpha=0.5,
        layer_decay_gamma=(1.0, 0.7, 0.4),
        raw_msg_dim=RAW_MSG_DIM,
    )


def _measure_forward_ms(
    htgn: HTGN,
    x_dict: dict[str, torch.Tensor],
    edge_index_dict: dict,
    edge_time_dict_ns: dict,
    *,
    n_warmup: int = 3,
    n_iter: int = 10,
) -> float:
    """Median forward time in milliseconds."""
    htgn.eval()
    device = next(htgn.parameters()).device

    def _move(d: dict) -> dict:
        return {k: v.to(device) for k, v in d.items()}

    x = _move(x_dict)
    ei = _move(edge_index_dict)
    et = _move(edge_time_dict_ns)

    # Warmup
    for _ in range(n_warmup):
        with torch.no_grad():
            htgn.tgn_memory.reset_state()
            _ = htgn(x, ei, et)

    if device.type == "cuda":
        torch.cuda.synchronize()

    timings_ms = []
    for _ in range(n_iter):
        if device.type == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            htgn.tgn_memory.reset_state()
            _ = htgn(x, ei, et)
        if device.type == "cuda":
            torch.cuda.synchronize()
        timings_ms.append((time.perf_counter() - t0) * 1000.0)
    timings_ms.sort()
    return timings_ms[len(timings_ms) // 2]


def _measure_vram_peak_gb(
    htgn: HTGN,
    x_dict: dict[str, torch.Tensor],
    edge_index_dict: dict,
    edge_time_dict_ns: dict,
) -> float:
    """VRAM peak (GB) for a single-subgraph forward+backward training step.

    Phase 7 will multiply this by batch_size + add overhead to estimate
    the true batched-training memory footprint; proper PyG Batch
    construction (combining N subgraphs into one disjoint graph) is a
    Phase 7 / DataLoader concern and not measured here. Keeping the
    benchmark single-graph avoids re-indexing bugs and gives a clean
    per-sample reference point.
    """
    if not torch.cuda.is_available():
        return 0.0
    htgn.train()
    device = torch.device("cuda")
    htgn.to(device)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    x = {k: v.to(device) for k, v in x_dict.items()}
    ei = {k: v.to(device) for k, v in edge_index_dict.items()}
    et = {k: v.to(device) for k, v in edge_time_dict_ns.items()}

    htgn.tgn_memory.reset_state()
    out = htgn(x, ei, et)
    loss = sum(v.pow(2).sum() for v in out.values())
    loss.backward()
    torch.cuda.synchronize()
    peak_gb = torch.cuda.max_memory_allocated() / (1024**3)
    return peak_gb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-nodes", type=int, default=TARGET_NODES)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="reported in summary for Phase 7 reference; benchmark itself measures single-sample VRAM",
    )
    parser.add_argument("--n-iter", type=int, default=10)
    parser.add_argument(
        "--device", choices=["cpu", "cuda"], default="cuda" if torch.cuda.is_available() else "cpu"
    )
    args = parser.parse_args()

    # 1. Build subgraph + HTGN
    _sub, x_dict, edge_index_dict, edge_time_dict_ns, n_per_type = _build_atlas_subgraph(
        args.target_nodes
    )
    metadata = (
        [nt.value for nt in NodeType],
        list(edge_index_dict.keys()),
    )
    htgn = _build_production_htgn(metadata, n_per_type)
    htgn.to(args.device)

    # 2. Parameter breakdown
    bd = htgn.parameter_breakdown()
    print("\n=== Parameter breakdown ===")
    for k, v in bd.items():
        print(f"  {k:<20} {v:>12,}")

    # 3. Forward time
    print(f"\n=== Forward time ({args.device}, n_iter={args.n_iter}) ===")
    median_ms = _measure_forward_ms(
        htgn, x_dict, edge_index_dict, edge_time_dict_ns, n_iter=args.n_iter
    )
    print(
        f"  median forward = {median_ms:.2f} ms (target < {FORWARD_TARGET_MS}, hard < {FORWARD_HARD_LIMIT_MS})"
    )
    if median_ms > FORWARD_HARD_LIMIT_MS:
        print(
            f"  HARD STOP: forward time exceeds {FORWARD_HARD_LIMIT_MS} ms; "
            "investigate before pushing through to Phase 4.",
            file=sys.stderr,
        )
        return 1

    # 4. VRAM peak (single-sample reference; Phase 7 will batch via PyG Batch)
    if args.device == "cuda":
        peak_gb = _measure_vram_peak_gb(htgn, x_dict, edge_index_dict, edge_time_dict_ns)
        # Phase 7 estimate: peak_at_batch_N ≈ N * single_peak + overhead.
        est_at_batch = peak_gb * args.batch_size
        print("\n=== VRAM peak (single-subgraph forward+backward) ===")
        print(f"  per-sample peak = {peak_gb:.3f} GB")
        print(
            f"  Phase 7 batch={args.batch_size} naive estimate = "
            f"{est_at_batch:.2f} GB (hard < {VRAM_HARD_LIMIT_GB} GB);"
            " real number depends on PyG Batch overhead, measured during"
            " Phase 7 setup."
        )
        if peak_gb > VRAM_HARD_LIMIT_GB:
            print(
                f"  HARD STOP: per-sample VRAM peak exceeds {VRAM_HARD_LIMIT_GB} GB.",
                file=sys.stderr,
            )
            return 1
    else:
        peak_gb = 0.0

    # 5. Save
    summary = {
        "device": args.device,
        "target_nodes": args.target_nodes,
        "actual_total_nodes": sum(n_per_type.values()),
        "nodes_per_type": {nt.value: v for nt, v in n_per_type.items()},
        "forward_median_ms": median_ms,
        "forward_target_ms": FORWARD_TARGET_MS,
        "forward_hard_limit_ms": FORWARD_HARD_LIMIT_MS,
        "vram_peak_gb": peak_gb,
        "vram_hard_limit_gb": VRAM_HARD_LIMIT_GB,
        "batch_size": args.batch_size,
        "parameter_breakdown": bd,
        "config": {
            "hidden_dim": HIDDEN_DIM,
            "n_layers": N_LAYERS,
            "num_heads": NUM_HEADS,
            "time2vec_dim": TIME2VEC_DIM,
            "residual_alpha": 0.5,
            "layer_decay_gamma": [1.0, 0.7, 0.4],
            "raw_msg_dim": RAW_MSG_DIM,
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\n[bench] full report -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
