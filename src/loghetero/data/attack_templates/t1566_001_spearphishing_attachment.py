"""T1566.001 - Spearphishing Attachment (Phase 5 / Checkpoint 15 Cycle D).

ATT&CK reference: https://attack.mitre.org/techniques/T1566/001/

Behavioural chain (7 events, shared-seed APT design):

    1. user --> USER_LOGON --> outlook.exe  [seed = victim user]
       Seed event: victim user opens Outlook; attacker has already sent the
       malicious email with a weaponized attachment (.docm macro document).
    2. outlook.exe --> FILE_WRITE --> malicious_attachment.docm
       Outlook writes the malicious attachment to the user's temp/download path.
    3. outlook.exe --> PROCESS_CREATE --> winword.exe
       Outlook spawns Word to open the attachment (user double-clicks).
    4. winword.exe --> PROCESS_CREATE --> cmd.exe
       Macro inside the .docm executes a shell command via WScript.Shell or
       cmd.exe invocation (ATLAS EventID 4688, parent=winword.exe).
    5. cmd.exe --> PROCESS_CREATE --> dropper.exe
       The macro shell command downloads and executes a second-stage dropper.
    6. dropper.exe --> FILE_WRITE --> stage2.exe
       Dropper writes the second-stage payload to disk.
    7. dropper.exe --> NET_CONNECT --> c2_net
       Dropper establishes C2 connection to exfil/receive further instructions.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_outlook.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

No schema workaround needed:
    All 7 triples are in ALLOWED_EDGE_TRIPLES with no modification:
    - (user, USER_LOGON, process) x1
    - (process, FILE_WRITE, file) x2  (events 2 and 6)
    - (process, PROCESS_CREATE, process) x3  (events 3, 4, 5)
    - (process, NET_CONNECT, network) x1  (event 7)

Module-level constants pattern (Phase 5 new convention):
    T1566.001 uses module-level constants (e.g. ``_OUTLOOK = "outlook.exe"``)
    rather than class-level constants to keep the inner ``_ev()`` closure
    inside ``generate()`` clean -- accessing module-level names avoids
    ``self.`` prefix inside the closure. Follows the Phase 5 convention
    established in T1055 (Cycle A), T1068 (Cycle B), and T1021.001 (Cycle C).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_OUTLOOK = "outlook.exe"
_ATTACHMENT = "malicious_attachment.docm"
_WINWORD = "winword.exe"
_CMD = "cmd.exe"
_DROPPER = "dropper.exe"
_STAGE2 = "stage2.exe"
_C2_IP = "185.220.101.48"
_C2_PORT = "443"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h5"


class T1566001SpearphishingAttachment(AttackTemplate):
    """Spearphishing attachment delivery chain (T1566.001) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1566.001", "Spearphishing Attachment")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event spearphishing attachment chain.

        No schema workaround needed: all triples in ALLOWED_EDGE_TRIPLES.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        outlook = f"atk_{iid}_{_OUTLOOK}"
        attachment = f"atk_{iid}_{_ATTACHMENT}"
        winword = f"atk_{iid}_{_WINWORD}"
        cmd = f"atk_{iid}_{_CMD}"
        dropper = f"atk_{iid}_{_DROPPER}"
        stage2 = f"atk_{iid}_{_STAGE2}"
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
            # 1. USER_LOGON (4624): victim user opens Outlook; malicious email
            #    with weaponized .docm attachment is already in the inbox.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                outlook,
                NodeType.process,
            ),
            # 2. outlook.exe writes malicious attachment to temp/download path.
            _ev(
                timestamps[1],
                outlook,
                NodeType.process,
                EdgeType.FILE_WRITE,
                attachment,
                NodeType.file,
            ),
            # 3. outlook.exe spawns winword.exe to open the .docm attachment.
            _ev(
                timestamps[2],
                outlook,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                winword,
                NodeType.process,
            ),
            # 4. winword.exe executes shell command via macro (WScript.Shell or
            #    CreateObject("Shell.Application")); spawns cmd.exe (EventID 4688).
            _ev(
                timestamps[3],
                winword,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                cmd,
                NodeType.process,
            ),
            # 5. cmd.exe downloads and executes the second-stage dropper.
            _ev(
                timestamps[4],
                cmd,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                dropper,
                NodeType.process,
            ),
            # 6. dropper.exe writes the second-stage payload (stage2.exe) to disk.
            _ev(
                timestamps[5],
                dropper,
                NodeType.process,
                EdgeType.FILE_WRITE,
                stage2,
                NodeType.file,
            ),
            # 7. dropper.exe establishes C2 connection for further instructions.
            _ev(
                timestamps[6],
                dropper,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
        ]
