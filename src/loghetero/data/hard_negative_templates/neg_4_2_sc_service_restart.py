"""T#4.2 benign_admin_sc_service_restart — Hard Negative Template.

Class: #4 Admin Tool 执行 (per design propose §3.4)
NEG-ID: NEG-4.2
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.4 minimal sketch
    + §5.4 schema readiness (USER_PRIV_GRANT user-anchor reuses T1068
    workaround #2; svcctl pipe write reuses T1543.003 sc.exe pattern;
    explicit do NOT reuse T1547.001 registry-as-file because sc service
    restart 不写 IMAGEPATH).

ATT&CK-like NEG-ID:
    NEG-4.2 — second of three Admin-Tool-执行 hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.4 sub-pattern
    split (NEG-4.1 PowerShell user mgmt / NEG-4.2 sc service restart /
    NEG-4.3 schtasks create).

Distinct lexical signature + boundary (verbatim from design propose §3.4
plus Cycle H specific enhancement):
    Confound TTPs (T#4.2 verbatim from §3.4): T1543.003 windows-service.

    Five-anchor chain cross-reference (T#4.2 specific): §4.3 line 321-329
    C8 mitigation + §3.7 line 157 conditional anchor note + NEG-7.1
    implementation (commit 07251b2) + NEG-7.2 implementation (commit
    07251b2 + docstring fix commit 2d83dc7) + T#4.2 自身 — together these
    form the service-type-specific conditional-anchor finding chain. T#4.2
    是 service-restart not service-installation 加与 T1543.003 sc.exe 攻击
    模板 (sc create + binPath 建立新 service) distinct 加 T#4.2 仅 sc start
    或 sc stop 加 sc start 不创建新 service 不写 IMAGEPATH。

    Three anchors per template (派生自 §3.4 boundary verbatim):
      (i) NO (sc.exe, FILE_WRITE, C:\\Windows\\System32\\<new_svc>.exe) —
          不创建新 service 二进制.
      (ii) NO IMAGEPATH registry write (NO FILE_WRITE to
           \\Registry\\Machine\\SYSTEM\\CurrentControlSet\\Services\\
           <svc>\\ImagePath) — sc start不修改 IMAGEPATH.
      (iii) Service-restart (start/stop) semantic NOT service-creation
            semantic — vs T1543.003 attack which sc create + binPath +
            IMAGEPATH set.

    Boundary (§3.4 verbatim):
        合法 sc.exe restart **不**包含 (sc.exe, FILE_WRITE,
        C:\\Windows\\System32\\<new_svc>.exe)(不创建新 service 二进制)加
        **不**包含 IMAGEPATH 修改写 registry 模拟边。BERT-only 看 sc.exe +
        svcctl 词频与 T1543.003 share,区分必须靠 service-binary write 加
        service IMAGEPATH 修改缺失。

ALLOWED_EDGE_TRIPLES workaround reuse:
    Two reuses (svcctl pipe-as-file + USER_PRIV_GRANT user-anchor),
    EXPLICIT do NOT reuse T1547.001 registry-as-file (sc_service_restart
    不写 IMAGEPATH per §3.4 boundary verbatim). Cross-reference NEG-7.1
    commit 07251b2 + NEG-7.2 commit 07251b2 + docstring fix commit
    2d83dc7 chain. ZERO new schema workaround inventory entries
    (Checkpoint 17 inventory remains at 4 entries, known_issues.md lines
    437-440):

      1. **USER_PRIV_GRANT user-anchor reuses T1068 workaround #2**
         (known_issues.md inventory entry #2). The triple
         (user, USER_PRIV_GRANT, process) with seed_user as subject —
         semantic "privilege attributed to user's session per Windows 4672
         Special Privileges Assigned to New Logon".

      2. **svcctl pipe write reuses T1543.003 sc.exe pattern**
         (known_issues.md inventory entry #3 — file-node-as-X higher-level
         workaround spirit per line 437-440 4-entry inventory). Per design
         §5.4 row, the svcctl pipe path ``\\\\.\\pipe\\svcctl`` is modeled
         as a file node target of FILE_WRITE — already-landed pattern from
         T1543.003 attack template (svcctl RPC modeled as pipe-as-file).
         NO new inventory entry triggered.

    All triples used by T#4.2 are natively in ALLOWED_EDGE_TRIPLES
    (parsers/base.py lines 106-141):
      - (user, USER_LOGON, process)            line 135
      - (user, USER_PRIV_GRANT, process)       line 138 (T1068 reuse)
      - (process, FILE_WRITE, file)            line 111 (svcctl pipe reuse)
      - (process, PROCESS_EXIT, process)       line 123 (self-loop)

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON       (user → sc.exe)
          → USER_PRIV_GRANT (user → sc.exe — 4672 priv-grant for SCM)
          → FILE_WRITE   (sc → \\\\.\\pipe\\svcctl — SCM RPC, svcctl
                          pipe-as-file workaround reuse)
          → PROCESS_EXIT (sc.exe → sc.exe — clean exit)
    Length range: events_min=4, events_max=4 (deterministic admin sc
        restart chain — single SCM RPC against existing service).
    Distinguishing structural pattern: USER_LOGON → USER_PRIV_GRANT →
        svcctl pipe FILE_WRITE → PROCESS_EXIT 即 svcctl pipe write 后
        立即 PROCESS_EXIT 结束 (NOT IMAGEPATH + PROCESS_EXIT 是 T#7.1
        driver installation 加 NOT FILE_READ x ≥3 + NET_CONNECT
        internal_repo + FILE_WRITE 是 T#10.3 backup pattern). Structurally
        disjoint from T1543.003 attack which contains additional
        (sc.exe, FILE_WRITE, System32\\<new_svc>.exe) + IMAGEPATH registry
        write + downstream PROCESS_CREATE + NET_CONNECT c2_net.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_SC = "sc.exe"
_SVCCTL_PIPE = r"\\.\pipe\svcctl"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_4_2"
_NEG_ID = "NEG-4.2"


class Neg42ScServiceRestart(HardNegativeTemplate):
    """T#4.2 benign admin sc.exe service-restart workflow (no service install)."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_admin_sc_service_restart")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 4-event admin sc service restart chain.

        Anonymization-robust anchors:
          - No FILE_WRITE to System32\\<new_svc>.exe — no new service
            binary creation (anchor (i)).
          - No IMAGEPATH registry write — no service definition mutation
            (anchor (ii)).
          - Service-restart semantic only (anchor (iii)).
          - svcctl pipe FILE_WRITE reuses T1543.003 sc.exe pattern.
          - USER_PRIV_GRANT user-anchor reuses T1068 workaround #2.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        sc = f"neg_{iid}_{_SC}"
        svcctl_pipe = f"neg_{iid}_{_SVCCTL_PIPE}"

        n_events = 4
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
            # 1. Admin user logs on, launches sc.exe (interactive admin).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                sc,
                NodeType.process,
            ),
            # 2. USER_PRIV_GRANT (4672) — sc service control requires
            #    SeServiceLogonRight / SC_MANAGER privileges. Schema
            #    workaround #2 reuse: subject is seed_user.
            _ev(
                timestamps[1],
                seed_subject,
                NodeType.user,
                EdgeType.USER_PRIV_GRANT,
                sc,
                NodeType.process,
            ),
            # 3. sc.exe writes svcctl pipe to send SCM RPC (StartService /
            #    ControlService for existing service). svcctl-pipe-as-file
            #    pattern reuses T1543.003 sc.exe svcctl write (no new
            #    inventory entry).
            _ev(
                timestamps[2],
                sc,
                NodeType.process,
                EdgeType.FILE_WRITE,
                svcctl_pipe,
                NodeType.file,
            ),
            # 4. sc.exe PROCESS_EXIT — clean exit after SCM RPC. NO new
            #    service binary FILE_WRITE + NO IMAGEPATH registry write
            #    (anchors (i)+(ii) vs T1543.003 attack chain).
            _ev(
                timestamps[3],
                sc,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                sc,
                NodeType.process,
            ),
        ]
