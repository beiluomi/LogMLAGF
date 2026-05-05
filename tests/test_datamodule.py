"""Phase 1.6 / Checkpoint 5 DataModule tests.

Required ≥2 counter-examples per launch spec:

1. ``test_leakage_assert_triggers_on_constructed_overlap`` -- decision 6
   invariant; manually overlap (host, window) keys between train and test
   sets and verify the AssertionError fires with a diagnosable message.
2. ``test_tz_assert_triggers_on_constructed_offset`` -- TZ sanity check;
   manually offset a host's dns events by 12 hours from its firefox events
   and verify the AssertionError fires pointing at localize_eastern.

Plus happy-path tests for the per-window sampling rules from decision 9
(benign down-sampling cap, attack events kept in full, NumPy-seeded
reproducibility).
"""

from __future__ import annotations

import numpy as np
import pytest

from loghetero.data.datamodule import (
    HostWindowKey,
    _assert_no_window_leakage,
    _assert_tz_alignment,
    benign_only_label_loader,
    event_to_text,
    sample_target_events,
)
from loghetero.data.parsers.base import EdgeType, Event, NodeType


def _ev(
    ts_ns: int,
    *,
    subject: str = "p",
    obj: str = "f",
    log_type: str = "atlas.security_events",
    operation: EdgeType = EdgeType.FILE_READ,
    subject_type: NodeType = NodeType.process,
    obj_type: NodeType = NodeType.file,
) -> Event:
    return Event(
        timestamp_ns=ts_ns,
        subject=subject,
        subject_type=subject_type,
        obj=obj,
        obj_type=obj_type,
        operation=operation,
        log_type=log_type,
        scenario_id="T",
        host_id="h",
    )


# ---------------------------------------------------------------------------
# COUNTER-EXAMPLE 1: decision 6 leakage assert
# ---------------------------------------------------------------------------


class TestLeakageAssert:
    def test_leakage_assert_triggers_on_constructed_overlap(self) -> None:
        # Train and test share (host_id="X", window_idx=3) -- decision 6
        # forbids this. The assert must fire with a diagnosable message.
        train = {HostWindowKey("X", 3), HostWindowKey("Y", 0)}
        test = {HostWindowKey("X", 3), HostWindowKey("Z", 1)}
        with pytest.raises(AssertionError) as exc:
            _assert_no_window_leakage(train, test)
        msg = str(exc.value)
        assert "DECISION 6 VIOLATION" in msg
        assert "host" in msg.lower() and "window" in msg.lower()
        # Pointer to the partition site (good error message hygiene)
        assert "_partition_by_scenario" in msg

    def test_disjoint_train_test_passes(self) -> None:
        # Happy path: no overlap = no exception.
        train = {HostWindowKey("X", 0), HostWindowKey("X", 1), HostWindowKey("Y", 0)}
        test = {HostWindowKey("Z", 0), HostWindowKey("X", 5)}
        _assert_no_window_leakage(train, test)  # should not raise

    def test_empty_test_passes(self) -> None:
        # Pretrain mode: test set is empty; assert should pass.
        train = {HostWindowKey("X", 0)}
        test: set[HostWindowKey] = set()
        _assert_no_window_leakage(train, test)


# ---------------------------------------------------------------------------
# COUNTER-EXAMPLE 2: cross-log-type TZ sanity assert
# ---------------------------------------------------------------------------


