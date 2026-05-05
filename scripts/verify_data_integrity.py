"""Verify ATLAS dataset integrity and emit data/atlas_manifest.json.

This script walks data/raw/atlas/ for all 10 scenarios (S1-S4, M1-M6); for every
file it records bytes, newline count, and SHA-256. It then either:

* writes the initial deterministic manifest JSON (data/atlas_manifest.json) when
  none exists -- that file becomes the reproducibility anchor and is committed
  to git so reviewers see the exact dataset, or
* compares against the existing manifest, fail-fasts on any divergence, and
  appends details to docs/known_issues.md under "## 数据完整性偏差".

Per design_decisions.md decision 1 / known_issues.md "ATLAS 数据校验清单":
the upstream README does not publish per-file checksums, so we fall back to
byte + line counts. SHA-256 is computed locally and recorded too -- it costs
nothing to record and lets future re-downloads catch silent corruption.

WORKFLOW WHEN YOU NEED TO MODIFY RAW DATA (e.g. patch a known format bug)
========================================================================
sha256 mismatch will fail-fast on next re-run; the only sanctioned path
to update the manifest is:

    1) make refresh-manifest      # re-generate data/atlas_manifest.json
    2) git diff data/atlas_manifest.json   # confirm exactly what changed
    3) git commit data/atlas_manifest.json with a message naming the
       reason for the underlying data change
    4) record the data modification in docs/known_issues.md

Do NOT delete data/atlas_manifest.json and silently re-run this script:
that loses the audit trail. Use `make refresh-manifest` so the intent is
explicit in the shell history."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_SCENARIOS: tuple[str, ...] = ("S1", "S2", "S3", "S4", "M1", "M2", "M3", "M4", "M5", "M6")
DEFAULT_DATA_DIR = Path("data/raw/atlas")
DEFAULT_MANIFEST = Path("data/atlas_manifest.json")
KNOWN_ISSUES = Path("docs/known_issues.md")
DEVIATION_HEADER = "## 数据完整性偏差"


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def line_count_of(path: Path, chunk: int = 1 << 20) -> int:
    """Count newline bytes without loading the whole file into memory."""
    count = 0
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            count += block.count(b"\n")
    return count


def collect_scenario(scenario_dir: Path) -> dict:
    files: list[dict] = []
    for path in sorted(scenario_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(scenario_dir).as_posix()
        files.append(
            {
                "path": rel,
                "bytes": path.stat().st_size,
                "lines": line_count_of(path),
                "sha256": sha256_of(path),
            }
        )
    return {"file_count": len(files), "files": files}


def build_manifest(data_dir: Path) -> dict:
    scenarios: dict[str, dict] = {}
    missing: list[str] = []
    for s in EXPECTED_SCENARIOS:
        sdir = data_dir / s
        if not sdir.is_dir():
            missing.append(s)
            continue
        scenarios[s] = collect_scenario(sdir)
    return {
        "dataset": "ATLAS",
        "source": "https://github.com/purseclab/ATLAS",
        "citation": "Alsaheel et al., USENIX Security '21",
        "expected_scenarios": list(EXPECTED_SCENARIOS),
        "missing_scenarios": missing,
        "checksum_protocol": (
            "sha256 + bytes + lines (README publishes no sha256, so sha256 is locally computed "
            "and serves as a downstream reproducibility anchor; primary equality check is "
            "bytes + lines per docs/known_issues.md)"
        ),
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "scenarios": scenarios,
    }


def diff_manifests(old: dict, new: dict) -> list[str]:
    diffs: list[str] = []
    old_sc = old.get("scenarios", {})
    new_sc = new.get("scenarios", {})
    for s in sorted(set(old_sc) | set(new_sc)):
        if s not in old_sc:
            diffs.append(f"- scenario {s}: new (not in previous manifest)")
            continue
        if s not in new_sc:
            diffs.append(f"- scenario {s}: missing now (was {old_sc[s]['file_count']} files)")
            continue
        old_files = {f["path"]: f for f in old_sc[s]["files"]}
        new_files = {f["path"]: f for f in new_sc[s]["files"]}
        for p in sorted(set(old_files) | set(new_files)):
            if p not in old_files:
                diffs.append(f"- {s}/{p}: new file (bytes={new_files[p]['bytes']})")
            elif p not in new_files:
                diffs.append(f"- {s}/{p}: deleted (was bytes={old_files[p]['bytes']})")
            else:
                o, n = old_files[p], new_files[p]
                for k in ("bytes", "lines", "sha256"):
                    if o[k] != n[k]:
                        diffs.append(f"- {s}/{p}: {k} {o[k]} -> {n[k]}")
    return diffs


def append_deviation_section(diffs: list[str]) -> None:
    if not diffs:
        return
    timestamp = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    body_lines = [f"\n### {timestamp} ATLAS manifest mismatch\n", "\n".join(diffs), "\n"]
    body = "".join(body_lines)
    text = KNOWN_ISSUES.read_text(encoding="utf-8")
    if DEVIATION_HEADER in text:
        KNOWN_ISSUES.write_text(text + body, encoding="utf-8")
    else:
        KNOWN_ISSUES.write_text(text + "\n" + DEVIATION_HEADER + "\n" + body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(
            f"[verify] FATAL: {args.data_dir} not found. Run scripts/download_atlas.sh first.",
            file=sys.stderr,
        )
        return 2

    new_manifest = build_manifest(args.data_dir)

    if args.manifest.exists():
        old_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        diffs = diff_manifests(old_manifest, new_manifest)
        if diffs:
            append_deviation_section(diffs)
            print(
                f"[verify] FAIL: manifest divergence detected ({len(diffs)} diffs); "
                f"details appended to {KNOWN_ISSUES}.",
                file=sys.stderr,
            )
            for d in diffs[:20]:
                print(f"  {d}", file=sys.stderr)
            if len(diffs) > 20:
                print(f"  ... and {len(diffs) - 20} more", file=sys.stderr)
            return 1
        print(f"[verify] OK: current state matches {args.manifest}.")
        return 0

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(new_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[verify] Wrote initial manifest to {args.manifest}.")
    print(
        f"[verify] {len(new_manifest['scenarios'])} scenarios present; "
        f"{len(new_manifest['missing_scenarios'])} missing."
    )
    if new_manifest["missing_scenarios"]:
        print(f"[verify] WARN missing: {new_manifest['missing_scenarios']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
