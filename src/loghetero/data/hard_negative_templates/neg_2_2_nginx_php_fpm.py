"""T#2.2 benign_webserver_nginx_php_fpm — Hard Negative Template.

Class: #2 Web Server CGI (per design propose §3.2 + §5.2)
NEG-ID: NEG-2.2
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.2 minimal sketch
    + §5.2 schema readiness (vanilla, no workaround) + §4.1 boundary clarification

ATT&CK-like NEG-ID:
    NEG-2.2 — second of two Web-Server-CGI hard-negative templates.
    Per-class numbering matches Checkpoint 16 design doc §3.2 sub-pattern
    split (NEG-2.1 apache+CGI perl / NEG-2.2 nginx+PHP-FPM).

Distinct lexical signature + boundary (verbatim from design propose §3.2):
    Confound TTP: T1505.003 web-shell.

    Boundary:
        合法 PHP-FPM 子进程 **不**写新 .php 文件加 **不**调用 shell utilities
        (无 (php-fpm.exe, PROCESS_CREATE, sh / bash / cmd)). BERT-only 看
        nginx + php-fpm + .php 词频与 T1505.003 web-shell-as-php 共享, 区分
        必须靠下游 process spawn 加 file-write 信号.

    Anonymization-robust structural anchors:
      (a) NO FILE_WRITE to *.php (PHP-FPM serves PHP NOT writes new PHP —
          structural anchor vs T1505.003 webshell drop).
      (b) NO PROCESS_CREATE child from php-fpm.exe (no shell-utility spawn
          — anonymization-robust vs T1505.003 webshell-as-RCE).
      (c) NET_SEND_SOCKET nginx → php-fpm IPC socket (Unix-domain socket
          IPC) is the standard nginx → PHP-FPM bridge — distinguishing
          structural pattern from CGI-spawn-child model.
      (d) PHP-FPM downstream NET_CONNECT to internal_db_backend_network
          (RFC1918 internal anchor) for SQL query — DB backend network
          anchor distinct from T1505.003 webshell C2 outbound.

ALLOWED_EDGE_TRIPLES workaround reuse:
    NONE — vanilla schema. Per design §5.2, all triples used by T#2.2 are
    natively in ALLOWED_EDGE_TRIPLES (parsers/base.py lines 106-141):
      - (process, NET_ACCEPT, network)         line 126
      - (process, NET_SEND_SOCKET, socket)     line 127
      - (process, FILE_READ, file)             line 110
      - (process, NET_CONNECT, network)        line 125
      - (process, NET_SEND_NETWORK, network)   line 128
      - (process, NET_RECV_NETWORK, network)   line 130
    No workaround inventory entry triggered.

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        NET_ACCEPT (nginx←inbound)
          → NET_SEND_SOCKET (nginx→fpm-ipc-socket FastCGI bridge)
          → FILE_READ  (php-fpm reads /var/www/html/checkout.php)
          → NET_CONNECT (php-fpm→internal_db_backend_network)
          → NET_SEND_NETWORK (php-fpm→db-backend, SQL query)
          → NET_RECV_NETWORK (php-fpm←db-backend, SQL response)
    Length range: events_min=6, events_max=6 (deterministic shape — single
        request → single FastCGI bridge → single DB query/response cycle).
    Distinguishing structural pattern: nginx→php-fpm via Unix-domain socket
        bridge (NET_SEND_SOCKET process→socket triple) followed by
        php-fpm→DB internal-network query, NO FILE_WRITE anywhere AND NO
        PROCESS_CREATE child — structurally disjoint from T1505.003 (which
        contains FILE_WRITE to webshell *.php on disk + downstream
        PROCESS_CREATE shell-utility for command execution).
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_NGINX = "nginx.exe"
_PHP_FPM = "php-fpm.exe"
_INBOUND_NET = "internal_web_inbound_network:443"
_FPM_SOCKET = "/run/php/php-fpm.sock"
_PHP_FILE = "/var/www/html/checkout.php"
_DB_BACKEND_NET = "internal_db_backend_network:5432"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_2_2"
_NEG_ID = "NEG-2.2"


class Neg22NginxPhpFpm(HardNegativeTemplate):
    """T#2.2 benign nginx + PHP-FPM via Unix-domain socket bridge workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_webserver_nginx_php_fpm")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 6-event nginx → PHP-FPM → DB chain.

        Anonymization-robust anchors:
          - No FILE_WRITE anywhere (PHP-FPM serves PHP, doesn't write).
          - No PROCESS_CREATE child from php-fpm.exe.
          - NET_SEND_SOCKET nginx → fpm-socket bridge (FastCGI structural
            anchor distinct from CGI-spawn-child model).
          - php-fpm DB query to internal_db_backend_network (internal anchor).
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        nginx = f"neg_{iid}_{_NGINX}"
        php_fpm = f"neg_{iid}_{_PHP_FPM}"
        inbound_net = f"neg_{iid}_{_INBOUND_NET}"
        fpm_socket = f"neg_{iid}_{_FPM_SOCKET}"
        php_file = f"neg_{iid}_{_PHP_FILE}"
        db_backend_net = f"neg_{iid}_{_DB_BACKEND_NET}"

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
            "seed_subject": seed_subject,
            "seed_subject_type": seed_subject_type,
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
            # 1. nginx.exe accepts inbound HTTPS request.
            _ev(
                timestamps[0],
                nginx,
                NodeType.process,
                EdgeType.NET_ACCEPT,
                inbound_net,
                NodeType.network,
            ),
            # 2. nginx → php-fpm via Unix-domain socket FastCGI bridge
            #    (NET_SEND_SOCKET process → socket — structural anchor for
            #    nginx-FPM model vs apache-CGI spawn-child model).
            _ev(
                timestamps[1],
                nginx,
                NodeType.process,
                EdgeType.NET_SEND_SOCKET,
                fpm_socket,
                NodeType.socket,
            ),
            # 3. php-fpm.exe reads the PHP file to serve.
            _ev(
                timestamps[2],
                php_fpm,
                NodeType.process,
                EdgeType.FILE_READ,
                php_file,
                NodeType.file,
            ),
            # 4. php-fpm.exe connects to internal DB backend.
            _ev(
                timestamps[3],
                php_fpm,
                NodeType.process,
                EdgeType.NET_CONNECT,
                db_backend_net,
                NodeType.network,
            ),
            # 5. php-fpm.exe sends SQL query to DB backend.
            _ev(
                timestamps[4],
                php_fpm,
                NodeType.process,
                EdgeType.NET_SEND_NETWORK,
                db_backend_net,
                NodeType.network,
            ),
            # 6. php-fpm.exe receives SQL response.
            _ev(
                timestamps[5],
                php_fpm,
                NodeType.process,
                EdgeType.NET_RECV_NETWORK,
                db_backend_net,
                NodeType.network,
            ),
        ]
