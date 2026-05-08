"""Unit tests for NEG-7.2 benign_driver_install_av_engine hard-negative template.

Schema-workaround reuse (verified by schema test class):
  - USER_PRIV_GRANT user-anchor reuses T1068 workaround #2.
  - svcctl pipe-as-file reuses T1543.003 sc.exe pattern.
  - (No registry-as-file in this 7-event variant — vendor SCM call sets
    ImagePath internally; only standard FILE_WRITE to vendor staging path.)
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_7_2_driver_install_av_engine import (
    Neg72DriverInstallAvEngine,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg72DriverInstallAvEngine()
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


def test_neg_7_2_schema_all_triples_in_allowed() -> None:
    """All emitted triples must be in ALLOWED_EDGE_TRIPLES."""
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_7_2_user_priv_grant_workaround_reuse_t1068_pattern() -> None:
    """USER_PRIV_GRANT workaround #2 reuse: subject is seed_user (NOT process)."""
    events = _generate()
    priv_grant_events = [ev for ev in events if ev.operation == EdgeType.USER_PRIV_GRANT.value]
    assert len(priv_grant_events) == 1
    ev = priv_grant_events[0]
    assert ev.subject_type == NodeType.user
    assert ev.subject == "benign_admin_user"


def test_neg_7_2_svcctl_pipe_path_matches_t1543_003_workaround() -> None:
    """svcctl pipe path FILE_WRITE reuses T1543.003 sc.exe pattern.

    Cross-reference: known_issues.md lines 437-440 inventory remains at
    4 entries (no new inventory entry triggered by this reuse).
    """
    events = _generate()
    svcctl_writes = [
        ev
        for ev in events
        if ev.operation == EdgeType.FILE_WRITE.value and r"\\.\pipe\svcctl" in ev.obj
    ]
    assert (
        len(svcctl_writes) == 1
    ), f"NEG-7.2 must emit exactly 1 svcctl pipe FILE_WRITE; got {len(svcctl_writes)}"
    ev = svcctl_writes[0]
    assert ev.subject_type == NodeType.process
    assert ev.obj_type == NodeType.file


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_7_2_sequence_shape_7_events() -> None:
    events = _generate()
    assert len(events) == 7


def test_neg_7_2_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, USER_PRIV_GRANT, 3x FILE_WRITE, NET_CONNECT, NET_RECV_NETWORK."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.USER_PRIV_GRANT.value,
        EdgeType.FILE_WRITE.value,  # vendor staging
        EdgeType.FILE_WRITE.value,  # drivers/<file>.sys copy
        EdgeType.FILE_WRITE.value,  # svcctl pipe
        EdgeType.NET_CONNECT.value,
        EdgeType.NET_RECV_NETWORK.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_7_2_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature
# ---------------------------------------------------------------------------


def test_neg_7_2_vendor_update_network_distinguishing_anchor() -> None:
    """Anchor (a): the only NET_CONNECT goes to vendor_update_network (NOT C2).

    Distinguishing structural pattern vs T1014 Rootkit / T1543.003 attack
    flows that connect to attacker-controlled C2 destinations.
    """
    events = _generate()
    net_connects = [ev for ev in events if ev.operation == EdgeType.NET_CONNECT.value]
    assert len(net_connects) == 1, (
        f"NEG-7.2 must have exactly 1 NET_CONNECT (vendor signature endpoint); "
        f"got {len(net_connects)}"
    )
    assert "vendor_update_network" in net_connects[0].obj, (
        f"NET_CONNECT must target vendor_update_network (vendor signature endpoint), "
        f"NOT C2; got {net_connects[0].obj!r}"
    )


def test_neg_7_2_recv_only_direction_no_send_exfil() -> None:
    """Anchor (e): RECV-only direction (no NET_SEND_NETWORK exfil burst).

    T1014 Rootkit / T1543.003 attacks typically NET_SEND_NETWORK to C2 for
    exfil/beacon. NEG-7.2 only RECV (server-pushes-to-client signature
    delivery).
    """
    events = _generate()
    sends = [ev for ev in events if ev.operation == EdgeType.NET_SEND_NETWORK.value]
    recvs = [ev for ev in events if ev.operation == EdgeType.NET_RECV_NETWORK.value]
    assert len(sends) == 0, (
        f"NEG-7.2 must have NO NET_SEND_NETWORK (RECV-only signature update); " f"got {len(sends)}"
    )
    assert len(recvs) == 1, (
        f"NEG-7.2 must have exactly 1 NET_RECV_NETWORK (signature update payload); "
        f"got {len(recvs)}"
    )


def test_neg_7_2_programdata_vendor_staging_first_anchor() -> None:
    """Anchor (b): FIRST .sys FILE_WRITE goes to ProgramData vendor staging path.

    Distinguishing structural pattern vs T1547.006 attack drivers that
    SKIP ProgramData/Vendor staging and write directly to drivers/.
    """
    events = _generate()
    ev_first_sys = events[2]
    assert ev_first_sys.operation == EdgeType.FILE_WRITE.value
    assert (
        "ProgramData\\Vendor\\Engine" in ev_first_sys.obj
    ), f"First .sys write must target ProgramData/Vendor/Engine staging; got {ev_first_sys.obj!r}"
    assert ev_first_sys.obj.endswith(".sys")
    # Event 4 = drivers/ copy
    ev_drivers_sys = events[3]
    assert "System32\\drivers\\" in ev_drivers_sys.obj
    assert ev_drivers_sys.obj.endswith(".sys")
    assert ev_first_sys.timestamp_ns < ev_drivers_sys.timestamp_ns


def test_neg_7_2_no_process_create_downstream() -> None:
    """Anchor (c): no PROCESS_CREATE downstream — depth-1 process tree."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.PROCESS_CREATE.value


def test_neg_7_2_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-7.2"
