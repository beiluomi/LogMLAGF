"""T1070.004 - Indicator Removal: File Deletion (Phase 5 / Checkpoint 15 Cycle E).

ATT&CK reference: https://attack.mitre.org/techniques/T1070/004/

Behavioural chain (7 events, shared-seed APT design):

    1. user --> USER_LOGON --> cleanup_tool.exe  [seed = victim user]
       Seed event: attacker runs cleanup_tool.exe under victim user's session
       to delete attack artifacts (ATLAS EventID 4624 -> 4688).
    2. cleanup_tool.exe --> FILE_READ --> malware.exe
       cleanup_tool.exe reads the malware binary before deletion (verify target).
    3. cleanup_tool.exe --> FILE_DELETE --> malware.exe
       cleanup_tool.exe deletes the malware binary to remove evidence.
    4. cleanup_tool.exe --> FILE_READ --> attack_log.txt
       cleanup_tool.exe reads the attack log before deletion.
    5. cleanup_tool.exe --> FILE_DELETE --> attack_log.txt
       cleanup_tool.exe deletes the attack log to cover tracks.
    6. cleanup_tool.exe --> FILE_DELETE --> cred_dump.dmp
       cleanup_tool.exe deletes the credential dump artifact (cross-TTP reference:
       artifact name matches T1003.001 Phase 4 template's cred_dump.dmp output).
       NOTE: synthetic_injector keeps these as separate atk_-prefixed nodes per
       its iid namespacing, so there is no actual graph node collision between
       T1003.001 and T1070.004 chain instances; the string match is purely for
       attack chain narrative coherence.
    7. cleanup_tool.exe --> NET_CONNECT --> c2_net
       cleanup_tool.exe phones home to signal cleanup completion.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_cleanup_tool.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

No schema workaround needed:
    All 7 triples are in ALLOWED_EDGE_TRIPLES:
    - (user, USER_LOGON, process) x1  (event 1)
    - (process, FILE_READ, file) x2  (events 2 and 4)
    - (process, FILE_DELETE, file) x3  (events 3, 5, and 6)
    - (process, NET_CONNECT, network) x1  (event 7)
    FILE_DELETE was already confirmed present (T1041 Exfiltration uses it).

Cross-TTP narrative note (event 6):
    ``cred_dump.dmp`` artifact name matches the T1003.001 (LSASS memory) Phase 4
    template output. This is intentional for attack-chain realism. The
    synthetic_injector iid namespacing ensures the two chain instances use
    distinct ``atk_<iid>_`` prefixed node IDs and do not share graph nodes.

Module-level constants pattern (Phase 5 convention):
    T1070.004 uses module-level constants following the Phase 5 convention
    established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C),
    and T1057/T1083 (Cycle D).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_CLEANUP_TOOL = "cleanup_tool.exe"
_MALWARE = "malware.exe"
_ATTACK_LOG = "attack_log.txt"
_CRED_DUMP = "cred_dump.dmp"
_C2_IP = "185.220.101.53"
_C2_PORT = "4444"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h10"


class T1070004FileDeletion(AttackTemplate):
    """File deletion (indicator removal) chain (T1070.004) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1070.004", "Indicator Removal: File Deletion")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event file-deletion indicator-removal chain.

        No schema workaround needed: all triples in ALLOWED_EDGE_TRIPLES.
        Event 6 references cred_dump.dmp for T1003.001 cross-TTP narrative
        coherence; iid namespacing prevents graph node collision.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        cleanup_tool = f"atk_{iid}_{_CLEANUP_TOOL}"
        malware = f"atk_{iid}_{_MALWARE}"
        attack_log = f"atk_{iid}_{_ATTACK_LOG}"
        cred_dump = f"atk_{iid}_{_CRED_DUMP}"
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
            # 1. USER_LOGON (4624): victim user session; cleanup_tool.exe spawned
            #    by attacker to delete post-attack artifacts.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                cleanup_tool,
                NodeType.process,
            ),
            # 2. cleanup_tool.exe reads malware.exe before deletion (target verification).
            _ev(
                timestamps[1],
                cleanup_tool,
                NodeType.process,
                EdgeType.FILE_READ,
                malware,
                NodeType.file,
            ),
            # 3. cleanup_tool.exe deletes malware.exe to remove the dropper artifact.
            _ev(
                timestamps[2],
                cleanup_tool,
                NodeType.process,
                EdgeType.FILE_DELETE,
                malware,
                NodeType.file,
            ),
            # 4. cleanup_tool.exe reads attack_log.txt before deletion.
            _ev(
                timestamps[3],
                cleanup_tool,
                NodeType.process,
                EdgeType.FILE_READ,
                attack_log,
                NodeType.file,
            ),
            # 5. cleanup_tool.exe deletes attack_log.txt to cover activity tracks.
            _ev(
                timestamps[4],
                cleanup_tool,
                NodeType.process,
                EdgeType.FILE_DELETE,
                attack_log,
                NodeType.file,
            ),
            # 6. cleanup_tool.exe deletes cred_dump.dmp (T1003.001 cross-TTP artifact name;
            #    see module docstring for narrative coherence explanation).
            _ev(
                timestamps[5],
                cleanup_tool,
                NodeType.process,
                EdgeType.FILE_DELETE,
                cred_dump,
                NodeType.file,
            ),
            # 7. cleanup_tool.exe phones home to signal cleanup completion.
            _ev(
                timestamps[6],
                cleanup_tool,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
        ]
