"""Phase 1.6 / Checkpoint 5 fold-stats report.

For each of the 10 leave-one-attack-out folds (S1, S2, S3, S4, M1...M6),
compute the train / test sample sizes the DataModule would emit. Used by the
Checkpoint 5 report to show that the per-event sample unit (decision 9)
yields the predicted ~64k train / ~4k-8k test sizes per fold.

Skips the per-event subgraph sampling step (graphs are not needed for
counts), so this is fast: parse-once + 10 fold partitions in ~50s wall.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig

from loghetero.data.datamodule import (
    HostWindowKey,
    benign_only_label_loader,
    sample_target_events,
)
from loghetero.data.parsers.atlas import (
    DnsParser,
    FirefoxParser,
    SecurityEventsParser,
)
from loghetero.data.parsers.base import Event
from loghetero.data.window_splitter import window_index

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs" / "data"
SUMMARY_OUT = PROJECT_ROOT / "data" / "atlas_fold_stats.json"
REPORT_OUT = PROJECT_ROOT / "data" / "processed" / "atlas_fold_stats_report.md"

ALL_SCENARIOS = ["S1", "S2", "S3", "S4", "M1", "M2", "M3", "M4", "M5", "M6"]
_PARSERS = {
    "dns": DnsParser,
    "firefox.txt": FirefoxParser,
    "security_events.txt": SecurityEventsParser,
}


def _scenario_of_host(host_id: str) -> str:
    return host_id.split("_")[0] if "_" in host_id else host_id


def _parse_one_host(args: tuple[str, str, list[str]]) -> tuple[str, list[Event]]:
    scenario, host_id, paths = args
    events: list[Event] = []
    for p_str in paths:
        p = Path(p_str)
        events.extend(_PARSERS[p.name]().parse_file(p, scenario_id=scenario, host_id=host_id))
    events.sort(key=lambda e: e.timestamp_ns)
    return host_id, events


def _discover_hosts(data_dir: Path) -> list[tuple[str, str, list[str]]]:
    out: list[tuple[str, str, list[str]]] = []
    for sd in sorted(data_dir.iterdir()):
        if not sd.is_dir():
            continue
        scenario = sd.name
        if (sd / "logs").is_dir():
            host_dirs = [(sd / "logs", scenario)]
        else:
            host_dirs = [
                (s / "logs", f"{scenario}_{s.name}")
                for s in sorted(sd.iterdir())
                if s.is_dir() and (s / "logs").is_dir()
            ]
        for logs_dir, host_id in host_dirs:
            paths = [str(logs_dir / fn) for fn in _PARSERS if (logs_dir / fn).is_file()]
            out.append((scenario, host_id, paths))
    return out


def main() -> int:
    with initialize_config_dir(config_dir=str(CONFIG_DIR.resolve()), version_base=None):
        cfg: DictConfig = compose(config_name="atlas")

    data_dir = PROJECT_ROOT / cfg.data_dir
    if not data_dir.is_dir():
        print(f"FATAL: {data_dir} not found", file=sys.stderr)
        return 2

    units = _discover_hosts(data_dir)
    print(f"[fold_stats] parsing {len(units)} (scenario, host) pairs ...")
    workers = max(1, (os.cpu_count() or 8) - 1)

    events_by_host: dict[str, list[Event]] = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_parse_one_host, u) for u in units]
        for fut in as_completed(futs):
            host_id, evs = fut.result()
            events_by_host[host_id] = evs
    print(
        f"[fold_stats] parse done in {time.time()-t0:.1f}s; "
        f"{sum(len(v) for v in events_by_host.values()):,} total events"
    )

    # Bucket by (host, window) once
    window_hours = float(cfg.window.time_window_hours)
    bucketed: dict[HostWindowKey, list[tuple[int, Event]]] = defaultdict(list)
    for host_id, evs in events_by_host.items():
        for ev_idx, ev in enumerate(evs):
            w = window_index(ev.timestamp_ns, window_hours)
            bucketed[HostWindowKey(host_id, w)].append((ev_idx, ev))
    print(
        f"[fold_stats] bucketed: {len(bucketed):,} (host, window) buckets at "
        f"{window_hours}h granularity"
    )

    # Per fold
    max_per_window = int(cfg.sample.max_events_per_window)
    folds: list[dict] = []
    for leave_out in ALL_SCENARIOS:
        train_keys: set[HostWindowKey] = set()
        test_keys: set[HostWindowKey] = set()
        for key in bucketed:
            scen = _scenario_of_host(key.host_id)
            if scen == leave_out:
                test_keys.add(key)
            else:
                train_keys.add(key)

        # Verify no leakage (decision 6)
        assert not (train_keys & test_keys), f"leakage in fold {leave_out}"

        # Sample (decision 9) -- fresh seed per fold for fair stats
        rng = np.random.default_rng(42)
        train_events: list = []
        test_events: list = []
        for key in train_keys:
            train_events.extend(
                sample_target_events(
                    bucketed[key],
                    max_events_per_window=max_per_window,
                    label_loader=benign_only_label_loader,
                    rng=rng,
                )
            )
        for key in test_keys:
            test_events.extend(
                sample_target_events(
                    bucketed[key],
                    max_events_per_window=max_per_window,
                    label_loader=benign_only_label_loader,
                    rng=rng,
                )
            )

        train_attack = sum(1 for _, _, lab in train_events if lab == 1)
        test_attack = sum(1 for _, _, lab in test_events if lab == 1)

        # Per-host breakdown for the test fold
        test_host_breakdown: dict[str, int] = defaultdict(int)
        for k in test_keys:
            test_host_breakdown[k.host_id] += sum(
                1
                for _, _, _ in sample_target_events(
                    bucketed[k],
                    max_events_per_window=max_per_window,
                    label_loader=benign_only_label_loader,
                    rng=np.random.default_rng(42),
                )
            )

        folds.append(
            {
                "leave_out": leave_out,
                "train_n_target_events": len(train_events),
                "test_n_target_events": len(test_events),
                "train_n_host_window_keys": len(train_keys),
                "test_n_host_window_keys": len(test_keys),
                "train_attack_count": train_attack,
                "test_attack_count": test_attack,
                "train_benign_count": len(train_events) - train_attack,
                "test_benign_count": len(test_events) - test_attack,
                "test_host_breakdown": dict(test_host_breakdown),
            }
        )

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "time_window_hours": window_hours,
            "max_events_per_window": max_per_window,
            "subgraph_max_nodes": int(cfg.subgraph.max_nodes),
            "subgraph_khop": int(cfg.subgraph.khop),
            "subgraph_edge_ranking": str(cfg.subgraph.edge_ranking),
            "label_loader": "benign_only_label_loader (Phase 8 stub)",
        },
        "n_total_events": sum(len(v) for v in events_by_host.values()),
        "n_buckets": len(bucketed),
        "folds": folds,
    }
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[fold_stats] summary -> {SUMMARY_OUT}")

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(_render_md(summary), encoding="utf-8")
    print(f"[fold_stats] report -> {REPORT_OUT}")

    print("\n=== Fold sizes summary ===")
    print(f"{'leave-out':<10} {'train_evt':>10} {'test_evt':>10} {'train_buc':>10} {'test_buc':>9}")
    for f in folds:
        print(
            f"{f['leave_out']:<10} {f['train_n_target_events']:>10,} "
            f"{f['test_n_target_events']:>10,} {f['train_n_host_window_keys']:>10,} "
            f"{f['test_n_host_window_keys']:>9,}"
        )
    return 0


def _render_md(summary: dict) -> str:
    out = []
    add = out.append
    add("# Phase 1.6 / Checkpoint 5 Leave-One-Attack-Out Fold Stats\n")
    add(f"Generated at {summary['generated_at_utc']}.\n")
    add(
        f"Config: time_window_hours={summary['config']['time_window_hours']}, "
        f"max_events_per_window={summary['config']['max_events_per_window']}, "
        f"subgraph(max_nodes={summary['config']['subgraph_max_nodes']}, "
        f"khop={summary['config']['subgraph_khop']}, "
        f"edge_ranking={summary['config']['subgraph_edge_ranking']}).\n"
    )
    add(
        f"Label loader: {summary['config']['label_loader']} (Phase 8 plug-in: "
        f"AtlasGroundTruthLabelLoader).\n"
    )
    add(
        f"Total events parsed: {summary['n_total_events']:,}; "
        f"total (host, window) buckets: {summary['n_buckets']:,}.\n"
    )

    add("## Fold sizes\n")
    add(
        "| leave-out | train events | test events | train (h,w) buckets | "
        "test (h,w) buckets | train attack | test attack |"
    )
    add("|---|---:|---:|---:|---:|---:|---:|")
    for f in summary["folds"]:
        add(
            f"| {f['leave_out']} | {f['train_n_target_events']:,} | "
            f"{f['test_n_target_events']:,} | {f['train_n_host_window_keys']:,} | "
            f"{f['test_n_host_window_keys']:,} | {f['train_attack_count']} | "
            f"{f['test_attack_count']} |"
        )
    add("")
    add("Note: attack counts are 0 across all folds because the Phase-8 ground-")
    add("truth label loader has not been wired in yet -- the stub treats every")
    add("event as benign. Phase 8 will replace `benign_only_label_loader` with")
    add("`AtlasGroundTruthLabelLoader` (parsing the attack-entity lists from")
    add("ATLAS paper_experiments/) at which point the columns above will show")
    add("real attack counts.\n")

    add("## Test set per-host breakdown\n")
    for f in summary["folds"]:
        if not f["test_host_breakdown"]:
            continue
        add(f"### Leave-out {f['leave_out']}")
        for h, n in sorted(f["test_host_breakdown"].items()):
            add(f"- {h}: {n:,} events")
        add("")
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(main())
