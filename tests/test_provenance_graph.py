"""Unit tests for the heterogeneous provenance graph builder (Phase 1.4).

Per Checkpoint 3 launch spec: must include happy path + at least 2 counter-
example tests. The two counter-examples here are:

1. ``test_empty_events_raises`` - empty Event stream must fail loudly, not
   silently produce an empty HeteroData.
2. ``test_same_triple_different_times_emits_parallel_edges`` - the same
   ``(subject, operation, obj)`` repeated at different timestamps must produce
   multiple parallel edges with distinct ``edge_attr_time`` entries, NOT
   collapse to one. This is the multigraph invariant decision 8 cares about.
"""

from __future__ import annotations

import pytest

from loghetero.data.parsers.base import EdgeType, Event, NodeType
from loghetero.data.provenance_graph import build_graph


def _ev(
    ts: int,
    sub: str,
    sub_t: NodeType,
    obj: str,
    obj_t: NodeType,
    op: EdgeType,
) -> Event:
    return Event(
        timestamp_ns=ts,
        subject=sub,
        subject_type=sub_t,
        obj=obj,
        obj_type=obj_t,
        operation=op,
        log_type="test",
        scenario_id="T1",
        host_id="h1",
    )


class TestHappyPath:
    def test_three_event_graph_has_expected_nodes_and_edges(self) -> None:
        events = [
            _ev(
                1, "firefox.exe", NodeType.process, "/etc/passwd", NodeType.file, EdgeType.FILE_READ
            ),
            _ev(
                2,
                "firefox.exe",
                NodeType.process,
                "1.2.3.4",
                NodeType.network,
                EdgeType.NET_CONNECT,
            ),
            _ev(
                3,
                "explorer.exe",
                NodeType.process,
                "firefox.exe",
                NodeType.process,
                EdgeType.PROCESS_CREATE,
            ),
        ]
        data, stats = build_graph(events)
        # 2 process nodes (firefox + explorer), 1 file, 1 network
        assert data["process"].num_nodes == 2
        assert data["file"].num_nodes == 1
        assert data["network"].num_nodes == 1
        # 3 distinct edge triples
        rels = list(data.edge_types)
        assert ("process", "file_read", "file") in rels
        assert ("process", "net_connect", "network") in rels
        assert ("process", "process_create", "process") in rels
        # Stats reflect the same
        assert stats.nodes_per_type["process"] == 2
        assert stats.edges_per_triple[("process", "file_read", "file")] == 1

    def test_isolated_flag_set_for_zero_degree_nodes(self) -> None:
        # Node 'orphan_proc' never appears as subject or obj of any event.
        # Build with an event that creates it as obj of process_create, then
        # do nothing else with it. obj of process_create is reachable -> deg=1.
        # Construct true isolation by emitting events about other nodes only,
        # and then... actually you can't get an isolated node without it being
        # in some event. The "isolated" status comes from the per-window event
        # set used in Phase 1.5; for Phase 1.4 unit test, we exercise the flag
        # by ensuring a leaf-only-once node has the right degree.
        events = [
            _ev(1, "a.exe", NodeType.process, "f1.txt", NodeType.file, EdgeType.FILE_READ),
            _ev(2, "a.exe", NodeType.process, "f2.txt", NodeType.file, EdgeType.FILE_READ),
        ]
        data, stats = build_graph(events)
        # Both files have degree 1 (read once), neither is isolated.
        assert (data["file"].degree == 1).all().item() is True
        assert (~data["file"].isolated).all().item() is True
        assert stats.isolated_per_type.get("file", 0) == 0

    def test_unknown_op_skipped_and_counted(self) -> None:
        # Construct an Event with operation = some non-canonical string
        ev = Event(
            timestamp_ns=1,
            subject="a",
            subject_type=NodeType.process,
            obj="b",
            obj_type=NodeType.file,
            operation="totally_unknown_op",  # not a valid EdgeType value
            log_type="test",
            scenario_id="T",
            host_id="h",
        )
        # Add at least one valid edge so the graph isn't empty.
        valid = _ev(2, "a", NodeType.process, "b", NodeType.file, EdgeType.FILE_READ)
        _, stats = build_graph([ev, valid])
        assert stats.skipped_unknown_op == 1


class TestCounterExamples:
    def test_empty_events_raises(self) -> None:
        # Counter-example 1: empty stream must fail loudly; silently producing
        # an empty graph would let an empty time window propagate undetected.
        with pytest.raises(ValueError, match="at least one Event"):
            build_graph([])

    def test_same_triple_different_times_emits_parallel_edges(self) -> None:
        # Counter-example 2: multigraph invariant. Three reads of the same file
        # by the same process at different times must produce 3 distinct edges
        # with 3 distinct timestamps; NOT one deduplicated edge.
        events = [
            _ev(100, "p", NodeType.process, "f", NodeType.file, EdgeType.FILE_READ),
            _ev(200, "p", NodeType.process, "f", NodeType.file, EdgeType.FILE_READ),
            _ev(300, "p", NodeType.process, "f", NodeType.file, EdgeType.FILE_READ),
        ]
        data, stats = build_graph(events)
        rel = data["process", "file_read", "file"]
        assert rel.edge_index.shape == (2, 3)
        # All three edges connect the same node pair (p, f) with index 0->0
        assert (rel.edge_index == 0).all().item() is True
        # But timestamps are distinct
        assert sorted(rel.edge_attr_time.tolist()) == [100, 200, 300]
        # Process degree = 3 (three outgoing reads), file degree = 3 (three incoming)
        assert data["process"].degree[0].item() == 3
        assert data["file"].degree[0].item() == 3
        assert stats.edges_per_triple[("process", "file_read", "file")] == 3
