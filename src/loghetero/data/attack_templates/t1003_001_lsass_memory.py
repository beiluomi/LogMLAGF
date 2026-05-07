"""T1003.001 - OS Credential Dumping: LSASS Memory (Phase 4 / Checkpoint 14.5).

ATT&CK reference: https://attack.mitre.org/techniques/T1003/001/

Behavioural chain (7 events, per RFC-14.5-1 accepted sequence):

    1. user --> USER_PRIV_GRANT --> process (mimikatz.exe) [seed = user]
    2. mimikatz.exe --> PROCESS_CREATE --> mimikatz.exe (elevated child)
    3. mimikatz.exe (elevated) --> HANDLE_REQUEST --> lsass.exe [modeled as file node]
    4. mimikatz.exe (elevated) --> FILE_READ --> lsass.exe [memory read via handle]
    5. mimikatz.exe (elevated) --> FILE_WRITE --> cred_dump.dmp
    6. mimikatz.exe --> FILE_READ --> cred_dump.dmp
    7. mimikatz.exe --> NET_CONNECT --> network (exfil C2)

Schema workaround (RFC-14.5-1):

    lsass.exe is modeled as a ``file`` node accessed via ``HANDLE_REQUEST``
    (process --> file edge).  This reflects how EDR tools emit handle
    acquisition events (Windows EventID 4656) which reference lsass.exe's
    process object path as if it were a file handle target.

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


class T1003001LsassMemory(AttackTemplate):
    """LSASS credential dump chain (T1003.001) synthetic event generator."""

    _MIMI = "mimikatz.exe"
    # lsass.exe modeled as file node per RFC-14.5-1 / RFC-14.5-2 rationale above.
    _LSASS = "lsass.exe"
    _DUMP = "cred_dump.dmp"
    _C2_IP = "91.108.4.6"
    _C2_PORT = "443"
    _LOG_TYPE = "synthetic_atlas"
    _SCENARIO = "synthetic_apt"
    _HOST = "h2"

    def __init__(self) -> None:
        super().__init__("T1003.001", "LSASS Memory")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event LSASS credential dump chain."""
        assert isinstance(rng, random.Random)
        iid = instance_id

        mimi = f"atk_{iid}_{self._MIMI}"
        mimi_el = f"atk_{iid}_{self._MIMI}_elevated"
        # lsass_node is treated as a file node (schema workaround documented above).
        lsass_node = f"atk_{iid}_{self._LSASS}"
        dump = f"atk_{iid}_{self._DUMP}"
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
            # 1. Compromised user gets special privileges (SeDebugPrivilege).
            _ev(timestamps[0], seed_subject, NodeType.user, EdgeType.USER_PRIV_GRANT, mimi, NodeType.process),
            # 2. Mimikatz creates an elevated child process.
            _ev(timestamps[1], mimi, NodeType.process, EdgeType.PROCESS_CREATE, mimi_el, NodeType.process),
            # 3. Elevated mimikatz requests a handle to lsass.exe (modeled as file node per schema workaround).
            _ev(timestamps[2], mimi_el, NodeType.process, EdgeType.HANDLE_REQUEST, lsass_node, NodeType.file),
            # 4. Elevated mimikatz reads lsass memory via the handle.
            _ev(timestamps[3], mimi_el, NodeType.process, EdgeType.FILE_READ, lsass_node, NodeType.file),
            # 5. Elevated mimikatz writes credential dump to disk.
            _ev(timestamps[4], mimi_el, NodeType.process, EdgeType.FILE_WRITE, dump, NodeType.file),
            # 6. Mimikatz reads the dump for further processing.
            _ev(timestamps[5], mimi, NodeType.process, EdgeType.FILE_READ, dump, NodeType.file),
            # 7. Mimikatz connects to C2 for exfiltration.
            _ev(timestamps[6], mimi, NodeType.process, EdgeType.NET_CONNECT, c2_net, NodeType.network),
        ]
