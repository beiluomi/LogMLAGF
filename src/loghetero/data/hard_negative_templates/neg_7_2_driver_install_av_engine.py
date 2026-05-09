"""T#7.2 benign_driver_install_av_engine — Hard Negative Template.

Class: #7 软件驱动安装 (per design propose §3.7 + §5.7)
NEG-ID: NEG-7.2
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.7 minimal sketch
    + §5.7 schema readiness (USER_PRIV_GRANT user-subject reuses T1068
    workaround #2; svcctl pipe write reuses T1543.003 sc.exe pattern;
    no T1547.001 registry-as-file reuse — NEG-7.2 verbatim §3.7 sketch
    无 IMAGEPATH registry write per Result B push verify per
    service-type-specific conditional anchor finding cf. NEG-7.1 line
    286-288 includes IMAGEPATH FILE_WRITE for printer driver SCM
    registration whereas NEG-7.2 av engine driver uses Filter Manager
    API minifilter registration not requiring IMAGEPATH).

ATT&CK-like NEG-ID:
    NEG-7.2 — second of two software-driver-install hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.7 sub-pattern
    split (NEG-7.1 printer driver / NEG-7.2 AV-engine driver).

Distinct lexical signature + boundary (verbatim from design propose §3.7):
    Confound TTPs: T1543.003 Windows Service Create-or-Modify (primary,
        svcctl pipe write + service registration share) + T1547.006 Kernel
        Modules and Extensions (secondary, .sys driver write share)
        + T1014 Rootkit (tertiary — kernel-mode AV engine .sys driver
        shares lexical surface with rootkit driver install).

    Boundary (§3.7 verbatim):
        合法 AV driver 安装 **包含 vendor update domain network 而非 attacker
        C2** (vendor_update_network 是 well-known signature endpoint) 加
        service 是 known-AV-vendor name. BERT-only 看 .sys + drivers + service
        词频共享, 区分必须靠 network-destination domain reputation +
        service-name semantics.

    Anonymization-robust structural anchors:
      (a) Distinguishing anchor: NET_CONNECT to vendor_update_network
          (well-known AV vendor signature endpoint, RFC1918-style or
          vendor-controlled DNS) — followed by NET_RECV_NETWORK signature
          download. T1014 Rootkit and T1543.003 attack flows connect to
          C2 networks, NOT to vendor signature endpoints. The
          vendor_update_network destination is the structural anchor (the
          fact that it appears at all + the fact that the payload
          direction is RECV not SEND_LARGE_VOLUME — signature update is
          server-pushes-to-client, not exfil).
      (b) AV engine .sys is staged under
          ``C:\\ProgramData\\Vendor\\Engine\\engine.sys`` (vendor-managed
          ProgramData install path) BEFORE the system-wide .sys copy to
          ``C:\\Windows\\System32\\drivers\\vendor_av.sys``. ProgramData/
          Vendor/Engine/ prefix is anchor — T1547.006 attack drivers skip
          ProgramData staging and write directly to drivers/.
      (c) Process tree depth = 1 (av_installer.exe → exits, no
          PROCESS_CREATE child shell). T1014 Rootkit attack flows
          typically spawn or hide a backdoor process subsequently;
          NEG-7.2 has NO PROCESS_CREATE downstream.
      (d) Service registration via svcctl pipe write only (no separate
          IMAGEPATH overwrite to attacker payload — internal consistency
          anchor: implicit ImagePath set via vendor's SCM call).
      (e) Vendor-signature update direction is RECV
          (NET_RECV_NETWORK from vendor_update_network) — this is server-
          pushes-to-client signature delivery. T1014 Rootkit and
          T1543.003 attack flows typically NET_SEND_NETWORK to C2
          (exfil / beacon direction). The RECV-only direction is
          distinguishing anchor.

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

      3. **Item 3 (T1547.001 registry-as-file reuse) does NOT apply to
         NEG-7.2**. NEG-7.2 verbatim §3.7 7-event sequence 无 IMAGEPATH
         registry write event. Driver staging-path FILE_WRITE + drivers
         directory FILE_WRITE 都是 standard (process, FILE_WRITE, file)
         triples natively in ALLOWED_EDGE_TRIPLES 不构成 workaround
         pattern. Vendor AV typically uses Filter Manager API minifilter
         driver registration mechanism 不需 IMAGEPATH for SCM (cf.
         NEG-7.1 printer driver T#7.1 service type which DOES require
         IMAGEPATH). 此 Item 3 omission 是 service-type-specific
         conditional anchor finding (design propose §3.7 line 157
         Cycle G retro-write) 应用 to Result B push verify outcome.

    All triples used by T#7.2 are natively in ALLOWED_EDGE_TRIPLES
    (parsers/base.py lines 106-141):
      - (user, USER_LOGON, process)            line 135
      - (user, USER_PRIV_GRANT, process)       line 138 (T1068 reuse)
      - (process, FILE_WRITE, file)            line 111 (svcctl + .sys)
      - (process, NET_CONNECT, network)        line 125
      - (process, NET_RECV_NETWORK, network)   line 130

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON       (user → av_installer.exe)
          → USER_PRIV_GRANT (user → av_installer.exe — 4672 priv-grant)
          → FILE_WRITE   (av_installer → ProgramData/Vendor/Engine/
                          engine.sys — vendor-managed staging path)
          → FILE_WRITE   (av_installer → System32/drivers/vendor_av.sys
                          — system-wide driver copy)
          → FILE_WRITE   (av_installer → \\\\.\\pipe\\svcctl — register
                          AV service via SCM RPC, svcctl pipe-as-file
                          workaround reuse)
          → NET_CONNECT  (av_installer → vendor_update_network — vendor
                          signature endpoint, distinguishing anchor (a))
          → NET_RECV_NETWORK (av_installer ← vendor_update_network —
                              signature update server-pushes-to-client,
                              RECV-only direction anchor (e))
    Length range: events_min=7, events_max=7 (deterministic vendor AV
        installer chain — single .sys staged + copied + service registered
        + signature update fetched).
    Distinguishing structural pattern: the only NET_CONNECT in the
        sequence is to vendor_update_network (known vendor signature
        endpoint, NOT C2) and the network direction is RECV-only
        (NET_RECV_NETWORK without paired NET_SEND_NETWORK exfil burst).
        Process tree depth = 1 with NO PROCESS_CREATE downstream.
        Structurally disjoint from T1014 Rootkit (which typically spawns
        or hides a backdoor process subsequently), T1543.003 attack
        (which spawns malicious_service.exe + NET_SEND_NETWORK c2_net
        exfil), and T1547.006 attack (which writes .sys directly to
        drivers/ skipping ProgramData/Vendor staging).
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_AV_INSTALLER = "av_installer.exe"
_VENDOR_STAGING_SYS = r"C:\ProgramData\Vendor\Engine\engine.sys"
_DRIVERS_SYS = r"C:\Windows\System32\drivers\vendor_av.sys"
_SVCCTL_PIPE = r"\\.\pipe\svcctl"
_VENDOR_UPDATE_NET = "vendor_update_network:443"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_7_2"
_NEG_ID = "NEG-7.2"


class Neg72DriverInstallAvEngine(HardNegativeTemplate):
    """T#7.2 benign AV-engine driver vendor installer + signature update."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_driver_install_av_engine")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event vendor AV-engine driver install + sigupdate chain.

        Anonymization-robust anchors:
          - .sys staged under ProgramData/Vendor/Engine/ before
            drivers/<file>.sys (vendor-managed ProgramData prefix).
          - Process tree depth = 1 (av_installer → exit; no PROCESS_CREATE
            downstream — anchor vs T1014 Rootkit / T1543.003 service spawn).
          - Only NET_CONNECT in sequence is to vendor_update_network
            (NOT C2) — distinguishing anchor (a).
          - Network direction is RECV-only (NET_RECV_NETWORK without paired
            NET_SEND_NETWORK exfil) — distinguishing anchor (e).
          - svcctl pipe write reuses T1543.003 sc.exe pattern.

        USER_PRIV_GRANT user-anchor reuses T1068 workaround #2.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        av_installer = f"neg_{iid}_{_AV_INSTALLER}"
        vendor_staging = f"neg_{iid}_{_VENDOR_STAGING_SYS}"
        drivers_sys = f"neg_{iid}_{_DRIVERS_SYS}"
        svcctl_pipe = f"neg_{iid}_{_SVCCTL_PIPE}"
        vendor_net = f"neg_{iid}_{_VENDOR_UPDATE_NET}"

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
            # 1. Admin user logs on, launches vendor av_installer.exe.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                av_installer,
                NodeType.process,
            ),
            # 2. USER_PRIV_GRANT (4672) — AV-engine driver install requires
            #    SeLoadDriverPrivilege. Schema workaround #2 reuse: subject
            #    is seed_user per ALLOWED_EDGE_TRIPLES.
            _ev(
                timestamps[1],
                seed_subject,
                NodeType.user,
                EdgeType.USER_PRIV_GRANT,
                av_installer,
                NodeType.process,
            ),
            # 3. av_installer.exe writes the AV engine .sys to vendor's
            #    ProgramData staging area (vendor-managed install root).
            #    ProgramData/Vendor/Engine/ prefix is structural anchor
            #    vs T1547.006 attack drivers that skip ProgramData
            #    staging.
            _ev(
                timestamps[2],
                av_installer,
                NodeType.process,
                EdgeType.FILE_WRITE,
                vendor_staging,
                NodeType.file,
            ),
            # 4. av_installer.exe copies the .sys from staging to
            #    System32/drivers/ for kernel load.
            _ev(
                timestamps[3],
                av_installer,
                NodeType.process,
                EdgeType.FILE_WRITE,
                drivers_sys,
                NodeType.file,
            ),
            # 5. av_installer.exe writes svcctl pipe to register the AV
            #    service via SCM RPC. svcctl-pipe-as-file pattern reuses
            #    T1543.003 sc.exe svcctl write (no new inventory entry).
            _ev(
                timestamps[4],
                av_installer,
                NodeType.process,
                EdgeType.FILE_WRITE,
                svcctl_pipe,
                NodeType.file,
            ),
            # 6. av_installer.exe NET_CONNECT to vendor signature update
            #    endpoint. Distinguishing anchor (a) — vendor_update_network
            #    is well-known signature endpoint, NOT C2.
            _ev(
                timestamps[5],
                av_installer,
                NodeType.process,
                EdgeType.NET_CONNECT,
                vendor_net,
                NodeType.network,
            ),
            # 7. av_installer.exe receives signature update payload from
            #    vendor (server-pushes-to-client RECV-only direction —
            #    distinguishing anchor (e) vs T1014 Rootkit /
            #    T1543.003 attack flows that NET_SEND_NETWORK to C2 for
            #    exfil/beacon).
            _ev(
                timestamps[6],
                av_installer,
                NodeType.process,
                EdgeType.NET_RECV_NETWORK,
                vendor_net,
                NodeType.network,
            ),
        ]
