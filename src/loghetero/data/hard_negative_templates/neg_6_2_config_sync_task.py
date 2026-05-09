"""T#6.2 benign_fs_config_sync_task — Hard Negative Template.

Class: #6 FS 操作 (per design propose §3.6 + §6.1)
NEG-ID: NEG-6.2
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.6 minimal sketch
    + §6.1 T1486 ransomware-mimicry pair sanity check + §5.6 schema
    readiness (vanilla, no workaround).

ATT&CK-like NEG-ID:
    NEG-6.2 — second of three FS-操作 hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.6 sub-pattern
    split (NEG-6.1 audit log scan / NEG-6.2 config sync task /
    NEG-6.3 sysadmin directory listing).

Distinct lexical signature + boundary (verbatim from design propose §3.6
plus Cycle H specific enhancement):
    Confound TTPs (T#6.2 verbatim from §3.6): T1083 / T1003 / T1005.
    Sanity check pair: T1486 ransomware-mimicry (per §6.1 detailed
    evaluation).

    Three anchors per template (派生自 §6.1 line 487-503 + §3.6 line
    128-143 verbatim):
      (i) Single FILE_RENAME .new→.conf non-mass-rename — sequence 含
          exactly 1 FILE_RENAME event.
      (ii) Plain config text non-encrypted — nginx.conf 是 plain text
           配置.
      (iii) Distinct extension semantics .new→.conf atomic config update
            vs T1486 .locked append-extension 加 FILE_RENAME single-file
            vs T1486 batch FILE_DELETE source 是结构性 disjoint.

    Boundary (§3.6 verbatim):
        合法 config sync **包含 internal repo network 而非 external IP**
        加 **写回原 path** 加 FILE_RENAME 是单 file 而非 batch mass-rename。
        BERT-only 看 /etc/nginx/* 词频与 T1083 share,区分必须靠 network
        destination 加 rename pattern semantics。

    Footnote (verbatim, must include): per NEEDS_CONTEXT #5 Option B 裁定
    user + 指导 Claude 共同 adjudicate 2026-05-08 per §14 clause; design
    propose §3.6 + §6.1 spec authoritative; v4 handoff §6.3 视为 v4
    handoff 撰写期 drafting drift; v5 handoff doc §6.3 + §11 item 4
    correction defer.

ALLOWED_EDGE_TRIPLES workaround reuse:
    Vanilla schema. All edge triples natively in ALLOWED_EDGE_TRIPLES.
    No workaround reuse. Zero new schema workaround inventory entries
    triggered. Triples used:
      - (user, USER_LOGON, process)            line 135
      - (process, FILE_READ, file)             line 110
      - (process, NET_CONNECT, network)        line 125
      - (process, NET_SEND_NETWORK, network)   line 128
      - (process, NET_RECV_NETWORK, network)   line 130
      - (process, FILE_WRITE, file)            line 111
      - (process, FILE_RENAME, file)           line 115

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON          (user → config_sync.exe — Task Scheduler
                             triggered)
          → FILE_READ        (config_sync → /etc/nginx/nginx.conf)
          → NET_CONNECT      (config_sync → internal_config_repo_network)
          → NET_SEND_NETWORK (config_sync → internal_config_repo_network)
          → NET_RECV_NETWORK (config_sync → internal_config_repo_network)
          → FILE_WRITE       (config_sync → /etc/nginx/nginx.conf.new)
          → FILE_RENAME      (config_sync → /etc/nginx/nginx.conf —
                             atomic .new→.conf swap)
    Length range: events_min=7, events_max=7 (deterministic Task
        Scheduler triggered config sync chain).
    Distinguishing structural pattern: SINGLE FILE_RENAME event with
        .new→.conf extension swap (anchor (i) + (iii)) — NOT batch mass-
        rename. Plain config text (anchor (ii)). Internal config repo
        network NOT external IP. Cross-reference docstring item 3 三
        anchors. Structurally disjoint from T1486 ransomware (which
        contains batch FILE_WRITE .locked + batch FILE_DELETE source +
        external C2 NET_CONNECT) and from T1083/T1003/T1005 (which would
        chain to external NET_CONNECT exfil).
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_CONFIG_SYNC = "config_sync.exe"
_NGINX_CONF = "/etc/nginx/nginx.conf"
_NGINX_CONF_NEW = "/etc/nginx/nginx.conf.new"
_INTERNAL_REPO_NET = "internal_config_repo_network:443"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_6_2"
_NEG_ID = "NEG-6.2"


class Neg62ConfigSyncTask(HardNegativeTemplate):
    """T#6.2 benign Task-Scheduler-triggered config sync workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_fs_config_sync_task")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 7-event Task-Scheduler triggered config sync chain.

        Anonymization-robust anchors:
          - Single FILE_RENAME .new→.conf atomic swap (anchor (i)+(iii)).
          - Plain config text (anchor (ii)).
          - Internal config repo network destination (NOT external IP).
          - No FILE_DELETE — structural disjoint from T1486 ransomware
            DELETE source-file step.
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        config_sync = f"neg_{iid}_{_CONFIG_SYNC}"
        nginx_conf = f"neg_{iid}_{_NGINX_CONF}"
        nginx_conf_new = f"neg_{iid}_{_NGINX_CONF_NEW}"
        internal_repo = f"neg_{iid}_{_INTERNAL_REPO_NET}"

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
            # 1. Task Scheduler triggered config_sync.exe launches under
            #    admin user context.
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                config_sync,
                NodeType.process,
            ),
            # 2. config_sync.exe FILE_READ /etc/nginx/nginx.conf (current
            #    config baseline).
            _ev(
                timestamps[1],
                config_sync,
                NodeType.process,
                EdgeType.FILE_READ,
                nginx_conf,
                NodeType.file,
            ),
            # 3. config_sync.exe NET_CONNECT to internal_config_repo (NOT
            #    external IP — internal repo destination).
            _ev(
                timestamps[2],
                config_sync,
                NodeType.process,
                EdgeType.NET_CONNECT,
                internal_repo,
                NodeType.network,
            ),
            # 4. config_sync.exe NET_SEND_NETWORK config-version request
            #    to internal repo.
            _ev(
                timestamps[3],
                config_sync,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                internal_repo,
                NodeType.network,
            ),
            # 5. config_sync.exe NET_RECV_NETWORK new config payload
            #    from internal repo.
            _ev(
                timestamps[4],
                config_sync,
                NodeType.process,
                EdgeType.NET_RECV_NETWORK,
                internal_repo,
                NodeType.network,
            ),
            # 6. config_sync.exe FILE_WRITE nginx.conf.new (staged new
            #    config — write to .new before atomic rename).
            _ev(
                timestamps[5],
                config_sync,
                NodeType.process,
                EdgeType.FILE_WRITE,
                nginx_conf_new,
                NodeType.file,
            ),
            # 7. config_sync.exe FILE_RENAME nginx.conf (atomic .new→.conf
            #    swap — single FILE_RENAME, anchor (i)+(iii); destination
            #    is original config path, anchor (ii) plain text).
            #    Subject FILE_RENAME on the destination (write-side rename
            #    semantic per ALLOWED_EDGE_TRIPLES (process, FILE_RENAME,
            #    file)).
            _ev(
                timestamps[6],
                config_sync,
                NodeType.process,
                EdgeType.FILE_RENAME,
                nginx_conf,
                NodeType.file,
            ),
        ]
