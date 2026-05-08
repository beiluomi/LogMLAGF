"""T#2.1 benign_webserver_apache_cgi_perl — Hard Negative Template.

Class: #2 Web Server CGI (per design propose §3.2 + §5.2)
NEG-ID: NEG-2.1
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.2 minimal sketch
    + §5.2 schema readiness (vanilla, no workaround) + §4.1 boundary clarification

ATT&CK-like NEG-ID:
    NEG-2.1 — first of two Web-Server-CGI hard-negative templates (NEG-2.1
    apache+CGI perl, NEG-2.2 nginx+PHP-FPM). Per-class numbering matches
    Checkpoint 16 design doc §3.2 sub-pattern split.

Distinct lexical signature + boundary (verbatim from design propose §3.2):
    Confound TTP: T1190 exploit-public-facing-application (specifically the
    webshell-write workaround #4 already landed in T1190 attack template).

    Boundary:
        合法 CGI perl 子进程 **不**写 webshell (无 (perl.exe, FILE_WRITE,
        *.php / *.jsp / *.aspx in /var/www/) 加 **不**进入 reverse shell
        (无 (perl.exe, NET_CONNECT, external_ip)). BERT-only 看 apache + perl
        + cgi-bin 词频与 T1190 已落地 webshell-write workaround event 重叠
        (apache.exe, FILE_WRITE, webshell.php), 区分必须靠 file-extension +
        write-target-path semantics.

    Anonymization-robust structural anchors:
      (a) FILE_WRITE target is /tmp/perl_render_<pid>.html (CGI render tmp
          file) NOT /var/www/*.php / *.jsp / *.aspx (webshell drop). Path
          prefix /tmp/ vs /var/www/ is structural disjoint regardless of
          file-name lexical mask.
      (b) NO NET_CONNECT outbound from perl.exe (anonymization-robust vs
          T1190 webshell exploitation reverse-shell).
      (c) Process tree depth = 2 (apache → perl → exit), NO further
          PROCESS_CREATE child (no shell spawn). T1190 webshell-as-RCE
          would depth >= 3 (apache → webshell → cmd.exe / sh).

ALLOWED_EDGE_TRIPLES workaround reuse:
    NONE — vanilla schema. Per design §5.2, all triples used by T#2.1 are
    natively in ALLOWED_EDGE_TRIPLES (parsers/base.py lines 106-141):
      - (process, NET_ACCEPT, network)         line 126
      - (process, PROCESS_CREATE, process)     line 120
      - (process, FILE_READ, file)             line 110
      - (process, FILE_WRITE, file)            line 111
      - (process, PROCESS_EXIT, process)       line 123 (self-loop)
    No workaround inventory entry triggered.

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        NET_ACCEPT (apache←inbound)
          → PROCESS_CREATE (apache→perl)
          → FILE_READ  (perl reads /var/www/cgi-bin/report.pl script)
          → FILE_READ  (perl reads /var/www/data/report.csv data)
          → FILE_WRITE (perl writes /tmp/perl_render_<pid>.html — render tmp)
          → PROCESS_EXIT (perl)
    Length range: events_min=6, events_max=6 (deterministic shape — single
        CGI request → single perl child → single render output).
    Distinguishing structural pattern: apache→perl 2-deep process chain
        with FILE_WRITE only to /tmp/ render path AND NO outbound
        NET_CONNECT — structurally disjoint from T1190 (which contains
        FILE_WRITE to /var/www/*.php webshell-extension via the schema
        workaround #4 reverse-direction approximation).
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_APACHE = "apache.exe"
_PERL = "perl.exe"
_INBOUND_NET = "internal_web_inbound_network:80"
_CGI_SCRIPT = "/var/www/cgi-bin/report.pl"
_CGI_DATA = "/var/www/data/report.csv"
_RENDER_TMP_TEMPLATE = "/tmp/perl_render_{pid}.html"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_2_1"
_NEG_ID = "NEG-2.1"


class Neg21ApacheCgiPerl(HardNegativeTemplate):
    """T#2.1 benign Apache + CGI perl child-process render workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_webserver_apache_cgi_perl")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 6-event Apache → CGI perl render chain.

        Anonymization-robust anchors:
          - FILE_WRITE only to /tmp/ render tmp (NOT /var/www/*.php).
          - No NET_CONNECT outbound from perl.exe.
          - Process tree depth = 2 (apache → perl → exit).
        """
        assert isinstance(rng, random.Random)
        iid = instance_id
        # Synthetic pid — derives from rng so seed reproducibility is preserved.
        pid = rng.randint(1000, 65535)

        apache = f"neg_{iid}_{_APACHE}"
        perl = f"neg_{iid}_{_PERL}"
        inbound_net = f"neg_{iid}_{_INBOUND_NET}"
        cgi_script = f"neg_{iid}_{_CGI_SCRIPT}"
        cgi_data = f"neg_{iid}_{_CGI_DATA}"
        render_tmp = f"neg_{iid}_{_RENDER_TMP_TEMPLATE.format(pid=pid)}"

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

        # NOTE: This template is anchored on the apache server process (NOT
        # the seed user) because CGI requests are inbound-network-driven —
        # the seed_subject parameter is recorded into attributes so the
        # injector still has a benign-user audit anchor, but no USER_LOGON
        # event is emitted (CGI requests do not produce 4624 events).
        attrs_base["seed_subject"] = seed_subject
        attrs_base["seed_subject_type"] = seed_subject_type

        return [
            # 1. apache.exe accepts inbound CGI request (NET_ACCEPT process →
            #    network — the standard "server listening" anchor).
            _ev(
                timestamps[0],
                apache,
                NodeType.process,
                EdgeType.NET_ACCEPT,
                inbound_net,
                NodeType.network,
            ),
            # 2. apache.exe spawns perl.exe child for CGI execution
            #    (process tree depth = 2 anchor).
            _ev(
                timestamps[1],
                apache,
                NodeType.process,
                EdgeType.PROCESS_CREATE,
                perl,
                NodeType.process,
            ),
            # 3. perl.exe reads the CGI script source.
            _ev(
                timestamps[2],
                perl,
                NodeType.process,
                EdgeType.FILE_READ,
                cgi_script,
                NodeType.file,
            ),
            # 4. perl.exe reads the data CSV the script renders.
            _ev(
                timestamps[3],
                perl,
                NodeType.process,
                EdgeType.FILE_READ,
                cgi_data,
                NodeType.file,
            ),
            # 5. perl.exe writes the render output to /tmp/ (NOT /var/www/*.php
            #    — anonymization-robust vs T1190 webshell-write workaround #4).
            _ev(
                timestamps[4],
                perl,
                NodeType.process,
                EdgeType.FILE_WRITE,
                render_tmp,
                NodeType.file,
            ),
            # 6. perl.exe exits cleanly (no further child process — depth 2
            #    structural anchor vs T1190 webshell-as-RCE depth >= 3).
            _ev(
                timestamps[5],
                perl,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                perl,
                NodeType.process,
            ),
        ]
