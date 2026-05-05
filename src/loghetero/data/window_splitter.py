"""Time-window bucketing helpers (Phase 1.5).

Pure functions used by:

* ``scripts/build_window_density_histograms.py`` to produce the Checkpoint 4
  per-(scenario, host) events/hour histograms;
* ``loghetero.data.datamodule`` (Phase 1.6) to materialise the ``(host_id,
  time_window)`` partitions decision 6 requires.

No module here hardcodes a granularity; callers pass ``window_hours`` from
the Hydra config (``configs/data/atlas.yaml::window.time_window_hours``).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable

NS_PER_HOUR: int = 3600 * 1_000_000_000


def window_index(ts_ns: int, window_hours: float) -> int:
    """Return ``floor(ts_ns / window_size_ns)`` -- the bucket index."""
    if window_hours <= 0:
        raise ValueError(f"window_hours must be positive, got {window_hours}")
    window_ns = int(window_hours * NS_PER_HOUR)
    return ts_ns // window_ns


def bucket_counts(timestamps: Iterable[int], window_hours: float) -> dict[int, int]:
    """Bucket timestamps by ``window_hours`` and count per bucket.

    The bucket key is the integer ``floor(ts_ns / window_ns)``; only
    buckets with ≥1 event appear in the returned dict.
    """
    if window_hours <= 0:
        raise ValueError(f"window_hours must be positive, got {window_hours}")
    window_ns = int(window_hours * NS_PER_HOUR)
    counts: dict[int, int] = {}
    for ts in timestamps:
        idx = ts // window_ns
        counts[idx] = counts.get(idx, 0) + 1
    return counts


def window_density_stats(timestamps: list[int], window_hours: float) -> dict[str, float]:
    """Summary stats of events-per-window for one (scenario, host).

    Returns keys:
        n_events:       total events.
        n_nonempty:     number of non-empty windows.
        mean:           mean events per non-empty window.
        median:         median events per non-empty window.
        p99:            99th percentile events per non-empty window.
        max:            max events in any single window.
        min_nonzero:    smallest non-empty window's count.
    """
    if not timestamps:
        return {
            "n_events": 0,
            "n_nonempty": 0,
            "mean": 0.0,
            "median": 0.0,
            "p99": 0.0,
            "max": 0.0,
            "min_nonzero": 0.0,
        }
    counts = sorted(bucket_counts(timestamps, window_hours).values())
    n = len(counts)
    p99_idx = min(n - 1, max(0, int(round(n * 0.99)) - 1))
    return {
        "n_events": float(len(timestamps)),
        "n_nonempty": float(n),
        "mean": float(statistics.mean(counts)),
        "median": float(statistics.median(counts)),
        "p99": float(counts[p99_idx]),
        "max": float(counts[-1]),
        "min_nonzero": float(counts[0]),
    }
