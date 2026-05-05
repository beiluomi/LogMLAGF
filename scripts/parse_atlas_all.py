"""Phase 1.2 / Checkpoint 2 driver: parse all 10 ATLAS scenarios end-to-end.

Walks ``data/raw/atlas/`` (all 48 raw files for S1-S4 + M1-M6) using the three
concrete ATLAS parsers and produces:

* ``data/atlas_parse_summary.json`` — committed to git as a reproducibility
  anchor for the parse stats. Contains per-(scenario, host, log_type)
  counters and EventID histograms but NOT raw failure samples (those can
  contain payloads we don't want in git).
* ``data/processed/atlas_parse_full_report.md`` — gitignored, contains
  failure-sample dumps and event sample dumps for human inspection.

The two outputs are designed so the committed summary is small and stable;
the full report (samples) is reproduced from data on demand and never enters
git.

Multi-process: per-(scenario, host, log_type) work units fan out across a
ProcessPoolExecutor; the largest single file (S2/firefox.txt = 789 MB) drives
the wall-clock floor.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loghetero.data.parsers.atlas import (
    DnsParser,
    FirefoxParser,
    SecurityEventsParser,
)
from loghetero.data.parsers.base import Event, ParseStats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw" / "atlas"
SUMMARY_OUT = PROJECT_ROOT / "data" / "atlas_parse_summary.json"
REPORT_OUT = PROJECT_ROOT / "data" / "processed" / "atlas_parse_full_report.md"

SAMPLES_PER_LOGTYPE = 5
FAILURE_RATE_THRESHOLD = 0.01  # cells above this get failure-sample dumps in the markdown report


# ---------------------------------------------------------------------------
# Work-unit / result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkUnit:
    path: str
    scenario_id: str
    host_id: str
    log_type: str  # "atlas.dns" | "atlas.firefox" | "atlas.security_events"


@dataclass(slots=True)
class WorkResult:
    unit: WorkUnit
    success: int = 0
    failed: int = 0
    skipped: int = 0
    failure_samples: list[dict] = field(default_factory=list)  # capped
    sample_events: list[dict] = field(default_factory=list)  # first N events as dicts
    eventid_counts: dict[str, int] = field(default_factory=dict)  # security_events only
    elapsed_s: float = 0.0


# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

_PARSERS = {
    "atlas.dns": DnsParser,
    "atlas.firefox": FirefoxParser,
    "atlas.security_events": SecurityEventsParser,
}

_FILE_TO_LOGTYPE = {
    "dns": "atlas.dns",
    "firefox.txt": "atlas.firefox",
    "security_events.txt": "atlas.security_events",
}


def discover_work() -> list[WorkUnit]:
    """Build the 48 (path, scenario, host, log_type) work units.

    host_id is *globally unique* (not just unique within a scenario):
    single-host scenarios use ``host_id == scenario`` (e.g. ``"S1"``); multi-
    host scenarios use ``f"{scenario}_{subdir}"`` (e.g. ``"M1_h1"``). This
    matches decision 6's wording, which keys the leave-one-attack-out split
    on ``(host_id, time_window)`` directly.
    """
    units: list[WorkUnit] = []
    for scenario_dir in sorted(DATA_RAW.iterdir()):
        if not scenario_dir.is_dir():
            continue
        scenario = scenario_dir.name
        # Single-host scenarios have logs/ at top level; multi-host have
        # h1/, h2/, ... subdirs. We discriminate by looking for logs/ first.
        if (scenario_dir / "logs").is_dir():
            host_dirs = [(scenario_dir / "logs", scenario)]
        else:
            host_dirs = []
            for sub in sorted(scenario_dir.iterdir()):
                if sub.is_dir() and (sub / "logs").is_dir():
                    host_dirs.append((sub / "logs", f"{scenario}_{sub.name}"))
        for logs_dir, host_id in host_dirs:
            for f in sorted(logs_dir.iterdir()):
                lt = _FILE_TO_LOGTYPE.get(f.name)
                if lt is None:
                    continue
                units.append(
                    WorkUnit(
                        path=str(f),
                        scenario_id=scenario,
                        host_id=host_id,
                        log_type=lt,
                    )
                )
    return units


# ---------------------------------------------------------------------------
# Worker (must be picklable: defined at module scope, no closures)
# ---------------------------------------------------------------------------


def _event_to_dict(ev: Event) -> dict:
    d = dataclasses.asdict(ev)
    # NodeType is (str, Enum); asdict gives plain string. attributes already dict.
    return d


def parse_one_file(unit: WorkUnit) -> WorkResult:
    parser_cls = _PARSERS[unit.log_type]
    parser = parser_cls()
    stats = ParseStats()
    samples: list[dict] = []
    eventid_counter: Counter[str] = Counter()
    is_sec = unit.log_type == "atlas.security_events"

    t0 = time.time()
    for ev in parser.parse_file(
        Path(unit.path),
        scenario_id=unit.scenario_id,
        host_id=unit.host_id,
        stats=stats,
    ):
        if len(samples) < SAMPLES_PER_LOGTYPE:
            samples.append(_event_to_dict(ev))
        if is_sec:
            eid = ev.attributes.get("event_id")
            if eid:
                eventid_counter[eid] += 1
    elapsed = time.time() - t0

    return WorkResult(
        unit=unit,
        success=stats.success,
        failed=stats.failed,
        skipped=stats.skipped,
        failure_samples=[
            {"line_num": fs.line_num, "raw": fs.raw, "error": fs.error}
            for fs in stats.failure_samples
        ],
        sample_events=samples,
        eventid_counts=dict(eventid_counter),
        elapsed_s=elapsed,
    )


# ---------------------------------------------------------------------------
# Aggregation + reporting
# ---------------------------------------------------------------------------


def aggregate(results: list[WorkResult]) -> dict:
    # Per-(scenario, host, log_type) — most granular cell
    per_unit: list[dict] = []
    # Per-(scenario, log_type) — collapse host
    per_scenario_logtype: dict[tuple[str, str], dict[str, int]] = {}
    # Global per-log_type sample bag (first N events)
    samples_by_lt: dict[str, list[dict]] = {lt: [] for lt in _PARSERS}
    # Per-log_type aggregate
    per_logtype: dict[str, dict[str, int]] = {
        lt: {"success": 0, "failed": 0, "skipped": 0} for lt in _PARSERS
    }
    # EventID histograms keyed by (scenario, host) for security_events
    sec_hist: dict[str, dict[str, int]] = {}

    for r in sorted(results, key=lambda x: (x.unit.scenario_id, x.unit.host_id, x.unit.log_type)):
        u = r.unit
        denom = r.success + r.failed
        rate = r.failed / denom if denom else 0.0
        per_unit.append(
            {
                "scenario": u.scenario_id,
                "host": u.host_id,
                "log_type": u.log_type,
                "success": r.success,
                "failed": r.failed,
                "skipped": r.skipped,
                "failure_rate": rate,
                "elapsed_s": round(r.elapsed_s, 2),
            }
        )
        key = (u.scenario_id, u.log_type)
        cell = per_scenario_logtype.setdefault(key, {"success": 0, "failed": 0, "skipped": 0})
        for k in ("success", "failed", "skipped"):
            cell[k] += getattr(r, k)
            per_logtype[u.log_type][k] += getattr(r, k)
        if len(samples_by_lt[u.log_type]) < SAMPLES_PER_LOGTYPE and r.sample_events:
            need = SAMPLES_PER_LOGTYPE - len(samples_by_lt[u.log_type])
            samples_by_lt[u.log_type].extend(r.sample_events[:need])
        if u.log_type == "atlas.security_events" and r.eventid_counts:
            sec_hist[f"{u.scenario_id}/{u.host_id}"] = r.eventid_counts

    # Materialise the matrix view as a list with failure rate
    matrix: list[dict] = []
    for (sc, lt), cell in sorted(per_scenario_logtype.items()):
        denom = cell["success"] + cell["failed"]
        matrix.append(
            {
                "scenario": sc,
                "log_type": lt,
                "success": cell["success"],
                "failed": cell["failed"],
                "skipped": cell["skipped"],
                "failure_rate": cell["failed"] / denom if denom else 0.0,
            }
        )

    overall: dict[str, int] = {"success": 0, "failed": 0, "skipped": 0}
    for r in results:
        overall["success"] += r.success
        overall["failed"] += r.failed
        overall["skipped"] += r.skipped
    overall_denom = overall["success"] + overall["failed"]
    overall_rate = overall["failed"] / overall_denom if overall_denom else 0.0

    return {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "overall": {**overall, "failure_rate": overall_rate},
        "per_log_type": {
            lt: {
                **per_logtype[lt],
                "failure_rate": (
                    per_logtype[lt]["failed"]
                    / max(1, per_logtype[lt]["success"] + per_logtype[lt]["failed"])
                ),
            }
            for lt in _PARSERS
        },
        "per_scenario_log_type": matrix,
        "per_scenario_host_log_type": per_unit,
        "samples_by_log_type": samples_by_lt,
        "security_events_eventid_histograms": sec_hist,
    }


def write_summary_json(summary: dict) -> None:
    # Keep the committed JSON small: drop sample_events and failure_samples,
    # only keep stats + EventID histograms.
    redacted = {k: v for k, v in summary.items() if k != "samples_by_log_type"}
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(
        json.dumps(redacted, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def render_markdown_report(summary: dict, results: list[WorkResult]) -> str:
    lines: list[str] = []
    out = lines.append  # local alias for brevity in the long render below
    out("# ATLAS Phase 1.2 Parse Report (full)\n")
    out(f"Generated at {summary['generated_at_utc']}.\n")

    overall = summary["overall"]
    out("## Overall\n")
    out(
        f"- success: {overall['success']:,}\n"
        f"- failed:  {overall['failed']:,}\n"
        f"- skipped: {overall['skipped']:,}\n"
        f"- failure_rate: {overall['failure_rate']:.4%}\n"
    )

    out("## Per log_type\n")
    out("| log_type | success | failed | skipped | failure_rate |")
    out("|---|---:|---:|---:|---:|")
    for lt, cell in summary["per_log_type"].items():
        out(
            f"| {lt} | {cell['success']:,} | {cell['failed']:,} | "
            f"{cell['skipped']:,} | {cell['failure_rate']:.4%} |"
        )
    out("")

    out("## Per (scenario, log_type)\n")
    out("| scenario | log_type | success | failed | skipped | failure_rate |")
    out("|---|---|---:|---:|---:|---:|")
    for row in summary["per_scenario_log_type"]:
        out(
            f"| {row['scenario']} | {row['log_type']} | "
            f"{row['success']:,} | {row['failed']:,} | {row['skipped']:,} | "
            f"{row['failure_rate']:.4%} |"
        )
    out("")

    out("## Per (scenario, host, log_type)\n")
    out("| scenario | host | log_type | success | failed | skipped | failure_rate | elapsed_s |")
    out("|---|---|---|---:|---:|---:|---:|---:|")
    for row in summary["per_scenario_host_log_type"]:
        out(
            f"| {row['scenario']} | {row['host']} | {row['log_type']} | "
            f"{row['success']:,} | {row['failed']:,} | {row['skipped']:,} | "
            f"{row['failure_rate']:.4%} | {row['elapsed_s']} |"
        )
    out("")

    out("## Sample events (first 5 per log_type)\n")
    for lt, samples in summary["samples_by_log_type"].items():
        out(f"### {lt}\n")
        for ev in samples:
            out("```json")
            out(json.dumps(ev, indent=2, ensure_ascii=False, default=str))
            out("```")
        out("")

    out("## EventID histograms (security_events, top-20 per host)\n")
    for key in sorted(summary["security_events_eventid_histograms"]):
        hist = summary["security_events_eventid_histograms"][key]
        top = sorted(hist.items(), key=lambda kv: -kv[1])[:20]
        out(f"### {key}")
        out("| EventID | count |")
        out("|---|---:|")
        for eid, c in top:
            out(f"| {eid} | {c:,} |")
        out("")

    out("## Failure samples for cells with failure_rate > 1%\n")
    any_hot = False
    for r in sorted(results, key=lambda x: (x.unit.scenario_id, x.unit.host_id, x.unit.log_type)):
        denom = r.success + r.failed
        rate = r.failed / denom if denom else 0.0
        if rate > FAILURE_RATE_THRESHOLD and r.failure_samples:
            any_hot = True
            u = r.unit
            out(
                f"### {u.scenario_id}/{u.host_id}/{u.log_type} — failure_rate={rate:.4%} ({r.failed} failed / {denom})\n"
            )
            for fs in r.failure_samples[:10]:
                out(f"- line {fs['line_num']}: `{fs['error']}`")
                out("  ```")
                out(f"  {fs['raw']}")
                out("  ```")
            out("")
    if not any_hot:
        out("_None — no (scenario, host, log_type) cell exceeded the 1% failure-rate threshold._\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 8) - 1),
        help="ProcessPoolExecutor max_workers (default: CPU-1).",
    )
    args = parser.parse_args()

    if not DATA_RAW.is_dir():
        print(f"FATAL: {DATA_RAW} not found; run scripts/download_atlas.sh first.", file=sys.stderr)
        return 2

    units = discover_work()
    print(f"[parse_atlas_all] discovered {len(units)} work units; {args.workers} workers")
    print(
        "[parse_atlas_all] expected: 4 single-host scenarios * 3 logs = 12, "
        "plus 6 multi-host * 6 logs = 36, total 48"
    )
    if len(units) != 48:
        print(f"[parse_atlas_all] WARN expected 48, got {len(units)}", file=sys.stderr)

    results: list[WorkResult] = []
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(parse_one_file, u) for u in units]
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            u = r.unit
            print(
                f"  done {u.scenario_id}/{u.host_id}/{u.log_type}: "
                f"success={r.success:,} failed={r.failed:,} skipped={r.skipped:,} "
                f"in {r.elapsed_s:.1f}s",
                flush=True,
            )
    total_elapsed = time.time() - t_start
    print(f"[parse_atlas_all] all {len(results)} units done in {total_elapsed:.1f}s")

    summary = aggregate(results)
    write_summary_json(summary)
    print(f"[parse_atlas_all] summary -> {SUMMARY_OUT}")

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(render_markdown_report(summary, results), encoding="utf-8")
    print(f"[parse_atlas_all] full report -> {REPORT_OUT}")

    print("\n=== Quick summary ===")
    print(
        f"overall: success={summary['overall']['success']:,} "
        f"failed={summary['overall']['failed']:,} "
        f"skipped={summary['overall']['skipped']:,} "
        f"rate={summary['overall']['failure_rate']:.4%}"
    )
    for lt, cell in summary["per_log_type"].items():
        print(
            f"  {lt}: success={cell['success']:,} failed={cell['failed']:,} "
            f"skipped={cell['skipped']:,} rate={cell['failure_rate']:.4%}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
