"""Build PyG :class:`HeteroData` provenance graphs from :class:`Event` lists.

Per ``docs/design_decisions.md``:

* **Decision 5**: 5-type heterogeneous schema (process / file / socket / network / user).
* **Decision 8**: isolated nodes (degree == 0) are KEPT, marked via the
  ``isolated`` bool tensor on each node store. Downstream modules decide what
  to do with them; the data pipeline never silently drops a node.

Edge stores are keyed by the canonical ``(src_type, edge_type, dst_type)``
triples in :data:`ALLOWED_EDGE_TRIPLES` (Checkpoint 3 lock). Multiple events
with the same ``(subject, operation, obj)`` over time produce **multiple
parallel edges** with distinct timestamps -- the graph is a multigraph in
PyG terms (``edge_attr_time`` carries the per-edge timestamp).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torch_geometric.data import HeteroData

from loghetero.data.parsers.base import (
    ALLOWED_EDGE_TRIPLES,
    EdgeType,
    Event,
    NodeType,
)


@dataclass
class GraphBuildStats:
    """Per-(NodeType / edge_triple) stats produced alongside the graph."""

    nodes_per_type: dict[str, int] = field(default_factory=dict)
    isolated_per_type: dict[str, int] = field(default_factory=dict)
    edges_per_triple: dict[tuple[str, str, str], int] = field(default_factory=dict)
    skipped_unknown_op: int = 0
    skipped_disallowed_triple: int = 0

    def isolated_pct(self, ntype: str) -> float:
        n = self.nodes_per_type.get(ntype, 0)
        if n == 0:
            return 0.0
        return self.isolated_per_type.get(ntype, 0) / n


def build_graph(events: Iterable[Event]) -> tuple["HeteroData", GraphBuildStats]:
    """Build a :class:`HeteroData` from ``events`` and return it with stats.

    Args:
        events: Stream of parser-emitted :class:`Event` records. Order does
            not matter (events are bucketed by node id internally), but
            timestamps are preserved on the edges.

    Returns:
        ``(HeteroData, GraphBuildStats)``. ``HeteroData`` has, for each
        :class:`NodeType` that appears in ``events``:

        * ``data[ntype].num_nodes`` int
        * ``data[ntype].node_id`` list[str] (preserves the human-readable
          identifier for every node, used by Phase 4 attention visualisation
          and Phase 8 case studies)
        * ``data[ntype].degree`` long tensor of shape ``(num_nodes,)``
        * ``data[ntype].isolated`` bool tensor of shape ``(num_nodes,)`` --
          decision 8: True iff degree==0; downstream modules may attach a
          learnable isolated-node bias.

        And for each ``(src_type, edge_type, dst_type)`` triple that has at
        least one edge:

        * ``data[(src_type, edge_type, dst_type)].edge_index`` long
          ``(2, num_edges)``
        * ``data[(src_type, edge_type, dst_type)].edge_attr_time`` long
          ``(num_edges,)`` UTC nanoseconds

    Raises:
        ValueError: if ``events`` is empty (a graph with no nodes has no
            meaningful semantics; callers should handle empty windows
            explicitly rather than silently dropping them).
    """
    import torch
    from torch_geometric.data import HeteroData

    events = list(events)
    if not events:
        raise ValueError(
            "build_graph requires at least one Event; an empty event stream "
            "should be handled explicitly by the caller (e.g. skip the time "
            "window) rather than silently producing an empty graph."
        )

    # Pass 1: intern node identifiers per type.
    node_id_by_type: dict[NodeType, dict[str, int]] = {nt: {} for nt in NodeType}

    def _intern(name: str, ntype: NodeType) -> int:
        d = node_id_by_type[ntype]
        if name not in d:
            d[name] = len(d)
        return d[name]

    # Pass 2: bucket edges by their canonical triple, accumulate degrees.
    edges_by_triple: dict[
        tuple[NodeType, EdgeType, NodeType], list[tuple[int, int, int]]
    ] = defaultdict(list)
    degree_by_type: dict[NodeType, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    stats = GraphBuildStats()

    for ev in events:
        # Resolve operation -> EdgeType. Parsers should always emit canonical
        # values, but defensively coerce so unknown strings degrade to UNKNOWN.
        try:
            edge_type = EdgeType(ev.operation) if not isinstance(ev.operation, EdgeType) else ev.operation
        except ValueError:
            edge_type = EdgeType.UNKNOWN
        if edge_type is EdgeType.UNKNOWN:
            stats.skipped_unknown_op += 1
            continue
        triple = (ev.subject_type, edge_type, ev.obj_type)
        if triple not in ALLOWED_EDGE_TRIPLES:
            stats.skipped_disallowed_triple += 1
            continue
        src_idx = _intern(ev.subject, ev.subject_type)
        dst_idx = _intern(ev.obj, ev.obj_type)
        edges_by_triple[triple].append((src_idx, dst_idx, ev.timestamp_ns))
        degree_by_type[ev.subject_type][src_idx] += 1
        degree_by_type[ev.obj_type][dst_idx] += 1

    data = HeteroData()
    for ntype in NodeType:
        name_to_idx = node_id_by_type[ntype]
        n_nodes = len(name_to_idx)
        if n_nodes == 0:
            continue
        # node_id list ordered by index
        ids: list[str] = [""] * n_nodes
        for name, idx in name_to_idx.items():
            ids[idx] = name
        deg = torch.zeros(n_nodes, dtype=torch.long)
        for idx, d in degree_by_type[ntype].items():
            deg[idx] = d
        data[ntype.value].num_nodes = n_nodes
        data[ntype.value].node_id = ids
        data[ntype.value].degree = deg
        data[ntype.value].isolated = deg == 0
        stats.nodes_per_type[ntype.value] = n_nodes
        stats.isolated_per_type[ntype.value] = int((deg == 0).sum().item())

    for (src_t, edge_t, dst_t), triple_edges in edges_by_triple.items():
        rel_key = (src_t.value, edge_t.value, dst_t.value)
        edge_index = torch.tensor(
            [
                [s for s, _, _ in triple_edges],
                [d for _, d, _ in triple_edges],
            ],
            dtype=torch.long,
        )
        ts = torch.tensor([t for _, _, t in triple_edges], dtype=torch.long)
        data[rel_key].edge_index = edge_index
        data[rel_key].edge_attr_time = ts
        stats.edges_per_triple[rel_key] = edge_index.shape[1]

    return data, stats
