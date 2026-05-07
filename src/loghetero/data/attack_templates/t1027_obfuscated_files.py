"""T1027 - Obfuscated Files or Information (Phase 5 / Checkpoint 15 Cycle E).

ATT&CK reference: https://attack.mitre.org/techniques/T1027/

Behavioural chain (7 events, shared-seed APT design):

    1. user --> USER_LOGON --> certutil.exe  [seed = victim user]
       Seed event: attacker leverages certutil.exe (LOLBin) under victim user's
       session to decode a base64-encoded payload (ATLAS EventID 4624 -> 4688).
    2. certutil.exe --> FILE_READ --> encoded_payload.b64
       certutil.exe reads the base64-encoded payload file for decoding.
    3. certutil.exe --> FILE_WRITE --> decoded_payload.exe
       certutil.exe writes the decoded binary to disk (certutil -decode).
    4. certutil.exe --> PROCESS_CREATE --> decoded_payload.exe
       certutil.exe (or a parent orchestrator) launches the decoded payload.
    5. decoded_payload.exe --> FILE_READ --> decoded_payload.exe
       Decoded payload reads its own image (self-inspection / anti-analysis check).
    6. decoded_payload.exe --> NET_CONNECT --> c2_net
       Decoded payload establishes C2 channel (TCP connect to attacker infra).
    7. decoded_payload.exe --> NET_SEND_NETWORK --> c2_net
       Decoded payload sends beaconing/data over established C2 channel.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_certutil.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

No schema workaround needed:
    All 7 triples are in ALLOWED_EDGE_TRIPLES:
    - (user, USER_LOGON, process) x1  (event 1)
    - (process, FILE_READ, file) x2  (events 2 and 5)
    - (process, FILE_WRITE, file) x1  (event 3)
    - (process, PROCESS_CREATE, process) x1  (event 4)
    - (process, NET_CONNECT, network) x1  (event 6)
    - (process, NET_SEND_NETWORK, network) x1  (event 7)

Module-level constants pattern (Phase 5 convention):
    T1027 uses module-level constants following the Phase 5 convention
    established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C),
    and T1057/T1083 (Cycle D).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_CERTUTIL = "certutil.exe"
_ENCODED_PAYLOAD = "encoded_payload.b64"
_DECODED_PAYLOAD = "decoded_payload.exe"
_C2_IP = "185.220.101.52"
_C2_PORT = "4443"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h9"


class T1027ObfuscatedFiles(AttackTemplate):
    """Obfuscated files (certutil decode + execute) chain (T1027) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1027", "Obfuscated Files or Information")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event obfuscated-files LOLBin decode chain.

        No schema workaround needed: all triples in ALLOWED_EDGE_TRIPLES.
        Event 5 is a self-read (decoded_payload.exe reads its own image) --
        subject and object share the same base name but both are atk_-prefixed
        process vs file disambiguation is NOT needed here because PROCESS_CREATE
        at event 4 creates a process node, while FILE_READ at event 5 targets
        the same file path (both are atk_{iid}_decoded_payload.exe); the graph
        schema resolves them via distinct node_type labels.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        certutil = f"atk_{iid}_{_CERTUTIL}"
        encoded_payload = f"atk_{iid}_{_ENCODED_PAYLOAD}"
        decoded_payload = f"atk_{iid}_{_DECODED_PAYLOAD}"
        c2_net = f"atk_{iid}_{_C2_IP}:{_C2_PORT}"

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
                log_type=_LOG_TYPE,
                scenario_id=_SCENARIO,
                host_id=_HOST,
                attributes={"ttp": self.ttp_id, "instance_id": iid, "label": 1},
            )

        return [
            # 1. USER_LOGON (4624): victim user session; certutil.exe (LOLBin) spawned
            #    by attacker's implant to decode a base64-encoded payload.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                certutil,
                NodeType.process,
            ),
            # 2. certutil.exe reads the base64-encoded payload file.
            _ev(
                timestamps[1],
                certutil,
                NodeType.process,
                EdgeType.FILE_READ,
                encoded_payload,
                NodeType.file,
            ),
            # 3. certutil.exe writes the decoded binary to disk (certutil -decode output).
            _ev(
                timestamps[2],
                certutil,
                NodeType.process,
                EdgeType.FILE_WRITE,
                decoded_payload,
                NodeType.file,
            ),
            # 4. certutil.exe (or orchestrator) launches the decoded payload (EventID 4688).
            _ev(
                timestamps[3],
                certutil,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                decoded_payload,
                NodeType.process,
            ),
            # 5. decoded_payload.exe self-reads its own image (anti-analysis / integrity check).
            #    Subject is the process node; object is the file node with same basename.
            _ev(
                timestamps[4],
                decoded_payload,
                NodeType.process,
                EdgeType.FILE_READ,
                decoded_payload,
                NodeType.file,
            ),
            # 6. decoded_payload.exe connects to C2 (TCP connect, EventID NetConnect).
            _ev(
                timestamps[5],
                decoded_payload,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
            # 7. decoded_payload.exe sends beaconing data over established C2 channel.
            _ev(
                timestamps[6],
                decoded_payload,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                c2_net,
                NodeType.network,
            ),
        ]
