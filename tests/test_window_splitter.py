"""Unit tests for window_splitter (Phase 1.5)."""

from __future__ import annotations

import pytest

from loghetero.data.window_splitter import (
    NS_PER_HOUR,
    bucket_counts,
    window_density_stats,
    window_index,
)


class TestWindowIndex:
    def test_zero_ts_in_bucket_zero(self) -> None:
        assert window_index(0, 1.0) == 0

    def test_one_hour_boundary(self) -> None:
        assert window_index(NS_PER_HOUR - 1, 1.0) == 0
        assert window_index(NS_PER_HOUR, 1.0) == 1

    def test_half_hour_granularity(self) -> None:
        # 30-minute windows: ts at 1.5h -> bucket 3
        assert window_index(int(1.5 * NS_PER_HOUR), 0.5) == 3

    def test_rejects_non_positive_window(self) -> None:
        with pytest.raises(ValueError):
            window_index(0, 0.0)
        with pytest.raises(ValueError):
            window_index(0, -1.0)


class TestBucketCounts:
    def test_buckets_only_nonempty_appear(self) -> None:
        # Three events: t=0.5h, t=0.7h (same bucket), t=2.5h (different bucket)
        ts = [
            int(0.5 * NS_PER_HOUR),
            int(0.7 * NS_PER_HOUR),
            int(2.5 * NS_PER_HOUR),
        ]
        counts = bucket_counts(ts, 1.0)
        assert counts == {0: 2, 2: 1}

    def test_empty_input(self) -> None:
        assert bucket_counts([], 1.0) == {}


class TestWindowDensityStats:
    def test_empty_input_returns_zeros(self) -> None:
        s = window_density_stats([], 1.0)
        assert s["n_events"] == 0
        assert s["n_nonempty"] == 0
        assert s["mean"] == 0.0
        assert s["max"] == 0.0

    def test_uniform_density(self) -> None:
        # 100 timestamps spread one per hour over 100 hours -> 100 buckets
        # of size 1 each.
        ts = [i * NS_PER_HOUR for i in range(100)]
        s = window_density_stats(ts, 1.0)
        assert s["n_events"] == 100
        assert s["n_nonempty"] == 100
        assert s["mean"] == 1.0
        assert s["median"] == 1.0
        assert s["max"] == 1.0
        assert s["min_nonzero"] == 1.0

    def test_skewed_density(self) -> None:
        # Single hot bucket: 9 events at t=0.1h..0.9h all fall in bucket 0
        # (range stops at 9 so no 1.0h boundary edge case). Plus 1 sparse
        # event at t=50h in bucket 50.
        ts = [int(0.1 * i * NS_PER_HOUR) for i in range(1, 10)] + [int(50 * NS_PER_HOUR)]
        s = window_density_stats(ts, 1.0)
        assert s["n_events"] == 10
        assert s["n_nonempty"] == 2
        assert s["max"] == 9.0
        assert s["min_nonzero"] == 1.0

    def test_window_size_changes_n_buckets(self) -> None:
        # 100 events over 100 hours, with 4-hour windows -> 25 buckets of 4 each.
        ts = [i * NS_PER_HOUR for i in range(100)]
        s = window_density_stats(ts, 4.0)
        assert s["n_nonempty"] == 25
        assert s["mean"] == 4.0
