"""Unit tests for the DARPA TC E3 CDM parser skeleton."""

from __future__ import annotations

from pathlib import Path

from loghetero.data.parsers.base import NodeType, ParseStats
from loghetero.data.parsers.darpa_e3 import (
    _CDM_NODE_TYPE_MAP,
    CDMParser,
    cdm_node_type,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cdm_sample.jsonl"


class TestCDMNodeTypeMap:
    """Exhaustively pin decision 5's CDM -> NodeType mapping table."""

    def test_subject_is_process(self) -> None:
        assert _CDM_NODE_TYPE_MAP["Subject"] is NodeType.process

    def test_principal_is_user(self) -> None:
        assert _CDM_NODE_TYPE_MAP["Principal"] is NodeType.user

    def test_file_object_is_file(self) -> None:
        assert _CDM_NODE_TYPE_MAP["FileObject"] is NodeType.file

    def test_unnamed_pipe_is_file_per_decision_5(self) -> None:
        # Decision 5: pipe aligned with KAIROS / MAGIC / FLASH (not socket).
        assert _CDM_NODE_TYPE_MAP["UnnamedPipeObject"] is NodeType.file

    def test_memory_object_is_file(self) -> None:
        assert _CDM_NODE_TYPE_MAP["MemoryObject"] is NodeType.file

    def test_srcsink_is_socket(self) -> None:
        # Decision 5 footnote: SrcSinkObject -> socket is LogHetero default,
        # subject to Phase 8 baseline-consistency adjustment.
        assert _CDM_NODE_TYPE_MAP["SrcSinkObject"] is NodeType.socket

    def test_netflow_is_network(self) -> None:
        assert _CDM_NODE_TYPE_MAP["NetFlowObject"] is NodeType.network

    def test_unknown_falls_back_to_file(self) -> None:
        # Decision 5: 未列出的边缘类型 -> file 兜底
        assert cdm_node_type("UnknownExoticType") is NodeType.file

    def test_map_has_exactly_seven_entries(self) -> None:
        # Locks the public surface so any addition forces a decision-5 RFC.
        assert set(_CDM_NODE_TYPE_MAP.keys()) == {
            "Subject",
            "Principal",
            "FileObject",
            "UnnamedPipeObject",
            "MemoryObject",
            "SrcSinkObject",
            "NetFlowObject",
        }


class TestCDMParser:
    def test_parses_fixture_events(self) -> None:
        stats = ParseStats()
        events = list(
            CDMParser().parse_file(FIXTURE, scenario_id="cadets-e3", host_id="host-A", stats=stats)
        )
        # 6 Event records in fixture (open / write / connect / sendto / read / fork)
        assert stats.success == 6
        assert len(events) == 6
        # 7 object records (Subject + Principal + 5 object types) all skipped,
        # 1 invalid-json line failed.
        assert stats.skipped == 7
        assert stats.failed == 1

    def test_event_open_resolves_types(self) -> None:
        events = list(CDMParser().parse_file(FIXTURE, scenario_id="cadets-e3", host_id="host-A"))
        open_event = next(e for e in events if e.operation == "file_open")
        assert open_event.subject_type is NodeType.process  # Subject -> process
        assert open_event.obj_type is NodeType.file  # FileObject -> file
        assert open_event.timestamp_ns == 1523344567890123456

    def test_unnamed_pipe_event_obj_type_is_file(self) -> None:
        # EVENT_WRITE on UnnamedPipeObject must come out as obj_type=file (decision 5).
        events = list(CDMParser().parse_file(FIXTURE, scenario_id="e3", host_id="host-A"))
        write_event = next(e for e in events if e.operation == "file_write")
        assert write_event.obj_type is NodeType.file
        assert write_event.attributes["obj_cdm_type"] == "UnnamedPipeObject"

    def test_srcsink_event_obj_type_is_socket(self) -> None:
        events = list(CDMParser().parse_file(FIXTURE, scenario_id="e3", host_id="host-A"))
        sendto_event = next(e for e in events if e.operation == "send")
        assert sendto_event.obj_type is NodeType.socket
        assert sendto_event.attributes["obj_cdm_type"] == "SrcSinkObject"

    def test_netflow_event_obj_type_is_network(self) -> None:
        events = list(CDMParser().parse_file(FIXTURE, scenario_id="e3", host_id="host-A"))
        connect_event = next(e for e in events if e.operation == "connect")
        assert connect_event.obj_type is NodeType.network
        assert connect_event.attributes["obj_cdm_type"] == "NetFlowObject"

    def test_memory_event_obj_type_is_file(self) -> None:
        events = list(CDMParser().parse_file(FIXTURE, scenario_id="e3", host_id="host-A"))
        read_event = next(e for e in events if e.operation == "file_read")
        assert read_event.obj_type is NodeType.file
        assert read_event.attributes["obj_cdm_type"] == "MemoryObject"

    def test_fork_event_subject_and_obj_both_process(self) -> None:
        events = list(CDMParser().parse_file(FIXTURE, scenario_id="e3", host_id="host-A"))
        fork_event = next(e for e in events if e.operation == "fork")
        assert fork_event.subject_type is NodeType.process
        assert fork_event.obj_type is NodeType.process

    def test_log_type_constant(self) -> None:
        assert CDMParser.LOG_TYPE == "darpa.cdm"
