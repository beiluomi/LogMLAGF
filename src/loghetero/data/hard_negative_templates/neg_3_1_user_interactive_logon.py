"""T#3.1 benign_auth_user_interactive_logon — Hard Negative Template.

Class: #3 合法 Auth (per design propose §3.3 + §5.3)
NEG-ID: NEG-3.1
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.3 minimal sketch
    + §5.3 schema readiness (vanilla, no workaround) + §4.1 Pair §4.1.D
    boundary (#3 vs #8 RDP)

ATT&CK-like NEG-ID:
    NEG-3.1 — first of two legitimate-Auth hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.3 sub-pattern
    split (NEG-3.1 single interactive logon / NEG-3.2 Kerberos service
    ticket).

Distinct lexical signature + boundary (verbatim from design propose §3.3
plus Pair §4.1.D from §4.1):
    Confound TTP: T1078 valid-accounts.

    Boundary (§3.3 verbatim):
        合法用户 logon → explorer → 启动项链 **不**包含 credential-access 子链
        (无 LSASS access, 无 SAM hive read), 加进入正常应用而非 shell. BERT-only
        看 winlogon + userinit + explorer 词频几乎与 T1078 共享前 3 步, 区分
        必须靠后续 process-tree branch (normal app vs shell + credential dump).

    Boundary §4.1.D (#3 vs #8 RDP):
        单次 logon 属 #3 (无 mstsc.exe / mstscax.dll involvement, 无
        NET_CONNECT 到 RDP target_host_network). 本模板不含 mstsc.exe 加
        不含 NET_CONNECT 到 target_host.

    Anonymization-robust structural anchors:
      (a) Process tree depth >= 3 (winlogon → userinit → explorer → app).
      (b) Final process is normal user-facing app (slack.exe in this
          template) NOT a shell (cmd.exe / powershell.exe / sh / bash).
          T1078 valid-accounts launches admin / shell process tree
          subsequently (per T1078 attack template event 5: target_svc.exe
          reads sensitive_config.cfg).
      (c) NO FILE_READ to credential-access paths (LSASS / SAM / NTDS.dit
          / SECURITY hive / shadow / passwd hash).
      (d) NO NET_CONNECT — single-host interactive logon to startup app.
      (e) NO mstsc.exe / RDP NET_CONNECT (vs Class #8 boundary).
      (f) NO USER_LOGON_FAIL (vs Class #9 weak-pwd-test boundary
          §4.1.G — single successful USER_LOGON only).

ALLOWED_EDGE_TRIPLES workaround reuse:
    NONE — vanilla schema. Per design §5.3, all triples used by T#3.1 are
    natively in ALLOWED_EDGE_TRIPLES (parsers/base.py lines 106-141):
      - (user, USER_LOGON, process)            line 135
      - (process, PROCESS_CREATE, process)     line 120
      - (process, FILE_READ, file)             line 110
    No workaround inventory entry triggered.

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON   (user → winlogon.exe)
          → PROCESS_CREATE (winlogon → userinit.exe)
          → PROCESS_CREATE (userinit → explorer.exe)
          → FILE_READ      (explorer reads Startup folder)
          → PROCESS_CREATE (explorer → slack.exe — startup app)
    Length range: events_min=5, events_max=5 (deterministic interactive
        logon chain).
    Distinguishing structural pattern: 3-deep process chain
        winlogon→userinit→explorer→app where the leaf is a normal
        user-facing app (slack.exe), with NO NET_CONNECT, NO LSASS access,
        NO shell spawn — structurally disjoint from T1078 (which subsequently
        spawns target_svc.exe → FILE_READ sensitive_config.cfg → NET_CONNECT
        c2_net). T1078 also uses USER_LOGON_FAIL x 2 + USER_LOGON +
        USER_PRIV_GRANT seed sequence (4-edge auth burst); NEG-3.1 is single
        USER_LOGON only.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_WINLOGON = "winlogon.exe"
_USERINIT = "userinit.exe"
_EXPLORER = "explorer.exe"
_STARTUP_DIR = r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
_STARTUP_APP = "slack.exe"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_3_1"
_NEG_ID = "NEG-3.1"


class Neg31UserInteractiveLogon(HardNegativeTemplate):
    """T#3.1 benign user interactive logon → startup app workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_auth_user_interactive_logon")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 5-event interactive logon → startup app chain.

        Anonymization-robust anchors:
          - 3-deep process chain (winlogon → userinit → explorer → app).
          - Leaf process is normal app (slack.exe) NOT shell.
          - No LSASS / SAM access.
          - No NET_CONNECT.
          - No mstsc.exe (vs RDP class #8).
          - Single USER_LOGON only (no USER_LOGON_FAIL burst).
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        winlogon = f"neg_{iid}_{_WINLOGON}"
        userinit = f"neg_{iid}_{_USERINIT}"
        explorer = f"neg_{iid}_{_EXPLORER}"
        startup_dir = f"neg_{iid}_{_STARTUP_DIR}"
        startup_app = f"neg_{iid}_{_STARTUP_APP}"

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
            # 1. User logs on, OS launches winlogon.exe (interactive logon
            #    via 4624 LogonType 2 / 11 — "interactive" — modeled here as
            #    standard USER_LOGON edge per ALLOWED_EDGE_TRIPLES).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                winlogon,
                NodeType.process,
            ),
            # 2. winlogon → userinit (standard Windows logon process tree).
            _ev(
                timestamps[1],
                winlogon,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                userinit,
                NodeType.process,
            ),
            # 3. userinit → explorer.exe shell launch.
            _ev(
                timestamps[2],
                userinit,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                explorer,
                NodeType.process,
            ),
            # 4. explorer reads Startup-folder shortcut metadata.
            _ev(
                timestamps[3],
                explorer,
                NodeType.process,
                EdgeType.FILE_READ,
                startup_dir,
                NodeType.file,
            ),
            # 5. explorer launches startup app (slack.exe — normal user-facing
            #    app, NOT cmd / powershell / shell — structural anchor vs
            #    T1078 valid-accounts which spawns target_svc.exe + reads
            #    sensitive_config.cfg + NET_CONNECT c2_net).
            _ev(
                timestamps[4],
                explorer,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                startup_app,
                NodeType.process,
            ),
        ]
