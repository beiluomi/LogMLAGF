"""T#4.3 benign_admin_schtasks_create — Hard Negative Template.

Class: #4 Admin Tool 执行 (per design propose §3.4)
NEG-ID: NEG-4.3
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.4 minimal sketch
    + §5.4 schema readiness (USER_PRIV_GRANT user-anchor reuses T1068
    workaround #2).

ATT&CK-like NEG-ID:
    NEG-4.3 — third of three Admin-Tool-执行 hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.4 sub-pattern
    split (NEG-4.1 PowerShell user mgmt / NEG-4.2 sc service restart /
    NEG-4.3 schtasks create).

Distinct lexical signature + boundary (verbatim from design propose §3.4):
    Confound TTPs (T#4.3 verbatim from §3.4): T1053.005 scheduled-task.

    Three anchors per template (派生自 §3.4 boundary verbatim):
      (i) Task command points to well-known admin tool (backup utility /
          patch script) — well-known admin path semantic anchor.
      (ii) Task trigger is daily schedule (NOT onlogon-immediate) —
           daily-trigger semantic anchor.
      (iii) Task XML written to Tasks\\ admin-managed dir, points to
            patch_script.cmd well-known admin script location.

    Boundary (§3.4 verbatim):
        合法 schtasks 创建 **task 命令是 well-known admin tool**(指向
        backup utility / patch script)+ trigger 是 daily 而非
        onlogon-immediate;T1053.005 attack 创建 **task 命令指向 attacker
        payload** 加 trigger 是 immediate-onlogon。BERT-only 看 schtasks +
        Tasks 词频共享,区分必须靠 task-payload + trigger semantics。

ALLOWED_EDGE_TRIPLES workaround reuse:
    One reuse (USER_PRIV_GRANT user-anchor). ZERO new schema workaround
    inventory entries (Checkpoint 17 inventory remains at 4 entries,
    known_issues.md lines 437-440):

      1. **USER_PRIV_GRANT user-anchor reuses T1068 workaround #2**
         (known_issues.md inventory entry #2). The triple
         (user, USER_PRIV_GRANT, process) with seed_user as subject —
         semantic "privilege attributed to user's session per Windows 4672
         Special Privileges Assigned to New Logon".

    All triples used by T#4.3 are natively in ALLOWED_EDGE_TRIPLES
    (parsers/base.py lines 106-141):
      - (user, USER_LOGON, process)            line 135
      - (user, USER_PRIV_GRANT, process)       line 138 (T1068 reuse)
      - (process, FILE_READ, file)             line 110
      - (process, FILE_WRITE, file)            line 111
      - (process, PROCESS_EXIT, process)       line 123 (self-loop)

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON       (user → schtasks.exe)
          → USER_PRIV_GRANT (user → schtasks.exe — 4672 priv-grant)
          → FILE_READ    (schtasks → C:\\Windows\\System32\\Tasks\\
                          existing_task — read existing task XML)
          → FILE_WRITE   (schtasks → C:\\Windows\\System32\\Tasks\\
                          backup_daily — write new task XML, daily
                          trigger pointing to admin backup utility)
          → PROCESS_EXIT (schtasks.exe → schtasks.exe — clean exit)
    Length range: events_min=5, events_max=5 (deterministic admin
        schtasks /Create chain).
    Distinguishing structural pattern: task XML write to backup_daily
        targets admin backup utility (well-known path semantic) + daily
        trigger semantic (non-onlogon-immediate) + clean PROCESS_EXIT
        termination. Structurally disjoint from T1053.005 attack which
        creates task pointing to attacker payload + onlogon-immediate
        trigger + downstream PROCESS_CREATE for payload execution.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_SCHTASKS = "schtasks.exe"
_EXISTING_TASK = r"C:\Windows\System32\Tasks\existing_maintenance"
_NEW_TASK = r"C:\Windows\System32\Tasks\backup_daily"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_4_3"
_NEG_ID = "NEG-4.3"


class Neg43SchtasksCreate(HardNegativeTemplate):
    """T#4.3 benign admin schtasks /Create daily-backup workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_admin_schtasks_create")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 5-event admin schtasks /Create chain.

        Anonymization-robust anchors:
          - Task XML written to Tasks\\backup_daily — well-known admin
            backup utility path.
          - Daily trigger semantic (non-onlogon-immediate).
          - Read existing task BEFORE write new task — admin idempotency
            check anchor.
          - USER_PRIV_GRANT user-anchor reuses T1068 workaround #2.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        schtasks = f"neg_{iid}_{_SCHTASKS}"
        existing_task = f"neg_{iid}_{_EXISTING_TASK}"
        new_task = f"neg_{iid}_{_NEW_TASK}"

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
            # 1. Admin user logs on, launches schtasks.exe.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                schtasks,
                NodeType.process,
            ),
            # 2. USER_PRIV_GRANT (4672) — schtasks /Create requires admin
            #    rights. Schema workaround #2 reuse: subject is seed_user.
            _ev(
                timestamps[1],
                seed_subject,
                NodeType.user,
                EdgeType.USER_PRIV_GRANT,
                schtasks,
                NodeType.process,
            ),
            # 3. schtasks.exe FILE_READ existing task XML (admin idempotency
            #    check — read before create).
            _ev(
                timestamps[2],
                schtasks,
                NodeType.process,
                EdgeType.FILE_READ,
                existing_task,
                NodeType.file,
            ),
            # 4. schtasks.exe FILE_WRITE new task XML (backup_daily —
            #    well-known admin backup utility path, daily trigger
            #    semantic).
            _ev(
                timestamps[3],
                schtasks,
                NodeType.process,
                EdgeType.FILE_WRITE,
                new_task,
                NodeType.file,
            ),
            # 5. schtasks.exe PROCESS_EXIT — clean exit after task XML
            #    write. NO downstream PROCESS_CREATE child shell vs
            #    T1053.005 attack onlogon-immediate trigger chain.
            _ev(
                timestamps[4],
                schtasks,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                schtasks,
                NodeType.process,
            ),
        ]
