"""T#6.1 benign_fs_audit_log_scan — Hard Negative Template.

Class: #6 FS 操作 (per design propose §3.6 + §6.1)
NEG-ID: NEG-6.1
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.6 minimal sketch
    + §6.1 T1486 ransomware-mimicry pair sanity check + §5.6 schema
    readiness (vanilla, no workaround).

ATT&CK-like NEG-ID:
    NEG-6.1 — first of three FS-操作 hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.6 sub-pattern
    split (NEG-6.1 audit log scan / NEG-6.2 config sync task /
    NEG-6.3 sysadmin directory listing).

Distinct lexical signature + boundary (verbatim from design propose §3.6
plus Cycle H specific enhancement):
    Confound TTPs (T#6.1 verbatim from §3.6): T1083 file-and-directory-
    discovery / T1005 data-from-local-system. Sanity check pair: T1486
    ransomware-mimicry (per §6.1 detailed evaluation).

    Three anchors per template (派生自 §6.1 line 487-503 + §3.6 line
    128-143 verbatim):
      (i) Source-files-read-only — /var/log/auth.log + /var/log/secure +
          /var/log/syslog 全 FILE_READ (no FILE_WRITE / FILE_DELETE on
          source log files).
      (ii) audit_report.txt distinct write target single-file —
           /var/log/audit_report_<date>.txt 单 FILE_WRITE event 不是 batch
           加 .txt extension 与 T1486 .locked extension distinct.
      (iii) Plain-content non-encrypted — audit report 是文本格式 (plain
            ASCII / structured log) 非 encrypted bytes.

    Boundary (§3.6 verbatim):
        合法 audit log scan **是 cron-triggered + 写出 audit report 到
        local audit dir** 加 **不**包含 outbound network exfiltration
        (无 NET_CONNECT 到 external IP)。BERT-only 看 /var/log/* 词频与
        T1083 file-discovery share,区分必须靠 write-destination semantics
        + 缺失 exfil 链。**T1486 ransomware-mimicry 单独 sanity check 关键
        anchor**:本模板无 mass-rename to .lock/.crypt + 无 high-entropy
        write,§6.1 详细评估。

    Footnote (verbatim, must include): per NEEDS_CONTEXT #5 Option B 裁定
    user + 指导 Claude 共同 adjudicate 2026-05-08 per §14 clause; design
    propose §3.6 + §6.1 spec authoritative; v4 handoff §6.3 视为 v4
    handoff 撰写期 drafting drift; v5 handoff doc §6.3 + §11 item 4
    correction defer.

ALLOWED_EDGE_TRIPLES workaround reuse:
    Vanilla schema. All edge triples natively in ALLOWED_EDGE_TRIPLES.
    No workaround reuse. Zero new schema workaround inventory entries
    triggered. Triples used:
      - (user, USER_LOGON, process)            line 135
      - (process, FILE_READ, file)             line 110
      - (process, FILE_WRITE, file)            line 111
      - (process, PROCESS_EXIT, process)       line 123 (self-loop)

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON     (user → audit_scanner.exe — cron triggered)
          → FILE_READ  (audit_scanner → /var/log/auth.log)
          → FILE_READ  (audit_scanner → /var/log/secure)
          → FILE_READ  (audit_scanner → /var/log/syslog)
          → FILE_WRITE (audit_scanner → /var/log/audit_report_<date>.txt)
          → PROCESS_EXIT (audit_scanner → audit_scanner — clean exit)
    Length range: events_min=6, events_max=6 (deterministic cron-triggered
        audit log scan chain).
    Distinguishing structural pattern: 3 source-file FILE_READ events
        followed by SINGLE audit_report.txt FILE_WRITE — NO FILE_DELETE
        anywhere + NO FILE_RENAME (anchor (i)+(ii)) + .txt extension on
        single write target (anchor (ii) vs T1486 .locked extension batch)
        + plain-content semantic (anchor (iii) vs T1486 encrypted bytes).
        Cross-reference docstring item 3 三 anchors. Structurally disjoint
        from T1486 ransomware (which contains batch FILE_READ → FILE_WRITE
        .locked → FILE_DELETE triplet x N + RANSOM_NOTE.txt + NET_CONNECT
        c2_net) and from T1083 / T1005 (which would chain to NET_CONNECT
        exfil).
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_SCANNER = "audit_scanner.exe"
_AUTH_LOG = "/var/log/auth.log"
_SECURE_LOG = "/var/log/secure"
_SYSLOG = "/var/log/syslog"
_AUDIT_REPORT = "/var/log/audit_report_2026-05-09.txt"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_6_1"
_NEG_ID = "NEG-6.1"


class Neg61AuditLogScan(HardNegativeTemplate):
    """T#6.1 benign cron-triggered audit log scan workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_fs_audit_log_scan")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 6-event cron-triggered audit log scan chain.

        Anonymization-robust anchors:
          - Source log files are FILE_READ only (anchor (i)).
          - audit_report.txt single FILE_WRITE non-batch with .txt
            extension (anchor (ii) vs T1486 .locked batch).
          - Plain-content audit report (anchor (iii) vs T1486 encrypted).
          - No FILE_DELETE + no FILE_RENAME — structural disjoint from
            T1486 ransomware READ→WRITE.locked→DELETE triplet.
          - No NET_CONNECT — no exfil chain.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        scanner = f"neg_{iid}_{_SCANNER}"
        auth_log = f"neg_{iid}_{_AUTH_LOG}"
        secure_log = f"neg_{iid}_{_SECURE_LOG}"
        syslog = f"neg_{iid}_{_SYSLOG}"
        audit_report = f"neg_{iid}_{_AUDIT_REPORT}"

        n_events = 6
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
            # 1. Cron-triggered audit_scanner.exe launches under admin
            #    user context (cron service uid).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                scanner,
                NodeType.process,
            ),
            # 2. audit_scanner.exe FILE_READ /var/log/auth.log (source log
            #    read-only — anchor (i)).
            _ev(
                timestamps[1],
                scanner,
                NodeType.process,
                EdgeType.FILE_READ,
                auth_log,
                NodeType.file,
            ),
            # 3. audit_scanner.exe FILE_READ /var/log/secure.
            _ev(
                timestamps[2],
                scanner,
                NodeType.process,
                EdgeType.FILE_READ,
                secure_log,
                NodeType.file,
            ),
            # 4. audit_scanner.exe FILE_READ /var/log/syslog.
            _ev(
                timestamps[3],
                scanner,
                NodeType.process,
                EdgeType.FILE_READ,
                syslog,
                NodeType.file,
            ),
            # 5. audit_scanner.exe FILE_WRITE single audit_report_<date>.txt
            #    (anchor (ii) — single .txt write, not batch .locked).
            _ev(
                timestamps[4],
                scanner,
                NodeType.process,
                EdgeType.FILE_WRITE,
                audit_report,
                NodeType.file,
            ),
            # 6. audit_scanner.exe PROCESS_EXIT — clean exit. NO
            #    NET_CONNECT (no exfil) + NO FILE_DELETE / FILE_RENAME
            #    (structural disjoint from T1486 ransomware triplet).
            _ev(
                timestamps[5],
                scanner,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                scanner,
                NodeType.process,
            ),
        ]
