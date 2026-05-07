"""T1543.003 - Create or Modify System Process: Windows Service (Phase 5 / Checkpoint 15 Cycle E).

ATT&CK reference: https://attack.mitre.org/techniques/T1543/003/

Behavioural chain (7 events, shared-seed APT design):

    1. user --> USER_PRIV_GRANT --> sc.exe  [seed event with USER_PRIV_GRANT]
       Seed event: attacker requires a privileged session (SeServiceLogonRight /
       SeImpersonatePrivilege) before sc.exe can install a service. USER_PRIV_GRANT
       (ATLAS EventID 4672 -- Special privileges assigned to new logon) replaces
       the usual USER_LOGON seed because service installation requires elevated
       privileges. Triple (user, USER_PRIV_GRANT, process) IS in ALLOWED_EDGE_TRIPLES.
    2. sc.exe --> FILE_WRITE --> malicious_service.exe
       sc.exe (or the attacker's dropper) writes the service binary to disk.
    3. sc.exe --> FILE_WRITE --> Service registry key  [registry-as-file workaround]
       sc.exe writes the service registration to
       ``\\Registry\\Machine\\System\\CurrentControlSet\\Services\\MalSvc``.
       Modeled as FILE_WRITE to a file node per the registry-as-file workaround
       documented in T1547.001 (see cross-reference below).
    4. sc.exe --> PROCESS_CREATE --> malicious_service.exe
       sc.exe starts the service: Windows Service Control Manager spawns the
       service binary (EventID 4688 / ServiceStart).
    5. malicious_service.exe --> FILE_READ --> config.dat
       Service reads a configuration / staging file for C2 parameters or target info.
    6. malicious_service.exe --> NET_CONNECT --> c2_net
       Service establishes a C2 channel (beacon / reverse shell connect).
    7. malicious_service.exe --> NET_SEND_NETWORK --> c2_net
       Service sends beaconing or exfiltration data over established C2 channel.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_PRIV_GRANT from that existing benign user node to a new
    ``atk_<iid>_sc.exe`` process node. All remaining nodes are ``atk_``-prefixed.

    USER_PRIV_GRANT seed (not USER_LOGON):
    sc.exe requires SeServiceLogonRight / elevated privileges to install a Windows
    service. ATLAS EventID 4672 (Special privileges assigned to new logon) fires
    immediately after a privileged logon and is the correct seed for service
    installation scenarios. The triple (user, USER_PRIV_GRANT, process) is in
    ALLOWED_EDGE_TRIPLES (line 138 of parsers/base.py), so no new workaround is
    introduced.

Schema workaround (event 3) -- REUSED from T1547.001 (NO new inventory entry):
    The Windows service registry key path
    ``\\Registry\\Machine\\System\\CurrentControlSet\\Services\\MalSvc``
    is modeled as a ``file`` node, and the write is modeled as FILE_WRITE
    (process --> file edge). This is the SAME registry-as-file workaround
    documented in T1547.001 (Phase 4 / Checkpoint 14.5). No new inventory entry
    is created; this is a reuse of the established pattern.

    Cross-reference: T1547.001 inventory entry (docs/known_issues.md):
        "Registry write modeled as FILE_WRITE to \\Registry\\Machine\\... path
        (file node). Rationale: ALLOWED_EDGE_TRIPLES lacks registry edge type;
        EDR tools route ETW EventID 4657 registry value writes to file-like edges."

Triple summary (all in ALLOWED_EDGE_TRIPLES):
    - (user, USER_PRIV_GRANT, process) x1  (event 1; privileged seed)
    - (process, FILE_WRITE, file) x2  (events 2 and 3; event 3 uses registry-as-file)
    - (process, PROCESS_CREATE, process) x1  (event 4)
    - (process, FILE_READ, file) x1  (event 5)
    - (process, NET_CONNECT, network) x1  (event 6)
    - (process, NET_SEND_NETWORK, network) x1  (event 7)

Module-level constants pattern (Phase 5 convention):
    T1543.003 uses module-level constants following the Phase 5 convention
    established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C),
    and T1057/T1083 (Cycle D).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_SC = "sc.exe"
_MALICIOUS_SERVICE = "malicious_service.exe"
# Windows service registry key path modeled as file node (registry-as-file workaround,
# reused from T1547.001; see module docstring for cross-reference).
_SERVICE_REG = r"\Registry\Machine\System\CurrentControlSet\Services\MalSvc"
_CONFIG = "config.dat"
_C2_IP = "185.220.101.55"
_C2_PORT = "9443"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h12"


class T1543003WindowsService(AttackTemplate):
    """Windows service installation persistence chain (T1543.003) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1543.003", "Create or Modify System Process: Windows Service")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event Windows service installation + execution chain.

        Event 1 uses USER_PRIV_GRANT (not USER_LOGON) as seed because service
        installation requires elevated privileges (ATLAS EventID 4672).
        Event 3 uses the registry-as-file workaround (REUSED from T1547.001,
        no new inventory entry): service registry key path modeled as FILE_WRITE
        to a file node. Cross-reference T1547.001 module docstring and
        docs/known_issues.md schema workaround inventory.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        sc = f"atk_{iid}_{_SC}"
        malicious_service = f"atk_{iid}_{_MALICIOUS_SERVICE}"
        # Registry key path modeled as file node (registry-as-file workaround, T1547.001 reuse).
        service_reg_node = f"atk_{iid}_{_SERVICE_REG}"
        config = f"atk_{iid}_{_CONFIG}"
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
            # 1. USER_PRIV_GRANT (4672): privileged session seed. sc.exe requires elevated
            #    privileges (SeServiceLogonRight) to install a Windows service. ATLAS
            #    EventID 4672 fires immediately after a privileged logon.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_PRIV_GRANT,
                sc,
                NodeType.process,
            ),
            # 2. sc.exe writes the malicious service binary to disk.
            _ev(
                timestamps[1],
                sc,
                NodeType.process,
                EdgeType.FILE_WRITE,
                malicious_service,
                NodeType.file,
            ),
            # 3. sc.exe writes service registration to the SCM registry hive (EventID 4657).
            #    Registry-as-file workaround REUSED from T1547.001 (no new inventory entry).
            #    Services\MalSvc path modeled as file node with FILE_WRITE edge.
            _ev(
                timestamps[2],
                sc,
                NodeType.process,
                EdgeType.FILE_WRITE,
                service_reg_node,
                NodeType.file,
            ),
            # 4. sc.exe starts the service: Service Control Manager spawns service binary.
            _ev(
                timestamps[3],
                sc,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                malicious_service,
                NodeType.process,
            ),
            # 5. malicious_service.exe reads config.dat (C2 parameters / target staging).
            _ev(
                timestamps[4],
                malicious_service,
                NodeType.process,
                EdgeType.FILE_READ,
                config,
                NodeType.file,
            ),
            # 6. malicious_service.exe connects to C2 (beacon / reverse shell).
            _ev(
                timestamps[5],
                malicious_service,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
            # 7. malicious_service.exe sends beaconing/exfil data over C2 channel.
            _ev(
                timestamps[6],
                malicious_service,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                c2_net,
                NodeType.network,
            ),
        ]
