"""Unit tests for the three ATLAS log parsers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from loghetero.data.parsers.atlas import (
    DnsParser,
    FirefoxParser,
    SecurityEventsParser,
)
from loghetero.data.parsers.base import (
    EdgeType,
    NodeType,
    ParseStats,
    localize_eastern,
    to_utc_ns,
)

# ---------------------------------------------------------------------------
# DNS parser
# ---------------------------------------------------------------------------

DNS_SAMPLE = (
    "    1 2018-11-02 22:43:52.292203 192.168.223.128 → 192.168.223.2 DNS 84 Standard query 0x60f4 A detectportal.firefox.com\n"
    "    2 2018-11-02 22:43:52.301364 192.168.223.2 → 192.168.223.128 DNS 242 Standard query response 0x60f4 A detectportal.firefox.com CNAME detectportal.prod.mozaws.net A 149.165.180.17\n"
    "this line is total garbage and should fail\n"
    "    3 2018-11-02 22:43:52.304313 192.168.223.128 → 192.168.223.2 DNS 81 Standard query 0x140c A a1089.dscd.akamai.net\n"
    "\n"  # blank line, should be skipped
)


def _write_tmp(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


class TestDnsParser:
    def test_happy_path(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "dns", DNS_SAMPLE)
        stats = ParseStats()
        events = list(DnsParser().parse_file(p, scenario_id="S1", host_id="h1", stats=stats))
        assert len(events) == 3
        assert stats.success == 3
        assert stats.failed == 1
        assert stats.skipped == 1
        assert stats.failure_rate == pytest.approx(1 / 4)

    def test_query_vs_response(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "dns", DNS_SAMPLE)
        events = list(DnsParser().parse_file(p, scenario_id="S1", host_id="h1"))
        ops = [e.operation for e in events]
        assert ops == [
            EdgeType.NET_DNS_QUERY,
            EdgeType.NET_DNS_RESPONSE,
            EdgeType.NET_DNS_QUERY,
        ]

    def test_subject_object_are_ips_typed_network(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "dns", DNS_SAMPLE)
        e = next(DnsParser().parse_file(p, scenario_id="S1", host_id="h1"))
        assert e.subject == "192.168.223.128"
        assert e.subject_type is NodeType.network
        assert e.obj == "192.168.223.2"
        assert e.obj_type is NodeType.network
        assert e.attributes["query_name"] == "detectportal.firefox.com"

    def test_eastern_time_localization(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "dns", DNS_SAMPLE)
        e = next(DnsParser().parse_file(p, scenario_id="S1", host_id="h1"))
        # 2018-11-02 22:43:52.292203 EDT (DST on, UTC-4) -> 2018-11-03 02:43:52.292203 UTC
        expected = to_utc_ns(localize_eastern(datetime(2018, 11, 2, 22, 43, 52, 292_203)))
        assert e.timestamp_ns == expected

    def test_log_type_constant(self) -> None:
        assert DnsParser.LOG_TYPE == "atlas.dns"


# ---------------------------------------------------------------------------
# Firefox parser
# ---------------------------------------------------------------------------

FIREFOX_SAMPLE = (
    "2018-11-03 02:44:43.813000 UTC - [Main Thread]: D/nsStreamPump nsInputStreamPump::OnInputStreamReady [this=10def580]\n"
    "2018-11-03 02:44:43.977000 UTC - [Main Thread]: V/nsHttp uri=https://tiles-cloudfront.cdn.mozilla.net/images/foo.png\n"
    "2018-11-03 02:44:43.978000 UTC - [Socket Thread]: V/nsHttp uri=http://example.com/page\n"
    "this line totally lacks a timestamp; should be skipped\n"
)


class TestFirefoxParser:
    def test_only_uri_lines_become_events(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "firefox.txt", FIREFOX_SAMPLE)
        stats = ParseStats()
        events = list(FirefoxParser().parse_file(p, scenario_id="S1", host_id="h1", stats=stats))
        assert len(events) == 2
        assert stats.success == 2
        # 1 debug + 1 unparseable + Phase 1.2 design treats unparseable firefox
        # spam as skipped (not failed) -> 2 skipped, 0 failed.
        assert stats.failed == 0
        assert stats.skipped == 2

    def test_subject_constant_firefox(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "firefox.txt", FIREFOX_SAMPLE)
        e = next(FirefoxParser().parse_file(p, scenario_id="S1", host_id="h1"))
        assert e.subject == "firefox.exe"
        assert e.subject_type is NodeType.process
        assert e.obj.startswith("https://")
        assert e.obj_type is NodeType.network
        assert e.operation == EdgeType.NET_HTTP_REQUEST

    def test_utc_authoritative(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "firefox.txt", FIREFOX_SAMPLE)
        e = next(FirefoxParser().parse_file(p, scenario_id="S1", host_id="h1"))
        expected = to_utc_ns(datetime(2018, 11, 3, 2, 44, 43, 977_000, tzinfo=timezone.utc))
        assert e.timestamp_ns == expected

    def test_log_type_constant(self) -> None:
        assert FirefoxParser.LOG_TYPE == "atlas.firefox"


# ---------------------------------------------------------------------------
# Security events parser
# ---------------------------------------------------------------------------

# Tab-separated. The body is a CSV-quoted multi-line field. UTF-8 BOM at the
# start of the first line so we can verify utf-8-sig handling.
SEC_EVENTS_SAMPLE = (
    "﻿Keywords\tDate and Time\tSource\tEvent ID\tTask Category\n"
    'Audit Success\t11/5/2018 8:31:56 PM\tMicrosoft-Windows-Security-Auditing\t4663\tFile System\t"An attempt was made to access an object.\n'
    "\n"
    "Subject:\n"
    "\tSecurity ID:\t\tWIN-D65GVM5K5FO\\aalsahee\n"
    "\tAccount Name:\t\taalsahee\n"
    "\tAccount Domain:\t\tWIN-D65GVM5K5FO\n"
    "\tLogon ID:\t\t0x20e88\n"
    "\n"
    "Object:\n"
    "\tObject Server:\tSecurity\n"
    "\tObject Type:\tFile\n"
    "\tObject Name:\tC:\\Users\\aalsahee\n"
    "\tHandle ID:\t0x56c\n"
    "\n"
    "Process Information:\n"
    "\tProcess ID:\t0x660\n"
    "\tProcess Name:\tC:\\Windows\\System32\\mmc.exe\n"
    "\n"
    "Access Request Information:\n"
    "\tAccesses:\tReadData (or ListDirectory)\n"
    '\tAccess Mask:\t0x1"\n'
    'Audit Success\t11/5/2018 8:32:01 PM\tMicrosoft-Windows-Security-Auditing\t4688\tProcess Creation\t"A new process has been created.\n'
    "\n"
    "Subject:\n"
    "\tAccount Name:\t\taalsahee\n"
    "\n"
    "Process Information:\n"
    "\tNew Process Name:\tC:\\Users\\aalsahee\\payload.exe\n"
    '\tCreator Process Name:\tC:\\Windows\\explorer.exe"\n'
    'Audit Success\t11/5/2018 8:32:02 PM\tMicrosoft-Windows-Security-Auditing\t9999\tNot in dispatch\t"Should be skipped"\n'
)


class TestSecurityEventsParser:
    def test_parses_4663_and_4688_skips_9999(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "security_events.txt", SEC_EVENTS_SAMPLE)
        stats = ParseStats()
        events = list(
            SecurityEventsParser().parse_file(p, scenario_id="S1", host_id="h1", stats=stats)
        )
        assert len(events) == 2
        assert stats.success == 2
        # header (1) + EventID 9999 not in dispatch (1) = 2 skipped
        assert stats.skipped == 2
        assert stats.failed == 0

    def test_4663_extracts_subject_and_object(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "security_events.txt", SEC_EVENTS_SAMPLE)
        events = list(SecurityEventsParser().parse_file(p, scenario_id="S1", host_id="h1"))
        e = events[0]
        assert e.attributes["event_id"] == "4663"
        assert "mmc.exe" in e.subject
        assert e.subject_type is NodeType.process
        assert e.obj == "C:\\Users\\aalsahee"
        assert e.obj_type is NodeType.file
        assert e.operation == EdgeType.FILE_ACCESS
        assert e.attributes["account_name"] == "aalsahee"
        assert e.attributes["access_mask"] == "0x1"

    def test_4688_extracts_creator_and_new_process(self, tmp_path: Path) -> None:
        p = _write_tmp(tmp_path, "security_events.txt", SEC_EVENTS_SAMPLE)
        events = list(SecurityEventsParser().parse_file(p, scenario_id="S1", host_id="h1"))
        e = events[1]
        assert e.attributes["event_id"] == "4688"
        assert "explorer.exe" in e.subject
        assert "payload.exe" in e.obj
        assert e.subject_type is NodeType.process
        assert e.obj_type is NodeType.process
        assert e.operation == EdgeType.PROCESS_CREATE

    def test_eastern_time_localization_post_dst_end(self, tmp_path: Path) -> None:
        # Nov 5 2018 is after DST end (Nov 4 02:00) -> EST (UTC-5)
        p = _write_tmp(tmp_path, "security_events.txt", SEC_EVENTS_SAMPLE)
        e = next(SecurityEventsParser().parse_file(p, scenario_id="S1", host_id="h1"))
        # 11/5/2018 8:31:56 PM EST -> 11/6/2018 1:31:56 UTC
        utc_dt = datetime.fromtimestamp(e.timestamp_ns / 1e9, tz=timezone.utc)
        assert utc_dt.day == 6
        assert utc_dt.hour == 1
        assert utc_dt.minute == 31

    def test_log_type_constant(self) -> None:
        assert SecurityEventsParser.LOG_TYPE == "atlas.security_events"


# ---------------------------------------------------------------------------
# User-logon EventIDs (Q-1 mini-checkpoint: 4624 / 4625 / 4672 / 4648)
# ---------------------------------------------------------------------------


def _make_4624_sample(logon_type: str, account: str = "alice", domain: str = "CORP") -> str:
    """Build a single-record CSV sample for EventID 4624 with a chosen LogonType.

    Subject section uses SYSTEM (the typical 4624 pattern); New Logon section
    carries the actual logon-target account. With our last-wins body parser,
    ``Account Name`` resolves to the New Logon value.
    """
    return (
        "﻿Keywords\tDate and Time\tSource\tEvent ID\tTask Category\n"
        f'Audit Success\t11/5/2018 9:00:00 PM\tMicrosoft-Windows-Security-Auditing\t4624\tLogon\t"An account was successfully logged on.\n'
        "\n"
        "Subject:\n"
        "\tSecurity ID:\t\tSYSTEM\n"
        "\tAccount Name:\t\tWIN-D65GVM5K5FO$\n"
        "\tAccount Domain:\t\tWORKGROUP\n"
        "\tLogon ID:\t\t0x3e7\n"
        "\n"
        f"Logon Type:\t\t\t{logon_type}\n"
        "\n"
        "New Logon:\n"
        "\tSecurity ID:\t\tS-1-5-21-1\n"
        f"\tAccount Name:\t\t{account}\n"
        f"\tAccount Domain:\t\t{domain}\n"
        "\tLogon ID:\t\t0x12345\n"
        "\n"
        "Process Information:\n"
        "\tProcess ID:\t0x204\n"
        '\tProcess Name:\tC:\\Windows\\System32\\winlogon.exe"\n'
    )


class TestUserLogon4624LogonTypeFilter:
    """Counter-examples per Q-1 mini-checkpoint spec: only LogonType in {3, 9, 10} admitted."""

    def test_logon_type_2_interactive_filtered(self, tmp_path: Path) -> None:
        # Counter-example: Interactive console logon = noise per spec.
        p = _write_tmp(tmp_path, "security_events.txt", _make_4624_sample("2"))
        stats = ParseStats()
        events = list(
            SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1", stats=stats)
        )
        assert events == []
        # Header + filtered 4624 = 2 skipped, 0 success, 0 failed
        assert stats.success == 0
        assert stats.failed == 0
        assert stats.skipped == 2

    def test_logon_type_5_service_filtered(self, tmp_path: Path) -> None:
        # Counter-example: Service logon = the dominant ATLAS background noise.
        p = _write_tmp(tmp_path, "security_events.txt", _make_4624_sample("5"))
        stats = ParseStats()
        events = list(
            SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1", stats=stats)
        )
        assert events == []
        assert stats.skipped == 2

    def test_logon_type_3_network_admitted(self, tmp_path: Path) -> None:
        # Network logon = T1021 lateral movement signal. MUST be admitted.
        p = _write_tmp(
            tmp_path, "security_events.txt", _make_4624_sample("3", account="bob", domain="DOM")
        )
        events = list(SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1"))
        assert len(events) == 1
        e = events[0]
        assert e.attributes["event_id"] == "4624"
        assert e.subject == "DOM\\bob"
        assert e.subject_type is NodeType.user
        assert e.subject_type is NodeType.user
        assert "winlogon.exe" in e.obj
        assert e.obj_type is NodeType.process
        assert e.operation == EdgeType.USER_LOGON
        assert e.attributes["logon_type"] == "3"

    def test_logon_type_9_new_credentials_admitted(self, tmp_path: Path) -> None:
        # NewCredentials = runas / credential reuse. APT signal.
        p = _write_tmp(tmp_path, "security_events.txt", _make_4624_sample("9", account="charlie"))
        events = list(SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1"))
        assert len(events) == 1
        assert events[0].operation == EdgeType.USER_LOGON
        assert events[0].attributes["logon_type"] == "9"

    def test_logon_type_10_rdp_admitted(self, tmp_path: Path) -> None:
        # RemoteInteractive = RDP = T1021.001 horizontal movement. APT critical.
        p = _write_tmp(tmp_path, "security_events.txt", _make_4624_sample("10"))
        events = list(SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1"))
        assert len(events) == 1
        assert events[0].operation == EdgeType.USER_LOGON
        assert events[0].attributes["logon_type"] == "10"

    def test_user_id_uses_domain_account_format(self, tmp_path: Path) -> None:
        # When both Account Domain + Account Name present, subject id is "DOMAIN\Account".
        p = _write_tmp(
            tmp_path,
            "security_events.txt",
            _make_4624_sample("3", account="dave", domain="EVILCORP"),
        )
        e = next(SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1"))
        assert e.subject == "EVILCORP\\dave"


class TestUserLogonOtherEventIds:
    def test_4625_failure_emits_user_logon_fail(self, tmp_path: Path) -> None:
        sample = (
            "﻿Keywords\tDate and Time\tSource\tEvent ID\tTask Category\n"
            'Audit Failure\t11/5/2018 9:01:00 PM\tMicrosoft-Windows-Security-Auditing\t4625\tLogon\t"An account failed to log on.\n'
            "\n"
            "Subject:\n"
            "\tAccount Name:\t\tSYSTEM\n"
            "\n"
            "Account For Which Logon Failed:\n"
            "\tAccount Name:\t\teve\n"
            "\tAccount Domain:\t\tEVILCORP\n"
            "\n"
            "Failure Information:\n"
            "\tFailure Reason:\t\tUnknown user name or bad password.\n"
            "\tStatus:\t0xC000006D\n"
            "\n"
            "Process Information:\n"
            '\tCaller Process Name:\tC:\\Windows\\System32\\lsass.exe"\n'
        )
        p = _write_tmp(tmp_path, "security_events.txt", sample)
        events = list(SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1"))
        assert len(events) == 1
        e = events[0]
        assert e.attributes["event_id"] == "4625"
        assert e.subject == "EVILCORP\\eve"
        assert e.subject_type is NodeType.user
        assert e.operation == EdgeType.USER_LOGON_FAIL
        assert "lsass.exe" in e.obj
        assert e.obj_type is NodeType.process
        # Failure reason captured in attrs (Phase 5 RAPA can use it)
        assert "Unknown user name" in (e.attributes.get("failure_reason") or "")

    def test_4672_priv_grant_uses_lsass_canonical_obj(self, tmp_path: Path) -> None:
        sample = (
            "﻿Keywords\tDate and Time\tSource\tEvent ID\tTask Category\n"
            'Audit Success\t11/5/2018 9:02:00 PM\tMicrosoft-Windows-Security-Auditing\t4672\tSpecial Logon\t"Special privileges assigned to new logon.\n'
            "\n"
            "Subject:\n"
            "\tSecurity ID:\t\tS-1-5-21-2\n"
            "\tAccount Name:\t\tadministrator\n"
            "\tAccount Domain:\t\tCORP\n"
            "\tLogon ID:\t\t0x99\n"
            "\n"
            '\tPrivileges:\t\tSeTcbPrivilege"\n'
        )
        p = _write_tmp(tmp_path, "security_events.txt", sample)
        events = list(SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1"))
        assert len(events) == 1
        e = events[0]
        assert e.attributes["event_id"] == "4672"
        assert e.subject == "CORP\\administrator"
        assert e.subject_type is NodeType.user
        # 4672 has no Process Name; LSASS is canonical privilege grantor.
        assert e.obj == "lsass.exe"
        assert e.obj_type is NodeType.process
        assert e.operation == EdgeType.USER_PRIV_GRANT
        assert e.attributes["privileges"] == "SeTcbPrivilege"

    def test_4648_explicit_credentials_emits_user_explicit_logon(self, tmp_path: Path) -> None:
        sample = (
            "﻿Keywords\tDate and Time\tSource\tEvent ID\tTask Category\n"
            'Audit Success\t11/5/2018 9:03:00 PM\tMicrosoft-Windows-Security-Auditing\t4648\tLogon\t"A logon was attempted using explicit credentials.\n'
            "\n"
            "Subject:\n"
            "\tAccount Name:\t\tcaller_user\n"
            "\n"
            "Account Whose Credentials Were Used:\n"
            "\tAccount Name:\t\timpersonated_admin\n"
            "\tAccount Domain:\t\tCORP\n"
            "\n"
            "Target Server:\n"
            "\tTarget Server Name:\tdc01.corp.local\n"
            "\n"
            "Process Information:\n"
            '\tProcess Name:\tC:\\Windows\\System32\\runas.exe"\n'
        )
        p = _write_tmp(tmp_path, "security_events.txt", sample)
        events = list(SecurityEventsParser().parse_file(p, scenario_id="T", host_id="h1"))
        assert len(events) == 1
        e = events[0]
        assert e.attributes["event_id"] == "4648"
        # last-wins picks the impersonated account, not the caller
        assert e.subject == "CORP\\impersonated_admin"
        assert e.subject_type is NodeType.user
        assert "runas.exe" in e.obj
        assert e.operation == EdgeType.USER_EXPLICIT_LOGON
        assert e.attributes["target_server"] == "dc01.corp.local"
