"""Unit tests for NEG-1.3 benign_office_browser_pdf_download_open hard-negative template.

Three test classes:
  - schema validation (vanilla schema)
  - sequence shape (5-event deterministic shape)
  - distinct lexical signature (T#1.3 anchors: AcroRd32 no NET_CONNECT,
    AcroRd32 no PROCESS_CREATE, downstream signal distinguishing)
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.neg_1_3_browser_pdf import Neg13BrowserPdf
from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _generate(seed: int = 42, iid: int = 0) -> list:
    template = Neg13BrowserPdf()
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


def test_neg_1_3_schema_all_triples_in_allowed() -> None:
    events = _generate()
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES


def test_neg_1_3_no_schema_workaround_triggered() -> None:
    events = _generate()
    for ev in events:
        assert "\\\\.\\pipe\\svcctl" not in ev.obj
        assert "\\Registry\\" not in ev.obj
        assert ev.operation != EdgeType.USER_PRIV_GRANT.value


# ---------------------------------------------------------------------------
# Class 2: sequence shape
# ---------------------------------------------------------------------------


def test_neg_1_3_sequence_shape_5_events() -> None:
    events = _generate()
    assert len(events) == 5


def test_neg_1_3_sequence_shape_ordered_edge_types() -> None:
    """Edge types: USER_LOGON, NET_HTTP_REQUEST, FILE_WRITE, PROCESS_CREATE, FILE_READ."""
    events = _generate()
    expected_ops = [
        EdgeType.USER_LOGON.value,
        EdgeType.NET_HTTP_REQUEST.value,
        EdgeType.FILE_WRITE.value,
        EdgeType.PROCESS_CREATE.value,
        EdgeType.FILE_READ.value,
    ]
    actual_ops = [ev.operation for ev in events]
    assert actual_ops == expected_ops


def test_neg_1_3_timestamps_in_window() -> None:
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = _generate()
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end


# ---------------------------------------------------------------------------
# Class 3: distinct lexical signature (T#1.3 three anchors)
# ---------------------------------------------------------------------------


def test_neg_1_3_acrord32_no_net_connect() -> None:
    """Anchor (i): AcroRd32.exe must NOT initiate NET_CONNECT."""
    events = _generate()
    for ev in events:
        # AcroRd32 is never the subject of any network operation
        if "AcroRd32.exe" in ev.subject:
            assert ev.operation != EdgeType.NET_CONNECT.value, (
                f"NEG-1.3 AcroRd32.exe must NOT initiate NET_CONNECT "
                f"(c2_net absent anchor vs spearphishing-link); "
                f"got op={ev.operation!r}"
            )
            assert ev.operation != EdgeType.NET_SEND_NETWORK.value
            assert ev.operation != EdgeType.NET_HTTP_REQUEST.value


def test_neg_1_3_acrord32_no_process_create() -> None:
    """Anchor (ii): AcroRd32.exe must NOT spawn any child process."""
    events = _generate()
    for ev in events:
        if "AcroRd32.exe" in ev.subject:
            assert ev.operation != EdgeType.PROCESS_CREATE.value, (
                f"NEG-1.3 AcroRd32.exe must NOT PROCESS_CREATE child "
                f"(downstream tree absent anchor); got op={ev.operation!r}"
            )


def test_neg_1_3_acrord32_terminal_leaf() -> None:
    """Anchor (iii): sequence terminates with AcroRd32.exe FILE_READ
    (no downstream)."""
    events = _generate()
    final_ev = events[4]
    assert final_ev.operation == EdgeType.FILE_READ.value
    assert (
        "AcroRd32.exe" in final_ev.subject
    ), f"Final event must be AcroRd32.exe FILE_READ; got subject={final_ev.subject!r}"
    assert final_ev.obj.endswith(".pdf")


def test_neg_1_3_chrome_request_to_vendor_url() -> None:
    """Browser NET_HTTP_REQUEST goes to vendor_pdf_url (not attacker link)."""
    events = _generate()
    http_events = [ev for ev in events if ev.operation == EdgeType.NET_HTTP_REQUEST.value]
    assert len(http_events) == 1
    ev = http_events[0]
    assert "chrome.exe" in ev.subject
    assert (
        "vendor_pdf_url" in ev.obj
    ), f"NET_HTTP_REQUEST must go to vendor_pdf_url; got obj={ev.obj!r}"


def test_neg_1_3_label_zero_and_neg_id() -> None:
    events = _generate()
    for ev in events:
        assert ev.attributes.get("label") == 0
        assert ev.attributes.get("neg_id") == "NEG-1.3"


def test_neg_1_3_seed_anchor() -> None:
    events = _generate()
    assert events[0].subject == "benign_admin_user"
    assert events[0].subject_type == NodeType.user
