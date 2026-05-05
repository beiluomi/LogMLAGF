"""ATLAS log parsers (dns / firefox.txt / security_events.txt).

Three log types from Alsaheel et al. ATLAS (USENIX Security '21):

* ``dns`` — tshark-format DNS log; one packet per line, naive Eastern-Time
  timestamps. Each line yields a single :class:`Event`.
* ``firefox.txt`` — Firefox debug log; mostly debug spam. Only lines that
  match an HTTP request pattern (``uri=https?://...``) become :class:`Event`;
  everything else is recorded as ``skipped`` (NOT failed).
* ``security_events.txt`` — Windows EventLog tab-separated export. Multi-line
  quoted bodies are handled via :class:`csv.reader`. Only a curated set of
  audit EventIDs (4656/4658/4660/4663/4688/4689/4690) become :class:`Event`;
  other EventIDs are skipped.

Timestamp policy
================
* firefox.txt uses authoritative ``UTC`` (the log writes ``UTC`` literally).
* dns and security_events.txt are naive strings interpreted as Eastern Time
  (Purdue's source TZ). DST transitions are handled by ``zoneinfo``.

This assumption is verified empirically in Phase 1.5 by checking that the
three log streams from the same (scenario, host) overlap in time. Any >1h
drift triggers a ``known_issues.md`` entry.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from .base import (
    EdgeType,
    Event,
    NodeType,
    ParseStats,
    Parser,
    localize_eastern,
    to_utc_ns,
)

# Forward type alias used by the dispatch table below; the actual definition
# of _Extraction lives further down.
ExtractorFn = Callable[[dict[str, str]], "_Extraction | None"]

# ---------------------------------------------------------------------------
# DNS parser
# ---------------------------------------------------------------------------

# tshark line: "    1 2018-11-02 22:43:52.292203 192.168.223.128 → 192.168.223.2 DNS 84 Standard query 0x60f4 A detectportal.firefox.com"
# The arrow is U+2192 (→). We tolerate either Unicode arrow or "->" just in case.
_DNS_LINE_RE = re.compile(
    r"""
    ^\s*
    \d+\s+                                  # frame number
    (?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+
    (?P<src>\S+)\s+
    (?:→|->)\s+
    (?P<dst>\S+)\s+
    DNS\s+
    \d+\s+                                  # length
    (?P<desc>.+?)
    \s*$
    """,
    re.VERBOSE,
)
_DNS_QUERY_NAME_RE = re.compile(r"\b(?:A|AAAA|CNAME|MX|NS|PTR|TXT|SRV)\s+(\S+)")


class DnsParser(Parser):
    LOG_TYPE: ClassVar[str] = "atlas.dns"

    def parse_file(
        self,
        path: Path,
        *,
        scenario_id: str,
        host_id: str,
        stats: ParseStats | None = None,
    ) -> Iterator[Event]:
        if stats is None:
            stats = ParseStats()

        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, start=1):
                stripped = line.rstrip("\r\n")
                if not stripped.strip():
                    stats.record_skipped()
                    continue
                m = _DNS_LINE_RE.match(stripped)
                if not m:
                    stats.record_failure(line_num, stripped, "did not match DNS line regex")
                    continue
                try:
                    naive = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S.%f")
                    ts_ns = to_utc_ns(localize_eastern(naive))
                except ValueError as e:
                    stats.record_failure(line_num, stripped, f"timestamp parse error: {e}")
                    continue

                desc = m.group("desc")
                is_response = "response" in desc.lower()
                operation = (
                    EdgeType.NET_DNS_RESPONSE if is_response else EdgeType.NET_DNS_QUERY
                )

                query_match = _DNS_QUERY_NAME_RE.search(desc)
                query_name = query_match.group(1) if query_match else None

                stats.record_success()
                yield Event(
                    timestamp_ns=ts_ns,
                    subject=m.group("src"),
                    subject_type=NodeType.network,
                    obj=m.group("dst"),
                    obj_type=NodeType.network,
                    operation=operation,
                    log_type=self.LOG_TYPE,
                    scenario_id=scenario_id,
                    host_id=host_id,
                    attributes={
                        "query_name": query_name,
                        "raw_description": desc[:500],
                    },
                )


# ---------------------------------------------------------------------------
# Firefox parser
# ---------------------------------------------------------------------------

_FIREFOX_LINE_RE = re.compile(
    r"""
    ^
    (?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+UTC
    \s+-\s+
    \[(?P<thread>[^\]]+)\]:\s+
    (?P<level>[A-Z]/\S+)\s+
    (?P<msg>.+)$
    """,
    re.VERBOSE,
)
_FIREFOX_URI_RE = re.compile(r"uri=(?P<url>https?://\S+)")


class FirefoxParser(Parser):
    LOG_TYPE: ClassVar[str] = "atlas.firefox"

    def parse_file(
        self,
        path: Path,
        *,
        scenario_id: str,
        host_id: str,
        stats: ParseStats | None = None,
    ) -> Iterator[Event]:
        if stats is None:
            stats = ParseStats()

        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, start=1):
                # Fast pre-filter: 99%+ of firefox.txt lines are debug spam and
                # carry no uri=http* substring. Bypassing the heavy regex on
                # those lines is the difference between ~10 min and ~3 min on
                # the largest scenario.
                if "uri=http" not in line:
                    stats.record_skipped()
                    continue
                stripped = line.rstrip("\r\n")
                m = _FIREFOX_LINE_RE.match(stripped)
                if not m:
                    stats.record_skipped()
                    continue
                uri_match = _FIREFOX_URI_RE.search(m.group("msg"))
                if not uri_match:
                    stats.record_skipped()
                    continue
                try:
                    naive_utc = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S.%f")
                    from datetime import timezone

                    ts_ns = to_utc_ns(naive_utc.replace(tzinfo=timezone.utc))
                except ValueError as e:
                    stats.record_failure(line_num, stripped, f"timestamp parse error: {e}")
                    continue

                stats.record_success()
                yield Event(
                    timestamp_ns=ts_ns,
                    subject="firefox.exe",
                    subject_type=NodeType.process,
                    obj=uri_match.group("url"),
                    obj_type=NodeType.network,
                    operation=EdgeType.NET_HTTP_REQUEST,
                    log_type=self.LOG_TYPE,
                    scenario_id=scenario_id,
                    host_id=host_id,
                    attributes={
                        "thread": m.group("thread"),
                        "level": m.group("level"),
                    },
                )


# ---------------------------------------------------------------------------
# Windows security_events parser
# ---------------------------------------------------------------------------
# 11-EventID dispatch (7 file/process events from Phase 1.2 Checkpoint 2 +
# 4 user-logon events added in the Q-1 mini-checkpoint after Checkpoint 3).
# Each EventID has its own extractor function so per-event filter logic
# (e.g. 4624's LogonType filter) lives next to the field extraction.

# Optional leading whitespace: most fields are indented under a section header
# ("\tAccount Name:\t\tfoo") but a few (e.g. "Logon Type:" in 4624) appear
# at column 0. Section headers themselves (line ending in just ":") are
# filtered out by the caller before they reach this regex.
_BODY_KV_RE = re.compile(r"^\s*([\w/\(\) ]+?):\s+(.+?)\s*$")


def _parse_event_body(body: str) -> dict[str, str]:
    """Extract key:value pairs from a Windows audit event body (last-wins).

    The body is roughly INI-style, with section headers like ``Subject:`` /
    ``Object:`` / ``Process Information:`` followed by indented ``Key: Value``
    lines. We flatten everything into one dict keyed by the field name with
    **last-wins** semantics: 4624 puts ``Account Name`` in both ``Subject``
    (typically SYSTEM) and ``New Logon`` (the actual logon-target user). The
    one we want is the *later* one, so last-wins is correct. For the 7
    file/process EventIDs (4656/4658/4660/4663/4688/4689/4690) every relevant
    field name is unique within the body, so first-wins vs last-wins is a
    no-op there.
    """
    out: dict[str, str] = {}
    for raw_line in body.splitlines():
        if not raw_line.strip() or raw_line.rstrip().endswith(":"):
            continue
        m = _BODY_KV_RE.match(raw_line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def _user_id(fields: dict[str, str]) -> str | None:
    """Compose ``DOMAIN\\Account`` from body fields, or just ``Account`` if no domain.

    Returns ``None`` if Account Name is missing, signalling the extractor to
    skip this event.
    """
    account = fields.get("Account Name")
    if not account:
        return None
    domain = fields.get("Account Domain")
    return f"{domain}\\{account}" if domain else account


@dataclass(frozen=True, slots=True)
class _Extraction:
    """An extractor's verdict for one Windows audit event.

    Returning ``None`` from an extractor signals "this event is by-design
    skipped" (e.g. 4624 with the wrong LogonType): caller records ``skipped``,
    not ``failed``.
    """

    subject: str
    subject_type: NodeType
    obj: str
    obj_type: NodeType
    operation: EdgeType
    extra_attrs: dict[str, object]


# --- File / handle / process extractors (the original 7) ----------------

def _extract_file_op(
    fields: dict[str, str], op: EdgeType
) -> _Extraction | None:
    proc = fields.get("Process Name")
    obj_name = fields.get("Object Name") or fields.get("Handle ID")
    if not proc or not obj_name:
        return None
    return _Extraction(
        subject=proc,
        subject_type=NodeType.process,
        obj=obj_name,
        obj_type=NodeType.file,
        operation=op,
        extra_attrs={
            "access_mask": fields.get("Access Mask"),
            "object_type": fields.get("Object Type"),
        },
    )


def _extract_4656(f: dict[str, str]) -> _Extraction | None:
    return _extract_file_op(f, EdgeType.HANDLE_REQUEST)


def _extract_4658(f: dict[str, str]) -> _Extraction | None:
    return _extract_file_op(f, EdgeType.HANDLE_CLOSE)


def _extract_4660(f: dict[str, str]) -> _Extraction | None:
    return _extract_file_op(f, EdgeType.FILE_DELETE)


def _extract_4663(f: dict[str, str]) -> _Extraction | None:
    return _extract_file_op(f, EdgeType.FILE_ACCESS)


def _extract_4690(f: dict[str, str]) -> _Extraction | None:
    return _extract_file_op(f, EdgeType.HANDLE_DUPLICATE)


def _extract_4688(f: dict[str, str]) -> _Extraction | None:
    creator = f.get("Creator Process Name")
    new_proc = f.get("New Process Name") or f.get("Process Name")
    if not creator or not new_proc:
        # Fall back to subject account if no creator process named (rare).
        creator = creator or f.get("Account Name")
        if not creator or not new_proc:
            return None
    return _Extraction(
        subject=creator,
        subject_type=NodeType.process,
        obj=new_proc,
        obj_type=NodeType.process,
        operation=EdgeType.PROCESS_CREATE,
        extra_attrs={},
    )


def _extract_4689(f: dict[str, str]) -> _Extraction | None:
    proc = f.get("Process Name")
    if not proc:
        return None
    # Self-loop edge: keeps (process, PROCESS_EXIT, process) consistent with
    # ALLOWED_EDGE_TRIPLES rather than inventing a sentinel sink node.
    return _Extraction(
        subject=proc,
        subject_type=NodeType.process,
        obj=proc,
        obj_type=NodeType.process,
        operation=EdgeType.PROCESS_EXIT,
        extra_attrs={},
    )


# --- User-logon extractors (Q-1 mini-checkpoint, 4 new EventIDs) --------

# 4624 LogonType filter: only Network (3), NewCredentials (9), and
# RemoteInteractive / RDP (10). Type 5 (Service) and Type 2 (Interactive)
# are excluded as they are baseline noise per the Q-1 spec.
_ADMITTED_LOGON_TYPES: frozenset[str] = frozenset({"3", "9", "10"})


def _extract_4624(f: dict[str, str]) -> _Extraction | None:
    logon_type = f.get("Logon Type", "").strip()
    if logon_type not in _ADMITTED_LOGON_TYPES:
        return None  # skipped (filtered) -- not failed
    user = _user_id(f)
    if not user:
        return None
    proc = f.get("Process Name") or "lsass.exe"  # logon-target process; lsass is canonical fallback
    return _Extraction(
        subject=user,
        subject_type=NodeType.user,
        obj=proc,
        obj_type=NodeType.process,
        operation=EdgeType.USER_LOGON,
        extra_attrs={"logon_type": logon_type},
    )


def _extract_4625(f: dict[str, str]) -> _Extraction | None:
    user = _user_id(f)
    if not user:
        return None
    proc = f.get("Caller Process Name") or f.get("Process Name") or "lsass.exe"
    return _Extraction(
        subject=user,
        subject_type=NodeType.user,
        obj=proc,
        obj_type=NodeType.process,
        operation=EdgeType.USER_LOGON_FAIL,
        extra_attrs={
            "failure_reason": f.get("Failure Reason"),
            "status": f.get("Status"),
            "sub_status": f.get("Sub Status"),
            "logon_type": f.get("Logon Type"),
        },
    )


def _extract_4672(f: dict[str, str]) -> _Extraction | None:
    user = _user_id(f)
    if not user:
        return None
    # 4672 has no Process Name field; LSASS is the canonical privilege grantor
    # (the security subsystem that actually attaches the privileges to the token).
    return _Extraction(
        subject=user,
        subject_type=NodeType.user,
        obj="lsass.exe",
        obj_type=NodeType.process,
        operation=EdgeType.USER_PRIV_GRANT,
        extra_attrs={"privileges": f.get("Privileges")},
    )


def _extract_4648(f: dict[str, str]) -> _Extraction | None:
    user = _user_id(f)
    if not user:
        return None
    proc = f.get("Process Name") or "runas.exe"
    return _Extraction(
        subject=user,
        subject_type=NodeType.user,
        obj=proc,
        obj_type=NodeType.process,
        operation=EdgeType.USER_EXPLICIT_LOGON,
        extra_attrs={"target_server": f.get("Target Server Name")},
    )


# --- Dispatch table ------------------------------------------------------

_AUDIT_EVENTID_EXTRACTORS: dict[str, "ExtractorFn"] = {
    # File / handle / process (Phase 1.2 / Checkpoint 2)
    "4656": _extract_4656,
    "4658": _extract_4658,
    "4660": _extract_4660,
    "4663": _extract_4663,
    "4688": _extract_4688,
    "4689": _extract_4689,
    "4690": _extract_4690,
    # User-logon (Q-1 mini-checkpoint after Checkpoint 3)
    "4624": _extract_4624,
    "4625": _extract_4625,
    "4672": _extract_4672,
    "4648": _extract_4648,
}


class SecurityEventsParser(Parser):
    LOG_TYPE: ClassVar[str] = "atlas.security_events"

    def parse_file(
        self,
        path: Path,
        *,
        scenario_id: str,
        host_id: str,
        stats: ParseStats | None = None,
    ) -> Iterator[Event]:
        if stats is None:
            stats = ParseStats()

        # utf-8-sig strips the BOM that ATLAS files start with.
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.reader(f, delimiter="\t", quotechar='"')
            for row_num, row in enumerate(reader, start=1):
                if not row:
                    stats.record_skipped()
                    continue
                # Header: ["Keywords", "Date and Time", "Source", "Event ID", "Task Category"]
                if row_num == 1 and row[0].lower().startswith("keywords"):
                    stats.record_skipped()
                    continue
                if len(row) < 5:
                    stats.record_failure(
                        row_num,
                        "\t".join(row)[:200],
                        f"row has only {len(row)} fields, expected >=5",
                    )
                    continue

                keywords, dt_str, source, eventid, task = row[:5]
                body = row[5] if len(row) >= 6 else ""

                extractor = _AUDIT_EVENTID_EXTRACTORS.get(eventid)
                if extractor is None:
                    stats.record_skipped()
                    continue

                # Parse Windows local-time string: "11/5/2018 8:31:56 PM"
                try:
                    naive = datetime.strptime(dt_str.strip(), "%m/%d/%Y %I:%M:%S %p")
                    ts_ns = to_utc_ns(localize_eastern(naive))
                except ValueError as e:
                    stats.record_failure(row_num, dt_str, f"datetime parse error: {e}")
                    continue

                fields = _parse_event_body(body)
                extraction = extractor(fields)
                if extraction is None:
                    # By-design skip (e.g. 4624 with LogonType ∉ {3, 9, 10}, or
                    # missing required field). Not a failure.
                    stats.record_skipped()
                    continue

                stats.record_success()
                yield Event(
                    timestamp_ns=ts_ns,
                    subject=extraction.subject,
                    subject_type=extraction.subject_type,
                    obj=extraction.obj,
                    obj_type=extraction.obj_type,
                    operation=extraction.operation,
                    log_type=self.LOG_TYPE,
                    scenario_id=scenario_id,
                    host_id=host_id,
                    attributes={
                        "event_id": eventid,
                        "keywords": keywords,
                        "source": source,
                        "task_category": task,
                        "account_name": fields.get("Account Name"),
                        "logon_id": fields.get("Logon ID"),
                        **extraction.extra_attrs,
                    },
                )
