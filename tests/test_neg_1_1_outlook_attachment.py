"""Unit tests for NEG-1.1 benign_office_outlook_attachment_view hard-negative template.

Three test classes per Cycle G/H dispatch contract:
  - schema validation (all triples in ALLOWED_EDGE_TRIPLES, vanilla schema)
  - sequence shape (5-event deterministic shape per docstring)
  - distinct lexical signature (T#1.1 anchors: no winword child shell,
    no NET_CONNECT, child-process-class signal)
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_1_1_outlook_attachment import (
    Neg11OutlookAttachment,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg11OutlookAttachment()
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


def test_neg_1_1_schema_all_triples_in_allowed() -> None:
    """All emitted triples must be in ALLOWED_EDGE_TRIPLES (vanilla schema)."""
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert (
            triple in ALLOWED_EDGE_TRIPLES
        ), f"Disallowed triple {triple} in NEG-1.1 (vanilla schema expected)"


def test_neg_1_1_no_schema_workaround_triggered() -> None:
    """NEG-1.1 must NOT use any schema workaround pattern (vanilla schema)."""
    events = _generate()
    for ev in events:
        assert (
            "\\\\.\\pipe\\svcctl" not in ev.obj
        ), f"NEG-1.1 must NOT use svcctl pipe workaround; got obj={ev.obj!r}"
        assert (
            "\\Registry\\" not in ev.obj
        ), f"NEG-1.1 must NOT use registry-as-file workaround; got obj={ev.obj!r}"
        assert (
            ev.operation != EdgeType.USER_PRIV_GRANT.value
        ), f"NEG-1.1 must NOT use USER_PRIV_GRANT workaround; got op={ev.operation!r}"


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_1_1_sequence_shape_5_events() -> None:
    events = _generate()
    assert len(events) == 5, f"Expected 5 events, got {len(events)}"


def test_neg_1_1_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, FILE_WRITE, PROCESS_CREATE, FILE_READ, FILE_WRITE."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.FILE_WRITE.value,
        EdgeType.PROCESS_CREATE.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_WRITE.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_1_1_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature (T#1.1 three anchors)
# ---------------------------------------------------------------------------


def test_neg_1_1_no_winword_child_shell() -> None:
    """Anchor (i): no (winword.exe, PROCESS_CREATE, cmd.exe/powershell.exe)."""
    events = _generate()
    for ev in events:
        if ev.operation == EdgeType.PROCESS_CREATE.value:
            # PROCESS_CREATE source must NOT be winword.exe
            assert "winword.exe" not in ev.subject, (
                f"NEG-1.1 must NOT have winword.exe spawning child process "
                f"(macro-child anchor); got subject={ev.subject!r}"
            )
        # Object must not be cmd.exe or powershell.exe spawned anywhere
        assert "cmd.exe" not in ev.obj, (
            f"NEG-1.1 must NOT contain cmd.exe (no shell spawn anchor); " f"got obj={ev.obj!r}"
        )
        assert "powershell.exe" not in ev.obj, (
            f"NEG-1.1 must NOT contain powershell.exe (no shell spawn anchor); "
            f"got obj={ev.obj!r}"
        )


def test_neg_1_1_no_net_connect_outbound_c2() -> None:
    """Anchor (ii): no NET_CONNECT to any outbound (C2 absent anchor)."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value, (
            f"NEG-1.1 must have NO NET_CONNECT (outbound C2 absent anchor "
            f"vs T1566.001); got {ev.operation!r}"
        )
        assert (
            ev.operation != EdgeType.NET_HTTP_REQUEST.value
        ), f"NEG-1.1 must have NO NET_HTTP_REQUEST; got {ev.operation!r}"


def test_neg_1_1_child_process_class_signal_winword() -> None:
    """Anchor (iii): only child process spawned is winword.exe (Office app),
    not shell."""
    events = _generate()
    process_create_events = [ev for ev in events if ev.operation == EdgeType.PROCESS_CREATE.value]
    assert len(process_create_events) == 1, (
        f"NEG-1.1 must have exactly 1 PROCESS_CREATE (depth-2 anchor); "
        f"got {len(process_create_events)}"
    )
    ev = process_create_events[0]
    assert "winword.exe" in ev.obj, (
        f"PROCESS_CREATE child must be winword.exe (Office app, not shell); " f"got obj={ev.obj!r}"
    )


def test_neg_1_1_label_zero_and_neg_id() -> None:
    """All events must carry label=0 (benign) + neg_id=NEG-1.1."""
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-1.1"


def test_neg_1_1_seed_anchor() -> None:
    """First event must have subject=seed_user (USER_LOGON anchor)."""
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
