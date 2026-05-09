"""Unit tests for NEG-4.3 benign_admin_schtasks_create hard-negative template.

Schema-workaround reuse:
  - USER_PRIV_GRANT user-anchor reuses T1068 workaround #2.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_4_3_schtasks_create import (
    Neg43SchtasksCreate,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg43SchtasksCreate()
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
# Class 1: schema validation (1 workaround reuse)
# ---------------------------------------------------------------------------


def test_neg_4_3_schema_all_triples_in_allowed() -> None:
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_4_3_user_priv_grant_workaround_reuse_t1068_pattern() -> None:
    """USER_PRIV_GRANT workaround #2 reuse: subject is seed_user (NOT process)."""
    events = _generate()
    priv_grant = [ev for ev in events if ev.operation == EdgeType.USER_PRIV_GRANT.value]
    assert len(priv_grant) == 1
    ev = priv_grant[0]
    assert ev.subject_type == NodeType.user
    assert ev.subject == "benign_admin_user"


def test_neg_4_3_no_svcctl_pipe_workaround() -> None:
    """NEG-4.3 must NOT use svcctl pipe workaround (no SCM RPC)."""
    events = _generate()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_4_3_sequence_shape_5_events() -> None:
    events = _generate()
    assert len(events) == 5


def test_neg_4_3_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, USER_PRIV_GRANT, FILE_READ, FILE_WRITE, PROCESS_EXIT."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.USER_PRIV_GRANT.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_WRITE.value,
        EdgeType.PROCESS_EXIT.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_4_3_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature (T#4.3 three anchors)
# ---------------------------------------------------------------------------


def test_neg_4_3_task_xml_admin_path_anchor() -> None:
    """Anchor (i)+(iii): task XML written to admin Tasks dir under
    well-known backup_daily path."""
    events = _generate()
    write_events = [ev for ev in events if ev.operation == EdgeType.FILE_WRITE.value]
    assert len(write_events) == 1
    ev = write_events[0]
    assert (
        "Tasks\\" in ev.obj or "Tasks/" in ev.obj
    ), f"Task XML must be written to Tasks\\ admin dir; got {ev.obj!r}"
    assert (
        "backup_daily" in ev.obj
    ), f"Task XML name must reference backup_daily admin utility; got {ev.obj!r}"


def test_neg_4_3_existing_task_read_before_write() -> None:
    """Read existing task XML BEFORE writing new task XML (idempotency)."""
    events = _generate()
    ev_read = events[2]
    ev_write = events[3]
    assert ev_read.operation == EdgeType.FILE_READ.value
    assert ev_write.operation == EdgeType.FILE_WRITE.value
    assert ev_read.timestamp_ns < ev_write.timestamp_ns


def test_neg_4_3_no_process_create_downstream() -> None:
    """schtasks /Create has NO PROCESS_CREATE downstream (no payload exec)."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.PROCESS_CREATE.value


def test_neg_4_3_no_net_connect() -> None:
    """schtasks /Create has NO NET_CONNECT (no C2 chain)."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value


def test_neg_4_3_terminates_with_process_exit() -> None:
    """Sequence terminates with schtasks.exe PROCESS_EXIT."""
    events = _generate()
    final_ev = events[4]
    assert final_ev.operation == EdgeType.PROCESS_EXIT.value
    assert "schtasks.exe" in final_ev.subject


def test_neg_4_3_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-4.3"


def test_neg_4_3_seed_anchor() -> None:
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
