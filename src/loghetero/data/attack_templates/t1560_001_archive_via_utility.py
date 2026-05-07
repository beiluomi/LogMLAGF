"""T1560.001 - Archive Collected Data: Archive via Utility (Phase 5 / Checkpoint 15 Cycle F).

ATT&CK reference: https://attack.mitre.org/techniques/T1560/001/

Behavioural chain (8 events, shared-seed APT design):

    1. (user, USER_LOGON, 7zip.exe)  [seed event]
    2. (7zip.exe, FILE_READ, sensitive_doc1.docx)
    3. (7zip.exe, FILE_READ, sensitive_doc2.xlsx)
    4. (7zip.exe, FILE_READ, sensitive_db.sqlite)
    5. (7zip.exe, FILE_WRITE, collected_archive.7z)
    6. (7zip.exe, FILE_READ, collected_archive.7z)
    7. (7zip.exe, NET_CONNECT, c2_net)
    8. (7zip.exe, NET_SEND_NETWORK, c2_net)

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_7zip.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

Schema workaround: NONE.
    All 8 triples are natively in ALLOWED_EDGE_TRIPLES. No schema workaround
    needed; no inventory entry created for this TTP.

Triple summary (all in ALLOWED_EDGE_TRIPLES; zero workarounds):
    - (user, USER_LOGON, process) x1  (event 1; seed)
    - (process, FILE_READ, file) x4  (events 2, 3, 4, 6)
    - (process, FILE_WRITE, file) x1  (event 5)
    - (process, NET_CONNECT, network) x1  (event 7)
    - (process, NET_SEND_NETWORK, network) x1  (event 8)

Module-level constants pattern (Phase 5 convention):
    T1560.001 uses module-level constants following the Phase 5 convention
    established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C),
    T1057/T1083 (Cycle D), and T1027/T1070.004/T1053.005/T1543.003 (Cycle E).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_7ZIP = "7zip.exe"
_DOC1 = "sensitive_doc1.docx"
_DOC2 = "sensitive_doc2.xlsx"
_DB = "sensitive_db.sqlite"
_ARCHIVE = "collected_archive.7z"
_C2_IP = "185.220.101.57"
_C2_PORT = "443"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h14"


class T1560001ArchiveViaUtility(AttackTemplate):
    """Archive collected data via 7zip utility chain (T1560.001) synthetic event generator.

    No schema workaround required: all 8 event triples are natively in
    ALLOWED_EDGE_TRIPLES (USER_LOGON seed + FILE_READ/FILE_WRITE + NET_CONNECT +
    NET_SEND_NETWORK). Standard collection-then-exfiltration pattern.
    """

    def __init__(self) -> None:
        super().__init__("T1560.001", "Archive Collected Data: Archive via Utility")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate an 8-event archive collection + exfiltration chain.

        Sequence: USER_LOGON -> multi-file READ (collection phase) -> archive
        FILE_WRITE -> archive FILE_READ (integrity verify) -> NET_CONNECT +
        NET_SEND_NETWORK (exfiltration). No schema workaround applied.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        sevenzip = f"atk_{iid}_{_7ZIP}"
        doc1 = f"atk_{iid}_{_DOC1}"
        doc2 = f"atk_{iid}_{_DOC2}"
        db = f"atk_{iid}_{_DB}"
        archive = f"atk_{iid}_{_ARCHIVE}"
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
            # 1. USER_LOGON (4624): victim_user session; attacker runs 7zip.exe
            #    under the compromised user account to archive collected data.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                sevenzip,
                NodeType.process,
            ),
            # 2. 7zip.exe reads sensitive Word document (data collection phase).
            _ev(
                timestamps[1],
                sevenzip,
                NodeType.process,
                EdgeType.FILE_READ,
                doc1,
                NodeType.file,
            ),
            # 3. 7zip.exe reads sensitive Excel spreadsheet (data collection phase).
            _ev(
                timestamps[2],
                sevenzip,
                NodeType.process,
                EdgeType.FILE_READ,
                doc2,
                NodeType.file,
            ),
            # 4. 7zip.exe reads sensitive SQLite database (data collection phase).
            _ev(
                timestamps[3],
                sevenzip,
                NodeType.process,
                EdgeType.FILE_READ,
                db,
                NodeType.file,
            ),
            # 5. 7zip.exe writes the collected archive (compression phase).
            _ev(
                timestamps[4],
                sevenzip,
                NodeType.process,
                EdgeType.FILE_WRITE,
                archive,
                NodeType.file,
            ),
            # 6. 7zip.exe reads the archive back (integrity verification / staging).
            _ev(
                timestamps[5],
                sevenzip,
                NodeType.process,
                EdgeType.FILE_READ,
                archive,
                NodeType.file,
            ),
            # 7. 7zip.exe connects to C2 for exfiltration (or intermediary uploader).
            _ev(
                timestamps[6],
                sevenzip,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
            # 8. 7zip.exe sends the archive over the established C2 channel.
            _ev(
                timestamps[7],
                sevenzip,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                c2_net,
                NodeType.network,
            ),
        ]
