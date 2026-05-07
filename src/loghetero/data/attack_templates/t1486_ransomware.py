"""T1486 - Data Encrypted for Impact (Ransomware) (Phase 5 / Checkpoint 15 Cycle F).

ATT&CK reference: https://attack.mitre.org/techniques/T1486/

Behavioural chain (9 events, shared-seed APT design):

    1. (user, USER_LOGON, ransom.exe)  [seed event]
    2. (ransom.exe, FILE_READ, important_doc.docx)
    3. (ransom.exe, FILE_WRITE, important_doc.docx.locked)
    4. (ransom.exe, FILE_DELETE, important_doc.docx)
    5. (ransom.exe, FILE_READ, financial_data.xlsx)
    6. (ransom.exe, FILE_WRITE, financial_data.xlsx.locked)
    7. (ransom.exe, FILE_DELETE, financial_data.xlsx)
    8. (ransom.exe, FILE_WRITE, RANSOM_NOTE.txt)
    9. (ransom.exe, NET_CONNECT, c2_net)

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_ransom.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

Schema workaround: NONE.
    All 9 triples are natively in ALLOWED_EDGE_TRIPLES. No schema workaround
    needed; no inventory entry created for this TTP.

Triple summary (all in ALLOWED_EDGE_TRIPLES; zero workarounds):
    - (user, USER_LOGON, process) x1  (event 1; seed)
    - (process, FILE_READ, file) x2  (events 2 and 5)
    - (process, FILE_WRITE, file) x3  (events 3, 6, 8)
    - (process, FILE_DELETE, file) x2  (events 4 and 7)
    - (process, NET_CONNECT, network) x1  (event 9)

Multi-anchor placeholder note (MANDATORY -- 3 placement anchor per Cycle F RFC):
    Checkpoint 16 必须做 T1486 与对应 ransomware-mimicry hard negative pair 即合法磁盘
    加密软件批量加密用户文件 anonymize-then-classify 单独 sanity check 期望 BERT-only F1
    显著降级到 < 0.6 这条 sanity check 不能在整体 hard negative library 层面做必须做单独
    pair。
    (Placement: (i) THIS module docstring -- implementer responsibility.)
    (Placement: (ii) Cycle F closure commit message body -- controller responsibility.)
    (Placement: (iii) DONE_STAGED report to controller -- implementer responsibility.)

Module-level constants pattern (Phase 5 convention):
    T1486 uses module-level constants following the Phase 5 convention
    established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C),
    T1057/T1083 (Cycle D), and T1027/T1070.004/T1053.005/T1543.003 (Cycle E).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_RANSOM = "ransom.exe"
_DOC = "important_doc.docx"
_DOC_LOCKED = "important_doc.docx.locked"
_FINANCIAL = "financial_data.xlsx"
_FINANCIAL_LOCKED = "financial_data.xlsx.locked"
_RANSOM_NOTE = "RANSOM_NOTE.txt"
_C2_IP = "185.220.101.58"
_C2_PORT = "8080"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h15"


class T1486Ransomware(AttackTemplate):
    """Data encrypted for impact / ransomware chain (T1486) synthetic event generator.

    No schema workaround required: all 9 event triples are natively in
    ALLOWED_EDGE_TRIPLES. The encrypt-delete cycle (READ -> WRITE.locked -> DELETE)
    repeats for each victim file, followed by RANSOM_NOTE.txt write and C2 beacon.

    Multi-anchor placeholder note (see module docstring for full text):
    Checkpoint 16 必须做 T1486 与对应 ransomware-mimicry hard negative pair 即合法磁盘
    加密软件批量加密用户文件 anonymize-then-classify 单独 sanity check 期望 BERT-only F1
    显著降级到 < 0.6 这条 sanity check 不能在整体 hard negative library 层面做必须做单独
    pair。
    """

    def __init__(self) -> None:
        super().__init__("T1486", "Data Encrypted for Impact")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 9-event ransomware encryption + ransom note + C2 beacon chain.

        Sequence: USER_LOGON -> (FILE_READ, FILE_WRITE.locked, FILE_DELETE) x2
        documents -> RANSOM_NOTE.txt FILE_WRITE -> C2 NET_CONNECT.
        The (READ, WRITE.locked, DELETE) triplet repeats for each encrypted file;
        this is the key behavioral signature distinguishing T1486 from T1070.004.
        No schema workaround applied.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        ransom = f"atk_{iid}_{_RANSOM}"
        doc = f"atk_{iid}_{_DOC}"
        doc_locked = f"atk_{iid}_{_DOC_LOCKED}"
        financial = f"atk_{iid}_{_FINANCIAL}"
        financial_locked = f"atk_{iid}_{_FINANCIAL_LOCKED}"
        ransom_note = f"atk_{iid}_{_RANSOM_NOTE}"
        c2_net = f"atk_{iid}_{_C2_IP}:{_C2_PORT}"

        n_events = 9
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
            # 1. USER_LOGON (4624): victim_user session; ransom.exe is executed
            #    by attacker under compromised user account.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                ransom,
                NodeType.process,
            ),
            # 2. ransom.exe reads important_doc.docx (encryption input, file 1).
            _ev(
                timestamps[1],
                ransom,
                NodeType.process,
                EdgeType.FILE_READ,
                doc,
                NodeType.file,
            ),
            # 3. ransom.exe writes important_doc.docx.locked (encrypted ciphertext, file 1).
            _ev(
                timestamps[2],
                ransom,
                NodeType.process,
                EdgeType.FILE_WRITE,
                doc_locked,
                NodeType.file,
            ),
            # 4. ransom.exe deletes important_doc.docx (removes plaintext, file 1).
            #    READ -> WRITE.locked -> DELETE triplet is the ransomware behavioral signature.
            _ev(
                timestamps[3],
                ransom,
                NodeType.process,
                EdgeType.FILE_DELETE,
                doc,
                NodeType.file,
            ),
            # 5. ransom.exe reads financial_data.xlsx (encryption input, file 2).
            _ev(
                timestamps[4],
                ransom,
                NodeType.process,
                EdgeType.FILE_READ,
                financial,
                NodeType.file,
            ),
            # 6. ransom.exe writes financial_data.xlsx.locked (encrypted ciphertext, file 2).
            _ev(
                timestamps[5],
                ransom,
                NodeType.process,
                EdgeType.FILE_WRITE,
                financial_locked,
                NodeType.file,
            ),
            # 7. ransom.exe deletes financial_data.xlsx (removes plaintext, file 2).
            #    READ -> WRITE.locked -> DELETE triplet repeats for second target file.
            _ev(
                timestamps[6],
                ransom,
                NodeType.process,
                EdgeType.FILE_DELETE,
                financial,
                NodeType.file,
            ),
            # 8. ransom.exe writes RANSOM_NOTE.txt (demand + payment instructions).
            _ev(
                timestamps[7],
                ransom,
                NodeType.process,
                EdgeType.FILE_WRITE,
                ransom_note,
                NodeType.file,
            ),
            # 9. ransom.exe connects to C2 (key reporting / beacon to operator).
            _ev(
                timestamps[8],
                ransom,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
        ]
