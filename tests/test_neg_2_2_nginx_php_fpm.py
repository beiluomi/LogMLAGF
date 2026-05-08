"""Unit tests for NEG-2.2 benign_webserver_nginx_php_fpm hard-negative template."""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_2_2_nginx_php_fpm import (
    Neg22NginxPhpFpm,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg22NginxPhpFpm()
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


def test_neg_2_2_schema_all_triples_in_allowed() -> None:
    """All emitted triples must be in ALLOWED_EDGE_TRIPLES (vanilla schema)."""
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert (
            triple in ALLOWED_EDGE_TRIPLES
        ), f"Disallowed triple {triple} in NEG-2.2 (vanilla schema expected)"


def test_neg_2_2_uses_net_send_socket_to_socket_node() -> None:
    """NET_SEND_SOCKET must target a socket-typed node (FastCGI bridge anchor)."""
    events = _generate()
    socket_sends = [ev for ev in events if ev.operation == EdgeType.NET_SEND_SOCKET.value]
    assert (
        len(socket_sends) == 1
    ), f"NEG-2.2 must emit exactly 1 NET_SEND_SOCKET (FastCGI bridge); got {len(socket_sends)}"
    assert socket_sends[0].obj_type == NodeType.socket


def test_neg_2_2_no_schema_workaround_triggered() -> None:
    """Vanilla schema only — no svcctl, no registry-as-file, no PRIV_GRANT reuse."""
    events = _generate()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_2_2_sequence_shape_6_events() -> None:
    """NEG-2.2 must generate exactly 6 events (deterministic shape)."""
    events = _generate()
    assert len(events) == 6


def test_neg_2_2_sequence_shape_ordered_edge_types() -> None:
    """Edge types: NET_ACCEPT → NET_SEND_SOCKET → FILE_READ → NET_CONNECT → NET_SEND_NETWORK → NET_RECV_NETWORK."""
    events = _generate()
    expected_ops = [
        EdgeType.NET_ACCEPT.value,
        EdgeType.NET_SEND_SOCKET.value,
        EdgeType.FILE_READ.value,
        EdgeType.NET_CONNECT.value,
        EdgeType.NET_SEND_NETWORK.value,
        EdgeType.NET_RECV_NETWORK.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_2_2_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature
# ---------------------------------------------------------------------------


def test_neg_2_2_no_file_write_anywhere() -> None:
    """Anchor (a): NO FILE_WRITE anywhere — PHP-FPM serves PHP, doesn't drop webshell."""
    events = _generate()
    for ev in events:
        assert (
            ev.operation != EdgeType.FILE_WRITE.value
        ), f"NEG-2.2 must have NO FILE_WRITE (PHP-FPM serves only); got {ev.operation!r}"


def test_neg_2_2_no_process_create_child() -> None:
    """Anchor (b): NO PROCESS_CREATE child from php-fpm.exe (no shell spawn)."""
    events = _generate()
    for ev in events:
        assert (
            ev.operation != EdgeType.PROCESS_CREATE.value
        ), f"NEG-2.2 must have NO PROCESS_CREATE (no shell-utility spawn); got {ev.operation!r}"


def test_neg_2_2_internal_db_backend_destination() -> None:
    """Anchor (d): NET_CONNECT/SEND/RECV all to internal_db_backend_network (RFC1918 anchor)."""
    events = _generate()
    db_ops = [
        ev
        for ev in events
        if ev.operation
        in (
            EdgeType.NET_CONNECT.value,
            EdgeType.NET_SEND_NETWORK.value,
            EdgeType.NET_RECV_NETWORK.value,
        )
    ]
    assert len(db_ops) == 3, f"NEG-2.2 must have 3 DB-bound network events; got {len(db_ops)}"
    for ev in db_ops:
        assert (
            "internal_db_backend_network" in ev.obj
        ), f"DB-bound network event must target internal_db_backend_network; got {ev.obj!r}"


def test_neg_2_2_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-2.2"
