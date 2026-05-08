"""Unit tests for NEG-3.1 benign_auth_user_interactive_logon hard-negative template."""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_3_1_user_interactive_logon import (
    Neg31UserInteractiveLogon,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg31UserInteractiveLogon()
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


def test_neg_3_1_schema_all_triples_in_allowed() -> None:
    """All emitted triples must be in ALLOWED_EDGE_TRIPLES (vanilla schema)."""
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_3_1_no_schema_workaround_triggered() -> None:
    """Vanilla schema only — no svcctl/registry workarounds, no PRIV_GRANT reuse."""
    events = _generate()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_3_1_sequence_shape_5_events() -> None:
    """NEG-3.1 must generate exactly 5 events (deterministic interactive logon chain)."""
    events = _generate()
    assert len(events) == 5


def test_neg_3_1_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON → PROCESS_CREATE → PROCESS_CREATE → FILE_READ → PROCESS_CREATE."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.PROCESS_CREATE.value,
        EdgeType.PROCESS_CREATE.value,
        EdgeType.FILE_READ.value,
        EdgeType.PROCESS_CREATE.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_3_1_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature
# ---------------------------------------------------------------------------


def test_neg_3_1_process_tree_3_deep_winlogon_userinit_explorer() -> None:
    """Anchor (a): 3-deep process chain winlogon → userinit → explorer → app.

    Verifies the canonical Windows interactive logon process tree by
    checking subject/obj names of the PROCESS_CREATE events.
    """
    events = _generate()
    # Event 2 (idx 1): winlogon → userinit
    assert "winlogon.exe" in events[1].subject
    assert "userinit.exe" in events[1].obj
    # Event 3 (idx 2): userinit → explorer
    assert "userinit.exe" in events[2].subject
    assert "explorer.exe" in events[2].obj
    # Event 5 (idx 4): explorer → app
    assert "explorer.exe" in events[4].subject


def test_neg_3_1_leaf_is_normal_user_app_not_shell() -> None:
    """Anchor (b): leaf process is normal user-facing app, NOT shell.

    The 5th event spawns slack.exe (normal app) — NOT cmd.exe / powershell.exe
    / sh / bash (which would indicate T1078 valid-accounts shell takeover).
    """
    events = _generate()
    leaf_obj = events[4].obj
    # Positive: leaf must be the expected normal user app
    assert "slack.exe" in leaf_obj, f"Leaf must be slack.exe normal app; got {leaf_obj!r}"
    # Explicit negative checks for all four shells (T2-A fix: previously the
    # OR-clause `or not any(...)` short-circuited because LHS was always True
    # under hard-coded slack.exe, leaving /sh and /bash unchecked).
    assert "cmd.exe" not in leaf_obj
    assert "powershell.exe" not in leaf_obj
    assert "/sh" not in leaf_obj
    assert "/bash" not in leaf_obj


def test_neg_3_1_no_credential_access_paths() -> None:
    """Anchor (c): NO FILE_READ to LSASS / SAM / NTDS.dit / SECURITY hive."""
    events = _generate()
    forbidden_substrings = ("lsass", "SAM", "NTDS.dit", "SECURITY", "/etc/shadow")
    for ev in events:
        for forbidden in forbidden_substrings:
            assert (
                forbidden.lower() not in ev.obj.lower()
            ), f"Must NOT touch credential-access path {forbidden!r}; got {ev.obj!r}"


def test_neg_3_1_no_net_connect() -> None:
    """Anchor (d): NO NET_CONNECT — single-host interactive logon."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value


def test_neg_3_1_no_mstsc_no_user_logon_fail() -> None:
    """Anchors (e)+(f): NO mstsc.exe (vs RDP #8) + single USER_LOGON only (vs #9)."""
    events = _generate()
    for ev in events:
        assert "mstsc.exe" not in ev.subject
        assert "mstsc.exe" not in ev.obj
        assert ev.operation != EdgeType.USER_LOGON_FAIL.value
    user_logons = [ev for ev in events if ev.operation == EdgeType.USER_LOGON.value]
    assert len(user_logons) == 1, f"NEG-3.1 must have exactly 1 USER_LOGON; got {len(user_logons)}"


def test_neg_3_1_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-3.1"


def test_neg_3_1_seed_anchor() -> None:
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
