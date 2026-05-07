"""T1071.001 - Application Layer Protocol: Web Protocols (Phase 4 / Checkpoint 14.5).

ATT&CK reference: https://attack.mitre.org/techniques/T1071/001/

Behavioural chain (7 events, per RFC-14.5-1 accepted sequence):

    1. user --> USER_LOGON --> process (implant.exe) [seed = user]
    2. implant.exe --> NET_CONNECT --> network (DNS server 192.168.1.2:53)
    3. implant.exe --> NET_CONNECT --> network (C2 HTTP endpoint)
    4. implant.exe --> NET_HTTP_REQUEST --> network (C2 HTTP endpoint, beacon)
    5. implant.exe --> FILE_WRITE --> beacon_response.tmp
    6. implant.exe --> NET_HTTP_REQUEST --> network (C2 HTTP endpoint, task fetch)
    7. implant.exe --> NET_SEND_NETWORK --> network (C2 HTTP endpoint, result upload)

DNS resolution step (RFC-14.5-2):
    Process-level DNS initiation is modeled as NET_CONNECT from process to a
    network node representing the DNS server IP (192.168.1.2:53).  This uses
    the existing (process, NET_CONNECT, network) triple without extending
    ALLOWED_EDGE_TRIPLES.

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


class T1071001WebProtocols(AttackTemplate):
    """HTTP C2 beacon chain (T1071.001) synthetic event generator."""

    _IMPLANT = "implant.exe"
    _DNS_SERVER = "192.168.1.2:53"
    _C2_HTTP = "185.220.101.45:80"
    _BEACON_TMP = "beacon_response.tmp"
    _LOG_TYPE = "synthetic_atlas"
    _SCENARIO = "synthetic_apt"
    _HOST = "h2"

    def __init__(self) -> None:
        super().__init__("T1071.001", "Web Protocols")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event HTTP C2 beacon chain."""
        assert isinstance(rng, random.Random)
        iid = instance_id

        implant = f"atk_{iid}_{self._IMPLANT}"
        dns_net = f"atk_{iid}_{self._DNS_SERVER}"
        c2_net = f"atk_{iid}_{self._C2_HTTP}"
        beacon_tmp = f"atk_{iid}_{self._BEACON_TMP}"

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
            # 1. Compromised user logon spawns the implant process.
            _ev(timestamps[0], seed_subject, NodeType.user, EdgeType.USER_LOGON, implant, NodeType.process),
            # 2. Process-level DNS resolution: NET_CONNECT to DNS server (RFC-14.5-2).
            _ev(timestamps[1], implant, NodeType.process, EdgeType.NET_CONNECT, dns_net, NodeType.network),
            # 3. Implant connects to the C2 HTTP endpoint.
            _ev(timestamps[2], implant, NodeType.process, EdgeType.NET_CONNECT, c2_net, NodeType.network),
            # 4. Implant sends initial HTTP beacon (check-in).
            _ev(timestamps[3], implant, NodeType.process, EdgeType.NET_HTTP_REQUEST, c2_net, NodeType.network),
            # 5. Implant writes the C2 response to a temp file.
            _ev(timestamps[4], implant, NodeType.process, EdgeType.FILE_WRITE, beacon_tmp, NodeType.file),
            # 6. Implant sends another HTTP request to fetch tasking.
            _ev(timestamps[5], implant, NodeType.process, EdgeType.NET_HTTP_REQUEST, c2_net, NodeType.network),
            # 7. Implant uploads results back to C2.
            _ev(timestamps[6], implant, NodeType.process, EdgeType.NET_SEND_NETWORK, c2_net, NodeType.network),
        ]
