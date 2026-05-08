"""Unit tests for NEG-7.1 benign_driver_install_printer hard-negative template.

Schema-workaround reuse (verified by schema test class):
  - USER_PRIV_GRANT user-anchor reuses T1068 workaround #2.
  - svcctl pipe-as-file reuses T1543.003 sc.exe pattern.
  - Driver-registry-as-file reuses T1547.001 pattern.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_7_1_driver_install_printer import (
    Neg71DriverInstallPrinter,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg71DriverInstallPrinter()
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
# Class 1: schema validation (3 workaround reuses)
# ---------------------------------------------------------------------------


def test_neg_7_1_schema_all_triples_in_allowed() -> None:
    """All emitted triples must be in ALLOWED_EDGE_TRIPLES."""
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_7_1_user_priv_grant_workaround_reuse_t1068_pattern() -> None:
    """USER_PRIV_GRANT workaround #2 reuse: subject is seed_user (NOT process)."""
    events = _generate()
    priv_grant_events = [ev for ev in events if ev.operation == EdgeType.USER_PRIV_GRANT.value]
    assert len(priv_grant_events) == 1
    ev = priv_grant_events[0]
    assert ev.subject_type == NodeType.user, (
        f"USER_PRIV_GRANT subject must be user (T1068 workaround #2 reuse); "
        f"got {ev.subject_type!r}"
    )
    assert ev.subject == "benign_admin_user"


def test_neg_7_1_svcctl_pipe_path_matches_t1543_003_workaround() -> None:
    """svcctl pipe path FILE_WRITE reuses T1543.003 sc.exe pattern.

    The path \\\\.\\pipe\\svcctl is modeled as a file node target of
    FILE_WRITE — same pattern as T1543.003 attack template (no new
    inventory entry triggered). Cross-reference: known_issues.md lines
    437-440 inventory remains at 4 entries.
    """
    events = _generate()
    svcctl_writes = [
        ev
        for ev in events
        if ev.operation == EdgeType.FILE_WRITE.value and r"\\.\pipe\svcctl" in ev.obj
    ]
    assert (
        len(svcctl_writes) == 1
    ), f"NEG-7.1 must emit exactly 1 svcctl pipe FILE_WRITE; got {len(svcctl_writes)}"
    ev = svcctl_writes[0]
    assert ev.subject_type == NodeType.process
    assert (
        ev.obj_type == NodeType.file
    ), f"svcctl pipe must be modeled as file node (T1543.003 reuse); got {ev.obj_type!r}"


def test_neg_7_1_registry_path_matches_t1547_001_workaround() -> None:
    """Driver registry IMAGEPATH FILE_WRITE reuses T1547.001 registry-as-file.

    The path \\Registry\\Machine\\... is modeled as file node target of
    FILE_WRITE — same pattern as T1547.001 attack template (no new
    inventory entry triggered).
    """
    events = _generate()
    registry_writes = [
        ev
        for ev in events
        if ev.operation == EdgeType.FILE_WRITE.value and "\\Registry\\Machine\\" in ev.obj
    ]
    assert (
        len(registry_writes) == 1
    ), f"NEG-7.1 must emit exactly 1 driver-registry FILE_WRITE; got {len(registry_writes)}"
    ev = registry_writes[0]
    assert "ImagePath" in ev.obj, f"Driver registry write must target ImagePath; got {ev.obj!r}"
    assert (
        ev.obj_type == NodeType.file
    ), f"Registry path must be modeled as file node (T1547.001 reuse); got {ev.obj_type!r}"


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_7_1_sequence_shape_7_events() -> None:
    events = _generate()
    assert len(events) == 7


def test_neg_7_1_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, USER_PRIV_GRANT, 4x FILE_WRITE, PROCESS_EXIT."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.USER_PRIV_GRANT.value,
        EdgeType.FILE_WRITE.value,  # DriverStore staging
        EdgeType.FILE_WRITE.value,  # drivers/<file>.sys copy
        EdgeType.FILE_WRITE.value,  # svcctl pipe
        EdgeType.FILE_WRITE.value,  # registry IMAGEPATH
        EdgeType.PROCESS_EXIT.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_7_1_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature
# ---------------------------------------------------------------------------


def test_neg_7_1_driverstore_staging_first_anchor() -> None:
    """Anchor (a): FIRST .sys FILE_WRITE goes to DriverStore staging path.

    Distinguishing structural pattern vs T1547.006 attack drivers that
    SKIP DriverStore and write directly to drivers/.
    """
    events = _generate()
    # Event 3 (index 2) = first .sys write = DriverStore staging
    ev_first_sys = events[2]
    assert ev_first_sys.operation == EdgeType.FILE_WRITE.value
    assert (
        "DriverStore\\FileRepository" in ev_first_sys.obj
    ), f"First .sys write must target DriverStore staging; got {ev_first_sys.obj!r}"
    assert ev_first_sys.obj.endswith(".sys")
    # Event 4 (index 3) = drivers/ copy (must come AFTER DriverStore staging)
    ev_drivers_sys = events[3]
    assert "System32\\drivers\\" in ev_drivers_sys.obj
    assert ev_drivers_sys.obj.endswith(".sys")
    assert ev_first_sys.timestamp_ns < ev_drivers_sys.timestamp_ns


def test_neg_7_1_no_process_create_downstream() -> None:
    """Anchor (b): process tree depth = 1, no PROCESS_CREATE downstream.

    Structural anchor vs T1543.003 attack which spawns malicious_service.exe.
    """
    events = _generate()
    for ev in events:
        assert (
            ev.operation != EdgeType.PROCESS_CREATE.value
        ), f"NEG-7.1 must have NO PROCESS_CREATE (depth=1 anchor); got {ev.operation!r}"


def test_neg_7_1_no_net_connect() -> None:
    """Anchor (c): NO NET_CONNECT — printer driver install is local-only."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value


def test_neg_7_1_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-7.1"
