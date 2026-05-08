"""T#7.1 benign_driver_install_printer — Hard Negative Template.

Class: #7 软件驱动安装 (per design propose §3.7 + §5.7)
NEG-ID: NEG-7.1
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.7 minimal sketch
    + §5.7 schema readiness (USER_PRIV_GRANT user-subject reuses T1068
    workaround #2; svcctl pipe write reuses T1543.003 sc.exe pattern;
    driver-registry write reuses T1547.001 registry-as-file pattern).

ATT&CK-like NEG-ID:
    NEG-7.1 — first of two software-driver-install hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.7 sub-pattern
    split (NEG-7.1 printer driver / NEG-7.2 AV-engine driver).

Distinct lexical signature + boundary (verbatim from design propose §3.7):
    Confound TTPs: T1543.003 Windows Service Create-or-Modify (primary,
        svcctl pipe write + service registration share) + T1547.006 Kernel
        Modules and Extensions (secondary, .sys driver write share).

    Boundary (§3.7 verbatim):
        合法打印机驱动安装 **驱动来自 vendor signed binary** (path 含 DriverStore
        + .inf_amd64 anchor) + service 不是 auto-start-network-listener.
        T1547.006 攻击驱动安装会把 .sys 直接写 drivers/ 不经 DriverStore +
        service binary 是 attacker payload. BERT-only 看 .sys + drivers +
        DriverStore 词频共享, 区分必须靠 path semantics + binary-signing
        context.

    Anonymization-robust structural anchors:
      (a) FIRST FILE_WRITE target is under DriverStore staging path
          ``C:\\Windows\\System32\\DriverStore\\FileRepository\\
          hp_printer.inf_amd64\\hp_printer.sys`` — Microsoft-documented
          managed driver-package staging area. T1547.006 attack drivers
          SKIP DriverStore staging and write directly to ``drivers\\``.
          The DriverStore prefix on the FIRST .sys write is structural
          anchor (it remains a distinguishing path token even after
          per-token anonymization, as the path-segment count differs
          from a direct ``System32\\drivers\\`` write).
      (b) Process tree depth = 1 (setup.exe → exits, no PROCESS_CREATE
          child shell). T1543.003 Windows Service create flow typically
          spawns the malicious service binary subsequently
          (sc.exe → PROCESS_CREATE malicious_service.exe in the attack
          template event 4); NEG-7.1 has NO PROCESS_CREATE downstream.
      (c) NO NET_CONNECT — printer driver install is local-only. Both
          T1547.006 and T1543.003 attack flows commonly have downstream
          NET_CONNECT to C2 (e.g. T1543.003 attack template event 6).
      (d) Service registration uses BOTH svcctl pipe write AND IMAGEPATH
          registry write — **both required** for Windows driver service
          registration (Windows real-world deployment fidelity: the SCM
          uses the IMAGEPATH registry value under
          ``Services\\<name>\\ImagePath`` to know the driver service
          .sys binary path; pure svcctl pipe write alone is insufficient
          to fully register a service). The distinguishing structural
          anchor vs T1543.003 attack flow is **what IMAGEPATH points
          to**: NEG-7.1 IMAGEPATH points to the just-installed
          DriverStore-staged vendor-signed binary (anchor (a) internal
          consistency); T1543.003 attack template IMAGEPATH points to
          attacker-controlled payload binary, often outside System32
          managed-staging conventions. T1543.003 attack flow also
          spawns the malicious service binary subsequently via
          PROCESS_CREATE event, which NEG-7.1 lacks (anchor (b)).
      (e) Driver registry write (FILE_WRITE to
          ``\\Registry\\Machine\\SYSTEM\\CurrentControlSet\\Services\\
          hp_printer\\ImagePath``) points to the just-installed
          DriverStore-staged binary path (anchor (a)) — internal
          consistency rather than attacker-controlled image path.

ALLOWED_EDGE_TRIPLES workaround reuse:
    Three reuses, ZERO new schema workaround inventory entries (Checkpoint
    17 inventory remains at 4 entries, known_issues.md lines 437-440):

      1. **USER_PRIV_GRANT user-anchor reuses T1068 workaround #2**
         (known_issues.md inventory entry #2). The triple
         (user, USER_PRIV_GRANT, process) with seed_user as subject —
         semantic "privilege attributed to user's session per Windows 4672
         Special Privileges Assigned to New Logon".

      2. **svcctl pipe write reuses T1543.003 sc.exe pattern**. Per design
         §5.4/§5.7 row, the svcctl pipe path ``\\\\.\\pipe\\svcctl`` is
         modeled as a file node target of FILE_WRITE — this is the
         already-landed pattern from T1543.003 attack template (svcctl
         RPC modeled as pipe-as-file). NO new inventory entry triggered.

      3. **Driver registry write reuses T1547.001 registry-as-file
         pattern** (prior workaround per known_issues.md line 411-427
         Checkpoint 14.5 RFC-14.5-1 audit anchor; note this pattern is
         NOT in the known_issues.md line 437-440 4-entry Cycle F
         inventory but is a Checkpoint 14.5 prior-landed pattern reuse).
         The Windows kernel-style registry path ``\\Registry\\Machine\\
         SYSTEM\\CurrentControlSet\\Services\\<svc>\\ImagePath`` is
         modeled as a file node with FILE_WRITE edge — the already-
         landed pattern from T1547.001 attack template. NO new inventory
         entry triggered.

    All triples used by T#7.1 are natively in ALLOWED_EDGE_TRIPLES
    (parsers/base.py lines 106-141):
      - (user, USER_LOGON, process)            line 135
      - (user, USER_PRIV_GRANT, process)       line 138 (T1068 reuse)
      - (process, FILE_WRITE, file)            line 111 (svcctl + registry
                                                          + .sys all reuse)
      - (process, PROCESS_EXIT, process)       line 123 (self-loop)

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON       (user → setup.exe)
          → USER_PRIV_GRANT (user → setup.exe — 4672 priv-grant for install)
          → FILE_WRITE   (setup → DriverStore/hp_printer.inf_amd64/
                          hp_printer.sys — vendor signed binary staging)
          → FILE_WRITE   (setup → System32/drivers/hp_printer.sys — driver
                          file copy, points to staged DriverStore binary)
          → FILE_WRITE   (setup → \\\\.\\pipe\\svcctl — register service
                          via SCM RPC, svcctl pipe-as-file workaround reuse)
          → FILE_WRITE   (setup → \\Registry\\Machine\\SYSTEM\\
                          CurrentControlSet\\Services\\hp_printer\\
                          ImagePath — driver registry IMAGEPATH write,
                          registry-as-file workaround reuse)
          → PROCESS_EXIT (setup.exe exits — depth-1 process tree anchor)
    Length range: events_min=7, events_max=7 (deterministic vendor
        installer chain — single .sys staged + copied + service registered
        + ImagePath set + clean exit).
    Distinguishing structural pattern: the FIRST .sys FILE_WRITE goes to
        DriverStore/<inf_pkg>/<file>.sys (managed staging) BEFORE the
        copy to drivers/<file>.sys; setup.exe exits with NO PROCESS_CREATE
        downstream and NO NET_CONNECT. Structurally disjoint from
        T1543.003 attack (which spawns malicious_service.exe + NET_CONNECT
        c2_net) and T1547.006 attack (which writes .sys directly to
        drivers/ skipping DriverStore staging).
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_SETUP = "setup.exe"
_DRIVER_STORE_SYS = (
    r"C:\Windows\System32\DriverStore\FileRepository"
    r"\hp_printer.inf_amd64\hp_printer.sys"
)
_DRIVERS_SYS = r"C:\Windows\System32\drivers\hp_printer.sys"
_SVCCTL_PIPE = r"\\.\pipe\svcctl"
_DRIVER_REG_PATH = (
    r"\Registry\Machine\SYSTEM\CurrentControlSet\Services"
    r"\hp_printer\ImagePath"
)
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_7_1"
_NEG_ID = "NEG-7.1"


class Neg71DriverInstallPrinter(HardNegativeTemplate):
    """T#7.1 benign HP printer driver vendor-signed installer workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_driver_install_printer")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event vendor-signed printer driver install chain.

        Anonymization-robust anchors:
          - First .sys FILE_WRITE goes to DriverStore staging
            (DriverStore/<inf_pkg>/<file>.sys before drivers/<file>.sys).
          - Process tree depth = 1 (setup.exe → exit; no PROCESS_CREATE
            downstream — anchor vs T1543.003 service spawn).
          - No NET_CONNECT (vs T1543.003/T1547.006 C2 downstream).
          - svcctl pipe write reuses T1543.003 sc.exe pattern.
          - Driver registry IMAGEPATH write reuses T1547.001 registry-
            as-file pattern; ImagePath value points back at the just-
            staged DriverStore binary (internal consistency anchor).

        USER_PRIV_GRANT user-anchor reuses T1068 workaround #2.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        setup = f"neg_{iid}_{_SETUP}"
        driver_store_sys = f"neg_{iid}_{_DRIVER_STORE_SYS}"
        drivers_sys = f"neg_{iid}_{_DRIVERS_SYS}"
        svcctl_pipe = f"neg_{iid}_{_SVCCTL_PIPE}"
        driver_reg = f"neg_{iid}_{_DRIVER_REG_PATH}"

        n_events = 7
        span = t_end_ns - t_start_ns
        base_step = span // n_events
        timestamps = [
            t_start_ns + k * base_step + rng.randint(0, max(1, base_step // 4))
            for k in range(n_events)
        ]
        timestamps.sort()

        attrs_base = {
            "neg_id": self.neg_id,
            "instance_id": iid,
            "label": 0,
        }

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
                attributes=dict(attrs_base),
            )

        return [
            # 1. Admin user logs on, launches vendor setup.exe (interactive
            #    install).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                setup,
                NodeType.process,
            ),
            # 2. USER_PRIV_GRANT (4672) — driver install requires elevated
            #    SeLoadDriverPrivilege. Schema workaround #2 reuse:
            #    subject is seed_user per ALLOWED_EDGE_TRIPLES.
            _ev(
                timestamps[1],
                seed_subject,
                NodeType.user,
                EdgeType.USER_PRIV_GRANT,
                setup,
                NodeType.process,
            ),
            # 3. setup.exe writes the vendor-signed .sys to DriverStore
            #    staging area (Microsoft-managed driver-package repo).
            #    Path prefix DriverStore/<inf_pkg>/ is structural anchor
            #    vs T1547.006 attack drivers that skip DriverStore.
            _ev(
                timestamps[2],
                setup,
                NodeType.process,
                EdgeType.FILE_WRITE,
                driver_store_sys,
                NodeType.file,
            ),
            # 4. setup.exe copies the .sys from DriverStore to System32/
            #    drivers/. The DriverStore-staged write FIRST is the
            #    structural ordering anchor.
            _ev(
                timestamps[3],
                setup,
                NodeType.process,
                EdgeType.FILE_WRITE,
                drivers_sys,
                NodeType.file,
            ),
            # 5. setup.exe writes svcctl pipe to register the printer
            #    driver service via SCM RPC. svcctl-pipe-as-file pattern
            #    reuses T1543.003 sc.exe svcctl write (no new inventory
            #    entry).
            _ev(
                timestamps[4],
                setup,
                NodeType.process,
                EdgeType.FILE_WRITE,
                svcctl_pipe,
                NodeType.file,
            ),
            # 6. setup.exe writes the driver registry IMAGEPATH key
            #    pointing to the just-staged DriverStore binary.
            #    Registry-as-file pattern reuses T1547.001 (no new
            #    inventory entry). Internal-consistency anchor: ImagePath
            #    value references staged binary, not attacker-controlled
            #    path.
            _ev(
                timestamps[5],
                setup,
                NodeType.process,
                EdgeType.FILE_WRITE,
                driver_reg,
                NodeType.file,
            ),
            # 7. setup.exe exits cleanly. NO PROCESS_CREATE downstream
            #    (depth-1 anchor vs T1543.003 service spawn). NO
            #    NET_CONNECT (vs both confound TTPs).
            _ev(
                timestamps[6],
                setup,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                setup,
                NodeType.process,
            ),
        ]
