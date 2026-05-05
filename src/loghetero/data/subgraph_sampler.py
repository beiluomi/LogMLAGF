"""K-hop heterogeneous subgraph sampler (Phase 1.5 sub-task 1.5/1.6).

For each "target event" the data pipeline emits the tuple
``(text_input, hetero_subgraph_with_timestamps)`` -- the local subgraph the
HTGN/cross-attention stack will consume. This module implements the
heterogeneous K-hop sampler with the edge-ranking policy that controls which
candidate edges to drop when the candidate frontier exceeds the node budget.

All knobs are Hydra-driven (``configs/data/atlas.yaml::subgraph``):

* ``max_nodes``      total node budget across all 5 NodeTypes.
* ``khop``           BFS depth in edge traversals.
* ``edge_ranking``   ``"weight"`` (frequency of the same triple),
                     ``"time_recency"`` (closeness to the target ts), or
                     ``"joint"`` (multiplicative product).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

import torch
from torch_geometric.data import HeteroData

from loghetero.data.parsers.base import NodeType


@dataclass(frozen=True, slots=True)
class SeedNode:
    """The target the subgraph sampler grows around."""

    node_type: NodeType
    node_idx: int


def sample_khop_subgraph(
    data: HeteroData,
    seed: SeedNode,
    *,
    max_nodes: int,
    khop: int,
    edge_ranking: str = "joint",
    target_timestamp_ns: int | None = None,
) -> HeteroData:
    """Return a K-hop heterogeneous subgraph centred on ``seed``.

    Algorithm:

    1. BFS from ``seed`` for at most ``khop`` edge-traversal layers, recording
       the candidate edges and the frontier of newly-reached nodes per layer.
    2. Score every candidate edge with :func:`_score_edge` per ``edge_ranking``.
    3. Greedy include nodes (and their edges) in score order until the total
       node budget ``max_nodes`` is exhausted.
    4. Re-pack as a fresh :class:`HeteroData` whose node indices are remapped
       to the kept subset; node ``isolated`` flags are recomputed for the
       subgraph (decision 8: still kept but the mask reflects sub-graph degree).

    Args:
        data: a HeteroData built by ``provenance_graph.build_graph``.
        seed: the seed node (its node_type must exist in ``data``).
        max_nodes: hard upper bound on total nodes in the output graph.
        khop: BFS depth (0 means "just the seed", 1 = seed + direct
            neighbours, etc.).
        edge_ranking: scoring policy.
        target_timestamp_ns: required when ``edge_ranking != "weight"``.

    Returns:
        A new :class:`HeteroData` with the same edge_attr_time semantics.
    """
    if khop < 0:
        raise ValueError(f"khop must be non-negative, got {khop}")
    if max_nodes < 1:
        raise ValueError(f"max_nodes must be >= 1, got {max_nodes}")
    if edge_ranking not in {"weight", "time_recency", "joint"}:
        raise ValueError(f"unknown edge_ranking: {edge_ranking!r}")

    seed_key = (seed.node_type.value, seed.node_idx)
    if seed.node_type.value not in data.node_types:
        raise ValueError(f"seed node type {seed.node_type} not present in graph")
    if seed.node_idx >= data[seed.node_type.value].num_nodes:
        raise ValueError(
            f"seed.node_idx={seed.node_idx} out of range for "
            f"{seed.node_type} num_nodes={data[seed.node_type.value].num_nodes}"
        )
    if edge_ranking != "weight" and target_timestamp_ns is None:
        raise ValueError(
            f"edge_ranking={edge_ranking!r} requires target_timestamp_ns"
        )

    # ------------------------------------------------------------------
    # 1. BFS frontier; record candidate edges per hop.
    # ------------------------------------------------------------------
    visited: set[tuple[str, int]] = {seed_key}
    frontier: set[tuple[str, int]] = {seed_key}
    candidate_edges: list[
        tuple[tuple[str, str, str], int, int, int, int]
    ] = []  # (edge_type_triple, edge_idx, src_idx, dst_idx, ts_ns)

    for _ in range(khop):
        next_frontier: set[tuple[str, int]] = set()
        for rel in data.edge_types:
            src_type, _, dst_type = rel
            ei = data[rel].edge_index
            ts = data[rel].edge_attr_time
            for e_i in range(ei.shape[1]):
                s_idx = int(ei[0, e_i].item())
                d_idx = int(ei[1, e_i].item())
                s_key = (src_type, s_idx)
                d_key = (dst_type, d_idx)
                # Edge is a candidate if either endpoint is currently in frontier.
                if s_key in frontier or d_key in frontier:
                    candidate_edges.append((rel, e_i, s_idx, d_idx, int(ts[e_i].item())))
                    if s_key not in visited:
                        next_frontier.add(s_key)
                    if d_key not in visited:
                        next_frontier.add(d_key)
        visited |= next_frontier
        frontier = next_frontier
        if not frontier:
            break

    # ------------------------------------------------------------------
    # 2. Edge scoring.
    # ------------------------------------------------------------------
    triple_freq = _count_triple_freq(candidate_edges)
    scored: list[tuple[float, tuple[str, str, str], int, int, int, int]] = []
    for (rel, e_i, s_idx, d_idx, ts_ns) in candidate_edges:
        score = _score_edge(
            triple_count=triple_freq[(rel, s_idx, d_idx)],
            ts_ns=ts_ns,
            target_ts_ns=target_timestamp_ns,
            policy=edge_ranking,
        )
        scored.append((score, rel, e_i, s_idx, d_idx, ts_ns))
    scored.sort(key=lambda t: -t[0])  # high score first

    # ------------------------------------------------------------------
    # 3. Greedy inclusion under the node budget.
    # ------------------------------------------------------------------
    kept_nodes: dict[str, set[int]] = defaultdict(set)
    kept_nodes[seed.node_type.value].add(seed.node_idx)

    def _node_count() -> int:
        return sum(len(v) for v in kept_nodes.values())

    kept_edges: dict[tuple[str, str, str], list[tuple[int, int, int]]] = defaultdict(list)
    seen_edges: set[tuple[tuple[str, str, str], int]] = set()
    for _, rel, e_i, s_idx, d_idx, ts_ns in scored:
        src_type, _, dst_type = rel
        # Compute incremental node cost
        new_cost = (
            int(s_idx not in kept_nodes[src_type])
            + int(d_idx not in kept_nodes[dst_type])
        )
        if _node_count() + new_cost > max_nodes:
            continue
        if (rel, e_i) in seen_edges:
            continue
        kept_nodes[src_type].add(s_idx)
        kept_nodes[dst_type].add(d_idx)
        kept_edges[rel].append((s_idx, d_idx, ts_ns))
        seen_edges.add((rel, e_i))

    # ------------------------------------------------------------------
    # 4. Re-pack as HeteroData with remapped indices.
    # ------------------------------------------------------------------
    sub = HeteroData()
    remap: dict[str, dict[int, int]] = {}
    for ntype_str, idx_set in kept_nodes.items():
        ordered = sorted(idx_set)
        remap[ntype_str] = {old: new for new, old in enumerate(ordered)}
        n = len(ordered)
        # Preserve node_id strings from the parent graph if present.
        original_ids = data[ntype_str].node_id if "node_id" in data[ntype_str] else None
        sub[ntype_str].num_nodes = n
        if original_ids is not None:
            sub[ntype_str].node_id = [original_ids[old] for old in ordered]

    # Place edges
    deg: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for rel, edge_list in kept_edges.items():
        src_type, _, dst_type = rel
        if not edge_list:
            continue
        s_arr = [remap[src_type][s] for s, _, _ in edge_list]
        d_arr = [remap[dst_type][d] for _, d, _ in edge_list]
        ts_arr = [t for _, _, t in edge_list]
        sub[rel].edge_index = torch.tensor([s_arr, d_arr], dtype=torch.long)
        sub[rel].edge_attr_time = torch.tensor(ts_arr, dtype=torch.long)
        for src_idx in s_arr:
            deg[src_type][src_idx] += 1
        for dst_idx in d_arr:
            deg[dst_type][dst_idx] += 1

    # Decision 8: re-emit the isolated mask for the subgraph (per-subgraph
    # degree, not parent-graph degree, so isolated-in-sub != isolated-in-full).
    for ntype_str in kept_nodes:
        n = sub[ntype_str].num_nodes
        deg_tensor = torch.zeros(n, dtype=torch.long)
        for new_idx, count in deg[ntype_str].items():
            deg_tensor[new_idx] = count
        sub[ntype_str].degree = deg_tensor
        sub[ntype_str].isolated = deg_tensor == 0

    return sub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_triple_freq(
    candidate_edges: list[tuple[tuple[str, str, str], int, int, int, int]],
) -> dict[tuple[tuple[str, str, str], int, int], int]:
    """Per-(rel, src_idx, dst_idx) edge multiplicity used by weight scoring."""
    out: dict[tuple[tuple[str, str, str], int, int], int] = {}
    for rel, _e_i, s_idx, d_idx, _ts in candidate_edges:
        key = (rel, s_idx, d_idx)
        out[key] = out.get(key, 0) + 1
    return out


def _score_edge(
    *,
    triple_count: int,
    ts_ns: int,
    target_ts_ns: int | None,
    policy: str,
) -> float:
    """Edge score: higher = more likely kept under the node budget."""
    if policy == "weight":
        return float(triple_count)
    # Time recency: gaussian-ish bump centred on target_ts.
    assert target_ts_ns is not None
    delta_h = abs(ts_ns - target_ts_ns) / (3600 * 1_000_000_000)
    recency = 1.0 / (1.0 + delta_h)
    if policy == "time_recency":
        return recency
    # joint
    return float(triple_count) * recency
