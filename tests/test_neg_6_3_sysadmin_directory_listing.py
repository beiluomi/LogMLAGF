"""Unit tests for NEG-6.3 benign_fs_sysadmin_directory_listing hard-negative template.

Three test classes per Cycle H upgraded contract:
  - schema validation (vanilla schema)
  - sequence shape (6-event deterministic shape — 2 commands ls + cat)
  - distinct lexical signature: SEQUENCE-PAIR tests against T1486
    ransomware — assert distinguishing anchors via paired comparison.
    NEG-6.3 is the strongest #6 anchor — completely zero destructive
    writes (no FILE_WRITE/FILE_DELETE/FILE_RENAME).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware
from loghetero.data.hard_negative_templates.neg_6_3_sysadmin_directory_listing import (
    Neg63SysadminDirectoryListing,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate_neg(seed: int = 42, iid: int = 0) -> list:
    template = Neg63SysadminDirectoryListing()
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


def _generate_t1486(seed: int = 42, iid: int = 0) -> list:
    template = T1486Ransomware()
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    return template.generate(
        seed_subject="victim_user",
        seed_subject_type="user",
        t_start_ns=t_start,
        t_end_ns=t_end,
        rng=_make_rng(seed),
        instance_id=iid,
    )


# ---------------------------------------------------------------------------
# Class 1: schema validation
# ---------------------------------------------------------------------------


def test_neg_6_3_schema_all_triples_in_allowed() -> None:
    events = _generate_neg()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_6_3_no_schema_workaround_triggered() -> None:
    """Vanilla schema."""
    events = _generate_neg()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_6_3_sequence_shape_6_events() -> None:
    events = _generate_neg()
    assert len(events) == 6


def test_neg_6_3_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, FILE_READ, PROCESS_EXIT (ls);
    USER_LOGON, FILE_READ, PROCESS_EXIT (cat) — 2-command interactive."""
    events = _generate_neg()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.FILE_READ.value,
        EdgeType.PROCESS_EXIT.value,
        EdgeType.USER_LOGON.value,
        EdgeType.FILE_READ.value,
        EdgeType.PROCESS_EXIT.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_6_3_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate_neg()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: SEQUENCE-PAIR distinct lexical signature tests vs T1486 ransomware
# ---------------------------------------------------------------------------


def test_neg_6_3_pair_vs_t1486_file_rename_count_distinct() -> None:
    """Anchor (i): #6 NEG-6.3 zero FILE_RENAME; T1486 zero FILE_RENAME
    (T1486 uses FILE_DELETE). Distinguishing pair anchor is via FILE_DELETE
    + FILE_WRITE batch absence in NEG-6.3."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_renames = [ev for ev in neg_events if ev.operation == EdgeType.FILE_RENAME.value]
    t1486_renames = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_RENAME.value]
    assert (
        len(neg_renames) == 0
    ), f"NEG-6.3 must have ZERO FILE_RENAME (anchor (i)); got {len(neg_renames)}"
    assert len(t1486_renames) == 0


def test_neg_6_3_pair_vs_t1486_file_write_classification_distinct() -> None:
    """Anchor (i)+(iii) strongest: NEG-6.3 has ZERO FILE_WRITE; T1486
    has multiple .locked encrypted FILE_WRITE."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_writes = [ev for ev in neg_events if ev.operation == EdgeType.FILE_WRITE.value]
    t1486_writes = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_WRITE.value]
    assert (
        len(neg_writes) == 0
    ), f"NEG-6.3 must have ZERO FILE_WRITE (anchor (i)+(iii)); got {len(neg_writes)}"
    assert len(t1486_writes) >= 2, f"T1486 must have batch FILE_WRITE; got {len(t1486_writes)}"
    # Strongest anchor: counts differ (0 vs >=2)
    assert len(neg_writes) != len(t1486_writes)


def test_neg_6_3_pair_vs_t1486_file_delete_batch_absence() -> None:
    """Anchor (i): NEG-6.3 zero FILE_DELETE; T1486 batch FILE_DELETE source."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_deletes = [ev for ev in neg_events if ev.operation == EdgeType.FILE_DELETE.value]
    t1486_deletes = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_DELETE.value]
    assert len(neg_deletes) == 0, f"NEG-6.3 must have ZERO FILE_DELETE; got {len(neg_deletes)}"
    assert len(t1486_deletes) >= 2, f"T1486 must have batch FILE_DELETE; got {len(t1486_deletes)}"


def test_neg_6_3_pair_vs_t1486_sequence_length_distinct() -> None:
    """Sequence length distinct: NEG-6.3 = 6 events; T1486 = 9 events."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    assert len(neg_events) == 6
    assert len(t1486_events) == 9
    assert len(neg_events) != len(t1486_events)


def test_neg_6_3_no_etc_shadow_read() -> None:
    """T1003.008 anchor: NEG-6.3 must NOT FILE_READ /etc/shadow (no hash dump)."""
    events = _generate_neg()
    for ev in events:
        assert (
            "/etc/shadow" not in ev.obj
        ), f"NEG-6.3 must NOT read /etc/shadow (T1003.008 anchor); got {ev.obj!r}"


def test_neg_6_3_etc_passwd_read_present() -> None:
    """Anchor (ii) interactive shell idiom: /etc/passwd is read."""
    events = _generate_neg()
    passwd_reads = [
        ev for ev in events if ev.operation == EdgeType.FILE_READ.value and "/etc/passwd" in ev.obj
    ]
    assert (
        len(passwd_reads) == 1
    ), f"NEG-6.3 must FILE_READ /etc/passwd exactly once (anchor (ii)); got {len(passwd_reads)}"


def test_neg_6_3_no_net_connect_no_exfil() -> None:
    """No outbound NET_CONNECT — no exfil chain (T1083 attacker chain anchor)."""
    events = _generate_neg()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value


def test_neg_6_3_zero_destructive_writes_strongest_anchor() -> None:
    """Anchor (i)+(iii) strongest: sequence has ZERO FILE_WRITE / FILE_DELETE
    / FILE_RENAME (structurally fully disjoint from T1486)."""
    events = _generate_neg()
    for ev in events:
        assert ev.operation != EdgeType.FILE_WRITE.value
        assert ev.operation != EdgeType.FILE_DELETE.value
        assert ev.operation != EdgeType.FILE_RENAME.value


def test_neg_6_3_label_zero_and_neg_id() -> None:
    events = _generate_neg()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-6.3"


def test_neg_6_3_seed_anchor() -> None:
    events = _generate_neg()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
