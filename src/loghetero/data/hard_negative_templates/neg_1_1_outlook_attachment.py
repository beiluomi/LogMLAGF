"""T#1.1 benign_office_outlook_attachment_view — Hard Negative Template.

Class: #1 Office/Email Normal (per design propose §3.1)
NEG-ID: NEG-1.1
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.1 minimal sketch
    + §5.1 schema readiness (vanilla, no workaround).

ATT&CK-like NEG-ID:
    NEG-1.1 — first of three Office/Email-Normal hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.1 sub-pattern
    split (NEG-1.1 Outlook attachment / NEG-1.2 Excel pivot edit /
    NEG-1.3 Browser PDF download-open).

Distinct lexical signature + boundary (verbatim from design propose §3.1
plus Cycle H specific enhancement):
    Confound TTPs (T#1.1 verbatim from §3.1): T1566.001 spearphishing-
    attachment.

    Three anchors per template (派生自 §3.1 line 67-68 boundary verbatim):
      (i) Process-tree depth — winword.exe 不 PROCESS_CREATE cmd.exe /
          powershell.exe (无 macro spawning child shell).
      (ii) Outbound C2 connection absent (no NET_CONNECT to external).
      (iii) Child-process-class signal 区分 vs T1566.001 共享前 4 步 shape
            — distinguishing point靠 process-tree depth + child-process-
            class signal 而非 token 词频, avoid BERT-only saturate.

    Boundary (§3.1 verbatim):
        合法 Outlook → Word 链 **不**含 macro spawning child shell(无
        (winword.exe, PROCESS_CREATE, cmd.exe/powershell.exe))+ **不**含
        outbound C2 connection。BERT-only 看 lexical 仅 outlook.exe +
        winword.exe + .docx 词频;与 T1566.001 共享前 4 步 shape,区分点
        必须靠 process-tree depth + child-process-class signal 而非 token
        词频,避免 BERT-only saturate。

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
      - (process, FILE_WRITE, file)            line 111
      - (process, PROCESS_CREATE, process)     line 120
      - (process, FILE_READ, file)             line 110

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON      (user → outlook.exe)
          → FILE_WRITE  (outlook.exe → attachment.docx — saved to disk)
          → PROCESS_CREATE (outlook.exe → winword.exe)
          → FILE_READ   (winword.exe → attachment.docx)
          → FILE_WRITE  (winword.exe → attachment.docx — user 编辑保存)
    Length range: events_min=5, events_max=5 (deterministic Outlook→Word
        view+edit chain).
    Distinguishing structural pattern: 2-deep process chain outlook→winword
        with leaf process winword.exe terminating without PROCESS_CREATE
        downstream — anchor (i) child-process-class signal absent +
        anchor (ii) NO NET_CONNECT in entire sequence + anchor (iii)
        process tree depth = 2 with NO macro-spawned shell. Structurally
        disjoint from T1566.001 spearphishing-attachment which subsequently
        contains macro-driven (winword.exe, PROCESS_CREATE, powershell.exe
        / cmd.exe) + outbound NET_CONNECT to C2.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_OUTLOOK = "outlook.exe"
_WINWORD = "winword.exe"
_ATTACHMENT = r"C:\Users\benign_admin_user\Documents\attachment.docx"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_1_1"
_NEG_ID = "NEG-1.1"


class Neg11OutlookAttachment(HardNegativeTemplate):
    """T#1.1 benign Outlook → Word attachment view + edit workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_office_outlook_attachment_view")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 5-event Outlook attachment view + Word edit chain.

        Anonymization-robust anchors:
          - No PROCESS_CREATE child shell from winword.exe (depth=2 anchor
            vs T1566.001 macro chain).
          - No NET_CONNECT in entire sequence (anchor vs T1566.001 C2 beacon).
          - Process tree leaf is winword.exe (not cmd.exe / powershell.exe)
            — child-process-class signal anchor.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        outlook = f"neg_{iid}_{_OUTLOOK}"
        winword = f"neg_{iid}_{_WINWORD}"
        attachment = f"neg_{iid}_{_ATTACHMENT}"

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
            # 1. Admin user logs on, launches outlook.exe (interactive
            #    Office user session).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                outlook,
                NodeType.process,
            ),
            # 2. outlook.exe writes the attachment.docx to local Documents
            #    (Outlook default attachment save path).
            _ev(
                timestamps[1],
                outlook,
                NodeType.process,
                EdgeType.FILE_WRITE,
                attachment,
                NodeType.file,
            ),
            # 3. outlook.exe spawns winword.exe to open the attachment
            #    (process-tree depth=2 anchor — no shell spawn).
            _ev(
                timestamps[2],
                outlook,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                winword,
                NodeType.process,
            ),
            # 4. winword.exe reads the attachment.docx (open for view).
            _ev(
                timestamps[3],
                winword,
                NodeType.process,
                EdgeType.FILE_READ,
                attachment,
                NodeType.file,
            ),
            # 5. winword.exe writes the attachment.docx (user 编辑保存
            #    after viewing — legitimate Word save). Sequence ends here
            #    with NO winword PROCESS_CREATE child shell + NO NET_CONNECT.
            _ev(
                timestamps[4],
                winword,
                NodeType.process,
                EdgeType.FILE_WRITE,
                attachment,
                NodeType.file,
            ),
        ]
