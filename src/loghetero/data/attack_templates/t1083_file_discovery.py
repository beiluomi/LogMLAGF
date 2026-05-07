"""T1083 - File and Directory Discovery (Phase 5 / Checkpoint 15 Cycle D).

ATT&CK reference: https://attack.mitre.org/techniques/T1083/

Behavioural chain (8 events, shared-seed APT design):

    1. user --> USER_LOGON --> cmd.exe  [seed = victim user]
       Seed event: attacker executes cmd.exe under victim user's session to
       drive directory enumeration (ATLAS EventID 4624 -> 4688 chain).
    2. cmd.exe --> PROCESS_CREATE --> dir_enum.exe
       cmd.exe spawns a directory enumeration tool (dir_enum.exe represents
       dir.exe, robocopy, or a custom enumeration utility).
    3. dir_enum.exe --> FILE_ACCESS --> C_drive_root
       dir_enum.exe accesses the C: drive root to begin file system traversal
       (ATLAS EventID 4663 generic file access -- FILE_ACCESS).
    4. dir_enum.exe --> FILE_READ --> Documents_folder
       dir_enum.exe reads the Documents folder for sensitive file discovery.
    5. dir_enum.exe --> FILE_READ --> Desktop_folder
       dir_enum.exe reads the Desktop folder (high-value credential/config files).
    6. dir_enum.exe --> FILE_WRITE --> file_listing.txt
       dir_enum.exe writes the collected directory listing to a staging file.
    7. cmd.exe --> FILE_READ --> file_listing.txt
       cmd.exe reads the directory listing for post-processing / exfil prep.
    8. cmd.exe --> NET_CONNECT --> c2_net
       cmd.exe exfiltrates the directory listing to attacker-controlled C2.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_cmd.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

No schema workaround needed:
    All 8 triples are in ALLOWED_EDGE_TRIPLES:
    - (user, USER_LOGON, process) x1  (event 1)
    - (process, PROCESS_CREATE, process) x1  (event 2)
    - (process, FILE_ACCESS, file) x1  (event 3) -- ATLAS EventID 4663
    - (process, FILE_READ, file) x3  (events 4, 5, 7)
    - (process, FILE_WRITE, file) x1  (event 6)
    - (process, NET_CONNECT, network) x1  (event 8)

Module-level constants pattern (Phase 5 new convention):
    T1083 uses module-level constants rather than class-level constants to keep
    the inner ``_ev()`` closure inside ``generate()`` clean. Follows the Phase 5
    convention established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_CMD = "cmd.exe"
_DIR_ENUM = "dir_enum.exe"
_C_DRIVE_ROOT = "C_drive_root"
_DOCUMENTS_FOLDER = "Documents_folder"
_DESKTOP_FOLDER = "Desktop_folder"
_FILE_LISTING = "file_listing.txt"
_C2_IP = "185.220.101.51"
_C2_PORT = "4444"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h8"


class T1083FileDiscovery(AttackTemplate):
    """File and directory discovery chain (T1083) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1083", "File and Directory Discovery")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate an 8-event file and directory discovery chain.

        No schema workaround needed: all triples in ALLOWED_EDGE_TRIPLES.
        Event 3 uses FILE_ACCESS (ATLAS EventID 4663) for generic file system
        access -- (process, FILE_ACCESS, file) is in ALLOWED_EDGE_TRIPLES.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        cmd = f"atk_{iid}_{_CMD}"
        dir_enum = f"atk_{iid}_{_DIR_ENUM}"
        c_drive_root = f"atk_{iid}_{_C_DRIVE_ROOT}"
        documents_folder = f"atk_{iid}_{_DOCUMENTS_FOLDER}"
        desktop_folder = f"atk_{iid}_{_DESKTOP_FOLDER}"
        file_listing = f"atk_{iid}_{_FILE_LISTING}"
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
            # 1. USER_LOGON (4624): victim user session; cmd.exe spawned by
            #    attacker's implant to begin directory enumeration.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                cmd,
                NodeType.process,
            ),
            # 2. cmd.exe spawns dir_enum.exe (directory enumeration tool, EventID 4688).
            _ev(
                timestamps[1],
                cmd,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                dir_enum,
                NodeType.process,
            ),
            # 3. dir_enum.exe accesses C: drive root to begin file system traversal.
            #    FILE_ACCESS maps to ATLAS EventID 4663 (generic object access).
            _ev(
                timestamps[2],
                dir_enum,
                NodeType.process,
                EdgeType.FILE_ACCESS,
                c_drive_root,
                NodeType.file,
            ),
            # 4. dir_enum.exe reads Documents folder (high-value sensitive documents).
            _ev(
                timestamps[3],
                dir_enum,
                NodeType.process,
                EdgeType.FILE_READ,
                documents_folder,
                NodeType.file,
            ),
            # 5. dir_enum.exe reads Desktop folder (credential files, shortcuts, configs).
            _ev(
                timestamps[4],
                dir_enum,
                NodeType.process,
                EdgeType.FILE_READ,
                desktop_folder,
                NodeType.file,
            ),
            # 6. dir_enum.exe writes collected directory listing to a staging file.
            _ev(
                timestamps[5],
                dir_enum,
                NodeType.process,
                EdgeType.FILE_WRITE,
                file_listing,
                NodeType.file,
            ),
            # 7. cmd.exe reads the directory listing for post-processing / exfil prep.
            _ev(
                timestamps[6],
                cmd,
                NodeType.process,
                EdgeType.FILE_READ,
                file_listing,
                NodeType.file,
            ),
            # 8. cmd.exe exfiltrates the directory listing to attacker-controlled C2.
            _ev(
                timestamps[7],
                cmd,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
        ]
