"""Phase 2 / Checkpoint 6 BERT-encoder sanity check on real ATLAS events.

Per the Phase 2 launch spec:

* take a benign log line, encode with BERT, look at top-5 nearest neighbours
  in the encoded set -- they should be semantically related (same operation
  type or same target file family);
* take a known-noteworthy log line (e.g. an event involving the ATLAS
  attack-process ``payload.exe``), look at its top-5 NN -- they should
  cluster with similar attacker-pattern events.

We intentionally use the ``benign_only_label_loader`` stub (Phase 8 will
plug in real ground-truth) so the "noteworthy" log here is selected by
hand-picked subject heuristic ("payload" in subject) rather than ground
truth. The point at this stage is to verify the encoder + tokenizer +
cleaner end-to-end pipeline produces semantically coherent embeddings,
NOT to evaluate detection accuracy.

Outputs printed to stdout + saved to ``data/bert_sanity_check.json`` for
later reproduction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

from loghetero.data.datamodule import event_to_text
from loghetero.data.parsers.atlas import (
    DnsParser,
    FirefoxParser,
    SecurityEventsParser,
)
from loghetero.models.encoders.bert_text import (
    DEFAULT_BERT_MODEL,
    TrainMode,
    build_bert_text_encoder,
    encode_texts,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = PROJECT_ROOT / "data" / "bert_sanity_check.json"

# We sample a single (scenario, host) pair so the script is fast (~10s on
# the ML stack); S1 is the smallest single-host scenario.
SAMPLE_SCENARIO = "S1"
SAMPLE_HOST = "S1"
SAMPLE_LOGS_DIR = PROJECT_ROOT / "data" / "raw" / "atlas" / SAMPLE_SCENARIO / "logs"


def _collect_sample_events(n_per_log_type: int) -> list:
    """Return the first N events of each log type for the sample host."""
    parsers = [
        ("dns", DnsParser()),
        ("firefox.txt", FirefoxParser()),
        ("security_events.txt", SecurityEventsParser()),
    ]
    out = []
    for fname, parser in parsers:
        path = SAMPLE_LOGS_DIR / fname
        if not path.is_file():
            print(f"  warn: {path} missing, skipping", file=sys.stderr)
            continue
        for count, ev in enumerate(
            parser.parse_file(path, scenario_id=SAMPLE_SCENARIO, host_id=SAMPLE_HOST), start=1
        ):
            out.append(ev)
            if count >= n_per_log_type:
                break
    return out


def _topk_neighbours(
    emb: torch.Tensor, query_idx: int, k: int, exclude: set[int]
) -> list[tuple[int, float]]:
    norm = emb / emb.norm(dim=1, keepdim=True).clamp_min(1e-12)
    sims = norm @ norm[query_idx]
    sims_masked = sims.clone()
    for i in exclude:
        sims_masked[i] = -2.0
    sims_masked[query_idx] = -2.0
    top_vals, top_ids = torch.topk(sims_masked, k)
    return [(int(i), float(v)) for i, v in zip(top_ids.tolist(), top_vals.tolist(), strict=True)]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n-per-log-type", type=int, default=200)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--model", default=DEFAULT_BERT_MODEL)
    p.add_argument("--mode", choices=[m.value for m in TrainMode], default=TrainMode.frozen.value)
    args = p.parse_args()

    if not SAMPLE_LOGS_DIR.is_dir():
        print(
            f"FATAL: {SAMPLE_LOGS_DIR} not present; " "run scripts/download_atlas.sh first.",
            file=sys.stderr,
        )
        return 2

    print(f"[bert_sanity] loading sample events from {SAMPLE_SCENARIO}/{SAMPLE_HOST} ...")
    events = _collect_sample_events(args.n_per_log_type)
    print(f"[bert_sanity] {len(events)} sample events; rendering text ...")
    texts = [event_to_text(ev) for ev in events]

    print(f"[bert_sanity] building {args.model} ({args.mode} mode) ...")
    model, tokenizer = build_bert_text_encoder(args.model, mode=TrainMode(args.mode))
    if torch.cuda.is_available():
        model = model.to("cuda")

    print(f"[bert_sanity] encoding {len(texts)} events ...")
    embs = []
    batch = 32
    for i in range(0, len(texts), batch):
        embs.append(encode_texts(model, tokenizer, texts[i : i + batch]))
    emb = torch.cat(embs, dim=0).cpu()
    print(f"[bert_sanity] encoded shape = {tuple(emb.shape)}")

    # Pick two query indices: one "benign" (first dns query), one
    # "noteworthy" (an event whose text mentions a payload-like or
    # attacker-marked subject).
    benign_query = 0  # first dns query in the sample
    noteworthy_query: int | None = None
    for i, ev in enumerate(events):
        s = (ev.subject + " " + ev.obj).lower()
        if any(needle in s for needle in ("payload", "aalsahee", "0xalsaheel", "evil")):
            noteworthy_query = i
            break

    report: dict = {
        "model": args.model,
        "mode": args.mode,
        "n_events": len(events),
        "top_k": args.top_k,
        "benign_query": None,
        "noteworthy_query": None,
    }

    print(f"\n=== Benign-query nearest neighbours (idx={benign_query}) ===")
    bq = events[benign_query]
    bq_text = texts[benign_query]
    print(
        f"  query event: log_type={bq.log_type} op={bq.operation} "
        f"subject={bq.subject!r} object={bq.obj!r}"
    )
    print(f"  query text:  {bq_text[:120]}")
    nn = _topk_neighbours(emb, benign_query, args.top_k, exclude=set())
    for idx, sim in nn:
        nev = events[idx]
        print(
            f"    [{sim:.3f}] log_type={nev.log_type} op={nev.operation} " f"text={texts[idx][:80]}"
        )
    report["benign_query"] = {
        "query_idx": benign_query,
        "query": {
            "log_type": bq.log_type,
            "operation": str(bq.operation),
            "subject": bq.subject,
            "obj": bq.obj,
        },
        "neighbours": [
            {
                "idx": idx,
                "cos_sim": sim,
                "log_type": events[idx].log_type,
                "operation": str(events[idx].operation),
                "text_snippet": texts[idx][:120],
            }
            for idx, sim in nn
        ],
    }

    if noteworthy_query is not None:
        print(f"\n=== Noteworthy-query nearest neighbours (idx={noteworthy_query}) ===")
        nq = events[noteworthy_query]
        nq_text = texts[noteworthy_query]
        print(
            f"  query event: log_type={nq.log_type} op={nq.operation} "
            f"subject={nq.subject!r} object={nq.obj!r}"
        )
        print(f"  query text:  {nq_text[:120]}")
        nn = _topk_neighbours(emb, noteworthy_query, args.top_k, exclude=set())
        for idx, sim in nn:
            nev = events[idx]
            print(
                f"    [{sim:.3f}] log_type={nev.log_type} op={nev.operation} "
                f"text={texts[idx][:80]}"
            )
        report["noteworthy_query"] = {
            "query_idx": noteworthy_query,
            "query": {
                "log_type": nq.log_type,
                "operation": str(nq.operation),
                "subject": nq.subject,
                "obj": nq.obj,
            },
            "neighbours": [
                {
                    "idx": idx,
                    "cos_sim": sim,
                    "log_type": events[idx].log_type,
                    "operation": str(events[idx].operation),
                    "text_snippet": texts[idx][:120],
                }
                for idx, sim in nn
            ],
        }
    else:
        print("\n  (no noteworthy-query candidate found in the sample slice)")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\n[bert_sanity] full report -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
