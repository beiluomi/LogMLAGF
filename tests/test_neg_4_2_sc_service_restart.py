"""Unit tests for NEG-4.2 benign_admin_sc_service_restart hard-negative template.

Schema-workaround reuse (verified by schema test class):
  - USER_PRIV_GRANT user-anchor reuses T1068 workaround #2.
  - svcctl pipe-as-file reuses T1543.003 sc.exe pattern.
  - EXPLICIT do NOT reuse T1547.001 registry-as-file (sc service restart
    不写 IMAGEPATH per §3.4 boundary verbatim).

Five-anchor chain cross-reference (T#4.2 specific, see module docstring
item 3): §4.3 line 321-329 + §3.7 line 157 + NEG-7.1 (commit 07251b2) +
NEG-7.2 (commit 07251b2 + docstring fix commit 2d83dc7) + T#4.2 自身.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_4_2_sc_service_restart import (
    Neg42ScServiceRestart,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg42ScServiceRestart()
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
# Class 1: schema validation (2 workaround reuses)
# ---------------------------------------------------------------------------


def test_neg_4_2_schema_all_triples_in_allowed() -> None:
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_4_2_user_priv_grant_workaround_reuse_t1068_pattern() -> None:
    """USER_PRIV_GRANT workaround #2 reuse: subject is seed_user (NOT process)."""
    events = _generate()
    priv_grant = [ev for ev in events if ev.operation == EdgeType.USER_PRIV_GRANT.value]
    assert len(priv_grant) == 1
    ev = priv_grant[0]
    assert ev.subject_type == NodeType.user
    assert ev.subject == "benign_admin_user"


def test_neg_4_2_svcctl_pipe_path_matches_t1543_003_workaround() -> None:
    """svcctl pipe FILE_WRITE reuses T1543.003 sc.exe pattern."""
    events = _generate()
    svcctl_writes = [
        ev
        for ev in events
        if ev.operation == EdgeType.FILE_WRITE.value and r"\\.\pipe\svcctl" in ev.obj
    ]
    assert (
        len(svcctl_writes) == 1
    ), f"NEG-4.2 must emit exactly 1 svcctl pipe FILE_WRITE; got {len(svcctl_writes)}"
    ev = svcctl_writes[0]
    assert ev.subject_type == NodeType.process
    assert ev.obj_type == NodeType.file


def test_neg_4_2_no_registry_as_file_workaround_used() -> None:
    """Anchor (ii) negative: NEG-4.2 does NOT reuse T1547.001 registry pattern."""
    events = _generate()
    for ev in events:
        assert "\\Registry\\" not in ev.obj, (
            f"NEG-4.2 must NOT reuse T1547.001 registry-as-file (sc service "
            f"restart 不写 IMAGEPATH); got obj={ev.obj!r}"
        )
        assert (
            "ImagePath" not in ev.obj
        ), f"NEG-4.2 must NOT write IMAGEPATH (anchor (ii)); got obj={ev.obj!r}"


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_4_2_sequence_shape_4_events() -> None:
    events = _generate()
    assert len(events) == 4


def test_neg_4_2_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, USER_PRIV_GRANT, FILE_WRITE (svcctl), PROCESS_EXIT."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.USER_PRIV_GRANT.value,
        EdgeType.FILE_WRITE.value,  # svcctl pipe
        EdgeType.PROCESS_EXIT.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_4_2_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature (T#4.2 three anchors)
# ---------------------------------------------------------------------------


def test_neg_4_2_no_new_service_binary_write() -> None:
    """Anchor (i): no FILE_WRITE to System32\\<new_svc>.exe — no new
    service binary."""
    events = _generate()
    for ev in events:
        if ev.operation == EdgeType.FILE_WRITE.value:
            # FILE_WRITE target must not be a System32 .exe binary
            assert not ("System32" in ev.obj and ev.obj.endswith(".exe")), (
                f"NEG-4.2 must NOT FILE_WRITE System32 service binary "
                f"(anchor (i)); got obj={ev.obj!r}"
            )


def test_neg_4_2_no_imagepath_registry_write() -> None:
    """Anchor (ii): no IMAGEPATH registry FILE_WRITE."""
    events = _generate()
    for ev in events:
        if ev.operation == EdgeType.FILE_WRITE.value:
            assert (
                "ImagePath" not in ev.obj
            ), f"NEG-4.2 must NOT write IMAGEPATH (anchor (ii)); got obj={ev.obj!r}"
            assert "\\Registry\\" not in ev.obj


def test_neg_4_2_service_restart_semantic_anchor() -> None:
    """Anchor (iii): service-restart semantic — svcctl pipe write directly
    followed by PROCESS_EXIT (no service-creation chain)."""
    events = _generate()
    # Event 3 (index 2) = svcctl pipe FILE_WRITE
    ev_svcctl = events[2]
    assert ev_svcctl.operation == EdgeType.FILE_WRITE.value
    assert r"\\.\pipe\svcctl" in ev_svcctl.obj
    # Event 4 (index 3) = PROCESS_EXIT (immediately after svcctl write)
    ev_exit = events[3]
    assert ev_exit.operation == EdgeType.PROCESS_EXIT.value
    assert "sc.exe" in ev_exit.subject
    assert ev_svcctl.timestamp_ns < ev_exit.timestamp_ns


def test_neg_4_2_no_process_create_downstream() -> None:
    """sc.exe restart has NO PROCESS_CREATE downstream (no spawned binary)."""
    events = _generate()
    for ev in events:
        assert (
            ev.operation != EdgeType.PROCESS_CREATE.value
        ), f"NEG-4.2 must have NO PROCESS_CREATE downstream; got op={ev.operation!r}"


def test_neg_4_2_no_net_connect() -> None:
    """sc service restart has NO outbound NET_CONNECT (vs T1543.003 C2 chain)."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value


def test_neg_4_2_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-4.2"


def test_neg_4_2_seed_anchor() -> None:
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
