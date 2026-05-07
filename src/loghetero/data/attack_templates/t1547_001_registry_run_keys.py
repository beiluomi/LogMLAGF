"""T1547.001 - Boot or Logon Autostart Execution: Registry Run Keys (Phase 4 / Checkpoint 14.5).

ATT&CK reference: https://attack.mitre.org/techniques/T1547/001/

Behavioural chain (7 events, per RFC-14.5-1 accepted sequence):

    1. user --> USER_LOGON --> process (dropper.exe) [seed = user]
    2. dropper.exe --> PROCESS_CREATE --> reg.exe (Windows registry CLI tool)
    3. dropper.exe --> FILE_WRITE --> persisted_payload.exe
    4. reg.exe --> FILE_WRITE --> \\Registry\\Machine\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
    5. dropper.exe --> FILE_READ --> persisted_payload.exe
    6. dropper.exe --> PROCESS_CREATE --> persisted_payload.exe
    7. persisted_payload.exe --> NET_CONNECT --> network (C2)

Schema workaround (RFC-14.5-1):
    The Windows registry key path
    ``\\Registry\\Machine\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
    is modeled as a ``file`` node, and the write is modeled as FILE_WRITE
    (process --> file edge).  This matches how Windows kernel-style registry
    paths appear in ETW/Sysmon events that map to EventID 4657 (Registry
    value write), and how EDR tools route these to file-like edges when a
    dedicated registry edge type is unavailable.

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

# Windows kernel-style registry path for Run keys.
_RUN_KEY_PATH = r"\Registry\Machine\Software\Microsoft\Windows\CurrentVersion\Run"


class T1547001RegistryRunKeys(AttackTemplate):
    """Registry Run Key persistence chain (T1547.001) synthetic event generator."""

    _DROPPER = "dropper.exe"
    _REG = "reg.exe"
    _PAYLOAD = "persisted_payload.exe"
    _C2_IP = "194.165.16.11"
    _C2_PORT = "8080"
    _LOG_TYPE = "synthetic_atlas"
    _SCENARIO = "synthetic_apt"
    _HOST = "h2"

    def __init__(self) -> None:
        super().__init__("T1547.001", "Registry Run Keys")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event Registry Run Key persistence chain."""
        assert isinstance(rng, random.Random)
        iid = instance_id

        dropper = f"atk_{iid}_{self._DROPPER}"
        reg = f"atk_{iid}_{self._REG}"
        payload = f"atk_{iid}_{self._PAYLOAD}"
        # Registry key path modeled as a file node (schema workaround documented above).
        run_key_node = f"atk_{iid}_{_RUN_KEY_PATH}"
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
            # 1. Compromised user logon spawns the dropper.
            _ev(timestamps[0], seed_subject, NodeType.user, EdgeType.USER_LOGON, dropper, NodeType.process),
            # 2. Dropper spawns reg.exe to manipulate the registry.
            _ev(timestamps[1], dropper, NodeType.process, EdgeType.PROCESS_CREATE, reg, NodeType.process),
            # 3. Dropper writes the persistence payload executable to disk.
            _ev(timestamps[2], dropper, NodeType.process, EdgeType.FILE_WRITE, payload, NodeType.file),
            # 4. reg.exe writes to the Run key path (modeled as FILE_WRITE to file node per schema workaround).
            _ev(timestamps[3], reg, NodeType.process, EdgeType.FILE_WRITE, run_key_node, NodeType.file),
            # 5. Dropper reads the payload back to verify.
            _ev(timestamps[4], dropper, NodeType.process, EdgeType.FILE_READ, payload, NodeType.file),
            # 6. Dropper executes the persisted payload.
            _ev(timestamps[5], dropper, NodeType.process, EdgeType.PROCESS_CREATE, payload, NodeType.process),
            # 7. Persisted payload connects to C2.
            _ev(timestamps[6], payload, NodeType.process, EdgeType.NET_CONNECT, c2_net, NodeType.network),
        ]
