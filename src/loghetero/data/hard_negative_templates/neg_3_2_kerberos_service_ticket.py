"""T#3.2 benign_auth_kerberos_service_ticket — Hard Negative Template.

Class: #3 合法 Auth (per design propose §3.3 + §5.3)
NEG-ID: NEG-3.2
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.3 minimal sketch
    + §5.3 schema readiness (USER_PRIV_GRANT user-subject reuses T1068
    workaround #2) + §4.1.D (#3 vs #8 RDP boundary) + §4.1.G (#3 vs #9
    weak-pwd-test boundary)

ATT&CK-like NEG-ID:
    NEG-3.2 — second of two legitimate-Auth hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.3 sub-pattern
    split (NEG-3.1 single interactive logon / NEG-3.2 Kerberos service
    ticket).

Distinct lexical signature + boundary (verbatim from design propose §3.3
plus §4.1.D + §4.1.G):

    Confound TTPs: T1558.003 Kerberoasting (primary, krb5cc / TGS lexical
        share) + T1078 valid-accounts (secondary, USER_LOGON +
        USER_PRIV_GRANT seed share).

    Boundary (§3.3 verbatim):
        合法 Kerberos service ticket 请求 **是单次** + ticket service
        principal 是 normal user-facing service (如 cifs/HTTP), 加 **不**包含
        ticket cache export 到外部 process (无 (powershell.exe, FILE_READ,
        krb5cc_*)). BERT-only 看 lsass + kerberos + krb5cc 词频与 T1558 共享,
        区分必须靠 service-principal 集合 + downstream ticket 用法.

    Boundary §4.1.D (#3 vs #8 RDP):
        单次 logon 加 single TGS-REQ 属 #3 (无 mstsc.exe / mstscax.dll
        involvement, 无 NET_CONNECT 到 RDP target_host_network). 本模板
        connects only to kdc_network — Kerberos KDC endpoint is structurally
        disjoint from any RDP target_host_network destination.

    Boundary §4.1.G (#3 vs #9 weak-pwd-test):
        本模板 emits exactly 1 USER_LOGON + 1 USER_PRIV_GRANT (single-success
        sequence) — does NOT contain the ≥ 3 USER_LOGON_FAIL burst that
        characterizes T#9.3 hydra weak-pwd-test (per §4.1.G threshold).

    Anonymization-robust structural anchors:
      (a) Single TGS-REQ / TGS-REP exchange (single NET_SEND_NETWORK +
          single NET_RECV_NETWORK to kdc_network). T1558.003 Kerberoasting
          characteristically requests TGS for MULTIPLE service principals
          (SPN spray) — typically 5+ TGS-REQ to enumerate kerberoastable
          accounts. Single REQ/REP is structural anchor.
      (b) Service-principal target is normal user-facing service (modeled
          here via destination ticket cache file krb5cc_<uid> per Linux
          MIT Kerberos / Heimdal convention). T1558.003 Kerberoasting
          extracts the ticket BLOB to attacker-controlled disk for offline
          cracking — typically writes a .kirbi / .ccache extracted dump.
      (c) NO downstream FILE_READ from a non-lsass process to krb5cc_*
          (no powershell.exe / mimikatz.exe / Invoke-Kerberoast reading
          the ticket cache). Sequence ends with FILE_WRITE krb5cc_<uid>
          owned by lsass.exe and no further events touch the ticket cache.
      (d) NO NET_CONNECT to attacker-controlled C2 — the only NET_CONNECT
          is to kdc_network (KDC endpoint). T1558.003 attack sequences
          typically follow with offline-crack workflow (no further network
          events) but anomalies in real attacks do correlate with C2 —
          either way our single kdc_network anchor is disjoint.
      (e) NO mstsc.exe (vs Class #8 RDP boundary).

ALLOWED_EDGE_TRIPLES workaround reuse:
    USER_PRIV_GRANT user-anchor reuses T1068 workaround #2
    (known_issues.md inventory entry #2). Per design §5.3, the triple
    (user, USER_PRIV_GRANT, process) with seed_user as subject — semantic
    "privilege attributed to user's session per Windows 4672 Special
    Privileges Assigned to New Logon" — is the established reuse pattern.
    NO new schema workaround inventory entry triggered (Checkpoint 17
    inventory remains at 4 entries, known_issues.md lines 437-440).

    All triples used by T#3.2 are natively in ALLOWED_EDGE_TRIPLES
    (parsers/base.py lines 106-141):
      - (user, USER_LOGON, process)            line 135
      - (user, USER_PRIV_GRANT, process)       line 138 (reuse pattern)
      - (process, NET_CONNECT, network)        line 125
      - (process, NET_SEND_NETWORK, network)   line 128
      - (process, NET_RECV_NETWORK, network)   line 130
      - (process, FILE_WRITE, file)            line 111

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON         (user → lsass.exe)
          → USER_PRIV_GRANT  (user → lsass.exe — 4672 priv-grant on logon)
          → NET_CONNECT      (lsass → kdc_network — TCP/88 to KDC)
          → NET_SEND_NETWORK (lsass → kdc_network — TGS-REQ AS-REQ payload)
          → NET_RECV_NETWORK (lsass → kdc_network — TGS-REP ticket payload)
          → FILE_WRITE       (lsass → /tmp/krb5cc_<uid> — local cache write)
    Length range: events_min=6, events_max=6 (deterministic single-TGS
        Kerberos exchange — single principal request produces fixed 6-event
        chain).
    Distinguishing structural pattern: single TGS-REQ/TGS-REP pair anchored
        on lsass.exe as Kerberos client (Windows-style; Linux uses sssd or
        krb5kdc client process — modeled here via lsass.exe convention) with
        FILE_WRITE only to local krb5cc_<uid> ticket cache. NO subsequent
        FILE_READ from a non-lsass process touches krb5cc_* (no Kerberoast
        ticket-cache export). NO multi-principal SPN spray (single REQ/REP
        only). Structurally disjoint from T1558.003 (which characteristically
        emits 5+ TGS-REQ for SPN enumeration + ticket extraction to attacker
        disk) and from T1078 valid-accounts (which subsequently spawns
        target_svc.exe + reads sensitive_config.cfg + NET_CONNECT c2_net).
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_LSASS = "lsass.exe"
_KDC_NET = "kdc_network:88"
_TICKET_CACHE_TEMPLATE = "/tmp/krb5cc_{uid}"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_3_2"
_NEG_ID = "NEG-3.2"


class Neg32KerberosServiceTicket(HardNegativeTemplate):
    """T#3.2 benign Kerberos single-TGS service-ticket request workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_auth_kerberos_service_ticket")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 6-event Kerberos single-TGS service-ticket chain.

        Anonymization-robust anchors:
          - Single TGS-REQ/TGS-REP pair (single NET_SEND/NET_RECV — no
            multi-principal SPN spray).
          - FILE_WRITE only to local krb5cc_<uid> (no ticket export to
            attacker disk).
          - No downstream non-lsass FILE_READ of krb5cc_* (no Kerberoast
            export).
          - NET_CONNECT only to kdc_network (no C2).
          - No mstsc.exe (vs RDP class #8).

        USER_PRIV_GRANT user-anchor reuses T1068 workaround #2 — privilege
        attributed to seed_user not lsass.exe (semantically Windows 4672
        Special Privileges Assigned to New Logon).
        """
        assert isinstance(rng, random.Random)
        iid = instance_id
        # Synthetic uid for ticket-cache filename — derived from rng for
        # reproducibility; numeric uid mirrors Linux MIT Kerberos /tmp/krb5cc_<uid>
        # convention.
        uid = rng.randint(1000, 9999)

        lsass = f"neg_{iid}_{_LSASS}"
        kdc_net = f"neg_{iid}_{_KDC_NET}"
        ticket_cache = f"neg_{iid}_{_TICKET_CACHE_TEMPLATE.format(uid=uid)}"

        n_events = 6
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
            # 1. User logs on, OS launches/anchors lsass.exe Kerberos client
            #    session (4624 LogonType 2/3 then KRB5 init).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                lsass,
                NodeType.process,
            ),
            # 2. USER_PRIV_GRANT (4672) — privileged session anchor for the
            #    Kerberos exchange. Schema workaround #2 reuse: subject is
            #    seed_user (per ALLOWED_EDGE_TRIPLES only (user,
            #    USER_PRIV_GRANT, process) is allowed — NOT process-subject).
            #    Semantic: privilege attributed to seed_user's session per
            #    Windows 4672 "Special Privileges Assigned to New Logon".
            _ev(
                timestamps[1],
                seed_subject,
                NodeType.user,
                EdgeType.USER_PRIV_GRANT,
                lsass,
                NodeType.process,
            ),
            # 3. lsass.exe TCP-connects to KDC on Kerberos port 88 (single
            #    NET_CONNECT — no SPN spray).
            _ev(
                timestamps[2],
                lsass,
                NodeType.process,
                EdgeType.NET_CONNECT,
                kdc_net,
                NodeType.network,
            ),
            # 4. lsass.exe sends TGS-REQ to KDC (single principal request —
            #    structural anchor vs T1558.003 multi-principal Kerberoast).
            _ev(
                timestamps[3],
                lsass,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                kdc_net,
                NodeType.network,
            ),
            # 5. lsass.exe receives TGS-REP from KDC (single ticket payload).
            _ev(
                timestamps[4],
                lsass,
                NodeType.process,
                EdgeType.NET_RECV_NETWORK,
                kdc_net,
                NodeType.network,
            ),
            # 6. lsass.exe writes the service ticket to the local
            #    krb5cc_<uid> credential cache. NO subsequent FILE_READ from
            #    a non-lsass process — anonymization-robust anchor vs
            #    T1558.003 ticket extraction to attacker disk (Kerberoast
            #    workflow ALWAYS reads ticket cache from a non-lsass tool
            #    process).
            _ev(
                timestamps[5],
                lsass,
                NodeType.process,
                EdgeType.FILE_WRITE,
                ticket_cache,
                NodeType.file,
            ),
        ]
