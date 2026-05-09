"""Unit tests for NEG-4.1 benign_admin_powershell_user_mgmt hard-negative template.

Three test classes:
  - schema validation (vanilla schema)
  - sequence shape (6-event deterministic shape)
  - distinct lexical signature (T#4.1 anchors: no powershell child,
    no .ps1 FILE_WRITE, single LDAP RPC clean exit)
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_4_1_powershell_user_mgmt import (
    Neg41PowershellUserMgmt,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg41PowershellUserMgmt()
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


def test_neg_4_1_schema_all_triples_in_allowed() -> None:
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_4_1_no_schema_workaround_triggered() -> None:
    """Vanilla schema — no svcctl pipe, no registry-as-file, no USER_PRIV_GRANT."""
    events = _generate()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_4_1_sequence_shape_6_events() -> None:
    events = _generate()
    assert len(events) == 6


def test_neg_4_1_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, FILE_READ, NET_CONNECT, NET_SEND_NETWORK,
    NET_RECV_NETWORK, PROCESS_EXIT."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.FILE_READ.value,
        EdgeType.NET_CONNECT.value,
        EdgeType.NET_SEND_NETWORK.value,
        EdgeType.NET_RECV_NETWORK.value,
        EdgeType.PROCESS_EXIT.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_4_1_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature (T#4.1 three anchors)
# ---------------------------------------------------------------------------


def test_neg_4_1_no_powershell_child_process() -> None:
    """Anchor (i): no (powershell.exe, PROCESS_CREATE, *) — depth-1 tree."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.PROCESS_CREATE.value, (
            f"NEG-4.1 must have NO PROCESS_CREATE (depth-1 anchor); " f"got op={ev.operation!r}"
        )


def test_neg_4_1_no_ps1_file_write() -> None:
    """Anchor (ii): no (powershell.exe, FILE_WRITE, *.ps1) — no payload drop."""
    events = _generate()
    for ev in events:
        if ev.operation == EdgeType.FILE_WRITE.value:
            assert not ev.obj.endswith(".ps1"), (
                f"NEG-4.1 must NOT FILE_WRITE *.ps1 (payload drop anchor); " f"got obj={ev.obj!r}"
            )


def test_neg_4_1_terminates_with_process_exit() -> None:
    """Anchor (iii): sequence terminates with PROCESS_EXIT (clean exit)."""
    events = _generate()
    final_ev = events[5]
    assert final_ev.operation == EdgeType.PROCESS_EXIT.value
    assert "powershell.exe" in final_ev.subject


def test_neg_4_1_dc_network_destination() -> None:
    """NET_CONNECT must go to dc_network (LDAP/RPC endpoint)."""
    events = _generate()
    net_connect = [ev for ev in events if ev.operation == EdgeType.NET_CONNECT.value]
    assert len(net_connect) == 1
    assert "dc_network" in net_connect[0].obj


def test_neg_4_1_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-4.1"


def test_neg_4_1_seed_anchor() -> None:
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
