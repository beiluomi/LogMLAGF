"""Unit tests for NEG-2.1 benign_webserver_apache_cgi_perl hard-negative template."""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_2_1_apache_cgi_perl import (
    Neg21ApacheCgiPerl,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg21ApacheCgiPerl()
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


def test_neg_2_1_schema_all_triples_in_allowed() -> None:
    """All emitted triples must be in ALLOWED_EDGE_TRIPLES (vanilla schema)."""
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert (
            triple in ALLOWED_EDGE_TRIPLES
        ), f"Disallowed triple {triple} in NEG-2.1 (vanilla schema expected)"


def test_neg_2_1_no_schema_workaround_triggered() -> None:
    """Vanilla schema only — no svcctl, no registry-as-file, no PRIV_GRANT reuse."""
    events = _generate()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_2_1_sequence_shape_6_events() -> None:
    """NEG-2.1 must generate exactly 6 events (deterministic shape)."""
    events = _generate()
    assert len(events) == 6, f"Expected 6 events, got {len(events)}"


def test_neg_2_1_sequence_shape_ordered_edge_types() -> None:
    """Edge types: NET_ACCEPT → PROCESS_CREATE → FILE_READ → FILE_READ → FILE_WRITE → PROCESS_EXIT."""
    events = _generate()
    expected_ops = [
        EdgeType.NET_ACCEPT.value,
        EdgeType.PROCESS_CREATE.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_WRITE.value,
        EdgeType.PROCESS_EXIT.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_2_1_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature
# ---------------------------------------------------------------------------


def test_neg_2_1_file_write_only_to_tmp_render() -> None:
    """Anchor (a): FILE_WRITE only to /tmp/ render path — NOT /var/www/*.php."""
    events = _generate()
    for ev in events:
        if ev.operation == EdgeType.FILE_WRITE.value:
            assert "/tmp/" in ev.obj, f"FILE_WRITE must target /tmp/ render path; got {ev.obj!r}"
            for ext in (".php", ".jsp", ".aspx"):
                assert not ev.obj.endswith(
                    ext
                ), f"FILE_WRITE must NOT write webshell extension {ext}; got {ev.obj!r}"
            assert (
                "/var/www/" not in ev.obj
            ), f"FILE_WRITE must NOT target /var/www/ webshell drop; got {ev.obj!r}"


def test_neg_2_1_no_outbound_net_connect_from_perl() -> None:
    """Anchor (b): NO NET_CONNECT outbound from perl.exe (vs T1190 reverse-shell)."""
    events = _generate()
    for ev in events:
        assert (
            ev.operation != EdgeType.NET_CONNECT.value
        ), f"NEG-2.1 must have NO NET_CONNECT outbound; got {ev.operation!r}"


def test_neg_2_1_process_tree_depth_2() -> None:
    """Anchor (c): process tree depth = 2 (apache→perl→exit) — no shell spawn."""
    events = _generate()
    process_creates = [ev for ev in events if ev.operation == EdgeType.PROCESS_CREATE.value]
    # Exactly 1 PROCESS_CREATE (apache → perl); no further child spawn
    assert (
        len(process_creates) == 1
    ), f"NEG-2.1 must have exactly 1 PROCESS_CREATE (depth=2); got {len(process_creates)}"


def test_neg_2_1_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-2.1"
