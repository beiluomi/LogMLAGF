"""T1057 - Process Discovery (Phase 5 / Checkpoint 15 Cycle D).

ATT&CK reference: https://attack.mitre.org/techniques/T1057/

Behavioural chain (7 events, shared-seed APT design):

    1. user --> USER_LOGON --> tasklist.exe  [seed = victim user]
       Seed event: attacker executes tasklist.exe under victim user's session
       to enumerate running processes (ATLAS EventID 4624 -> 4688 chain).
    2. tasklist.exe --> FILE_WRITE --> process_list.txt
       tasklist.exe writes the process enumeration output to a temp file.
    3. tasklist.exe --> FILE_READ --> process_list.txt
       tasklist.exe re-reads its own output to validate/process the listing.
    4. tasklist.exe --> PROCESS_CREATE --> findstr.exe
       tasklist.exe (or the attacker's wrapper script) spawns findstr.exe to
       search the process list for security tool processes (AV/EDR names).
    5. findstr.exe --> FILE_READ --> process_list.txt
       findstr.exe reads the process list to perform pattern matching.
    6. findstr.exe --> FILE_WRITE --> av_processes.txt
       findstr.exe writes matching AV/EDR process names to a results file.
    7. tasklist.exe --> NET_CONNECT --> c2_net
       tasklist.exe (or the attacker's orchestrator) exfiltrates the discovery
       results back to C2 for situational awareness.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_tasklist.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

No schema workaround needed:
    All 7 triples are in ALLOWED_EDGE_TRIPLES:
    - (user, USER_LOGON, process) x1  (event 1)
    - (process, FILE_WRITE, file) x2  (events 2 and 6)
    - (process, FILE_READ, file) x2  (events 3 and 5)
    - (process, PROCESS_CREATE, process) x1  (event 4)
    - (process, NET_CONNECT, network) x1  (event 7)

Module-level constants pattern (Phase 5 new convention):
    T1057 uses module-level constants rather than class-level constants to keep
    the inner ``_ev()`` closure inside ``generate()`` clean. Follows the Phase 5
    convention established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_TASKLIST = "tasklist.exe"
_PROCESS_LIST = "process_list.txt"
_FINDSTR = "findstr.exe"
_AV_PROCESSES = "av_processes.txt"
_C2_IP = "185.220.101.50"
_C2_PORT = "9090"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h7"


class T1057ProcessDiscovery(AttackTemplate):
    """Process discovery enumeration chain (T1057) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1057", "Process Discovery")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event process discovery chain.

        No schema workaround needed: all triples in ALLOWED_EDGE_TRIPLES.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        tasklist = f"atk_{iid}_{_TASKLIST}"
        process_list = f"atk_{iid}_{_PROCESS_LIST}"
        findstr = f"atk_{iid}_{_FINDSTR}"
        av_processes = f"atk_{iid}_{_AV_PROCESSES}"
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
            # 1. USER_LOGON (4624): victim user session; tasklist.exe spawned
            #    by attacker's implant to enumerate running processes.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                tasklist,
                NodeType.process,
            ),
            # 2. tasklist.exe writes process enumeration output to temp file.
            _ev(
                timestamps[1],
                tasklist,
                NodeType.process,
                EdgeType.FILE_WRITE,
                process_list,
                NodeType.file,
            ),
            # 3. tasklist.exe re-reads process_list.txt (validate/post-process output).
            _ev(
                timestamps[2],
                tasklist,
                NodeType.process,
                EdgeType.FILE_READ,
                process_list,
                NodeType.file,
            ),
            # 4. tasklist.exe (or attacker's wrapper) spawns findstr.exe to search
            #    for AV/EDR processes in the listing (EventID 4688).
            _ev(
                timestamps[3],
                tasklist,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                findstr,
                NodeType.process,
            ),
            # 5. findstr.exe reads process_list.txt to perform pattern matching.
            _ev(
                timestamps[4],
                findstr,
                NodeType.process,
                EdgeType.FILE_READ,
                process_list,
                NodeType.file,
            ),
            # 6. findstr.exe writes matched AV/EDR process names to results file.
            _ev(
                timestamps[5],
                findstr,
                NodeType.process,
                EdgeType.FILE_WRITE,
                av_processes,
                NodeType.file,
            ),
            # 7. tasklist.exe exfiltrates discovery results to C2 (situational awareness).
            _ev(
                timestamps[6],
                tasklist,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
        ]
