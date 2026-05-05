"""Foundation types shared by every concrete log parser.

Every parser converts raw log lines into a stream of :class:`Event` records, all
normalised to UTC nanosecond timestamps. The five :class:`NodeType` cases match
the LogHetero heterogeneous schema (decision 5 in ``docs/design_decisions.md``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

# Eastern Time is the source TZ for all ATLAS naive timestamps (the dataset is
# from Purdue, West Lafayette IN). zoneinfo handles EST/EDT DST transitions
# automatically; the 2018-11-04 02:00 fall-back is in scope for several ATLAS
# scenarios so this matters.
ATLAS_LOCAL_TZ_NAME = "America/New_York"

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


class NodeType(str, Enum):
    """The 5 LogHetero heterogeneous node types (decision 5).

    ``str, Enum`` mixin chosen over Python 3.11's ``StrEnum`` to keep the
    project on Python 3.10 (per pyproject pin). Equality with raw strings
    works identically: ``NodeType.process == "process"`` is True.
    """

    process = "process"
    file = "file"
    socket = "socket"
    network = "network"
    user = "user"


class EdgeType(str, Enum):
    """Canonical edge-operation enum.

    **Locked at Checkpoint 3 (Phase 1.4) — do not extend without an RFC.**
    PyG ``HeteroData`` keys edges by the triple ``(src_node_type,
    edge_type, dst_node_type)``. To keep that triple stable across the
    project, every concrete parser MUST emit ``Event.operation`` from
    this enum, and each enum member MUST appear in exactly one
    ``(src_type, dst_type)`` combination listed in :data:`ALLOWED_EDGE_TRIPLES`.

    The names are kept loud (``NET_SEND_SOCKET`` vs ``NET_SEND_NETWORK``)
    to enforce the "same operation -> same (src, dst)" invariant that the
    Checkpoint 3 launch spec calls out. Without that, the same operation
    string in two different (src, dst) cells would silently broadcast to
    multiple PyG edge stores, breaking message-passing semantics.
    """

    # File / handle operations: process -> file
    FILE_OPEN = "file_open"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_CLOSE = "file_close"
    FILE_ACCESS = "file_access"  # ATLAS EventID 4663 generic access
    FILE_DELETE = "file_delete"
    FILE_RENAME = "file_rename"
    HANDLE_REQUEST = "handle_request"      # ATLAS EventID 4656
    HANDLE_CLOSE = "handle_close"          # ATLAS EventID 4658
    HANDLE_DUPLICATE = "handle_duplicate"  # ATLAS EventID 4690

    # Process operations: process -> process
    PROCESS_CREATE = "process_create"  # ATLAS EventID 4688
    PROCESS_FORK = "fork"
    PROCESS_EXEC = "exec"
    PROCESS_EXIT = "process_exit"      # ATLAS EventID 4689 (self-loop)

    # Network operations (note: src/dst type baked into the name to keep
    # the triple unique, per Checkpoint 3 invariant)
    NET_CONNECT = "net_connect"             # process -> network
    NET_ACCEPT = "net_accept"               # process -> network
    NET_SEND_SOCKET = "net_send_socket"     # process -> socket (CDM SrcSink IPC)
    NET_SEND_NETWORK = "net_send_network"   # process -> network (TCP/UDP/CDM NetFlow)
    NET_RECV_SOCKET = "net_recv_socket"     # process -> socket
    NET_RECV_NETWORK = "net_recv_network"   # process -> network
    NET_HTTP_REQUEST = "net_http_request"   # process -> network (URL)
    NET_DNS_QUERY = "net_dns_query"         # network -> network
    NET_DNS_RESPONSE = "net_dns_response"   # network -> network

    # User auth (Q-1 mini-checkpoint after Checkpoint 3): ATLAS now emits these
    # via the 11-EventID dispatch (4624 with LogonType filter / 4625 / 4672 /
    # 4648). DARPA TC E3 will reuse them through Principal-driven event chains.
    USER_LOGON = "user_logon"                  # 4624 with LogonType in {3, 9, 10}
    USER_LOGOFF = "user_logoff"                # reserved for future
    USER_LOGON_FAIL = "user_logon_fail"        # 4625 (always emitted -- failure is rare + high signal)
    USER_PRIV_GRANT = "user_priv_grant"        # 4672 (special privileges to new logon)
    USER_EXPLICIT_LOGON = "user_explicit_logon"  # 4648 (logon with explicit credentials, e.g. runas)

    # Bottom type: an operation we don't know how to map. Builder will skip
    # edges with this type rather than guess a wrong (src, dst) triple.
    UNKNOWN = "unknown"


# The full, exhaustive list of canonical (src_type, edge_type, dst_type) triples
# the project understands. PyG HeteroData edge stores will be keyed by these.
# Adding to this set requires a design_decisions.md RFC.
ALLOWED_EDGE_TRIPLES: frozenset[tuple[NodeType, EdgeType, NodeType]] = frozenset(
    {
        # File / handle: process -> file
        (NodeType.process, EdgeType.FILE_OPEN, NodeType.file),
        (NodeType.process, EdgeType.FILE_READ, NodeType.file),
        (NodeType.process, EdgeType.FILE_WRITE, NodeType.file),
        (NodeType.process, EdgeType.FILE_CLOSE, NodeType.file),
        (NodeType.process, EdgeType.FILE_ACCESS, NodeType.file),
        (NodeType.process, EdgeType.FILE_DELETE, NodeType.file),
        (NodeType.process, EdgeType.FILE_RENAME, NodeType.file),
        (NodeType.process, EdgeType.HANDLE_REQUEST, NodeType.file),
        (NodeType.process, EdgeType.HANDLE_CLOSE, NodeType.file),
        (NodeType.process, EdgeType.HANDLE_DUPLICATE, NodeType.file),
        # Process -> process
        (NodeType.process, EdgeType.PROCESS_CREATE, NodeType.process),
        (NodeType.process, EdgeType.PROCESS_FORK, NodeType.process),
        (NodeType.process, EdgeType.PROCESS_EXEC, NodeType.process),
        (NodeType.process, EdgeType.PROCESS_EXIT, NodeType.process),
        # Network
        (NodeType.process, EdgeType.NET_CONNECT, NodeType.network),
        (NodeType.process, EdgeType.NET_ACCEPT, NodeType.network),
        (NodeType.process, EdgeType.NET_SEND_SOCKET, NodeType.socket),
        (NodeType.process, EdgeType.NET_SEND_NETWORK, NodeType.network),
        (NodeType.process, EdgeType.NET_RECV_SOCKET, NodeType.socket),
        (NodeType.process, EdgeType.NET_RECV_NETWORK, NodeType.network),
        (NodeType.process, EdgeType.NET_HTTP_REQUEST, NodeType.network),
        (NodeType.network, EdgeType.NET_DNS_QUERY, NodeType.network),
        (NodeType.network, EdgeType.NET_DNS_RESPONSE, NodeType.network),
        # User auth (Q-1 mini-checkpoint -- 5 triples for the 5 USER_* edges)
        (NodeType.user, EdgeType.USER_LOGON, NodeType.process),
        (NodeType.user, EdgeType.USER_LOGOFF, NodeType.process),
        (NodeType.user, EdgeType.USER_LOGON_FAIL, NodeType.process),
        (NodeType.user, EdgeType.USER_PRIV_GRANT, NodeType.process),
        (NodeType.user, EdgeType.USER_EXPLICIT_LOGON, NodeType.process),
    }
)


@dataclass(frozen=True, slots=True)
class Event:
    """One parsed log event, normalised to UTC ns and the 5-type schema.

    Designed to be the parser/graph boundary: parsers emit ``Event``; graph
    construction consumes ``Event``. Down-stream code never re-parses raw lines.
    """

    timestamp_ns: int
    subject: str
    subject_type: NodeType
    obj: str
    obj_type: NodeType
    operation: str
    log_type: str
    scenario_id: str
    host_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FailureSample:
    """A single parse failure captured for the report (bounded by MAX)."""

    line_num: int
    raw: str
    error: str


@dataclass
class ParseStats:
    """Per-file accumulator of parse outcomes.

    ``failure_rate`` excludes ``skipped`` from the denominator: skipped lines
    are "by design not an event we care about" (e.g. firefox debug spam),
    whereas ``failed`` is "tried to parse and choked". Reporting failure rate
    against ``success + failed`` keeps the metric meaningful regardless of how
    much skip-by-design content a log type has.
    """

    success: int = 0
    failed: int = 0
    skipped: int = 0
    failure_samples: list[FailureSample] = field(default_factory=list)

    MAX_FAILURE_SAMPLES: ClassVar[int] = 50

    def record_success(self) -> None:
        self.success += 1

    def record_skipped(self) -> None:
        self.skipped += 1

    def record_failure(self, line_num: int, raw: str, error: str) -> None:
        self.failed += 1
        if len(self.failure_samples) < self.MAX_FAILURE_SAMPLES:
            # truncate raw for memory hygiene; full-length raw goes nowhere useful
            sample_raw = raw if len(raw) <= 500 else raw[:500] + "…[truncated]"
            self.failure_samples.append(FailureSample(line_num, sample_raw, error))

    @property
    def total(self) -> int:
        return self.success + self.failed + self.skipped

    @property
    def failure_rate(self) -> float:
        denom = self.success + self.failed
        return self.failed / denom if denom else 0.0


class Parser(ABC):
    """Abstract base every concrete log parser inherits from."""

    LOG_TYPE: ClassVar[str]

    @abstractmethod
    def parse_file(
        self,
        path: Path,
        *,
        scenario_id: str,
        host_id: str,
        stats: ParseStats | None = None,
    ) -> Iterator[Event]:
        """Parse ``path`` and yield :class:`Event`. Updates ``stats`` in place."""
        raise NotImplementedError


def to_utc_ns(dt: datetime) -> int:
    """Return UTC nanoseconds since the Unix epoch.

    The input must be timezone-aware; passing a naive datetime is a programmer
    error and raises ``ValueError``. Use :func:`localize_eastern` to attach a
    timezone to a naive Eastern-Time string before calling this.

    Implementation note: we do NOT use ``datetime.timestamp()`` which goes via
    float seconds and loses sub-microsecond precision. We use a direct
    timedelta diff against the UNIX epoch instead.
    """
    if dt.tzinfo is None:
        raise ValueError(
            f"to_utc_ns requires a TZ-aware datetime; got naive {dt!r}. "
            "Use localize_eastern(naive_dt) or attach UTC explicitly."
        )
    delta = dt - _EPOCH_UTC
    return (
        delta.days * 86_400 * 1_000_000_000
        + delta.seconds * 1_000_000_000
        + delta.microseconds * 1_000
    )


def localize_eastern(naive: datetime) -> datetime:
    """Attach America/New_York TZ to a naive datetime (DST-aware via zoneinfo).

    ATLAS dns/security_events timestamps are naive Eastern Time strings; this
    helper makes the assumption explicit at every call site. zoneinfo correctly
    handles EDT->EST and EST->EDT transitions including the 2018-11-04 02:00
    fall-back relevant to several ATLAS scenarios.
    """
    if naive.tzinfo is not None:
        raise ValueError(f"localize_eastern expects a naive datetime; got {naive!r}")
    # Imported lazily so platforms missing tzdata can still import this module.
    from zoneinfo import ZoneInfo

    return naive.replace(tzinfo=ZoneInfo(ATLAS_LOCAL_TZ_NAME))
