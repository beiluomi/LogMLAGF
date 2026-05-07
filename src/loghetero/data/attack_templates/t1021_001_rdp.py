"""T1021.001 - Remote Desktop Protocol (Phase 5 / Checkpoint 15 Cycle C).

ATT&CK reference: https://attack.mitre.org/techniques/T1021/001/

Behavioural chain (8 events, shared-seed APT design):

    1. user --> USER_EXPLICIT_LOGON --> process (mstsc.exe)  [seed = victim user]
       Seed event: attacker uses explicit credentials (4648) to initiate RDP.
       USER_EXPLICIT_LOGON (4648) distinguishes T1021.001 from T1078 (which uses
       USER_LOGON / 4624). seed_subject = victim_user.
    2. mstsc.exe --> NET_CONNECT --> target_host_3389 (network node)
       RDP client establishes TCP connection to target host port 3389.
    3. mstsc.exe --> NET_SEND_NETWORK --> target_host_3389 (network node)
       RDP client sends authentication/session data to target.
    4. mstsc.exe --> FILE_READ --> rdp_session_config.rdp (file node)
       RDP client reads session configuration file.
    5. mstsc.exe --> PROCESS_CREATE --> rdp_clipboard.exe (process node)
       RDP client spawns clipboard/drive-mapping helper subprocess.
    6. rdp_clipboard.exe --> FILE_WRITE --> lateral_payload.exe (file node)
       Helper process drops lateral payload via drive-mapping or clipboard channel.
       [Single-host approximation -- see workaround section below.]
    7. rdp_clipboard.exe --> PROCESS_CREATE --> lateral_payload.exe (process node)
       Helper process executes the dropped lateral payload.
       [Single-host approximation -- see workaround section below.]
    8. lateral_payload.exe --> NET_CONNECT --> c2_net (network node)
       Lateral payload establishes C2 connection.

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_EXPLICIT_LOGON from that existing benign user node to a new
    ``atk_<iid>_mstsc.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

Schema workaround #3: single-host approximation (Checkpoint 17 schema workaround
inventory entry #3 -- docs/known_issues.md "Checkpoint 17 schema workaround
inventory tracking"):

    T1021.001 RDP lateral movement semantically spans SOURCE host (attacker
    initiates RDP session from mstsc.exe) and TARGET host (lateral execution
    occurs on the remote host). ATLAS schema is single-host: each event is
    recorded from one host's perspective and multi-host coordination is not
    represented in ALLOWED_EDGE_TRIPLES.

    Workaround per RFC adjudication (inventory entry #3):
    - Model SOURCE host's perspective only (mstsc.exe on attacker/pivot host).
    - Steps 5-6 simplified: ``rdp_clipboard.exe`` drops and executes the
      lateral payload in the source host's process graph. This reflects the
      drive-mapping artifact or clipboard-channel file-transfer observable
      from the SOURCE host's EDR telemetry (EventID 4688 spawning a clipboard
      helper + file write via mapped drive).
    - The "lateral execution on TARGET host" is NOT modeled. The target-side
      process tree (cmd.exe spawned under the RDP session on the remote host)
      is deferred to Phase 9 DARPA TC E3 multi-endpoint dataset integration.

    Phase 9 deferral note: DARPA TC E3 dataset contains host-to-host
    communication relationships and multi-endpoint process coordination. Phase 9
    will revisit T1021.001 to add a cross-host edge type and a target-host
    subgraph. Until then, the single-host approximation is the canonical
    T1021.001 representation in ATLAS-schema LogMLAGF datasets.

    Limitation documented per inventory entry #3 protocol: every implementer
    must reference this section when consuming T1021.001 synthetic data; the
    missing target-host subgraph means the model trains only on RDP
    connection + credential-use signals, not on lateral execution process
    genealogy.

    USER_EXPLICIT_LOGON (4648) vs USER_LOGON (4624):
    Event 1 deliberately uses USER_EXPLICIT_LOGON because RDP lateral movement
    with pass-the-hash or alternate credentials generates EventID 4648 on the
    source host ("A logon was attempted using explicit credentials"). Using
    USER_LOGON would conflate T1021.001 with T1078 credential abuse (which logs
    4624 interactive logon). This is the key semantic distinction preserved by
    the single-host approximation; the target-host 4624 is not modeled (see
    Phase 9 deferral above).

Module-level constants pattern (Phase 5 new convention):

    T1021.001 uses module-level constants (e.g. ``_MSTSC = "mstsc.exe"``)
    rather than class-level constants to keep the inner ``_ev()`` closure
    inside ``generate()`` clean -- accessing module-level names avoids
    ``self.`` prefix inside the closure. Follows the Phase 5 convention
    established in T1055 (Cycle A) and T1068 (Cycle B); differs from Phase 4
    exemplar T1003.001 (class-level constants). Phase 4 refactor deferred to
    Phase 11+ codebase consistency agenda.
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_MSTSC = "mstsc.exe"
_TARGET_HOST = "10.0.0.50"
_TARGET_PORT = 3389
_RDP_CONFIG = "rdp_session_config.rdp"
_RDP_CLIPBOARD = "rdp_clipboard.exe"
_LATERAL_PAYLOAD = "lateral_payload.exe"
_C2_IP = "185.220.101.47"
_C2_PORT = "8443"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h4"


class T1021001RDP(AttackTemplate):
    """RDP lateral movement chain (T1021.001) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1021.001", "Remote Desktop Protocol")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate an 8-event RDP lateral movement chain.

        Single-host approximation (workaround #3): models SOURCE host
        perspective only. Target-host lateral execution deferred to Phase 9.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        mstsc = f"atk_{iid}_{_MSTSC}"
        target_host = f"atk_{iid}_{_TARGET_HOST}:{_TARGET_PORT}"
        rdp_config = f"atk_{iid}_{_RDP_CONFIG}"
        rdp_clipboard = f"atk_{iid}_{_RDP_CLIPBOARD}"
        lateral_payload_file = f"atk_{iid}_{_LATERAL_PAYLOAD}"
        # lateral_payload process node uses same base name; distinct from file node
        # because PROCESS_CREATE object is a process node, FILE_WRITE object is a file node.
        lateral_payload_proc = f"atk_{iid}_{_LATERAL_PAYLOAD}"
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
            # 1. USER_EXPLICIT_LOGON (4648): attacker uses explicit credentials to
            #    initiate RDP from victim user's session; distinguishes T1021.001
            #    from T1078 (which uses USER_LOGON / 4624).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_EXPLICIT_LOGON,
                mstsc,
                NodeType.process,
            ),
            # 2. mstsc.exe connects to target host on port 3389 (network node).
            _ev(
                timestamps[1],
                mstsc,
                NodeType.process,
                EdgeType.NET_CONNECT,
                target_host,
                NodeType.network,
            ),
            # 3. mstsc.exe sends authentication/session data to target.
            _ev(
                timestamps[2],
                mstsc,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                target_host,
                NodeType.network,
            ),
            # 4. mstsc.exe reads RDP session configuration file.
            _ev(
                timestamps[3],
                mstsc,
                NodeType.process,
                EdgeType.FILE_READ,
                rdp_config,
                NodeType.file,
            ),
            # 5. mstsc.exe spawns rdp_clipboard.exe (drive-mapping/clipboard helper).
            _ev(
                timestamps[4],
                mstsc,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                rdp_clipboard,
                NodeType.process,
            ),
            # 6. rdp_clipboard.exe drops lateral payload via drive-mapping or clipboard.
            #    Single-host approximation (workaround #3, inventory entry #3):
            #    Modeled as FILE_WRITE on source host; target-host execution NOT modeled.
            _ev(
                timestamps[5],
                rdp_clipboard,
                NodeType.process,
                EdgeType.FILE_WRITE,
                lateral_payload_file,
                NodeType.file,
            ),
            # 7. rdp_clipboard.exe executes the dropped lateral payload.
            #    Single-host approximation (workaround #3, inventory entry #3):
            #    Lateral execution on TARGET host is NOT modeled (Phase 9 deferral).
            _ev(
                timestamps[6],
                rdp_clipboard,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                lateral_payload_proc,
                NodeType.process,
            ),
            # 8. lateral_payload.exe establishes C2 connection.
            _ev(
                timestamps[7],
                lateral_payload_proc,
                NodeType.process,
                EdgeType.NET_CONNECT,
                c2_net,
                NodeType.network,
            ),
        ]
