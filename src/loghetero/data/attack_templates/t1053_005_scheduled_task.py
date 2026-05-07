"""T1053.005 - Scheduled Task/Job: Scheduled Task (Phase 5 / Checkpoint 15 Cycle E).

ATT&CK reference: https://attack.mitre.org/techniques/T1053/005/

Behavioural chain (8 events, shared-seed APT design):

    1. user --> USER_LOGON --> schtasks.exe  [seed = victim user]
       Seed event: attacker runs schtasks.exe under victim user's session to
       register a malicious scheduled task (ATLAS EventID 4624 -> 4688).
    2. schtasks.exe --> FILE_WRITE --> malicious_task.xml
       schtasks.exe writes the task definition XML to disk (task export / import
       preparation; ATLAS EventID file write).
    3. schtasks.exe --> FILE_WRITE --> TaskCache registry key  [registry-as-file workaround]
       schtasks.exe writes the task registration to the Windows Task Scheduler
       registry hive. Modeled as FILE_WRITE to a file node per the registry-as-file
       workaround documented in T1547.001 (see cross-reference below).
    4. schtasks.exe --> FILE_READ --> malicious_task.xml
       schtasks.exe reads the task XML back to validate / load the task definition.
    5. schtasks.exe --> PROCESS_CREATE --> payload.exe
       The scheduled task triggers: schtasks.exe (or Task Scheduler service) spawns
       payload.exe as the task action (EventID 4688).
    6. payload.exe --> FILE_READ --> exfil_target.dat
       payload.exe reads the data file targeted for exfiltration.
    7. payload.exe --> NET_CONNECT --> c2_net
       payload.exe establishes a C2 channel for data exfiltration.
    8. payload.exe --> NET_SEND_NETWORK --> c2_net
       payload.exe sends exfil data over the established C2 channel.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_schtasks.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

Schema workaround (event 3) -- REUSED from T1547.001 (NO new inventory entry):
    The Windows Task Scheduler registry key path
    ``\\Registry\\Machine\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Schedule\\TaskCache``
    is modeled as a ``file`` node, and the write is modeled as FILE_WRITE
    (process --> file edge). This is the SAME registry-as-file workaround
    documented in T1547.001 (Phase 4 / Checkpoint 14.5) and its inventory entry
    in docs/known_issues.md "schema workaround inventory". No new inventory entry
    is created; this is a reuse of the established pattern.

    Cross-reference: T1547.001 inventory entry #4 (docs/known_issues.md):
        "Registry write modeled as FILE_WRITE to \\Registry\\Machine\\... path
        (file node). Rationale: ALLOWED_EDGE_TRIPLES lacks registry edge type;
        EDR tools route ETW EventID 4657 registry value writes to file-like edges."

Triple summary (all in ALLOWED_EDGE_TRIPLES):
    - (user, USER_LOGON, process) x1  (event 1)
    - (process, FILE_WRITE, file) x2  (events 2 and 3; event 3 uses registry-as-file)
    - (process, FILE_READ, file) x2  (events 4 and 6)
    - (process, PROCESS_CREATE, process) x1  (event 5)
    - (process, NET_CONNECT, network) x1  (event 7)
    - (process, NET_SEND_NETWORK, network) x1  (event 8)

Module-level constants pattern (Phase 5 convention):
    T1053.005 uses module-level constants following the Phase 5 convention
    established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C),
    and T1057/T1083 (Cycle D).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_SCHTASKS = "schtasks.exe"
_TASK_XML = "malicious_task.xml"
# Windows Task Scheduler registry path modeled as file node (registry-as-file workaround,
# reused from T1547.001; see module docstring for cross-reference).
_TASK_CACHE_REG = r"\Registry\Machine\Software\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache"
_PAYLOAD = "payload.exe"
_EXFIL_TARGET = "exfil_target.dat"
_C2_IP = "185.220.101.54"
_C2_PORT = "8443"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h11"


class T1053005ScheduledTask(AttackTemplate):
    """Scheduled task persistence chain (T1053.005) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1053.005", "Scheduled Task/Job: Scheduled Task")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate an 8-event scheduled task persistence + execution chain.

        Event 3 uses the registry-as-file workaround (REUSED from T1547.001,
        no new inventory entry): TaskCache registry key path modeled as FILE_WRITE
        to a file node. Cross-reference T1547.001 module docstring and
        docs/known_issues.md schema workaround inventory.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        schtasks = f"atk_{iid}_{_SCHTASKS}"
        task_xml = f"atk_{iid}_{_TASK_XML}"
        # Registry key path modeled as file node (registry-as-file workaround, T1547.001 reuse).
        task_cache_node = f"atk_{iid}_{_TASK_CACHE_REG}"
        payload = f"atk_{iid}_{_PAYLOAD}"
        exfil_target = f"atk_{iid}_{_EXFIL_TARGET}"
        c2_net = f"atk_{iid}_{_C2_IP}:{_C2_PORT}"

        n_events = 8
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
            # 1. USER_LOGON (4624): victim user session; schtasks.exe spawned
            #    by attacker to register a malicious scheduled task.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                schtasks,
                NodeType.process,
            ),
            # 2. schtasks.exe writes the task definition XML (task /create /xml).
            _ev(
                timestamps[1],
                schtasks,
                NodeType.process,
                EdgeType.FILE_WRITE,
                task_xml,
                NodeType.file,
            ),
            # 3. schtasks.exe writes to Task Scheduler registry hive (EventID 4657).
            #    Registry-as-file workaround REUSED from T1547.001 (no new inventory entry).
            #    TaskCache path modeled as file node with FILE_WRITE edge.
            _ev(
                timestamps[2],
                schtasks,
                NodeType.process,
                EdgeType.FILE_WRITE,
                task_cache_node,
                NodeType.file,
            ),
            # 4. schtasks.exe reads back the task XML to validate the task definition.
            _ev(
                timestamps[3],
                schtasks,
                NodeType.process,
                EdgeType.FILE_READ,
                task_xml,
                NodeType.file,
            ),
            # 5. Scheduled task triggers: schtasks.exe spawns payload.exe (EventID 4688).
            _ev(
                timestamps[4],
                schtasks,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                payload,
                NodeType.process,
            ),
            # 6. payload.exe reads the targeted exfiltration data file.
            _ev(
                timestamps[5],
                payload,
                NodeType.process,
                EdgeType.FILE_READ,
                exfil_target,
                NodeType.file,
            ),
            # 7. payload.exe connects to C2 for data exfiltration.
            _ev(
                timestamps[6],
                payload,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
            # 8. payload.exe sends exfiltrated data over established C2 channel.
            _ev(
                timestamps[7],
                payload,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                c2_net,
                NodeType.network,
            ),
        ]
