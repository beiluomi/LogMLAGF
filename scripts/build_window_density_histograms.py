"""Phase 1.5 / Checkpoint 4 driver: per-(scenario, host) events/hour density.

Produces the central artifact for deciding the final ``time_window_hours``
in decision 6:

* ``data/processed/window_density_per_host.png`` -- 4x4 grid of histograms,
  one panel per (scenario, host_id), log-x events/window axis. Each panel
  is annotated with mean / median / p99 / max / min-nonzero events/window.
* ``data/processed/window_density_global.png`` -- single panel that overlays
  all 16 host distributions on the same axes (CDF view). The shape of this
  plot answers "is there a single global granularity that fits every host
  reasonably, or does the bimodality between h1 and h2 force a tiered
  decision-6 protocol?"
* ``data/atlas_window_density_summary.json`` -- committed reproducibility
  anchor; per-host stats at the four granularities listed in
  ``configs/data/atlas.yaml::granularity_sweep_hours``.
* ``data/processed/window_density_decision_table.md`` -- the table the
  project owner reads to pick the final granularity.

All knobs come from the Hydra config; nothing here hardcodes "1 hour" or
"4 granularities".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hydra import compose, initialize_config_dir
from omegaconf import DictConfig

from loghetero.data.parsers.atlas import (
    DnsParser,
    FirefoxParser,
    SecurityEventsParser,
)
from loghetero.data.window_splitter import bucket_counts, window_density_stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs" / "data"
SUMMARY_OUT = PROJECT_ROOT / "data" / "atlas_window_density_summary.json"
PER_HOST_PNG = PROJECT_ROOT / "data" / "processed" / "window_density_per_host.png"
GLOBAL_PNG = PROJECT_ROOT / "data" / "processed" / "window_density_global.png"
DECISION_TABLE = PROJECT_ROOT / "data" / "processed" / "window_density_decision_table.md"

_LOG_FILE_PARSERS = {
    "dns": DnsParser,
    "firefox.txt": FirefoxParser,
    "security_events.txt": SecurityEventsParser,
}


@dataclass(frozen=True, slots=True)
class HostUnit:
    scenario_id: str
    host_id: str
    log_paths: tuple[str, ...]


@dataclass(slots=True)
class HostTimestamps:
    scenario_id: str
    host_id: str
    timestamps_ns: list[int]
    elapsed_s: float


def discover_host_units(data_dir: Path) -> list[HostUnit]:
    units: list[HostUnit] = []
    for scenario_dir in sorted(data_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        scenario = scenario_dir.name
        if (scenario_dir / "logs").is_dir():
            host_dirs = [(scenario_dir / "logs", scenario)]
        else:
            host_dirs = []
            for sub in sorted(scenario_dir.iterdir()):
                if sub.is_dir() and (sub / "logs").is_dir():
                    host_dirs.append((sub / "logs", f"{scenario}_{sub.name}"))
        for logs_dir, host_id in host_dirs:
            log_paths = tuple(
                str(logs_dir / fname) for fname in _LOG_FILE_PARSERS if (logs_dir / fname).is_file()
            )
            units.append(HostUnit(scenario, host_id, log_paths))
    return units


def collect_timestamps(unit: HostUnit) -> HostTimestamps:
    """Worker: parse all 3 logs for one host and return sorted timestamps."""
    t0 = time.time()
    timestamps: list[int] = []
    for path_str in unit.log_paths:
        path = Path(path_str)
        parser = _LOG_FILE_PARSERS[path.name]()
        for ev in parser.parse_file(path, scenario_id=unit.scenario_id, host_id=unit.host_id):
            timestamps.append(ev.timestamp_ns)
    timestamps.sort()
    return HostTimestamps(unit.scenario_id, unit.host_id, timestamps, time.time() - t0)


def load_config(config_dir: Path = CONFIG_DIR) -> DictConfig:
    """Load Hydra config; absolute path required by initialize_config_dir."""
    with initialize_config_dir(config_dir=str(config_dir.resolve()), version_base=None):
        cfg = compose(config_name="atlas")
    return cfg


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_per_host_grid(per_host: list[HostTimestamps], window_hours: float, out_path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(4, 4, figsize=(20, 14), sharex=False, sharey=False)
    axes = axes.flatten()
    for ax, ht in zip(
        axes, sorted(per_host, key=lambda x: (x.scenario_id, x.host_id)), strict=False
    ):
        counts = list(bucket_counts(ht.timestamps_ns, window_hours).values())
        if not counts:
            ax.text(0.5, 0.5, "(empty)", transform=ax.transAxes, ha="center")
            ax.set_title(f"{ht.scenario_id} / {ht.host_id}")
            continue
        # Log-x histogram of events-per-window.
        max_c = max(counts)
        log_max = max(1, int(np.ceil(np.log10(max_c)))) if max_c > 0 else 1
        bins = np.logspace(0, log_max, 24)
        ax.hist(counts, bins=bins, color="tab:blue", edgecolor="white", linewidth=0.3)
        ax.set_xscale("log")
        s = window_density_stats(ht.timestamps_ns, window_hours)
        title = f"{ht.scenario_id} / {ht.host_id}  ({int(s['n_nonempty'])} windows)"
        ax.set_title(title, fontsize=10)
        annotation = (
            f"mean={s['mean']:.1f}\n"
            f"median={s['median']:.0f}\n"
            f"p99={s['p99']:.0f}\n"
            f"max={int(s['max'])}\n"
            f"min>0={int(s['min_nonzero'])}"
        )
        ax.text(
            0.97,
            0.97,
            annotation,
            transform=ax.transAxes,
            fontsize=8,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
        )
        ax.set_xlabel("events / window")
        ax.set_ylabel("# windows")

    fig.suptitle(
        f"ATLAS events-per-{window_hours:g}h-window distribution, per (scenario, host)",
        fontsize=14,
        y=1.00,
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_global_overlay(
    per_host: list[HostTimestamps], window_hours: float, out_path: Path
) -> None:
    """The 17th plot: overlay all 16 host CDFs on a single axes.

    CDF orientation: x = events/window, y = fraction of windows with at most
    that many events. A "globally reasonable" granularity is one where all
    16 CDFs land in a similar x-range; bimodal separation between h1 and h2
    motivates a tiered decision-6 protocol.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(1, 1, figsize=(11, 7))
    cmap = plt.get_cmap("tab20")
    for i, ht in enumerate(sorted(per_host, key=lambda x: (x.scenario_id, x.host_id))):
        counts = sorted(bucket_counts(ht.timestamps_ns, window_hours).values())
        if not counts:
            continue
        n = len(counts)
        cdf_y = np.arange(1, n + 1) / n
        # Distinguish h1 / h2 / single-host with line style; scenario via colour.
        host = ht.host_id
        if host.endswith("_h1"):
            ls, lw = "-", 1.6
        elif host.endswith("_h2"):
            ls, lw = "--", 1.6
        else:
            ls, lw = "-.", 1.2
        ax.plot(
            counts,
            cdf_y,
            color=cmap(i % 20),
            linestyle=ls,
            linewidth=lw,
            label=f"{ht.scenario_id} / {ht.host_id}",
        )
    ax.set_xscale("log")
    ax.set_xlabel(f"events per {window_hours:g}h-window  (log scale)")
    ax.set_ylabel("CDF: fraction of windows ≤ x events")
    ax.set_title(
        "Global overlay -- 16 (scenario, host) CDFs.\n"
        "Tightly bunched curves => a single global window granularity is fine; "
        "bimodal separation (e.g. h1 right, h2 left) => decision-6 may need a tiered protocol.",
        fontsize=11,
    )
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=7, ncol=2, loc="lower right")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Decision table + JSON summary
# ---------------------------------------------------------------------------