class TestTzAssert:
    def test_tz_assert_triggers_on_constructed_offset(self) -> None:
        # Construct a host whose dns first event is 12 hours offset from its
        # firefox first event -- simulates localize_eastern returning the
        # wrong timezone (e.g. PST instead of EST).
        events_by_host = {
            "M1_h1": [
                _ev(0, log_type="atlas.dns"),  # dns at t=0
                _ev(12 * 3600 * 1_000_000_000, log_type="atlas.firefox"),  # firefox 12 h later
                _ev(60 * 1_000_000_000, log_type="atlas.security_events"),
            ]
        }
        with pytest.raises(AssertionError) as exc:
            _assert_tz_alignment(events_by_host, max_delta_minutes=5.0)
        msg = str(exc.value)
        assert "TZ SANITY FAIL" in msg
        assert "M1_h1" in msg
        # The error message MUST point at localize_eastern (per Q-1 launch spec).
        assert "localize_eastern" in msg

    def test_tz_alignment_passes_when_streams_close(self) -> None:
        # 51-second gap between dns and firefox -- matches the actual ATLAS
        # observation from Phase 1.2. Must pass.
        events_by_host = {
            "M1_h1": [
                _ev(0, log_type="atlas.dns"),
                _ev(51 * 1_000_000_000, log_type="atlas.firefox"),
            ]
        }
        _assert_tz_alignment(events_by_host, max_delta_minutes=5.0)

    def test_tz_alignment_skips_host_missing_dns_or_firefox(self) -> None:
        # Some hosts may legitimately lack one of the streams; we should
        # silently skip rather than error.
        events_by_host = {
            "X": [_ev(0, log_type="atlas.security_events")],
        }
        _assert_tz_alignment(events_by_host)  # should not raise


# ---------------------------------------------------------------------------
# Decision 9 sampling protocol
# ---------------------------------------------------------------------------


class TestSampleTargetEvents:
    def test_keeps_all_attack_events(self) -> None:
        # 5 attacks + 1000 benign in one window, cap=10. All 5 attacks must
        # remain; 5 of 1000 benigns get sampled (10 - 5 = 5 budget).
        attack_label = lambda ev: 1 if "attack" in ev.subject else 0  # noqa: E731
        events = [(i, _ev(i, subject=f"attack_{i}")) for i in range(5)] + [
            (i + 100, _ev(i + 100, subject=f"benign_{i}")) for i in range(1000)
        ]
        rng = np.random.default_rng(42)
        kept = sample_target_events(
            events,
            max_events_per_window=10,
            label_loader=attack_label,
            rng=rng,
        )
        n_attacks = sum(1 for _, _, label in kept if label == 1)
        n_benigns = sum(1 for _, _, label in kept if label == 0)
        assert n_attacks == 5
        assert n_benigns == 5

    def test_attack_events_can_exceed_cap(self) -> None:
        # If attacks alone exceed the cap, ALL attacks are kept (decision 9
        # trades benign budget for attack signal).
        events = [(i, _ev(i, subject=f"a_{i}")) for i in range(20)]
        rng = np.random.default_rng(0)
        kept = sample_target_events(
            events,
            max_events_per_window=5,
            label_loader=lambda ev: 1,  # everything is attack
            rng=rng,
        )
        assert len(kept) == 20

    def test_uniform_downsampling_is_seeded_reproducible(self) -> None:
        # Two runs with the same seed must produce the same chosen indices.
        events = [(i, _ev(i, subject=f"b_{i}")) for i in range(100)]
        rng_a = np.random.default_rng(42)
        rng_b = np.random.default_rng(42)
        kept_a = sample_target_events(
            events,
            max_events_per_window=10,
            label_loader=lambda _: 0,
            rng=rng_a,
        )
        kept_b = sample_target_events(
            events,
            max_events_per_window=10,
            label_loader=lambda _: 0,
            rng=rng_b,
        )
        idx_a = sorted(i for i, _, _ in kept_a)
        idx_b = sorted(i for i, _, _ in kept_b)
        assert idx_a == idx_b

    def test_empty_window_yields_empty_result(self) -> None:
        kept = sample_target_events(
            [],
            max_events_per_window=100,
            label_loader=lambda _: 0,
            rng=np.random.default_rng(0),
        )
        assert kept == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_event_to_text_is_clean(self) -> None:
        ev = _ev(0, subject="C:\\Users\\bob\\thing.exe", obj="C:\\Windows\\System32\\cmd.exe")
        text = event_to_text(ev)
        # Cleaner should have replaced both Windows paths with placeholders.
        assert "[PATH_WIN_USERS]" in text
        assert "[PATH_WIN_SYS32]" in text
        # Operation prefix preserved
        assert text.split()[0] == EdgeType.FILE_READ.value

    def test_benign_only_label_loader_returns_zero(self) -> None:
        assert benign_only_label_loader(_ev(0)) == 0
