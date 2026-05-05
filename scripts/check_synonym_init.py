"""SYNONYM_INIT regression check (Q-2 mini-checkpoint, persisted as standing script).

Loads a BERT model's tokenizer and verifies that every entry in
``loghetero.data.tokenizer.SYNONYM_INIT`` has at least one synonym word that
exists as a single token in the BERT vocabulary. The test the project owner
cares about (per the Checkpoint-3 Q-2 spec): does any new ``[TOKEN]`` we add
silently fall back to BERT random init (no in-vocab synonym), or collapse to
a single-synonym pure copy (cosine similarity 1.0 to that one survivor)?

Inputs
======

* ``--model`` (default ``bert-base-uncased``): tokenizer to query.
* ``--threshold`` (default 20): if more than this many tokens have <50%
  synonym survival, exit 1. Per Q-2 spec: a handful of single-survivor
  tokens like ``[OP_LOGON]`` are acceptable; >20 means SYNONYM_INIT
  should be revised to use shorter, BERT-vocab-friendly synonyms.

Outputs
=======

A 3-line summary printed to stdout:

    Tokens with 0 synonyms surviving (random init):  N
    Tokens with exactly 1 synonym surviving (cos-sim 1.0): N
    Tokens with < 50% survival rate:                  N

Plus, if non-empty: a list of all single-survivor tokens with their full
synonym list and the surviving word.

Exit codes
==========

* ``0`` — all SYNONYM_INIT entries have ≥1 in-vocab synonym AND fewer than
  ``--threshold`` tokens have <50% survival. Initialisation accepted.
* ``1`` — at least one token fell back to random init, or low-survival
  count exceeded threshold. Revise ``SYNONYM_INIT`` and re-run.

Usage
=====

    uv run python scripts/check_synonym_init.py
    uv run python scripts/check_synonym_init.py --threshold 10
    uv run python scripts/check_synonym_init.py --model bert-large-uncased
"""

from __future__ import annotations

import argparse
import sys

DEFAULT_LOW_SURVIVAL_THRESHOLD = 20  # per Q-2 spec at Checkpoint 3 launch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="bert-base-uncased")
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_LOW_SURVIVAL_THRESHOLD,
        help=(
            "Max tolerated tokens with <50%% synonym survival before exit 1. "
            "Default 20 per Q-2 spec."
        ),
    )
    args = parser.parse_args()

    from transformers import AutoTokenizer

    from loghetero.data.tokenizer import SPECIAL_TOKENS, SYNONYM_INIT

    tok = AutoTokenizer.from_pretrained(args.model)
    unk = tok.unk_token_id

    def survives(word: str) -> bool:
        tid = tok.convert_tokens_to_ids(word)
        return tid is not None and tid != unk

    zero_survival: list[tuple[str, list[str]]] = []
    single_survival: list[tuple[str, list[str], str]] = []
    low_survival: list[tuple[str, int, int]] = []

    for special, syns in SYNONYM_INIT.items():
        n_total = len(syns)
        survived = [w for w in syns if survives(w)]
        n_alive = len(survived)
        if n_alive == 0:
            zero_survival.append((special, syns))
        elif n_alive == 1:
            single_survival.append((special, syns, survived[0]))
        if n_total > 0 and n_alive / n_total < 0.5:
            low_survival.append((special, n_alive, n_total))

    print(
        f"=== SYNONYM_INIT regression check "
        f"({args.model}, {len(SPECIAL_TOKENS)} tokens, threshold={args.threshold}) ==="
    )
    print(f"Tokens with 0 synonyms surviving (random init):     {len(zero_survival)}")
    print(f"Tokens with exactly 1 synonym surviving (cos-sim 1.0): {len(single_survival)}")
    print(f"Tokens with < 50% survival rate:                    {len(low_survival)}")
    print()

    if single_survival:
        print("--- Single-synonym pure-copy collapses (cos-sim 1.0 to survivor) ---")
        for tok_, syns, alive in single_survival:
            print(f"  {tok_:<28} survivor={alive!r:<14}  full list: {syns}")
        print()

    if zero_survival:
        print("--- CRITICAL: tokens with ZERO in-vocab synonyms (random init) ---")
        for tok_, syns in zero_survival:
            print(f"  {tok_:<28} synonyms: {syns}")
        print()
        print(
            "FAIL: at least one token fell back to BERT random init. Revise "
            "SYNONYM_INIT to add at least one BERT-vocab-friendly synonym for "
            "each affected token.",
            file=sys.stderr,
        )
        return 1

    if len(low_survival) > args.threshold:
        print(
            f"FAIL: {len(low_survival)} tokens have <50% synonym survival "
            f"(threshold = {args.threshold}). Revise SYNONYM_INIT to use shorter, "
            f"BERT-vocab-friendly words (e.g. 'sign' / 'auth' / 'session' instead "
            f"of 'authenticate' / 'logon').",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {len(SPECIAL_TOKENS) - len(zero_survival)} / {len(SPECIAL_TOKENS)} "
        f"tokens have at least one in-vocab synonym; {len(low_survival)} below "
        f"50% survival (within threshold {args.threshold}). Accepted per Q-2 spec."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
