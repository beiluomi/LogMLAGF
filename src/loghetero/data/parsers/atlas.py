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
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from .base import (
    Event,
    NodeType,
    ParseStats,
    Parser,
    localize_eastern,
    to_utc_ns,
)

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
                operation = "dns_response" if is_response else "dns_query"

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
                    operation="http_request",
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

# Curated audit EventIDs we treat as security-relevant. Other EventIDs are
# skipped (not failed). Mapping: eventid -> (operation, obj_node_type).
_AUDIT_EVENTID_DISPATCH: dict[str, tuple[str, NodeType]] = {
    "4656": ("handle_request", NodeType.file),
    "4658": ("handle_close", NodeType.file),
    "4660": ("file_delete", NodeType.file),
    "4663": ("file_access", NodeType.file),
    "4688": ("process_create", NodeType.process),
    "4689": ("process_exit", NodeType.process),
    "4690": ("handle_duplicate", NodeType.file),
}

_BODY_KV_RE = re.compile(r"^\s+([\w/\(\) ]+?):\s+(.+?)\s*$")


def _parse_event_body(body: str) -> dict[str, str]:
    """Extract key:value pairs from a Windows audit event body.

    The body is roughly INI-style, with section headers like ``Subject:`` /
    ``Object:`` / ``Process Information:`` followed by indented ``Key: Value``
    lines. We flatten everything into one dict keyed by the field name; later
    fields with the same name win, which is fine because the EventID-specific
    extractors only ever read fields they expect.
    """
    out: dict[str, str] = {}
    for raw_line in body.splitlines():
        if not raw_line.strip() or raw_line.rstrip().endswith(":"):
            continue
        m = _BODY_KV_RE.match(raw_line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key not in out:
                out[key] = val
    return out


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

                if eventid not in _AUDIT_EVENTID_DISPATCH:
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
                operation, obj_type = _AUDIT_EVENTID_DISPATCH[eventid]

                # Subject: the process performing the action (Process Name); if
                # absent (rare), fall back to the account name.
                proc_name = fields.get("Process Name") or fields.get("New Process Name")
                account = fields.get("Account Name", "")

                if eventid in {"4688"}:
                    # Process creation: subject = creator process; obj = new process
                    subject = fields.get("Creator Process Name") or proc_name or account
                    subject_type = NodeType.process
                    obj_val = fields.get("New Process Name") or fields.get("Process Name") or "?"
                elif eventid in {"4689"}:
                    subject = proc_name or account
                    subject_type = NodeType.process
                    obj_val = "self"
                else:
                    # File-handle / access events
                    subject = proc_name or account
                    subject_type = NodeType.process
                    obj_val = fields.get("Object Name") or fields.get("Handle ID") or "?"

                if not subject:
                    stats.record_failure(
                        row_num,
                        dt_str,
                        f"could not derive subject for EventID {eventid}",
                    )
                    continue

                stats.record_success()
                yield Event(
                    timestamp_ns=ts_ns,
                    subject=subject,
                    subject_type=subject_type,
                    obj=obj_val,
                    obj_type=obj_type,
                    operation=operation,
                    log_type=self.LOG_TYPE,
                    scenario_id=scenario_id,
                    host_id=host_id,
                    attributes={
                        "event_id": eventid,
                        "keywords": keywords,
                        "source": source,
                        "task_category": task,
                        "account_name": account,
                        "logon_id": fields.get("Logon ID"),
                        "access_mask": fields.get("Access Mask"),
                        "object_type": fields.get("Object Type"),
                    },
                )
