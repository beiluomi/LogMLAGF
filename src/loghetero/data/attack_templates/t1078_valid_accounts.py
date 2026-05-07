"""T1078 - Valid Accounts (Phase 5 / Checkpoint 15 Cycle D).

ATT&CK reference: https://attack.mitre.org/techniques/T1078/

Behavioural chain (7 events, shared-seed APT design):

    1. user --> USER_LOGON_FAIL --> target_svc.exe  [seed = victim user, first fail]
       Seed event: attacker uses stolen credentials; first attempt fails (EventID 4625).
    2. user --> USER_LOGON_FAIL --> target_svc.exe  [second fail]
       Second failed logon attempt (attacker retries with slightly different creds).
    3. user --> USER_LOGON --> target_svc.exe  [success with stolen creds, EventID 4624]
       Successful logon using compromised account (EventID 4624 LogonType 3 network).
    4. user --> USER_PRIV_GRANT --> target_svc.exe
       Special privileges assigned to the new logon session (EventID 4672):
       attacker's session gains elevated rights via the stolen privileged account.
    5. target_svc.exe --> FILE_READ --> sensitive_config.cfg
       Service process (running under attacker's stolen credentials) reads a
       sensitive configuration file (credentials, DB connection strings, etc.).
    6. target_svc.exe --> FILE_WRITE --> exfil_staging.dat
       Service process writes collected data to an exfiltration staging file.
    7. target_svc.exe --> NET_CONNECT --> c2_net
       Service process exfiltrates staged data to attacker-controlled C2.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Events 1-4
    use the seed user as subject (auth events are user->process in ATLAS schema).
    Events 5-7 use target_svc.exe as subject (post-auth service activity).
    All process/file/network nodes are ``atk_``-prefixed.

No schema workaround needed:
    All 7 triples are in ALLOWED_EDGE_TRIPLES (confirmed via pre-write check):
    - (user, USER_LOGON_FAIL, process) x2  (events 1 and 2) -- added Q-1
    - (user, USER_LOGON, process) x1  (event 3)
    - (user, USER_PRIV_GRANT, process) x1  (event 4) -- same as T1068 workaround
      but NOT a workaround here: seed_user IS the correct semantic subject for
      USER_PRIV_GRANT (4672) because privileges attach to the logon session of the
      authenticated user, not to the process itself.
    - (process, FILE_READ, file) x1  (event 5)
    - (process, FILE_WRITE, file) x1  (event 6)
    - (process, NET_CONNECT, network) x1  (event 7)

Module-level constants pattern (Phase 5 new convention):
    T1078 uses module-level constants rather than class-level constants to keep
    the inner ``_ev()`` closure inside ``generate()`` clean. Follows the Phase 5
    convention established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_TARGET_SVC = "target_svc.exe"
_SENSITIVE_CONFIG = "sensitive_config.cfg"
_EXFIL_STAGING = "exfil_staging.dat"
_C2_IP = "185.220.101.49"
_C2_PORT = "8080"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h6"


class T1078ValidAccounts(AttackTemplate):
    """Valid accounts credential abuse chain (T1078) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1078", "Valid Accounts")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event valid-accounts credential abuse chain.

        No schema workaround needed: all triples in ALLOWED_EDGE_TRIPLES.
        Events 1-4 use seed_user as subject (auth events); events 5-7 use
        target_svc.exe as subject (post-auth service activity).
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        target_svc = f"atk_{iid}_{_TARGET_SVC}"
        sensitive_config = f"atk_{iid}_{_SENSITIVE_CONFIG}"
        exfil_staging = f"atk_{iid}_{_EXFIL_STAGING}"
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
            # 1. USER_LOGON_FAIL (4625): first failed logon attempt with stolen creds.
            #    seed_user is the compromised account; target_svc.exe is the service
            #    being accessed. (user, USER_LOGON_FAIL, process) in ALLOWED_EDGE_TRIPLES.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON_FAIL,
                target_svc,
                NodeType.process,
            ),
            # 2. USER_LOGON_FAIL (4625): second failed logon attempt (retry).
            _ev(
                timestamps[1],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON_FAIL,
                target_svc,
                NodeType.process,
            ),
            # 3. USER_LOGON (4624 LogonType 3): successful logon with stolen credentials.
            _ev(
                timestamps[2],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                target_svc,
                NodeType.process,
            ),
            # 4. USER_PRIV_GRANT (4672): special privileges assigned to the new logon
            #    session -- attacker gains elevated rights via privileged stolen account.
            #    seed_user is the correct semantic subject: privileges attach to the
            #    authenticated user's logon session (EventID 4672 lists the account name).
            _ev(
                timestamps[3],
                seed_subject,
                NodeType.user,
                EdgeType.USER_PRIV_GRANT,
                target_svc,
                NodeType.process,
            ),
            # 5. target_svc.exe reads sensitive configuration file (credentials, DB strings).
            _ev(
                timestamps[4],
                target_svc,
                NodeType.process,
                EdgeType.FILE_READ,
                sensitive_config,
                NodeType.file,
            ),
            # 6. target_svc.exe writes collected data to exfiltration staging file.
            _ev(
                timestamps[5],
                target_svc,
                NodeType.process,
                EdgeType.FILE_WRITE,
                exfil_staging,
                NodeType.file,
            ),
            # 7. target_svc.exe exfiltrates staged data to attacker-controlled C2.
            _ev(
                timestamps[6],
                target_svc,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
        ]
