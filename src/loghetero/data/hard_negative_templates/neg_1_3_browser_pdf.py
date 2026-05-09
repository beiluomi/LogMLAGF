"""T#1.3 benign_office_browser_pdf_download_open — Hard Negative Template.

Class: #1 Office/Email Normal (per design propose §3.1)
NEG-ID: NEG-1.3
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.1 minimal sketch
    + §5.1 schema readiness (vanilla, no workaround).

ATT&CK-like NEG-ID:
    NEG-1.3 — third of three Office/Email-Normal hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.1 sub-pattern
    split (NEG-1.1 Outlook attachment / NEG-1.2 Excel pivot edit /
    NEG-1.3 Browser PDF download-open).

Distinct lexical signature + boundary (verbatim from design propose §3.1
plus Cycle H specific enhancement):
    Confound TTPs (T#1.3 verbatim from §3.1): T1566.002 spearphishing-link
    / T1204.001 user-execution-malicious-link.

    Three anchors per template (派生自 §3.1 line 77-78 boundary verbatim):
      (i) (AcroRd32.exe, NET_CONNECT, c2_net) absent — AcroRd32 leaf
          process does not initiate outbound network.
      (ii) (AcroRd32.exe, PROCESS_CREATE, *) absent — AcroRd32 leaf
           process does not spawn any child process.
      (iii) Downstream process-tree + outbound-network signal
            distinguishing vs spearphishing-link follow-on chain.

    Boundary (§3.1 verbatim):
        合法 PDF 下载-打开链 **不**含 (AcroRd32.exe, NET_CONNECT, c2_net)
        加 **不**含 (AcroRd32.exe, PROCESS_CREATE, *)。BERT-only 看 chrome
        + AcroRd32 + .pdf 词频与 spearphishing-link 共享,区分必须靠下游
        process-tree + outbound-network signal。

    Footnote (verbatim, must include): per NEEDS_CONTEXT #6 Option B 裁定
    user + 指导 Claude 共同 adjudicate 2026-05-08 per §14 clause; design
    propose §3.1 spec authoritative; v4 handoff §6.5 + §11 item 6 confound
    TTPs T1059.001 + T1218 视为 v4 handoff 撰写期 drafting drift; T#1.1
    T1566 generic 加 T1566.001 sub-technique covered; v5 handoff doc §6.5
    + §11 item 6 correction defer.

ALLOWED_EDGE_TRIPLES workaround reuse:
    Vanilla schema. All edge triples natively in ALLOWED_EDGE_TRIPLES.
    No workaround reuse. Zero new schema workaround inventory entries
    triggered. Triples used:
      - (user, USER_LOGON, process)            line 135
      - (process, NET_HTTP_REQUEST, network)   line 131
      - (process, FILE_WRITE, file)            line 111
      - (process, PROCESS_CREATE, process)     line 120
      - (process, FILE_READ, file)             line 110

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON          (user → chrome.exe)
          → NET_HTTP_REQUEST (chrome → vendor_pdf_url)
          → FILE_WRITE       (chrome → vendor_quote.pdf)
          → PROCESS_CREATE   (chrome → AcroRd32.exe)
          → FILE_READ        (AcroRd32 → vendor_quote.pdf)
    Length range: events_min=5, events_max=5 (deterministic browser PDF
        download-open chain).
    Distinguishing structural pattern: AcroRd32.exe is the leaf process
        with NO downstream PROCESS_CREATE + NO downstream NET_CONNECT —
        sequence terminates at FILE_READ of the just-downloaded PDF.
        Structurally disjoint from T1566.002 spearphishing-link / T1204.001
        which subsequently contain (AcroRd32.exe, NET_CONNECT, c2_net) +
        (AcroRd32.exe, PROCESS_CREATE, *) follow-on chain. The chrome.exe
        NET_HTTP_REQUEST upstream is to vendor_pdf_url (well-known vendor
        URL semantic) NOT to attacker-controlled link.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_CHROME = "chrome.exe"
_ACRORD32 = "AcroRd32.exe"
_VENDOR_PDF_URL = "vendor_pdf_url:443/quote.pdf"
_PDF_FILE = r"C:\Users\benign_admin_user\Downloads\vendor_quote.pdf"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_1_3"
_NEG_ID = "NEG-1.3"


class Neg13BrowserPdf(HardNegativeTemplate):
    """T#1.3 benign Browser PDF download + open workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_office_browser_pdf_download_open")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 5-event Browser PDF download + Acrobat Reader open chain.

        Anonymization-robust anchors:
          - No (AcroRd32.exe, NET_CONNECT, *) — leaf process is read-only.
          - No (AcroRd32.exe, PROCESS_CREATE, *) — leaf process does not
            spawn child.
          - Browser request to vendor_pdf_url (well-known vendor URL),
            not attacker-controlled link.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        chrome = f"neg_{iid}_{_CHROME}"
        acrord = f"neg_{iid}_{_ACRORD32}"
        vendor_pdf_url = f"neg_{iid}_{_VENDOR_PDF_URL}"
        pdf_file = f"neg_{iid}_{_PDF_FILE}"

        n_events = 5
        span = t_end_ns - t_start_ns
        base_step = span // n_events
        timestamps = [
            t_start_ns + k * base_step + rng.randint(0, max(1, base_step // 4))
            for k in range(n_events)
        ]
        timestamps.sort()

        attrs_base = {
            "neg_id": self.neg_id,
            "instance_id": iid,
            "label": 0,
        }

        def _ev(
            ts: int,
            subj: str,
            s_type: NodeType,
            op: EdgeType,
            obj: str,
            o_type: NodeType,
        ) -> Event:
            return Event(
                timestamp_ns=ts,
                subject=subj,
                subject_type=s_type,
                obj=obj,
                obj_type=o_type,
                operation=op.value,
                log_type=_LOG_TYPE,
                scenario_id=_SCENARIO,
                host_id=_HOST,
                attributes=dict(attrs_base),
            )

        return [
            # 1. Admin user logs on, launches chrome.exe (interactive
            #    browser session).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                chrome,
                NodeType.process,
            ),
            # 2. chrome.exe issues HTTPS GET to vendor_pdf_url (well-known
            #    vendor PDF endpoint).
            _ev(
                timestamps[1],
                chrome,
                NodeType.process,
                EdgeType.NET_HTTP_REQUEST,
                vendor_pdf_url,
                NodeType.network,
            ),
            # 3. chrome.exe writes vendor_quote.pdf to Downloads folder.
            _ev(
                timestamps[2],
                chrome,
                NodeType.process,
                EdgeType.FILE_WRITE,
                pdf_file,
                NodeType.file,
            ),
            # 4. chrome.exe spawns AcroRd32.exe to open the PDF.
            _ev(
                timestamps[3],
                chrome,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                acrord,
                NodeType.process,
            ),
            # 5. AcroRd32.exe reads vendor_quote.pdf (terminal leaf — NO
            #    downstream PROCESS_CREATE + NO downstream NET_CONNECT
            #    vs T1566.002 spearphishing-link follow-on chain).
            _ev(
                timestamps[4],
                acrord,
                NodeType.process,
                EdgeType.FILE_READ,
                pdf_file,
                NodeType.file,
            ),
        ]
