"""Unit tests for NEG-6.2 benign_fs_config_sync_task hard-negative template.

Three test classes per Cycle H upgraded contract:
  - schema validation (vanilla schema)
  - sequence shape (7-event deterministic shape)
  - distinct lexical signature: SEQUENCE-PAIR tests against T1486
    ransomware — assert distinguishing anchors via paired comparison.
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware
from loghetero.data.hard_negative_templates.neg_6_2_config_sync_task import (
    Neg62ConfigSyncTask,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate_neg(seed: int = 42, iid: int = 0) -> list:
    template = Neg62ConfigSyncTask()
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


def test_neg_6_2_schema_all_triples_in_allowed() -> None:
    events = _generate_neg()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_6_2_no_schema_workaround_triggered() -> None:
    """Vanilla schema."""
    events = _generate_neg()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_6_2_sequence_shape_7_events() -> None:
    events = _generate_neg()
    assert len(events) == 7


def test_neg_6_2_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, FILE_READ, NET_CONNECT, NET_SEND, NET_RECV,
    FILE_WRITE, FILE_RENAME."""
    events = _generate_neg()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.FILE_READ.value,
        EdgeType.NET_CONNECT.value,
        EdgeType.NET_SEND_NETWORK.value,
        EdgeType.NET_RECV_NETWORK.value,
        EdgeType.FILE_WRITE.value,
        EdgeType.FILE_RENAME.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_6_2_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate_neg()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: SEQUENCE-PAIR distinct lexical signature tests vs T1486 ransomware
# ---------------------------------------------------------------------------


def test_neg_6_2_pair_vs_t1486_file_rename_count_distinct() -> None:
    """Anchor (i): #6 NEG single FILE_RENAME (.new→.conf atomic swap);
    T1486 zero FILE_RENAME (uses FILE_DELETE)."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_renames = [ev for ev in neg_events if ev.operation == EdgeType.FILE_RENAME.value]
    t1486_renames = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_RENAME.value]
    assert (
        len(neg_renames) == 1
    ), f"NEG-6.2 must have exactly 1 FILE_RENAME (anchor (i)); got {len(neg_renames)}"
    assert len(t1486_renames) == 0, f"T1486 must have ZERO FILE_RENAME; got {len(t1486_renames)}"
    # Distinguishing: counts differ (1 vs 0) — non-mass-rename anchor
    assert len(neg_renames) != len(t1486_renames)


def test_neg_6_2_pair_vs_t1486_file_write_classification_distinct() -> None:
    """Anchor (ii)+(iii): #6 NEG plain config text writes; T1486 .locked
    encrypted writes."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_writes = [ev for ev in neg_events if ev.operation == EdgeType.FILE_WRITE.value]
    t1486_writes = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_WRITE.value]
    # NEG-6.2: 1 FILE_WRITE to .conf.new (plain text staging)
    assert len(neg_writes) == 1, f"NEG-6.2 must have exactly 1 FILE_WRITE; got {len(neg_writes)}"
    assert neg_writes[0].obj.endswith(
        ".new"
    ), f"NEG-6.2 FILE_WRITE must target .new staging file; got {neg_writes[0].obj!r}"
    # NEG-6.2 must NOT have .locked write
    for ev in neg_writes:
        assert not ev.obj.endswith(
            ".locked"
        ), f"NEG-6.2 must NOT have .locked write (anchor (iii)); got {ev.obj!r}"
    # T1486 has batch .locked writes
    locked_writes = [ev for ev in t1486_writes if ev.obj.endswith(".locked")]
    assert len(locked_writes) >= 2


def test_neg_6_2_pair_vs_t1486_file_delete_batch_absence() -> None:
    """#6 NEG zero FILE_DELETE; T1486 batch FILE_DELETE source files."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    neg_deletes = [ev for ev in neg_events if ev.operation == EdgeType.FILE_DELETE.value]
    t1486_deletes = [ev for ev in t1486_events if ev.operation == EdgeType.FILE_DELETE.value]
    assert len(neg_deletes) == 0, f"NEG-6.2 must have ZERO FILE_DELETE; got {len(neg_deletes)}"
    assert len(t1486_deletes) >= 2


def test_neg_6_2_pair_vs_t1486_sequence_length_distinct() -> None:
    """Sequence length distinct: NEG-6.2 = 7 events; T1486 = 9 events."""
    neg_events = _generate_neg()
    t1486_events = _generate_t1486()
    assert len(neg_events) == 7
    assert len(t1486_events) == 9
    assert len(neg_events) != len(t1486_events)


def test_neg_6_2_internal_repo_network_destination() -> None:
    """NET_CONNECT must go to internal_config_repo (not external IP)."""
    events = _generate_neg()
    net_connects = [ev for ev in events if ev.operation == EdgeType.NET_CONNECT.value]
    assert len(net_connects) == 1
    assert "internal_config_repo" in net_connects[0].obj


def test_neg_6_2_atomic_rename_to_conf() -> None:
    """Final FILE_RENAME atomic swap targets .conf path (write-back to original)."""
    events = _generate_neg()
    rename_events = [ev for ev in events if ev.operation == EdgeType.FILE_RENAME.value]
    assert len(rename_events) == 1
    assert rename_events[0].obj.endswith(
        ".conf"
    ), f"FILE_RENAME target must end .conf; got {rename_events[0].obj!r}"


def test_neg_6_2_label_zero_and_neg_id() -> None:
    events = _generate_neg()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-6.2"


def test_neg_6_2_seed_anchor() -> None:
    events = _generate_neg()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
