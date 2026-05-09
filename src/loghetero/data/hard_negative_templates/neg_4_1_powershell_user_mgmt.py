"""T#4.1 benign_admin_powershell_user_mgmt — Hard Negative Template.

Class: #4 Admin Tool 执行 (per design propose §3.4)
NEG-ID: NEG-4.1
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.4 minimal sketch
    + §5.4 schema readiness (vanilla, no workaround).

ATT&CK-like NEG-ID:
    NEG-4.1 — first of three Admin-Tool-执行 hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.4 sub-pattern
    split (NEG-4.1 PowerShell user mgmt / NEG-4.2 sc service restart /
    NEG-4.3 schtasks create).

Distinct lexical signature + boundary (verbatim from design propose §3.4):
    Confound TTPs (T#4.1 verbatim from §3.4): T1059.001 PowerShell +
    T1136.002 create-domain-account.

    Three anchors per template (派生自 §3.4 boundary verbatim):
      (i) NO (powershell.exe, PROCESS_CREATE, child) — admin user-mgmt
          script does not spawn child process.
      (ii) NO (powershell.exe, FILE_WRITE, *.ps1) — admin context does
           NOT write secondary payload to disk (no script二次落地).
      (iii) Sequence terminates with PROCESS_EXIT — single end-to-end
            New-ADUser RPC against DC, no downstream lateral chain.

    Boundary (§3.4 verbatim):
        合法 admin PowerShell user-mgmt 只用 New-ADUser → DC RPC,**不**包含
        (powershell.exe, PROCESS_CREATE, child) 加 **不**写 payload 到 disk
        (无 (powershell.exe, FILE_WRITE, *.ps1) 二次落地)。BERT-only 看
        powershell + .ps1 + LDAP 词频与 T1059.001 PowerShell 攻击共享前 3 步
        几乎完全,区分必须靠 child-process + payload-write 缺失。

ALLOWED_EDGE_TRIPLES workaround reuse:
    Vanilla schema. All edge triples natively in ALLOWED_EDGE_TRIPLES.
    No workaround reuse. Zero new schema workaround inventory entries
    triggered. Triples used:
      - (user, USER_LOGON, process)            line 135
      - (process, FILE_READ, file)             line 110
      - (process, NET_CONNECT, network)        line 125
      - (process, NET_SEND_NETWORK, network)   line 128
      - (process, NET_RECV_NETWORK, network)   line 130
      - (process, PROCESS_EXIT, process)       line 123 (self-loop)

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON          (user → powershell.exe)
          → FILE_READ        (powershell → C:\\Scripts\\add_user.ps1)
          → NET_CONNECT      (powershell → dc_network — LDAP)
          → NET_SEND_NETWORK (powershell → dc_network — New-ADUser RPC)
          → NET_RECV_NETWORK (powershell → dc_network — RPC response)
          → PROCESS_EXIT     (powershell → powershell — clean exit)
    Length range: events_min=6, events_max=6 (deterministic single
        New-ADUser RPC chain).
    Distinguishing structural pattern: ps1 script FILE_READ ONLY (not
        FILE_WRITE) followed by single LDAP RPC round-trip terminating in
        PROCESS_EXIT — admin user-mgmt 单一 RPC 模式。Structurally disjoint
        from T1059.001 PowerShell attack which subsequently contains
        downstream PROCESS_CREATE + secondary .ps1 FILE_WRITE payload drop;
        also disjoint from T1136.002 create-domain-account which would
        chain New-ADUser to subsequent privilege grant + lateral movement.
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_POWERSHELL = "powershell.exe"
_ADD_USER_SCRIPT = r"C:\Scripts\add_user.ps1"
_DC_NETWORK = "dc_network:389"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_4_1"
_NEG_ID = "NEG-4.1"


class Neg41PowershellUserMgmt(HardNegativeTemplate):
    """T#4.1 benign admin PowerShell New-ADUser user-mgmt workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_admin_powershell_user_mgmt")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 6-event admin PowerShell New-ADUser → DC RPC chain.

        Anonymization-robust anchors:
          - No (powershell.exe, PROCESS_CREATE, *) — depth-1 process tree.
          - No (powershell.exe, FILE_WRITE, *.ps1) — no secondary payload
            drop.
          - Single LDAP RPC round-trip + clean PROCESS_EXIT termination.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        powershell = f"neg_{iid}_{_POWERSHELL}"
        add_user_script = f"neg_{iid}_{_ADD_USER_SCRIPT}"
        dc_network = f"neg_{iid}_{_DC_NETWORK}"

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
            # 1. Admin user logs on, launches powershell.exe.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                powershell,
                NodeType.process,
            ),
            # 2. powershell.exe reads C:\Scripts\add_user.ps1 (FILE_READ
            #    only — anchor (ii): no FILE_WRITE *.ps1).
            _ev(
                timestamps[1],
                powershell,
                NodeType.process,
                EdgeType.FILE_READ,
                add_user_script,
                NodeType.file,
            ),
            # 3. powershell.exe NET_CONNECT to DC LDAP endpoint (TCP/389).
            _ev(
                timestamps[2],
                powershell,
                NodeType.process,
                EdgeType.NET_CONNECT,
                dc_network,
                NodeType.network,
            ),
            # 4. powershell.exe NET_SEND_NETWORK New-ADUser RPC payload
            #    (LDAP/RPC bind + ADUser create request).
            _ev(
                timestamps[3],
                powershell,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                dc_network,
                NodeType.network,
            ),
            # 5. powershell.exe NET_RECV_NETWORK RPC response from DC
            #    (success / error code).
            _ev(
                timestamps[4],
                powershell,
                NodeType.process,
                EdgeType.NET_RECV_NETWORK,
                dc_network,
                NodeType.network,
            ),
            # 6. powershell.exe PROCESS_EXIT (clean exit — anchor (i)/(iii):
            #    NO PROCESS_CREATE downstream + sequence terminates here).
            _ev(
                timestamps[5],
                powershell,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                powershell,
                NodeType.process,
            ),
        ]
