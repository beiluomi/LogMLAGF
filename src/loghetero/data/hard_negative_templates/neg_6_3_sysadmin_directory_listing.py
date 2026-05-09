"""T#6.3 benign_fs_sysadmin_directory_listing — Hard Negative Template.

Class: #6 FS 操作 (per design propose §3.6 + §6.1)
NEG-ID: NEG-6.3
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.6 minimal sketch
    + §6.1 T1486 ransomware-mimicry pair sanity check + §5.6 schema
    readiness (vanilla, no workaround).

ATT&CK-like NEG-ID:
    NEG-6.3 — third of three FS-操作 hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.6 sub-pattern
    split (NEG-6.1 audit log scan / NEG-6.2 config sync task /
    NEG-6.3 sysadmin directory listing).

Distinct lexical signature + boundary (verbatim from design propose §3.6
plus Cycle H specific enhancement):
    Confound TTPs (T#6.3 verbatim from §3.6): T1083 file-and-directory-
    discovery / T1003.008 /etc/passwd-and-/etc/shadow. Sanity check pair:
    T1486 ransomware-mimicry (per §6.1 detailed evaluation).

    Three anchors per template (派生自 §6.1 line 487-503 + §3.6 line
    128-143 verbatim):
      (i) 完全无 destructive writes — sequence 完全无 FILE_WRITE /
          FILE_DELETE / FILE_RENAME 仅含 FILE_READ + USER_LOGON +
          PROCESS_EXIT.
      (ii) Interactive shell idiom — ls /etc + cat /etc/passwd Linux
           command pattern.
      (iii) Structural disjoint from T1486 ransomware — sequence 完全
            不含 FILE_WRITE 或 FILE_DELETE event.

    Boundary (§3.6 verbatim):
        合法 sysadmin ls + cat /etc/passwd **不**包含 (cat.exe, FILE_READ,
        /etc/shadow)(不读 hash 文件)加 **不**包含输出重定向到 attacker-
        controlled file(无 (*, FILE_WRITE, attacker_path))加 process
        tree 是 interactive shell 而非 scripted。BERT-only 看 /etc/passwd
        词频与 T1003.008 share 完全,区分必须靠 /etc/shadow 缺失加
        downstream exfil 缺失。

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
      - (process, PROCESS_EXIT, process)       line 123 (self-loop)

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON     (user → ls.exe)
          → FILE_READ  (ls → /etc — directory metadata read)
          → PROCESS_EXIT (ls.exe → ls.exe — clean exit)
          → USER_LOGON (user → cat.exe — second interactive command)
          → FILE_READ  (cat → /etc/passwd)
          → PROCESS_EXIT (cat.exe → cat.exe — clean exit)
    Length range: events_min=6, events_max=6 (deterministic 2-command
        sysadmin chain).
    Distinguishing structural pattern: TWO interactive commands (ls + cat)
        each with USER_LOGON → FILE_READ → PROCESS_EXIT shape. Sequence
        contains ZERO FILE_WRITE / FILE_DELETE / FILE_RENAME events
        (anchor (i) + (iii)). NO /etc/shadow read (vs T1003.008 hash
        dump). NO downstream exfil chain. Cross-reference docstring item
        3 三 anchors. Structurally fully disjoint from T1486 ransomware
        (zero destructive writes vs T1486 batch encrypt-delete chain) —
        this is the strongest #6 anchor.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_LS = "ls.exe"
_CAT = "cat.exe"
_ETC_DIR = "/etc"
_ETC_PASSWD = "/etc/passwd"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_6_3"
_NEG_ID = "NEG-6.3"


class Neg63SysadminDirectoryListing(HardNegativeTemplate):
    """T#6.3 benign sysadmin interactive ls /etc + cat /etc/passwd workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_fs_sysadmin_directory_listing")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 6-event sysadmin interactive ls + cat chain.

        Anonymization-robust anchors:
          - Zero FILE_WRITE / FILE_DELETE / FILE_RENAME (anchor (i)+(iii)).
          - Interactive shell idiom: ls /etc + cat /etc/passwd (anchor (ii)).
          - No /etc/shadow read (vs T1003.008 hash dump).
          - No downstream exfil chain.
          - Structurally fully disjoint from T1486 ransomware (zero
            destructive writes).
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        ls = f"neg_{iid}_{_LS}"
        cat = f"neg_{iid}_{_CAT}"
        etc_dir = f"neg_{iid}_{_ETC_DIR}"
        etc_passwd = f"neg_{iid}_{_ETC_PASSWD}"

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
            # 1. Sysadmin user logs on, launches ls.exe (interactive
            #    command 1).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                ls,
                NodeType.process,
            ),
            # 2. ls.exe FILE_READ /etc — directory metadata read (modeled
            #    as FILE_READ on the directory node).
            _ev(
                timestamps[1],
                ls,
                NodeType.process,
                EdgeType.FILE_READ,
                etc_dir,
                NodeType.file,
            ),
            # 3. ls.exe PROCESS_EXIT — clean exit after listing.
            _ev(
                timestamps[2],
                ls,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                ls,
                NodeType.process,
            ),
            # 4. Sysadmin user launches cat.exe (interactive command 2 —
            #    second USER_LOGON event for second command).
            _ev(
                timestamps[3],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                cat,
                NodeType.process,
            ),
            # 5. cat.exe FILE_READ /etc/passwd — NOT /etc/shadow (anchor:
            #    no hash dump vs T1003.008).
            _ev(
                timestamps[4],
                cat,
                NodeType.process,
                EdgeType.FILE_READ,
                etc_passwd,
                NodeType.file,
            ),
            # 6. cat.exe PROCESS_EXIT — clean exit. Sequence has ZERO
            #    FILE_WRITE / FILE_DELETE / FILE_RENAME (anchor (i)+(iii)
            #    structural disjoint from T1486 ransomware).
            _ev(
                timestamps[5],
                cat,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                cat,
                NodeType.process,
            ),
        ]
