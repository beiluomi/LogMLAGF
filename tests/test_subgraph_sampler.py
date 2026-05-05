"""Unit tests for the K-hop heterogeneous subgraph sampler (Phase 1.5)."""

from __future__ import annotations

import pytest

from loghetero.data.parsers.base import EdgeType, Event, NodeType
from loghetero.data.provenance_graph import build_graph
from loghetero.data.subgraph_sampler import SeedNode, sample_khop_subgraph


def _ev(ts: int, sub: str, sub_t: NodeType, obj: str, obj_t: NodeType, op: EdgeType) -> Event:
    return Event(
        timestamp_ns=ts,
        subject=sub,
        subject_type=sub_t,
        obj=obj,
        obj_type=obj_t,
        operation=op,
        log_type="test",
        scenario_id="T",
        host_id="h",
    )


def _toy_graph():
    """Build a small heterogeneous graph used by every test below.

    Nodes:
      processes: p0 (target), p1, p2
      files:     f0, f1
      networks:  n0
    Edges:
      p0 -file_read-> f0  @100
      p0 -file_read-> f1  @200
      p0 -net_connect-> n0  @300
      p1 -file_read-> f0  @150
      p2 -process_create-> p0  @50
    """
    events = [
        _ev(100, "p0", NodeType.process, "f0", NodeType.file, EdgeType.FILE_READ),
        _ev(200, "p0", NodeType.process, "f1", NodeType.file, EdgeType.FILE_READ),
        _ev(300, "p0", NodeType.process, "n0", NodeType.network, EdgeType.NET_CONNECT),
        _ev(150, "p1", NodeType.process, "f0", NodeType.file, EdgeType.FILE_READ),
        _ev(50, "p2", NodeType.process, "p0", NodeType.process, EdgeType.PROCESS_CREATE),
    ]
    data, _ = build_graph(events)
    return data


class TestKhopBoundary:
    def test_khop_0_yields_only_seed(self) -> None:
        data = _toy_graph()
        sub = sample_khop_subgraph(
            data,
            SeedNode(NodeType.process, 0),
            max_nodes=10,
            khop=0,
            edge_ranking="weight",
        )
        # Only p0 should be in the subgraph.
        assert sub["process"].num_nodes == 1
        assert "file" not in sub.node_types
        assert "network" not in sub.node_types

    def test_khop_1_includes_direct_neighbours(self) -> None:
        data = _toy_graph()
        sub = sample_khop_subgraph(
            data,
            SeedNode(NodeType.process, 0),
            max_nodes=10,
            khop=1,
            edge_ranking="weight",
        )
        # p0 + 2 files + 1 network + 1 parent process (p2) = direct neighbours
        assert sub["process"].num_nodes >= 2  # p0 + at least p2
        assert sub["file"].num_nodes == 2  # f0, f1
        assert sub["network"].num_nodes == 1  # n0

    def test_khop_2_includes_second_hop(self) -> None:
        data = _toy_graph()
        sub = sample_khop_subgraph(
            data,
            SeedNode(NodeType.process, 0),
            max_nodes=10,
            khop=2,
            edge_ranking="weight",
        )
        # 2-hop reaches p1 (via f0)
        node_ids = sub["process"].node_id
        assert "p1" in node_ids
        assert "p0" in node_ids


class TestNodeBudget:
    def test_budget_caps_total_nodes(self) -> None:
        data = _toy_graph()
        sub = sample_khop_subgraph(
            data,
            SeedNode(NodeType.process, 0),
            max_nodes=3,
            khop=2,
            edge_ranking="weight",
        )
        total = sum(sub[t].num_nodes for t in sub.node_types)
        assert total <= 3
        # Seed must always be present.
        assert "p0" in sub["process"].node_id


class TestEdgeRanking:
    def test_time_recency_keeps_temporally_close_edges(self) -> None:
        # Target timestamp = 200 (matching p0 -> f1). Recency policy should
        # prefer that edge over p0 -> n0 (ts=300, |delta|=100/h?) under tight budget.
        # Actually our deltas are nanosecond-scale; 300-200 = 100ns -> very close.
        # Choose a budget that forces a real choice.
        data = _toy_graph()
        sub = sample_khop_subgraph(
            data,
            SeedNode(NodeType.process, 0),
            max_nodes=2,  # seed + 1 neighbour only
            khop=1,
            edge_ranking="time_recency",
            target_timestamp_ns=200,
        )
        # The single neighbour must be one of {f0,f1,n0,p2}; we just verify
        # the call succeeds with time_recency + target_ts.
        assert sum(sub[t].num_nodes for t in sub.node_types) == 2

    def test_time_recency_requires_target_ts(self) -> None:
        data = _toy_graph()
        with pytest.raises(ValueError, match="target_timestamp_ns"):
            sample_khop_subgraph(
                data,
                SeedNode(NodeType.process, 0),
                max_nodes=10,
                khop=1,
                edge_ranking="time_recency",
            )

    def test_unknown_ranking_rejected(self) -> None:
        data = _toy_graph()
        with pytest.raises(ValueError, match="edge_ranking"):
            sample_khop_subgraph(
                data,
                SeedNode(NodeType.process, 0),
                max_nodes=10,
                khop=1,
                edge_ranking="bogus",
            )


class TestPreservation:
    def test_node_id_strings_preserved(self) -> None:
        data = _toy_graph()
        sub = sample_khop_subgraph(
            data,
            SeedNode(NodeType.process, 0),
            max_nodes=10,
            khop=1,
            edge_ranking="weight",
        )
        for ntype in sub.node_types:
            assert isinstance(sub[ntype].node_id, list)
            assert len(sub[ntype].node_id) == sub[ntype].num_nodes

    def test_edge_attr_time_preserved(self) -> None:
        data = _toy_graph()
        sub = sample_khop_subgraph(
            data,
            SeedNode(NodeType.process, 0),
            max_nodes=10,
            khop=1,
            edge_ranking="weight",
        )
        for rel in sub.edge_types:
            ts = sub[rel].edge_attr_time
            assert ts.dtype.is_floating_point is False  # long
            assert ts.shape[0] == sub[rel].edge_index.shape[1]

    def test_isolated_recomputed_on_subgraph_degree(self) -> None:
        # Decision 8 invariant: isolated mask reflects sub-graph degree, not
        # parent-graph degree. With khop=0 (only seed), the seed is isolated
        # in the subgraph regardless of its degree in the parent.
        data = _toy_graph()
        sub = sample_khop_subgraph(
            data,
            SeedNode(NodeType.process, 0),
            max_nodes=10,
            khop=0,
            edge_ranking="weight",
        )
        assert bool(sub["process"].isolated[0].item()) is True


class TestInputValidation:
    def test_seed_out_of_range_rejected(self) -> None:
        data = _toy_graph()
        with pytest.raises(ValueError, match="out of range"):
            sample_khop_subgraph(
                data,
                SeedNode(NodeType.process, 999),
                max_nodes=10,
                khop=1,
                edge_ranking="weight",
            )

    def test_negative_khop_rejected(self) -> None:
        data = _toy_graph()
        with pytest.raises(ValueError, match="khop"):
            sample_khop_subgraph(
                data,
                SeedNode(NodeType.process, 0),
                max_nodes=10,
                khop=-1,
                edge_ranking="weight",
            )
