"""T1059.001 - Command and Scripting Interpreter: PowerShell (Phase 4 / Checkpoint 14.5).

ATT&CK reference: https://attack.mitre.org/techniques/T1059/001/

Behavioural chain (7 events, per RFC-14.5-1 accepted sequence):

    1. user --> USER_LOGON --> process (cmd.exe) [seed is the user node]
    2. cmd.exe --> PROCESS_CREATE --> powershell.exe
    3. powershell.exe --> FILE_WRITE --> payload.ps1
    4. powershell.exe --> FILE_READ --> payload.ps1
    5. powershell.exe --> PROCESS_CREATE --> powershell.exe (second stage; child)
    6. powershell.exe (child) --> NET_CONNECT --> network (C2 IP)
    7. powershell.exe (child) --> NET_SEND_NETWORK --> network (C2 IP)

Shared-seed design (RFC-14.5-4):
    The seed is a ``user`` node (e.g. ``"victim_user"``).  Step 1 anchors
    the USER_LOGON event from that existing benign user node to a new
    ``atk_<iid>_cmd`` process node.  Remaining nodes are all ``atk_``-prefixed.

ALLOWED_EDGE_TRIPLES schema workaround (RFC-14.5-1):

    ALLOWED_EDGE_TRIPLES 当前不含 registry 边类型与 process-as-file-like-handle
    边类型, T1547.001 借用 FILE_WRITE 到 \\Registry\\Machine... 路径与 T1003.001
    借用 HANDLE_REQUEST 到 lsass.exe file node 是符合 EDR 工具实际建模习惯的工程妥
    协. Phase 5 RAPA 完整 20 个模板实施时如发现需要扩 ALLOWED_EDGE_TRIPLES 添加
    registry 与 process-handle 边类型再统一处理.
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType


class T1059001PowerShell(AttackTemplate):
    """PowerShell execution chain (T1059.001) synthetic event generator."""

    # Real EDR-style tokens; kept verbatim per RFC-14.5-6 (no anonymization).
    _CMD = "cmd.exe"
    _PS = "powershell.exe"
    _PAYLOAD = "payload.ps1"
    _C2_IP = "185.234.219.11"
    _C2_PORT = "4444"
    _LOG_TYPE = "synthetic_atlas"
    _SCENARIO = "synthetic_apt"
    _HOST = "h2"

    def __init__(self) -> None:
        super().__init__("T1059.001", "PowerShell")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event PowerShell execution + C2 chain."""
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Node IDs: seed user is shared; all attack-side nodes use atk_ prefix.
        cmd = f"atk_{iid}_{self._CMD}"
        ps1 = f"atk_{iid}_{self._PS}"
        ps2 = f"atk_{iid}_{self._PS}_child"
        payload = f"atk_{iid}_{self._PAYLOAD}"
        c2_net = f"atk_{iid}_{self._C2_IP}:{self._C2_PORT}"

        # Spread 7 events uniformly (with small jitter) across [t_start, t_end].
        n_events = 7
        span = t_end_ns - t_start_ns
        base_step = span // n_events
        timestamps = [
            t_start_ns + k * base_step + rng.randint(0, max(1, base_step // 4))
            for k in range(n_events)
        ]
        timestamps.sort()

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
                log_type=self._LOG_TYPE,
                scenario_id=self._SCENARIO,
                host_id=self._HOST,
                attributes={"ttp": self.ttp_id, "instance_id": iid, "label": 1},
            )

        return [
            # 1. Compromised user logon creates cmd.exe process.
            _ev(timestamps[0], seed_subject, NodeType.user, EdgeType.USER_LOGON, cmd, NodeType.process),
            # 2. cmd.exe spawns powershell.exe.
            _ev(timestamps[1], cmd, NodeType.process, EdgeType.PROCESS_CREATE, ps1, NodeType.process),
            # 3. powershell.exe writes the payload script.
            _ev(timestamps[2], ps1, NodeType.process, EdgeType.FILE_WRITE, payload, NodeType.file),
            # 4. powershell.exe reads the payload script.
            _ev(timestamps[3], ps1, NodeType.process, EdgeType.FILE_READ, payload, NodeType.file),
            # 5. powershell.exe spawns a child powershell.exe for C2 comms.
            _ev(timestamps[4], ps1, NodeType.process, EdgeType.PROCESS_CREATE, ps2, NodeType.process),
            # 6. child powershell.exe connects to C2.
            _ev(timestamps[5], ps2, NodeType.process, EdgeType.NET_CONNECT, c2_net, NodeType.network),
            # 7. child powershell.exe sends data to C2.
            _ev(timestamps[6], ps2, NodeType.process, EdgeType.NET_SEND_NETWORK, c2_net, NodeType.network),
        ]
