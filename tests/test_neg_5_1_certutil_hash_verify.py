"""Unit tests for NEG-5.1 benign_certutil_hash_verify_patch hard-negative template.

Three test classes per Cycle G dispatch contract:
  - schema validation (all triples in ALLOWED_EDGE_TRIPLES, no workaround
    fallback needed — vanilla schema)
  - sequence shape (5-event deterministic shape per docstring)
  - distinct lexical signature (T#5.1 explicit caveat: hash-verify-against-
    trusted-list workflow + admin Group Policy/WSUS context anchor — verifies
    trusted-list FILE_READ before hashfile compute, .sha256 output co-located
    in C:\\Patches\\, no NET_CONNECT, no decoded-payload write)
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_5_1_certutil_hash_verify import (
    Neg51CertutilHashVerify,
)
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg51CertutilHashVerify()
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


def test_neg_5_1_schema_all_triples_in_allowed() -> None:
    """All emitted triples must be in ALLOWED_EDGE_TRIPLES (vanilla schema)."""
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert (
            triple in ALLOWED_EDGE_TRIPLES
        ), f"Disallowed triple {triple} in NEG-5.1 (vanilla schema expected)"


def test_neg_5_1_no_schema_workaround_triggered() -> None:
    """NEG-5.1 must NOT use any schema workaround pattern.

    Per design §5.5 vanilla schema. Verifies no svcctl pipe paths, no
    Registry\\ paths, no USER_PRIV_GRANT (only USER_LOGON for auth seed).
    """
    events = _generate()
    for ev in events:
        # No svcctl pipe-as-file workaround usage
        assert (
            "\\\\.\\pipe\\svcctl" not in ev.obj
        ), f"NEG-5.1 must NOT use svcctl pipe workaround; got obj={ev.obj!r}"
        # No registry-as-file workaround usage
        assert (
            "\\Registry\\" not in ev.obj
        ), f"NEG-5.1 must NOT use registry-as-file workaround; got obj={ev.obj!r}"
        # No USER_PRIV_GRANT (T1068 workaround #2 reuse) — vanilla USER_LOGON only
        assert (
            ev.operation != EdgeType.USER_PRIV_GRANT.value
        ), f"NEG-5.1 must NOT use USER_PRIV_GRANT workaround; got op={ev.operation!r}"


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_5_1_sequence_shape_5_events() -> None:
    """NEG-5.1 must generate exactly 5 events (deterministic shape)."""
    events = _generate()
    assert len(events) == 5, f"Expected 5 events, got {len(events)}"


def test_neg_5_1_sequence_shape_ordered_edge_types() -> None:
    """Edge types must follow USER_LOGON → FILE_READ → FILE_READ → FILE_WRITE → PROCESS_EXIT."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_READ.value,
        EdgeType.FILE_WRITE.value,
        EdgeType.PROCESS_EXIT.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert (
        actual_ops == expected_ops
    ), f"Sequence shape mismatch: expected {expected_ops}, got {actual_ops}"


def test_neg_5_1_timestamps_in_window() -> None:
    """All event timestamps must lie within the [t_start, t_end] window."""
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature (T#5.1 explicit caveat)
# ---------------------------------------------------------------------------


def test_neg_5_1_trusted_hash_list_read_before_hashfile_compute() -> None:
    """Verify-against-trusted-list workflow anchor (caveat (c)).

    The trusted hash list FILE_READ MUST occur BEFORE the source-MSU
    FILE_READ + .sha256 FILE_WRITE — this encodes the "admin reads
    trusted-list to know what hash to expect" workflow, distinct from
    T1105 ingress-tool-transfer (never reads trusted-hash list).
    """
    events = _generate()
    # Event 2 (index 1) must read the trusted hash list
    ev_trusted_read = events[1]
    assert ev_trusted_read.operation == EdgeType.FILE_READ.value
    assert "trusted_hashes.txt" in ev_trusted_read.obj, (
        f"Event 2 must FILE_READ trusted_hashes.txt (verify-against-list "
        f"workflow anchor); got obj={ev_trusted_read.obj!r}"
    )
    # Event 3 must read the source MSU
    ev_msu_read = events[2]
    assert ev_msu_read.operation == EdgeType.FILE_READ.value
    assert (
        ".msu" in ev_msu_read.obj
    ), f"Event 3 must FILE_READ source MSU; got obj={ev_msu_read.obj!r}"
    assert ev_trusted_read.timestamp_ns < ev_msu_read.timestamp_ns


def test_neg_5_1_admin_managed_patches_dir_co_location() -> None:
    """C:\\Patches\\ admin-managed staging-dir co-location anchor (caveats (a)+(b)).

    Source MSU + .sha256 hash output MUST share the C:\\Patches\\ prefix —
    co-location with managed patch staging area is the WSUS / SCCM /
    Group Policy Software Installation admin-context anchor, distinct from
    T1105 (which would NOT co-locate hash with patch staging dir).
    """
    events = _generate()
    msu_obj = events[2].obj  # source MSU read
    hash_obj = events[3].obj  # .sha256 write
    assert (
        "C:\\Patches\\" in msu_obj
    ), f"Source MSU must be under C:\\Patches\\ admin-managed dir; got {msu_obj!r}"
    assert (
        "C:\\Patches\\" in hash_obj
    ), f".sha256 hash must be co-located in C:\\Patches\\; got {hash_obj!r}"
    assert hash_obj.endswith(
        ".sha256"
    ), f"Output file must be .sha256 (hash output) NOT decoded payload; got {hash_obj!r}"


def test_neg_5_1_no_net_connect_anonymization_anchor() -> None:
    """Caveat (d): NO NET_CONNECT in sequence (anonymization-robust vs T1105)."""
    events = _generate()
    for ev in events:
        assert ev.operation != EdgeType.NET_CONNECT.value, (
            f"NEG-5.1 must have NO NET_CONNECT (anonymization-robust vs T1105 "
            f"ingress-tool-transfer); got {ev.operation!r}"
        )


def test_neg_5_1_no_decoded_payload_file_write() -> None:
    """Caveat (e): NO FILE_WRITE to .exe/.dll/.ps1 (anonymization-robust vs T1140)."""
    events = _generate()
    forbidden_extensions = (".exe", ".dll", ".ps1")
    for ev in events:
        if ev.operation == EdgeType.FILE_WRITE.value:
            for ext in forbidden_extensions:
                assert not ev.obj.endswith(ext), (
                    f"NEG-5.1 must NOT FILE_WRITE to {ext} (decoded-payload "
                    f"anchor vs T1140 deobfuscate-decode-files); got {ev.obj!r}"
                )


def test_neg_5_1_label_zero_and_neg_id() -> None:
    """All events must carry label=0 (benign) + neg_id=NEG-5.1."""
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-5.1"


def test_neg_5_1_seed_anchor() -> None:
    """First event must have subject=seed_user (USER_LOGON anchor)."""
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
