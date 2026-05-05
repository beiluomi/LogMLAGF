"""Tokenizer nearest-neighbor sanity check (Phase 1.3 / Checkpoint 3 deliverable).

Loads bert-base-uncased, applies the LogHetero tokenizer extension (156
domain special tokens with synonym-mean init), then for a curated list of
representative special tokens reports the top-K nearest BERT tokens by
cosine similarity in the embedding space.

The Checkpoint 3 launch spec asks for 5 new tokens' top-5 nearest neighbours.
A "good" init looks like ``[IP]`` having neighbours ``address`` / ``network``
/ ``host`` / ``port`` (semantically related); a "failed" init looks like
common stop words (``the`` / ``a`` / ``,``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loghetero.data.tokenizer import (
    SPECIAL_TOKENS,
    build_tokenizer,
    init_special_token_embeddings,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = PROJECT_ROOT / "data" / "tokenizer_nn_sanity.json"

# 10 representative special tokens covering different categories.
SAMPLE_TOKENS_FOR_REPORT = [
    "[IP]",
    "[HASH_SHA256]",
    "[URL_HTTPS]",
    "[PATH_WIN_SYS32]",
    "[PATH_REGISTRY_HKLM]",
    "[PROC_POWERSHELL]",
    "[PROC_LSASS]",
    "[NET_DNS]",
    "[EVENT_PROC_CREATE]",
    "[OP_LOGON]",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--model", default="bert-base-uncased")
    args = parser.parse_args()

    print(f"[tokenizer_nn_sanity] loading {args.model} ...")
    import torch
    from transformers import AutoModel

    tokenizer = build_tokenizer(args.model)
    model = AutoModel.from_pretrained(args.model)
    model.resize_token_embeddings(len(tokenizer))
    statuses = init_special_token_embeddings(model, tokenizer)

    n_init = sum(1 for v in statuses.values() if v == "initialised")
    print(
        f"[tokenizer_nn_sanity] {n_init}/{len(SPECIAL_TOKENS)} special tokens initialised "
        f"({n_init/len(SPECIAL_TOKENS):.1%}); the rest fell back to BERT random init"
    )

    embeddings = model.get_input_embeddings().weight.data  # (V, D)
    # Normalise once for cosine similarity.
    norm = embeddings.norm(dim=1, keepdim=True).clamp_min(1e-12)
    normed = embeddings / norm

    # Resolve special token IDs and compute their NN against the entire vocab.
    # Mask out: the special token itself + all OTHER LogHetero specials (we
    # want to see how the new token relates to the natural-language vocab,
    # not to its sibling placeholders).
    special_ids = {tokenizer.convert_tokens_to_ids(t) for t in SPECIAL_TOKENS} | set(
        tokenizer.all_special_ids
    )

    report: dict[str, dict] = {
        "model": args.model,
        "top_k": args.top_k,
        "n_special_tokens": len(SPECIAL_TOKENS),
        "n_initialised": n_init,
        "samples": {},
    }

    print(
        f"\n=== top-{args.top_k} nearest BERT tokens for {len(SAMPLE_TOKENS_FOR_REPORT)} sample special tokens ===\n"
    )
    for tok in SAMPLE_TOKENS_FOR_REPORT:
        tok_id = tokenizer.convert_tokens_to_ids(tok)
        if tok_id is None or tok_id == tokenizer.unk_token_id:
            print(f"  {tok}: NOT IN VOCAB (skipped)")
            report["samples"][tok] = {"status": "missing", "neighbours": []}
            continue
        sims = normed @ normed[tok_id]
        # Exclude self + other LogHetero specials so neighbours are natural-language tokens.
        sims_masked = sims.clone()
        for sid in special_ids:
            sims_masked[sid] = -1.0
        top_vals, top_ids = torch.topk(sims_masked, args.top_k)
        neighbours = [
            (tokenizer.convert_ids_to_tokens(int(idx)), float(v))
            for idx, v in zip(top_ids.tolist(), top_vals.tolist(), strict=True)
        ]
        nb_str = " / ".join(f"{n} ({v:.3f})" for n, v in neighbours)
        print(f"  {tok:<26} -> {nb_str}")
        report["samples"][tok] = {
            "status": statuses.get(tok, "unknown"),
            "neighbours": [{"token": n, "cos_sim": v} for n, v in neighbours],
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n[tokenizer_nn_sanity] full report -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
