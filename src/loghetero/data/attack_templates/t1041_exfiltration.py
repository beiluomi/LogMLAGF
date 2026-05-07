"""T1041 - Exfiltration Over C2 Channel (Phase 4 / Checkpoint 14.5).

ATT&CK reference: https://attack.mitre.org/techniques/T1041/

Behavioural chain (7 events, per RFC-14.5-1 accepted sequence):

    1. user --> USER_LOGON --> process (exfil_tool.exe) [seed = user]
    2. exfil_tool.exe --> FILE_READ --> sensitive_data.db
    3. exfil_tool.exe --> FILE_WRITE --> archive.zip  (compress step)
    4. exfil_tool.exe --> NET_CONNECT --> network (C2 IP)
    5. exfil_tool.exe --> NET_SEND_NETWORK --> network (C2 IP)  (send archive)
    6. exfil_tool.exe --> FILE_DELETE --> archive.zip  (cleanup archive)
    7. exfil_tool.exe --> FILE_DELETE --> sensitive_data.db  (cleanup source)

Shared-seed design (RFC-14.5-4):
    Seed is the compromised user; step 1 anchors USER_LOGON from the shared
    benign user node to a new atk_-prefixed exfil_tool.exe process node.

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


class T1041Exfiltration(AttackTemplate):
    """Exfiltration over C2 channel (T1041) synthetic event generator."""

    _TOOL = "exfil_tool.exe"
    _SENSITIVE = "sensitive_data.db"
    _ARCHIVE = "archive.zip"
    _C2_IP = "45.142.212.100"
    _C2_PORT = "443"
    _LOG_TYPE = "synthetic_atlas"
    _SCENARIO = "synthetic_apt"
    _HOST = "h2"

    def __init__(self) -> None:
        super().__init__("T1041", "Exfiltration Over C2 Channel")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event data exfiltration chain."""
        assert isinstance(rng, random.Random)
        iid = instance_id

        tool = f"atk_{iid}_{self._TOOL}"
        sensitive = f"atk_{iid}_{self._SENSITIVE}"
        archive = f"atk_{iid}_{self._ARCHIVE}"
        c2_net = f"atk_{iid}_{self._C2_IP}:{self._C2_PORT}"

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
            # 1. Compromised user logon spawns exfil tool.
            _ev(timestamps[0], seed_subject, NodeType.user, EdgeType.USER_LOGON, tool, NodeType.process),
            # 2. Exfil tool reads the sensitive data file.
            _ev(timestamps[1], tool, NodeType.process, EdgeType.FILE_READ, sensitive, NodeType.file),
            # 3. Exfil tool compresses data into an archive.
            _ev(timestamps[2], tool, NodeType.process, EdgeType.FILE_WRITE, archive, NodeType.file),
            # 4. Exfil tool connects to the C2 server.
            _ev(timestamps[3], tool, NodeType.process, EdgeType.NET_CONNECT, c2_net, NodeType.network),
            # 5. Exfil tool sends the archive to C2.
            _ev(timestamps[4], tool, NodeType.process, EdgeType.NET_SEND_NETWORK, c2_net, NodeType.network),
            # 6. Cleanup: delete the compressed archive.
            _ev(timestamps[5], tool, NodeType.process, EdgeType.FILE_DELETE, archive, NodeType.file),
            # 7. Cleanup: delete the sensitive source file.
            _ev(timestamps[6], tool, NodeType.process, EdgeType.FILE_DELETE, sensitive, NodeType.file),
        ]
