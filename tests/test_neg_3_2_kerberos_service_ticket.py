"""Unit tests for NEG-3.2 benign_auth_kerberos_service_ticket hard-negative template.

Schema-workaround reuse: USER_PRIV_GRANT user-anchor reuses T1068 workaround
#2 (known_issues.md inventory entry #2). Verified by schema test class.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_3_2_kerberos_service_ticket import (
    Neg32KerberosServiceTicket,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg32KerberosServiceTicket()
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
# Class 1: schema validation (USER_PRIV_GRANT user-anchor T1068 workaround #2 reuse)
# ---------------------------------------------------------------------------


def test_neg_3_2_schema_all_triples_in_allowed() -> None:
    """All emitted triples must be in ALLOWED_EDGE_TRIPLES.

    Includes (user, USER_PRIV_GRANT, process) which IS natively in
    ALLOWED_EDGE_TRIPLES — but the user-as-subject choice is the
    T1068 workaround #2 reuse pattern (semantic: privilege attributed
    to user's session per Windows 4672, not to lsass.exe process).
    """
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_3_2_user_priv_grant_workaround_reuse_t1068_pattern() -> None:
    """USER_PRIV_GRANT workaround #2 reuse: subject is seed_user (NOT process).

    Verifies the same pattern as t1068_exploitation_for_privesc.py event 5:
    (seed_user, USER_PRIV_GRANT, lsass.exe) — privilege attributed to user
    session per Windows 4672. ALLOWED_EDGE_TRIPLES does NOT contain
    (process, USER_PRIV_GRANT, process).
    """
    events = _generate()
    priv_grant_events = [ev for ev in events if ev.operation == EdgeType.USER_PRIV_GRANT.value]
    assert len(priv_grant_events) == 1, (
        f"NEG-3.2 must emit exactly 1 USER_PRIV_GRANT (single TGS exchange); "
        f"got {len(priv_grant_events)}"
    )
    ev = priv_grant_events[0]
    # Workaround #2 anchor: subject is user (NOT process)
    assert ev.subject_type == NodeType.user, (
        f"USER_PRIV_GRANT subject must be user (T1068 workaround #2 reuse); "
        f"got {ev.subject_type!r}"
    )
    assert ev.subject == "benign_admin_user"
    assert ev.obj_type == NodeType.process


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_3_2_sequence_shape_6_events() -> None:
    """NEG-3.2 must generate exactly 6 events (deterministic single-TGS chain)."""
    events = _generate()
    assert len(events) == 6


def test_neg_3_2_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON → USER_PRIV_GRANT → NET_CONNECT → NET_SEND_NETWORK → NET_RECV_NETWORK → FILE_WRITE."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.USER_PRIV_GRANT.value,
        EdgeType.NET_CONNECT.value,
        EdgeType.NET_SEND_NETWORK.value,
        EdgeType.NET_RECV_NETWORK.value,
        EdgeType.FILE_WRITE.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_3_2_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature (boundary vs T1558.003 + T1078 + T#8 RDP)
# ---------------------------------------------------------------------------


def test_neg_3_2_single_tgs_req_rep_pair() -> None:
    """Anchor (a): exactly 1 NET_SEND_NETWORK + 1 NET_RECV_NETWORK (no SPN spray).

    T1558.003 Kerberoasting characteristically requests TGS for multiple
    service principals (5+ TGS-REQ); single REQ/REP is structural anchor.
    """
    events = _generate()
    sends = [ev for ev in events if ev.operation == EdgeType.NET_SEND_NETWORK.value]
    recvs = [ev for ev in events if ev.operation == EdgeType.NET_RECV_NETWORK.value]
    assert len(sends) == 1, f"Single TGS-REQ anchor: expected 1 SEND; got {len(sends)}"
    assert len(recvs) == 1, f"Single TGS-REP anchor: expected 1 RECV; got {len(recvs)}"


def test_neg_3_2_kdc_destination_only_no_c2() -> None:
    """Anchor (d): only NET_CONNECT in sequence is to kdc_network (no C2)."""
    events = _generate()
    for ev in events:
        if ev.operation in (
            EdgeType.NET_CONNECT.value,
            EdgeType.NET_SEND_NETWORK.value,
            EdgeType.NET_RECV_NETWORK.value,
        ):
            assert (
                "kdc_network" in ev.obj
            ), f"Network event must target kdc_network only (no C2); got {ev.obj!r}"


def test_neg_3_2_ticket_cache_local_write_only() -> None:
    """Anchor (b)+(c): FILE_WRITE only to local krb5cc_<uid>; no downstream read."""
    events = _generate()
    file_writes = [ev for ev in events if ev.operation == EdgeType.FILE_WRITE.value]
    assert len(file_writes) == 1
    assert (
        "krb5cc_" in file_writes[0].obj
    ), f"FILE_WRITE must target krb5cc_<uid> ticket cache; got {file_writes[0].obj!r}"
    # No FILE_READ of krb5cc_* in the sequence (no Kerberoast extraction)
    for ev in events:
        if ev.operation == EdgeType.FILE_READ.value:
            assert (
                "krb5cc_" not in ev.obj
            ), f"NEG-3.2 must NOT FILE_READ krb5cc_* (no Kerberoast); got {ev.obj!r}"


def test_neg_3_2_no_mstsc_no_user_logon_fail() -> None:
    """Anchors (e) + §4.1.D + §4.1.G: no mstsc, no USER_LOGON_FAIL burst."""
    events = _generate()
    for ev in events:
        assert "mstsc.exe" not in ev.subject
        assert "mstsc.exe" not in ev.obj
        assert ev.operation != EdgeType.USER_LOGON_FAIL.value


def test_neg_3_2_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-3.2"


def test_neg_3_2_seed_anchor() -> None:
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
