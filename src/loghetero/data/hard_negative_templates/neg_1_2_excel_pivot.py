"""T#1.2 benign_office_excel_pivot_edit — Hard Negative Template.

Class: #1 Office/Email Normal (per design propose §3.1)
NEG-ID: NEG-1.2
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.1 minimal sketch
    + §5.1 schema readiness (vanilla, no workaround).

ATT&CK-like NEG-ID:
    NEG-1.2 — second of three Office/Email-Normal hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.1 sub-pattern
    split (NEG-1.1 Outlook attachment / NEG-1.2 Excel pivot edit /
    NEG-1.3 Browser PDF download-open).

Distinct lexical signature + boundary (verbatim from design propose §3.1
plus Cycle H specific enhancement):
    Confound TTPs (T#1.2 verbatim from §3.1): T1204.002 user-execution-
    malicious-file.

    Three anchors per template (派生自 §3.1 line 72-73 boundary verbatim):
      (i) (excel.exe, PROCESS_CREATE, powershell.exe) absent — Office
          lock file write semantic 不伴随 macro-execute child shell.
      (ii) Outbound NET_CONNECT absent (no external network destination).
      (iii) Child-process+network 链 distinguishing vs T1204.002 reverse-
            shell-via-excel-macro pattern.

    Boundary (§3.1 verbatim):
        合法 Excel 编辑写 ~$ lock file 是 Office 标志特征;T1204.002
        reverse-shell-via-excel-macro 会有 (excel.exe, PROCESS_CREATE,
        powershell.exe) + outbound NET_CONNECT。BERT-only 仅看 excel.exe +
        .xlsx 词频不足以区分编辑 vs macro-execute;区分点必须靠
        child-process + network 链。

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
      - (process, PROCESS_CREATE, process)     line 120
      - (process, FILE_READ, file)             line 110
      - (process, FILE_WRITE, file)            line 111

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON      (user → explorer.exe)
          → PROCESS_CREATE (explorer → excel.exe)
          → FILE_READ   (excel → quarterly_report.xlsx)
          → FILE_WRITE  (excel → quarterly_report.xlsx — user save)
          → FILE_WRITE  (excel → ~$quarterly_report.xlsx — Office lock file)
    Length range: events_min=5, events_max=5 (deterministic Excel pivot
        edit chain — single workbook open + save + lock file write).
    Distinguishing structural pattern: terminal Office lock file write
        ~$<workbook>.xlsx is the Office-edit canonical signature; sequence
        terminates at lock-file write with NO downstream PROCESS_CREATE
        child shell from excel.exe + NO NET_CONNECT outbound. Structurally
        disjoint from T1204.002 reverse-shell-via-excel-macro which
        subsequently contains (excel.exe, PROCESS_CREATE, powershell.exe)
        + outbound NET_CONNECT to attacker-controlled host.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_EXPLORER = "explorer.exe"
_EXCEL = "excel.exe"
_WORKBOOK = r"C:\Users\benign_admin_user\Documents\quarterly_report.xlsx"
_LOCK_FILE = r"C:\Users\benign_admin_user\Documents\~$quarterly_report.xlsx"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_1_2"
_NEG_ID = "NEG-1.2"


class Neg12ExcelPivot(HardNegativeTemplate):
    """T#1.2 benign Excel pivot edit + Office lock file workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_office_excel_pivot_edit")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 5-event Excel pivot edit + Office lock file chain.

        Anonymization-robust anchors:
          - No (excel.exe, PROCESS_CREATE, powershell.exe) — Office lock
            file write 不伴随 macro-execute child shell.
          - No outbound NET_CONNECT (anchor vs T1204.002 reverse shell).
          - Terminal Office lock file ~$<workbook>.xlsx — Office-edit
            canonical signature.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        explorer = f"neg_{iid}_{_EXPLORER}"
        excel = f"neg_{iid}_{_EXCEL}"
        workbook = f"neg_{iid}_{_WORKBOOK}"
        lock_file = f"neg_{iid}_{_LOCK_FILE}"

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
            # 1. Admin user logs on, launches explorer.exe (interactive
            #    Office session shell).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                explorer,
                NodeType.process,
            ),
            # 2. explorer.exe spawns excel.exe (user double-clicks workbook).
            _ev(
                timestamps[1],
                explorer,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                excel,
                NodeType.process,
            ),
            # 3. excel.exe reads quarterly_report.xlsx (open workbook).
            _ev(
                timestamps[2],
                excel,
                NodeType.process,
                EdgeType.FILE_READ,
                workbook,
                NodeType.file,
            ),
            # 4. excel.exe writes quarterly_report.xlsx (user save after
            #    pivot edit).
            _ev(
                timestamps[3],
                excel,
                NodeType.process,
                EdgeType.FILE_WRITE,
                workbook,
                NodeType.file,
            ),
            # 5. excel.exe writes ~$quarterly_report.xlsx Office lock file
            #    — Office-edit canonical signature anchor. Sequence ends
            #    with NO excel.exe PROCESS_CREATE child shell + NO outbound
            #    NET_CONNECT (vs T1204.002 macro-execute reverse shell).
            _ev(
                timestamps[4],
                excel,
                NodeType.process,
                EdgeType.FILE_WRITE,
                lock_file,
                NodeType.file,
            ),
        ]