def build_summary(per_host: list[HostTimestamps], granularities: Iterable[float]) -> dict:
    granularities = list(granularities)
    return {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "granularities_hours": granularities,
        "per_host": [
            {
                "scenario": ht.scenario_id,
                "host": ht.host_id,
                "n_events": len(ht.timestamps_ns),
                "stats": {
                    f"{g}h": window_density_stats(ht.timestamps_ns, g) for g in granularities
                },
            }
            for ht in sorted(per_host, key=lambda x: (x.scenario_id, x.host_id))
        ],
    }


def render_decision_table(summary: dict) -> str:
    granularities = summary["granularities_hours"]
    lines: list[str] = []
    add = lines.append
    add("# Phase 1.5 / Checkpoint 4 — Time-Window Granularity Decision Table\n")
    add(f"Generated at {summary['generated_at_utc']}.\n")
    add("Granularity sweep: " + " / ".join(f"{g}h" for g in granularities) + ".\n")

    add("## Per (scenario, host) at each granularity: n_nonempty / mean events/window\n")
    header = "| scenario | host | n_events |"
    sep = "|---|---|---:|"
    for g in granularities:
        header += f" {g}h n_w | {g}h mean |"
        sep += "---:|---:|"
    add(header)
    add(sep)
    for row in summary["per_host"]:
        cells = [str(row["scenario"]), str(row["host"]), f"{row['n_events']:,}"]
        for g in granularities:
            s = row["stats"][f"{g}h"]
            cells.append(f"{int(s['n_nonempty']):,}")
            cells.append(f"{s['mean']:.1f}")
        add("| " + " | ".join(cells) + " |")
    add("")

    add("## How to read this\n")
    add(
        "- The 'sweet spot' for ``time_window_hours`` is a granularity at which "
        "every (scenario, host) row has a sane window count (>= ~5 windows so "
        "the leave-one-out split has signal) AND mean events/window in a "
        "trainable range (rough heuristic: ~10-10000)."
    )
    add(
        "- If no single granularity satisfies all 16 rows simultaneously, "
        "inspect the global-overlay PNG (`window_density_global.png`); a "
        "bimodal CDF separation between h1 and h2 motivates revising "
        "decision-6 to a tiered protocol (e.g. h1 uses X hours, h2 uses Y)."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 8) - 1))
    args = p.parse_args()

    cfg = load_config()
    print(
        f"[window_density] config: window_hours={cfg.window.time_window_hours}, "
        f"sweep={list(cfg.granularity_sweep_hours)}, "
        f"subgraph(max_nodes={cfg.subgraph.max_nodes}, khop={cfg.subgraph.khop}, "
        f"ranking={cfg.subgraph.edge_ranking})"
    )

    data_dir = PROJECT_ROOT / cfg.data_dir
    if not data_dir.is_dir():
        print(f"FATAL: {data_dir} not found.", file=sys.stderr)
        return 2
    units = discover_host_units(data_dir)
    print(f"[window_density] {len(units)} (scenario, host) units, {args.workers} workers")

    per_host: list[HostTimestamps] = []
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(collect_timestamps, u) for u in units]
        for fut in as_completed(futs):
            ht = fut.result()
            per_host.append(ht)
            print(
                f"  done {ht.scenario_id}/{ht.host_id}: {len(ht.timestamps_ns):,} events "
                f"in {ht.elapsed_s:.1f}s",
                flush=True,
            )
    print(f"[window_density] all {len(per_host)} units done in {time.time()-t_start:.1f}s")

    summary = build_summary(per_host, cfg.granularity_sweep_hours)
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[window_density] summary -> {SUMMARY_OUT}")

    DECISION_TABLE.parent.mkdir(parents=True, exist_ok=True)
    DECISION_TABLE.write_text(render_decision_table(summary), encoding="utf-8")
    print(f"[window_density] decision table -> {DECISION_TABLE}")

    plot_per_host_grid(per_host, cfg.window.time_window_hours, PER_HOST_PNG)
    print(f"[window_density] per-host grid -> {PER_HOST_PNG}")
    plot_global_overlay(per_host, cfg.window.time_window_hours, GLOBAL_PNG)
    print(f"[window_density] global overlay -> {GLOBAL_PNG}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
