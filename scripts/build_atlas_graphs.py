"""Phase 1.4 / Checkpoint 3 driver: build a heterogeneous graph per (scenario, host_id).

For each of the 16 globally-unique (scenario, host_id) pairs in ATLAS, this
script iterates that pair's 3 ATLAS log files (dns / firefox.txt /
security_events.txt), parses them, calls :func:`provenance_graph.build_graph`,
and reports:

* Per-NodeType: node count, isolated count, isolated %, mean degree, max degree.
* Per-(src_type, edge_type, dst_type) triple: edge count.
* Where any NodeType has zero nodes for a given (scenario, host) pair, the
  cell is reported as "0 (none)" so the project owner sees absence explicitly
  rather than inferring from a missing row.

Outputs:

* ``data/atlas_graph_summary.json`` — committed reproducibility anchor (~30 KB).
* ``data/processed/atlas_graph_full_report.md`` — gitignored, full breakdown.

The actual ``HeteroData`` objects are NOT serialised here -- Phase 1.5 builds
windowed sub-graphs that are the more useful artifact. This script's job is
purely the per-(scenario, host) statistical sanity check.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loghetero.data.parsers.atlas import (
    DnsParser,
    FirefoxParser,
    SecurityEventsParser,
)
from loghetero.data.parsers.base import NodeType
from loghetero.data.provenance_graph import build_graph

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw" / "atlas"
SUMMARY_OUT = PROJECT_ROOT / "data" / "atlas_graph_summary.json"
REPORT_OUT = PROJECT_ROOT / "data" / "processed" / "atlas_graph_full_report.md"

_LOG_FILE_PARSERS = {
    "dns": DnsParser,
    "firefox.txt": FirefoxParser,
    "security_events.txt": SecurityEventsParser,
}


@dataclass(frozen=True, slots=True)
class HostUnit:
    scenario_id: str
    host_id: str  # globally unique (S1 or M1_h1 etc.)
    log_paths: tuple[str, ...]


@dataclass(slots=True)
class HostGraphStats:
    unit: HostUnit
    nodes_per_type: dict[str, int] = field(default_factory=dict)
    isolated_per_type: dict[str, int] = field(default_factory=dict)
    mean_degree_per_type: dict[str, float] = field(default_factory=dict)
    max_degree_per_type: dict[str, int] = field(default_factory=dict)
    edges_per_triple: dict[str, int] = field(default_factory=dict)  # key: "src/edge/dst"
    skipped_unknown_op: int = 0
    skipped_disallowed_triple: int = 0
    elapsed_s: float = 0.0


def discover_host_units() -> list[HostUnit]:
    """Build the 16 (scenario, host_id) units mirroring scripts/parse_atlas_all.py."""
    units: list[HostUnit] = []
    for scenario_dir in sorted(DATA_RAW.iterdir()):
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
            log_paths = []
            for fname in _LOG_FILE_PARSERS:
                p = logs_dir / fname
                if p.is_file():
                    log_paths.append(str(p))
            units.append(HostUnit(scenario, host_id, tuple(log_paths)))
    return units


def build_one_host(unit: HostUnit) -> HostGraphStats:
    """Worker: parse all 3 logs for one (scenario, host) pair, build graph, return stats."""
    t0 = time.time()
    events = []
    for path_str in unit.log_paths:
        path = Path(path_str)
        parser_cls = _LOG_FILE_PARSERS[path.name]
        parser = parser_cls()
        events.extend(parser.parse_file(path, scenario_id=unit.scenario_id, host_id=unit.host_id))

    stats_obj = HostGraphStats(unit=unit)
    if not events:
        # No events at all -- record an empty-row stat so the report shows it
        # explicitly instead of dropping the host. (Decision 8 spirit: no
        # silent drops in the data pipeline.)
        for nt in NodeType:
            stats_obj.nodes_per_type[nt.value] = 0
            stats_obj.isolated_per_type[nt.value] = 0
            stats_obj.mean_degree_per_type[nt.value] = 0.0
            stats_obj.max_degree_per_type[nt.value] = 0
        stats_obj.elapsed_s = round(time.time() - t0, 2)
        return stats_obj

    data, build_stats = build_graph(events)

    # Fill in stats for ALL 5 NodeTypes (zeroed if absent), so the final
    # markdown can show absence explicitly per the Checkpoint 3 spec.
    for nt in NodeType:
        n = build_stats.nodes_per_type.get(nt.value, 0)
        stats_obj.nodes_per_type[nt.value] = n
        stats_obj.isolated_per_type[nt.value] = build_stats.isolated_per_type.get(nt.value, 0)
        if n > 0:
            deg = data[nt.value].degree
            stats_obj.mean_degree_per_type[nt.value] = round(float(deg.float().mean().item()), 2)
            stats_obj.max_degree_per_type[nt.value] = int(deg.max().item())
        else:
            stats_obj.mean_degree_per_type[nt.value] = 0.0
            stats_obj.max_degree_per_type[nt.value] = 0

    for (src_t, edge_t, dst_t), n_edges in build_stats.edges_per_triple.items():
        stats_obj.edges_per_triple[f"{src_t}/{edge_t}/{dst_t}"] = n_edges
    stats_obj.skipped_unknown_op = build_stats.skipped_unknown_op
    stats_obj.skipped_disallowed_triple = build_stats.skipped_disallowed_triple
    stats_obj.elapsed_s = round(time.time() - t0, 2)
    return stats_obj


def write_summary_json(units: list[HostGraphStats]) -> None:
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "n_units": len(units),
        "per_unit": [
            {
                "scenario": u.unit.scenario_id,
                "host": u.unit.host_id,
                "nodes_per_type": u.nodes_per_type,
                "isolated_per_type": u.isolated_per_type,
                "mean_degree_per_type": u.mean_degree_per_type,
                "max_degree_per_type": u.max_degree_per_type,
                "edges_per_triple": u.edges_per_triple,
                "skipped_unknown_op": u.skipped_unknown_op,
                "skipped_disallowed_triple": u.skipped_disallowed_triple,
                "elapsed_s": u.elapsed_s,
            }
            for u in units
        ],
    }
    SUMMARY_OUT.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def render_markdown(units: list[HostGraphStats]) -> str:
    out: list[str] = []
    add = out.append
    add("# ATLAS Phase 1.4 Per-(scenario, host) Graph Stats\n")
    add(f"Generated at {datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}.\n")
    add(
        f"{len(units)} (scenario, host) units, all 5 NodeTypes reported per row "
        "(zeros shown explicitly per Checkpoint 3 spec).\n"
    )

    # Nodes per type table
    add("## Nodes per (scenario, host) per NodeType\n")
    add("| scenario | host | process | file | socket | network | user |")
    add("|---|---|---:|---:|---:|---:|---:|")
    for u in units:
        nt = u.nodes_per_type
        cells = [
            f"{nt['process']:,}" if nt["process"] else "0 (none)",
            f"{nt['file']:,}" if nt["file"] else "0 (none)",
            f"{nt['socket']:,}" if nt["socket"] else "0 (none)",
            f"{nt['network']:,}" if nt["network"] else "0 (none)",
            f"{nt['user']:,}" if nt["user"] else "0 (none)",
        ]
        add(f"| {u.unit.scenario_id} | {u.unit.host_id} | " + " | ".join(cells) + " |")
    add("")

    add("## Isolated nodes per (scenario, host) per NodeType (decision 8: kept, not dropped)\n")
    add("| scenario | host | process iso/total (%) | file | socket | network | user |")
    add("|---|---|---|---|---|---|---|")

    def _iso_cell(unit_stats: HostGraphStats, t: str) -> str:
        n = unit_stats.nodes_per_type[t]
        iso = unit_stats.isolated_per_type[t]
        if n == 0:
            return "—"
        return f"{iso}/{n} ({iso/n:.1%})"

    for u in units:
        add(
            f"| {u.unit.scenario_id} | {u.unit.host_id} | "
            + " | ".join(_iso_cell(u, t) for t in ("process", "file", "socket", "network", "user"))
            + " |"
        )
    add("")

    add("## Degree stats per (scenario, host) per NodeType (mean / max)\n")
    add("| scenario | host | NodeType | nodes | mean_deg | max_deg | iso % |")
    add("|---|---|---|---:|---:|---:|---:|")
    for u in units:
        for t in ("process", "file", "socket", "network", "user"):
            n = u.nodes_per_type[t]
            if n == 0:
                continue
            iso = u.isolated_per_type[t]
            add(
                f"| {u.unit.scenario_id} | {u.unit.host_id} | {t} | {n:,} | "
                f"{u.mean_degree_per_type[t]:.2f} | {u.max_degree_per_type[t]:,} | {iso/n:.1%} |"
            )
    add("")

    add("## Edges per (src_type, edge_type, dst_type) triple, summed across hosts\n")
    triple_totals: dict[str, int] = {}
    for u in units:
        for k, v in u.edges_per_triple.items():
            triple_totals[k] = triple_totals.get(k, 0) + v
    add("| triple (src/edge/dst) | edge count |")
    add("|---|---:|")
    for k in sorted(triple_totals, key=lambda x: -triple_totals[x]):
        add(f"| {k} | {triple_totals[k]:,} |")
    add("")

    add("## Skip counters\n")
    total_unk = sum(u.skipped_unknown_op for u in units)
    total_dis = sum(u.skipped_disallowed_triple for u in units)
    add(f"- Events with unknown operation (mapped to EdgeType.UNKNOWN, skipped): {total_unk:,}")
    add(f"- Events with disallowed (src, edge, dst) triple (skipped): {total_dis:,}")

    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 8) - 1))
    args = parser.parse_args()

    if not DATA_RAW.is_dir():
        print(f"FATAL: {DATA_RAW} not found.", file=sys.stderr)
        return 2

    units = discover_host_units()
    print(
        f"[build_atlas_graphs] discovered {len(units)} (scenario, host) units; "
        f"{args.workers} workers"
    )
    if len(units) != 16:
        print(f"WARN expected 16 units, got {len(units)}", file=sys.stderr)

    results: list[HostGraphStats] = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(build_one_host, u) for u in units]
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            print(
                f"  done {r.unit.scenario_id}/{r.unit.host_id}: "
                f"nodes={sum(r.nodes_per_type.values()):,} "
                f"edges={sum(r.edges_per_triple.values()):,} "
                f"in {r.elapsed_s}s",
                flush=True,
            )
    print(f"[build_atlas_graphs] all {len(results)} units done in {time.time()-t0:.1f}s")
    results.sort(key=lambda x: (x.unit.scenario_id, x.unit.host_id))

    write_summary_json(results)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(render_markdown(results), encoding="utf-8")
    print(f"[build_atlas_graphs] summary -> {SUMMARY_OUT}")
    print(f"[build_atlas_graphs] full report -> {REPORT_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
