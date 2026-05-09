"""Unit tests for NEG-6.1 benign_fs_audit_log_scan hard-negative template.

Three test classes per Cycle H upgraded contract:
  - schema validation (vanilla schema)
  - sequence shape (6-event deterministic shape)
  - distinct lexical signature: SEQUENCE-PAIR tests against T1486
    ransomware — assert distinguishing anchors via paired comparison
    (FILE_RENAME count, FILE_WRITE classification, FILE_DELETE absence,
    sequence length range distinct).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware
from loghetero.data.hard_negative_templates.neg_6_1_audit_log_scan import (
    Neg61AuditLogScan,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate_neg(seed: int = 42, iid: int = 0) -> list:
    template = Neg61AuditLogScan()
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


def test_neg_6_1_schema_all_triples_in_allowed() -> None:
    events = _generate_neg()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_6_1_no_schema_workaround_triggered() -> None:
    """Vanilla schema — no svcctl pipe, no registry-as-file, no USER_PRIV_GRANT."""
    events = _generate_neg()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_6_1_sequence_shape_6_events() -> None:
    events = _generate_neg()
    assert len(events) == 6


def test_neg_6_1_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, FILE_READ x3, FILE_WRITE, PROCESS_EXIT."""
    events = _generate_neg()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_WRITE.value,
        EdgeType.PROCESS_EXIT.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_6_1_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate_neg()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: SEQUENCE-PAIR distinct lexical signature tests vs T1486 ransomware
# ---------------------------------------------------------------------------


def test_neg_6_1_pair_vs_t1486_file_rename_count_distinct() -> None:
    """#6 NEG zero FILE_RENAME; T1486 zero FILE_RENAME (T1486 uses
    FILE_DELETE for source removal not rename — the distinguishing pair
    anchor is FILE_DELETE batch absence + FILE_WRITE classification)."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_renames = [ev for ev in neg_events if ev.operation == EdgeType.FILE_RENAME.value]
    t1486_renames = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_RENAME.value]
    # NEG-6.1 has zero FILE_RENAME (single .txt audit report write)
    assert len(neg_renames) == 0, f"NEG-6.1 must have ZERO FILE_RENAME; got {len(neg_renames)}"
    # T1486 also has zero FILE_RENAME (uses FILE_DELETE) — distinguishing
    # is via FILE_DELETE not rename.
    assert len(t1486_renames) == 0


def test_neg_6_1_pair_vs_t1486_file_write_classification_distinct() -> None:
    """Anchor (ii)+(iii): #6 NEG single .txt FILE_WRITE plain content;
    T1486 batch .locked FILE_WRITE encrypted bytes."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_writes = [ev for ev in neg_events if ev.operation == EdgeType.FILE_WRITE.value]
    t1486_writes = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_WRITE.value]
    # NEG-6.1: exactly 1 FILE_WRITE, .txt extension
    assert (
        len(neg_writes) == 1
    ), f"NEG-6.1 must have exactly 1 FILE_WRITE (single audit report); got {len(neg_writes)}"
    assert neg_writes[0].obj.endswith(
        ".txt"
    ), f"NEG-6.1 FILE_WRITE must end .txt (plain content); got {neg_writes[0].obj!r}"
    # T1486: multiple FILE_WRITE, including .locked extension batch
    assert len(t1486_writes) >= 2, (
        f"T1486 ransomware must have batch FILE_WRITE (.locked x N + ransom note); "
        f"got {len(t1486_writes)}"
    )
    locked_writes = [ev for ev in t1486_writes if ev.obj.endswith(".locked")]
    assert (
        len(locked_writes) >= 2
    ), f"T1486 must have batch .locked writes; got {len(locked_writes)}"
    # NEG-6.1 must have NO .locked write
    for ev in neg_writes:
        assert not ev.obj.endswith(
            ".locked"
        ), f"NEG-6.1 must NOT have .locked write (anchor (iii)); got {ev.obj!r}"


def test_neg_6_1_pair_vs_t1486_file_delete_batch_absence() -> None:
    """Anchor (i): #6 NEG zero FILE_DELETE; T1486 batch FILE_DELETE source files."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_deletes = [ev for ev in neg_events if ev.operation == EdgeType.FILE_DELETE.value]
    t1486_deletes = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_DELETE.value]
    # NEG-6.1: zero FILE_DELETE (anchor (i) source-files-read-only)
    assert (
        len(neg_deletes) == 0
    ), f"NEG-6.1 must have ZERO FILE_DELETE (anchor (i)); got {len(neg_deletes)}"
    # T1486: batch FILE_DELETE source files (>= 2 per encrypt-delete cycle)
    assert (
        len(t1486_deletes) >= 2
    ), f"T1486 must have batch FILE_DELETE source files; got {len(t1486_deletes)}"


def test_neg_6_1_pair_vs_t1486_sequence_length_distinct() -> None:
    """Sequence length distinct: NEG-6.1 = 6 events; T1486 = 9 events."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    assert len(neg_events) == 6
    assert len(t1486_events) == 9
    assert len(neg_events) != len(t1486_events)


def test_neg_6_1_no_net_connect_no_exfil() -> None:
    """No NET_CONNECT — no exfil chain (vs T1486 C2 beacon)."""
    events = _generate_neg()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value


def test_neg_6_1_label_zero_and_neg_id() -> None:
    events = _generate_neg()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-6.1"


def test_neg_6_1_seed_anchor() -> None:
    events = _generate_neg()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
