"""Contract tests for the parser foundation (base.py).

These tests must pass BEFORE any concrete parser is implemented (decision per
the Phase 1.2 checkpoint plan: base interface stable first, then concretes).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from loghetero.data.parsers.base import (
    ALLOWED_EDGE_TRIPLES,
    EdgeType,
    Event,
    FailureSample,
    NodeType,
    Parser,
    ParseStats,
    localize_eastern,
    to_utc_ns,
)


class TestNodeType:
    def test_five_canonical_types(self) -> None:
        assert {nt.value for nt in NodeType} == {"process", "file", "socket", "network", "user"}

    def test_string_enum(self) -> None:
        assert NodeType.process == "process"  # StrEnum equality
        assert NodeType("file") is NodeType.file


class TestEvent:
    def test_required_fields(self) -> None:
        ev = Event(
            timestamp_ns=1_000_000_000,
            subject="proc:foo",
            subject_type=NodeType.process,
            obj="/etc/passwd",
            obj_type=NodeType.file,
            operation="file_read",
            log_type="atlas.security_events",
            scenario_id="S1",
            host_id="h1",
        )
        assert ev.timestamp_ns == 1_000_000_000
        assert ev.subject_type is NodeType.process
        assert ev.obj_type is NodeType.file
        assert ev.attributes == {}

    def test_frozen(self) -> None:
        ev = Event(
            timestamp_ns=0,
            subject="x",
            subject_type=NodeType.process,
            obj="y",
            obj_type=NodeType.file,
            operation="z",
            log_type="atlas.dns",
            scenario_id="S1",
            host_id="h1",
        )
        with pytest.raises((AttributeError, TypeError)):
            ev.subject = "mutated"  # type: ignore[misc]

    def test_attributes_default_independent(self) -> None:
        # default_factory must produce a fresh dict per instance, not share one
        a = Event(
            timestamp_ns=0,
            subject="a",
            subject_type=NodeType.process,
            obj="b",
            obj_type=NodeType.file,
            operation="op",
            log_type="t",
            scenario_id="S1",
            host_id="h1",
        )
        b = Event(
            timestamp_ns=0,
            subject="c",
            subject_type=NodeType.process,
            obj="d",
            obj_type=NodeType.file,
            operation="op",
            log_type="t",
            scenario_id="S1",
            host_id="h1",
        )
        a.attributes["k"] = "v"
        assert "k" not in b.attributes


class TestParseStats:
    def test_initial_zeroed(self) -> None:
        s = ParseStats()
        assert s.success == 0
        assert s.failed == 0
        assert s.skipped == 0
        assert s.total == 0
        assert s.failure_rate == 0.0
        assert s.failure_samples == []

    def test_record_success(self) -> None:
        s = ParseStats()
        s.record_success()
        s.record_success()
        assert s.success == 2
        assert s.total == 2
        assert s.failure_rate == 0.0

    def test_record_skipped_does_not_inflate_failure_rate(self) -> None:
        # Skipped lines are by-design non-events (e.g. firefox debug spam),
        # they must NOT pollute failure_rate.
        s = ParseStats()
        for _ in range(99):
            s.record_skipped()
        s.record_failure(0, "bad", "err")
        assert s.skipped == 99
        assert s.failed == 1
        assert s.success == 0
        assert s.failure_rate == 1.0  # 1 failed / (0 success + 1 failed)

    def test_failure_rate_typical(self) -> None:
        s = ParseStats()
        for _ in range(95):
            s.record_success()
        for i in range(5):
            s.record_failure(i, "raw", "err")
        assert s.failure_rate == 0.05

    def test_failure_samples_capped(self) -> None:
        s = ParseStats()
        for i in range(100):
            s.record_failure(i, f"line {i}", "err")
        assert s.failed == 100
        assert len(s.failure_samples) == ParseStats.MAX_FAILURE_SAMPLES

    def test_failure_sample_truncates_long_raw(self) -> None:
        s = ParseStats()
        s.record_failure(0, "x" * 1000, "err")
        sample = s.failure_samples[0]
        assert isinstance(sample, FailureSample)
        assert len(sample.raw) <= 600  # 500 + "…[truncated]" suffix
        assert sample.raw.endswith("[truncated]")


class TestTimeHelpers:
    def test_to_utc_ns_unix_epoch(self) -> None:
        assert to_utc_ns(datetime(1970, 1, 1, tzinfo=timezone.utc)) == 0

    def test_to_utc_ns_microsecond_precision(self) -> None:
        # 1970-01-01 00:00:00.123456 UTC -> 123_456_000 ns
        dt = datetime(1970, 1, 1, 0, 0, 0, 123_456, tzinfo=timezone.utc)
        assert to_utc_ns(dt) == 123_456_000

    def test_to_utc_ns_typical_atlas_timestamp(self) -> None:
        # firefox.txt header: 2018-11-03 02:44:43.813000 UTC
        dt = datetime(2018, 11, 3, 2, 44, 43, 813_000, tzinfo=timezone.utc)
        ns = to_utc_ns(dt)
        # Cross-check using datetime.timestamp() (only used here for verification;
        # production path avoids it for sub-microsecond determinism).
        expected_seconds = int(dt.replace(microsecond=0).timestamp())
        assert ns == expected_seconds * 1_000_000_000 + 813 * 1_000_000

    def test_to_utc_ns_rejects_naive(self) -> None:
        with pytest.raises(ValueError, match="TZ-aware"):
            to_utc_ns(datetime(2020, 1, 1))

    def test_localize_eastern_edt(self) -> None:
        # 2018-11-02 22:43:52 EDT (DST still active, UTC-4) -> 2018-11-03 02:43:52 UTC
        naive = datetime(2018, 11, 2, 22, 43, 52)
        local = localize_eastern(naive)
        utc = local.astimezone(timezone.utc)
        assert utc.hour == 2
        assert utc.day == 3
        assert utc.minute == 43

    def test_localize_eastern_est(self) -> None:
        # 2018-11-05 20:31:56 EST (post DST end, UTC-5) -> 2018-11-06 01:31:56 UTC
        naive = datetime(2018, 11, 5, 20, 31, 56)
        local = localize_eastern(naive)
        utc = local.astimezone(timezone.utc)
        assert utc.day == 6
        assert utc.hour == 1
        assert utc.minute == 31

    def test_localize_eastern_rejects_aware(self) -> None:
        aware = datetime(2018, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            localize_eastern(aware)


class TestEdgeTypeAndTriples:
    """Pin the EdgeType enum and the ALLOWED_EDGE_TRIPLES schema (Checkpoint 3 lock)."""

    def test_edge_type_string_enum_compat(self) -> None:
        # str-Enum equality with raw strings (same trick as NodeType).
        assert EdgeType.FILE_READ == "file_read"
        assert EdgeType("net_dns_query") is EdgeType.NET_DNS_QUERY

    def test_send_recv_split_by_dst_type(self) -> None:
        # Checkpoint 3 invariant: same operation must NOT span multiple
        # (src, dst) combos -> CDM EVENT_SENDTO/RECVFROM split into
        # SOCKET vs NETWORK variants so the (src, edge, dst) triple stays unique.
        assert EdgeType.NET_SEND_SOCKET != EdgeType.NET_SEND_NETWORK
        assert EdgeType.NET_RECV_SOCKET != EdgeType.NET_RECV_NETWORK

    def test_every_edge_type_appears_at_most_once_in_triples(self) -> None:
        # Each EdgeType maps to exactly ONE (src, dst) pair so the same
        # operation never broadcasts across multiple PyG edge stores.
        # UNKNOWN is the only intentional exception: it appears in zero
        # canonical triples (builder skips it).
        seen: dict[EdgeType, tuple[NodeType, NodeType]] = {}
        for src, edge, dst in ALLOWED_EDGE_TRIPLES:
            assert edge not in seen, (
                f"EdgeType.{edge.name} has multiple (src, dst) pairs in "
                f"ALLOWED_EDGE_TRIPLES: previously {seen[edge]}, now ({src}, {dst})"
            )
            seen[edge] = (src, dst)
        assert EdgeType.UNKNOWN not in seen

    def test_every_canonical_edge_type_member_is_in_triples(self) -> None:
        # Every EdgeType besides UNKNOWN must appear in ALLOWED_EDGE_TRIPLES,
        # so adding an enum entry without listing its triple fails this test.
        in_triples = {edge for _, edge, _ in ALLOWED_EDGE_TRIPLES}
        missing = set(EdgeType) - in_triples - {EdgeType.UNKNOWN}
        assert not missing, f"EdgeType members not in ALLOWED_EDGE_TRIPLES: {missing}"

    def test_dns_triples_use_network_on_both_sides(self) -> None:
        for edge in (EdgeType.NET_DNS_QUERY, EdgeType.NET_DNS_RESPONSE):
            triples = [t for t in ALLOWED_EDGE_TRIPLES if t[1] is edge]
            assert triples == [(NodeType.network, edge, NodeType.network)]

    def test_process_create_is_process_to_process(self) -> None:
        triples = [t for t in ALLOWED_EDGE_TRIPLES if t[1] is EdgeType.PROCESS_CREATE]
        assert triples == [(NodeType.process, EdgeType.PROCESS_CREATE, NodeType.process)]


class TestParserABC:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            Parser()  # type: ignore[abstract]

    def test_concrete_subclass_must_define_log_type_and_parse(self) -> None:
        class _Concrete(Parser):
            LOG_TYPE = "test.dummy"

            def parse_file(self, path, *, scenario_id, host_id, stats=None):  # type: ignore[no-untyped-def]
                if False:
                    yield  # makes this a generator

        # Should be instantiable now
        p = _Concrete()
        assert p.LOG_TYPE == "test.dummy"
        # Empty generator
        events = list(p.parse_file("/tmp/x", scenario_id="S1", host_id="h1"))
        assert events == []
