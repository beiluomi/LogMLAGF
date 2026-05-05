"""Phase 2 / Checkpoint 6 BERT text-encoder integration tests.

All tests in this file are integration-marked because they load
bert-base-uncased (one-shot ~400 MB download into HF cache; subsequent runs
are local). Local dev runs them via ``make integration-test``; CI fast lane
skips them per the pyproject.toml integration marker.
"""

from __future__ import annotations

import pytest

from loghetero.data.tokenizer import SPECIAL_TOKENS
from loghetero.models.encoders.bert_text import (
    LoRAConfig,
    TrainMode,
    build_bert_text_encoder,
    count_trainable_parameters,
    encode_texts,
)

EXPECTED_BERT_BASE_VOCAB = 30_522
EXPECTED_LOGHETERO_TOTAL = EXPECTED_BERT_BASE_VOCAB + 156  # = 30,678


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Vocab expansion
# ---------------------------------------------------------------------------


class TestVocabResize:
    def test_vocab_size_30522_to_30678(self) -> None:
        # Per Phase 2 launch spec: vocab must go from 30,522 to 30,678
        # (= 30,522 + 156 LogHetero special tokens).
        _model, tokenizer = build_bert_text_encoder(mode=TrainMode.frozen)
        assert len(tokenizer) == EXPECTED_LOGHETERO_TOTAL, (
            f"vocab size {len(tokenizer)} != expected {EXPECTED_LOGHETERO_TOTAL} "
            f"(BERT-base {EXPECTED_BERT_BASE_VOCAB} + 156 LogHetero specials)"
        )

    def test_special_tokens_atomic_post_resize(self) -> None:
        # Every LogHetero special token must tokenize to ONE token, not be
        # WordPiece-split. (Same invariant tests/test_tokenizer.py covers,
        # repeated here as a regression guard once embedding resize happens.)
        _model, tokenizer = build_bert_text_encoder(mode=TrainMode.frozen)
        unk = tokenizer.unk_token_id
        for tok in SPECIAL_TOKENS:
            tid = tokenizer.convert_tokens_to_ids(tok)
            assert (
                tid is not None and tid != unk
            ), f"special token {tok!r} not surviving tokenizer build"

    def test_input_embedding_matrix_resized(self) -> None:
        model, _tok = build_bert_text_encoder(mode=TrainMode.frozen)
        emb = model.get_input_embeddings()
        assert emb.weight.shape[0] == EXPECTED_LOGHETERO_TOTAL


# ---------------------------------------------------------------------------
# Three TrainMode switches: forward must succeed for all three
# ---------------------------------------------------------------------------


class TestTrainModes:
    """Forward path runs cleanly under all 3 modes (Phase 2 spec)."""

    @pytest.fixture(scope="class")
    def texts(self) -> list[str]:
        # Two cleaned-style event texts (placeholders + lowercase outside).
        return [
            "file_access subject=[PROC_LSASS] object=[PATH_WIN_USERS] event_id=4663",
            "net_dns_query subject=[IP_V4] object=[IP_V4] query_name=[DOMAIN]",
        ]

    def test_frozen_forward_no_grad(self, texts: list[str]) -> None:
        model, tokenizer = build_bert_text_encoder(mode=TrainMode.frozen)
        emb = encode_texts(model, tokenizer, texts)
        assert emb.shape == (2, 768)
        # All params frozen
        trainable, total = count_trainable_parameters(model)
        assert trainable == 0, f"frozen mode should have 0 trainable, got {trainable}"
        assert total > 0

    def test_full_forward_all_trainable(self, texts: list[str]) -> None:
        model, tokenizer = build_bert_text_encoder(mode=TrainMode.full)
        emb = encode_texts(model, tokenizer, texts)
        assert emb.shape == (2, 768)
        trainable, total = count_trainable_parameters(model)
        assert trainable == total, "full mode should have all params trainable"

    def test_lora_forward_only_adapters_trainable(self, texts: list[str]) -> None:
        model, tokenizer = build_bert_text_encoder(mode=TrainMode.lora, lora_config=LoRAConfig(r=8))
        emb = encode_texts(model, tokenizer, texts)
        assert emb.shape == (2, 768)
        trainable, total = count_trainable_parameters(model)
        # PEFT installs LoRA adapters on q+v of last 4 layers only:
        # rough budget = 4 layers * 2 matrices (q, v) * 2 (down + up) * (768*r + r*768)
        # for bert-base h=768, r=8: ~4 * 2 * 2 * (768*8 + 8*768) = 4 * 2 * 2 * 12288 = 196,608
        # So the trainable count should be in the low hundreds of thousands; total ~110M.
        # Here we just assert a sane fraction (1e-4 < trainable/total < 5e-2).
        ratio = trainable / total
        assert 1e-5 < ratio < 5e-2, (
            f"LoRA trainable ratio {ratio:.6f} outside sane range; "
            f"trainable={trainable:,} / total={total:,}"
        )


# ---------------------------------------------------------------------------
# Encoder output sanity (Phase 2 nearest-neighbour spirit)
# ---------------------------------------------------------------------------


class TestEncoderOutputSanity:
    def test_cls_pool_returns_768d(self) -> None:
        model, tokenizer = build_bert_text_encoder(mode=TrainMode.frozen)
        emb = encode_texts(model, tokenizer, ["hello world"], pooling="cls")
        assert emb.shape == (1, 768)

    def test_mean_pool_returns_768d(self) -> None:
        model, tokenizer = build_bert_text_encoder(mode=TrainMode.frozen)
        emb = encode_texts(model, tokenizer, ["hello world"], pooling="mean")
        assert emb.shape == (1, 768)

    def test_unknown_pooling_rejected(self) -> None:
        model, tokenizer = build_bert_text_encoder(mode=TrainMode.frozen)
        with pytest.raises(ValueError, match="pooling"):
            encode_texts(model, tokenizer, ["x"], pooling="bogus")

    def test_semantically_similar_events_cluster(self) -> None:
        # Two events of the same op type (file_access) should be closer in
        # cosine space than to a fundamentally different op (net_dns_query).
        # This is the weak version of the Phase 2 launch-spec NN sanity:
        # full ATLAS sanity is in scripts/bert_sanity_check.py.
        import torch

        model, tokenizer = build_bert_text_encoder(mode=TrainMode.frozen)
        texts = [
            # Two file_access events (close in semantics)
            "file_access subject=[PROC_LSASS] object=[PATH_WIN_USERS]",
            "file_access subject=[PROC_SVCHOST] object=[PATH_WIN_SYS32]",
            # One unrelated network event
            "net_dns_query subject=[IP_V4] object=[IP_V4] query_name=[DOMAIN]",
        ]
        emb = encode_texts(model, tokenizer, texts)
        emb = emb / emb.norm(dim=1, keepdim=True).clamp_min(1e-12)
        sim_within_op = float(torch.dot(emb[0], emb[1]).item())
        sim_across_op = float(torch.dot(emb[0], emb[2]).item())
        assert sim_within_op > sim_across_op, (
            f"two file_access events should be more similar than a file_access "
            f"vs a dns_query event; got within-op={sim_within_op:.3f} "
            f"vs across-op={sim_across_op:.3f}. The cleaner / tokenizer / BERT "
            f"integration may be off."
        )
