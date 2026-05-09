"""Unit tests for NEG-1.2 benign_office_excel_pivot_edit hard-negative template.

Three test classes:
  - schema validation (vanilla schema)
  - sequence shape (5-event deterministic shape)
  - distinct lexical signature (T#1.2 anchors: no excel→powershell, no
    NET_CONNECT, child-process+network 链 distinguishing)
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_1_2_excel_pivot import Neg12ExcelPivot
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg12ExcelPivot()
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    return template.generate(
        seed_subject="benign_admin_user",
        seed_subject_type="user",
        t_start_ns=t_start,
        t_end_ns=t_end,
        rng=_make_rng(seed),
        instance_id=iid,
    )


# ---------------------------------------------------------------------------
# Class 1: schema validation
# ---------------------------------------------------------------------------


def test_neg_1_2_schema_all_triples_in_allowed() -> None:
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_1_2_no_schema_workaround_triggered() -> None:
    events = _generate()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_1_2_sequence_shape_5_events() -> None:
    events = _generate()
    assert len(events) == 5


def test_neg_1_2_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, PROCESS_CREATE, FILE_READ, FILE_WRITE, FILE_WRITE."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.PROCESS_CREATE.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_WRITE.value,
        EdgeType.FILE_WRITE.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_1_2_office_lock_file_write_terminal() -> None:
    """Final FILE_WRITE must target ~$ Office lock file."""
    events = _generate()
    final_ev = events[4]
    assert final_ev.operation == EdgeType.FILE_WRITE.value
    assert (
        "~$" in final_ev.obj
    ), f"Final FILE_WRITE must target Office lock file ~$<workbook>.xlsx; got {final_ev.obj!r}"
    assert final_ev.obj.endswith(".xlsx")


def test_neg_1_2_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature (T#1.2 three anchors)
# ---------------------------------------------------------------------------


def test_neg_1_2_no_excel_powershell_spawn() -> None:
    """Anchor (i): no (excel.exe, PROCESS_CREATE, powershell.exe)."""
    events = _generate()
    for ev in events:
        if ev.operation == EdgeType.PROCESS_CREATE.value:
            assert "powershell.exe" not in ev.obj, (
                f"NEG-1.2 must NOT spawn powershell.exe (macro-execute anchor); "
                f"got obj={ev.obj!r}"
            )
            assert "cmd.exe" not in ev.obj, f"NEG-1.2 must NOT spawn cmd.exe; got obj={ev.obj!r}"


def test_neg_1_2_no_outbound_net_connect() -> None:
    """Anchor (ii): no outbound NET_CONNECT (T1204.002 reverse shell anchor)."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value
        assert ev.operation != EdgeType.NET_SEND_NETWORK.value
        assert ev.operation != EdgeType.NET_HTTP_REQUEST.value


def test_neg_1_2_excel_no_child_process_anchor() -> None:
    """Anchor (iii): excel.exe has NO PROCESS_CREATE downstream
    (child-process+network 链 distinguishing)."""
    events = _generate()
    for ev in events:
        if ev.operation == EdgeType.PROCESS_CREATE.value:
            # excel.exe must NOT be the subject of any PROCESS_CREATE event
            assert "excel.exe" not in ev.subject, (
                f"NEG-1.2 must NOT have excel.exe as PROCESS_CREATE subject "
                f"(child-process anchor); got subject={ev.subject!r}"
            )


def test_neg_1_2_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-1.2"


def test_neg_1_2_seed_anchor() -> None:
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
