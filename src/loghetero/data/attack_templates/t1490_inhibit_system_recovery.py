"""T1490 - Inhibit System Recovery (Phase 5 / Checkpoint 15 Cycle F).

ATT&CK reference: https://attack.mitre.org/techniques/T1490/

Behavioural chain (8 events, shared-seed APT design):

    1. (user, USER_PRIV_GRANT, cmd.exe)  [seed event with USER_PRIV_GRANT --
       privileged session needed for vssadmin/bcdedit]
    2. (cmd.exe, PROCESS_CREATE, vssadmin.exe)
    3. (vssadmin.exe, FILE_READ, shadow_copy_volume)  [system-object-as-file reuse]
    4. (vssadmin.exe, FILE_DELETE, shadow_copy_volume)
    5. (cmd.exe, PROCESS_CREATE, bcdedit.exe)
    6. (bcdedit.exe, FILE_WRITE, \\Registry\\Machine\\BCD00000000)  [registry-as-file reuse]
    7. (bcdedit.exe, FILE_READ, \\Registry\\Machine\\BCD00000000)
    8. (bcdedit.exe, FILE_WRITE, recovery_disabled_marker)

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_PRIV_GRANT from that existing benign user node to a new
    ``atk_<iid>_cmd.exe`` process node. All remaining nodes are ``atk_``-prefixed.

    USER_PRIV_GRANT seed (not USER_LOGON):
    vssadmin.exe and bcdedit.exe both require elevated privileges (SeBackupPrivilege /
    SeTakeOwnershipPrivilege for shadow copy deletion, and Admin rights for bcdedit).
    ATLAS EventID 4672 (Special privileges assigned to new logon) fires immediately
    after a privileged logon and is the correct seed for recovery-disablement scenarios.
    The triple (user, USER_PRIV_GRANT, process) IS in ALLOWED_EDGE_TRIPLES (line 138
    of parsers/base.py). This is the same USER_PRIV_GRANT seed pattern used by
    T1543.003 (Cycle E) -- no new schema issue.

Schema workaround -- shadow_copy_volume (REUSED "system object as file node" pattern):
    The VSS shadow copy volume (``shadow_copy_volume``) is a kernel-level VSS object,
    not a traditional file. Modeling it as a ``file`` node with FILE_READ / FILE_DELETE
    edges is the same "system object as file node" generalization used throughout
    Phase 4 and Phase 5:

    - T1547.001 (Phase 4): Windows registry key path as file node (registry-as-file).
    - T1543.003, T1053.005 (Cycle E): additional registry paths as file nodes.
    - T1490 BCD store (event 6/7): \\Registry\\Machine\\BCD00000000 as file node
      (registry-as-file reuse, same as T1547.001).

    Shadow copy volumes are kernel/system-namespace objects (like the BCD registry
    store and the Windows registry hive). All three share the same core property:
    ALLOWED_EDGE_TRIPLES has only (process, FILE_*, file) for object-manipulation
    edges, so system-namespace objects that are not traditional filesystem files
    must be modeled as file nodes when no dedicated edge type exists.

    Decision: shadow_copy_volume uses the SAME "system object as file node" reuse
    pattern (option (a), per RFC-first discipline + Cycle B-F default). NO new
    inventory entry #5. The pattern is documented here and cross-referenced to
    T1547.001 (original registry-as-file workaround) as established precedent.

    Checkpoint 17 note: shadow_copy_volume modeling is in the same category as
    T1021.001 (#3) and T1190 (#4) -- NOT scheduled for Checkpoint 17 upgrade.
    The VSS shadow copy type is a plausible Phase 9 DARPA TC E3 extension if
    that dataset includes VSS events; otherwise treat as permanent ATLAS workaround.

    Cross-reference: T1547.001 inventory entry (docs/known_issues.md "Checkpoint 17
    schema workaround inventory tracking", originally entry #1 for T1055, registry-
    as-file pattern first documented for T1547.001 Phase 4).

Schema workaround -- BCD registry (REUSED from T1547.001, same as T1543.003 / T1053.005):
    The BCD store ``\\Registry\\Machine\\BCD00000000`` is the same registry-as-file
    pattern. No new inventory entry. Cross-reference T1547.001 module docstring and
    docs/known_issues.md schema workaround inventory.

Triple summary (all in ALLOWED_EDGE_TRIPLES; system-object-as-file reuse pattern):
    - (user, USER_PRIV_GRANT, process) x1  (event 1; privileged seed)
    - (process, PROCESS_CREATE, process) x2  (events 2 and 5)
    - (process, FILE_READ, file) x2  (events 3 and 7; event 3 shadow-as-file reuse)
    - (process, FILE_DELETE, file) x1  (event 4; shadow-as-file reuse)
    - (process, FILE_WRITE, file) x2  (events 6 and 8; event 6 registry-as-file reuse)

Module-level constants pattern (Phase 5 convention):
    T1490 uses module-level constants following the Phase 5 convention
    established in T1055 (Cycle A), T1068 (Cycle B), T1021.001 (Cycle C),
    T1057/T1083 (Cycle D), and T1027/T1070.004/T1053.005/T1543.003 (Cycle E).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_CMD = "cmd.exe"
_VSSADMIN = "vssadmin.exe"
# VSS shadow copy volume modeled as file node (system-object-as-file reuse pattern;
# see module docstring for full rationale and cross-reference to T1547.001).
_SHADOW_COPY = "shadow_copy_volume"
_BCDEDIT = "bcdedit.exe"
# BCD registry store modeled as file node (registry-as-file workaround reused from
# T1547.001; same pattern as T1543.003 and T1053.005).
_BCD_STORE = r"\Registry\Machine\BCD00000000"
_RECOVERY_MARKER = "recovery_disabled_marker"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h16"


class T1490InhibitSystemRecovery(AttackTemplate):
    """Inhibit system recovery via vssadmin + bcdedit chain (T1490) synthetic event generator.

    Event 1 uses USER_PRIV_GRANT seed (4672) -- privileged session required for
    shadow copy deletion and BCD modification. Events 3-4 use the system-object-as-
    file reuse pattern for VSS shadow copy volumes. Events 6-7 use the registry-as-
    file workaround (REUSED from T1547.001, no new inventory entry) for the BCD store.
    No new schema workaround inventory entry created; both reuse established patterns.
    """

    def __init__(self) -> None:
        super().__init__("T1490", "Inhibit System Recovery")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate an 8-event shadow-copy deletion + BCD recovery disable chain.

        Event 1 uses USER_PRIV_GRANT (not USER_LOGON) as seed because vssadmin/
        bcdedit require elevated privileges (ATLAS EventID 4672). Events 3-4 use
        the "system object as file node" pattern for VSS shadow_copy_volume (reuse
        of the established file-node-for-system-objects pattern; no new inventory
        entry #5). Events 6-7 use registry-as-file reuse from T1547.001 for BCD
        store (same as T1543.003 and T1053.005; no new inventory entry).
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        cmd = f"atk_{iid}_{_CMD}"
        vssadmin = f"atk_{iid}_{_VSSADMIN}"
        # VSS shadow copy volume modeled as file node (system-object-as-file reuse).
        shadow_copy = f"atk_{iid}_{_SHADOW_COPY}"
        bcdedit = f"atk_{iid}_{_BCDEDIT}"
        # BCD registry store modeled as file node (registry-as-file reuse, T1547.001).
        bcd_store = f"atk_{iid}_{_BCD_STORE}"
        recovery_marker = f"atk_{iid}_{_RECOVERY_MARKER}"

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
            # 1. USER_PRIV_GRANT (4672): privileged session seed. vssadmin and bcdedit
            #    require elevated privileges (SeBackupPrivilege / Admin). ATLAS EventID
            #    4672 fires on privileged logon. Same seed pattern as T1543.003 (Cycle E).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_PRIV_GRANT,
                cmd,
                NodeType.process,
            ),
            # 2. cmd.exe spawns vssadmin.exe (shadow copy enumeration / deletion tool).
            _ev(
                timestamps[1],
                cmd,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                vssadmin,
                NodeType.process,
            ),
            # 3. vssadmin.exe reads shadow_copy_volume (enumerate existing snapshots).
            #    VSS shadow copy modeled as file node (system-object-as-file reuse;
            #    same "system-namespace object as file node" pattern as registry-as-file).
            _ev(
                timestamps[2],
                vssadmin,
                NodeType.process,
                EdgeType.FILE_READ,
                shadow_copy,
                NodeType.file,
            ),
            # 4. vssadmin.exe deletes shadow_copy_volume (vssadmin delete shadows /all /quiet).
            #    FILE_DELETE on the shadow copy file node completes the snapshot erasure.
            _ev(
                timestamps[3],
                vssadmin,
                NodeType.process,
                EdgeType.FILE_DELETE,
                shadow_copy,
                NodeType.file,
            ),
            # 5. cmd.exe spawns bcdedit.exe (Boot Configuration Data modification tool).
            _ev(
                timestamps[4],
                cmd,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                bcdedit,
                NodeType.process,
            ),
            # 6. bcdedit.exe writes BCD store (disable recovery mode / safeboot).
            #    \\Registry\\Machine\\BCD00000000 modeled as file node (registry-as-file
            #    reuse from T1547.001; same as T1543.003 event 3 and T1053.005 event 3).
            _ev(
                timestamps[5],
                bcdedit,
                NodeType.process,
                EdgeType.FILE_WRITE,
                bcd_store,
                NodeType.file,
            ),
            # 7. bcdedit.exe reads BCD store back (verify recovery option disabled).
            _ev(
                timestamps[6],
                bcdedit,
                NodeType.process,
                EdgeType.FILE_READ,
                bcd_store,
                NodeType.file,
            ),
            # 8. bcdedit.exe writes recovery_disabled_marker (audit file / completion flag).
            _ev(
                timestamps[7],
                bcdedit,
                NodeType.process,
                EdgeType.FILE_WRITE,
                recovery_marker,
                NodeType.file,
            ),
        ]
