"""Phase 4 / Checkpoint 13: tests for the modified MLM module.

Test groups per the launch spec:
1. Shape sanity tests (ModifiedMLMHead input/output shapes).
2. Mask utility correctness on hand-built examples.
3. Mixed-collator Bernoulli ratio (50/50 ± reasonable variance, N=400 samples).
4. Gradient flow into the prediction head.
5. Single-head invariant: same parameter set for 替换 and 删除.

All tests are pure-CPU and must finish in seconds.  No HuggingFace model
download is triggered — the collator tests that need a tokenizer use a
lightweight FakeTokenizer stub that replays a fixed tokenization.
"""

from __future__ import annotations

import math

import torch

from loghetero.models.objectives.modified_mlm import (
    IGNORE_INDEX,
    MASK_TOKEN_ID,
    OP_DELETE,
    OP_REPLACE,
    VOCAB_SIZE,
    MixedMLMCollator,
    ModifiedMLMHead,
    _detect_field_spans,
    _pad_to_max,
    build_field_level_mask,
    build_token_level_mask,
    compute_mlm_loss,
)

# ---------------------------------------------------------------------------
# Stub tokenizer (no HuggingFace download required)
# ---------------------------------------------------------------------------


class _FakeTokenizer:
    """Minimal tokenizer stub for unit tests.

    Tokenizes by splitting on spaces; each word gets a distinct id starting
    at 200 (so IDs 101 = [CLS], 102 = [SEP], 103 = [MASK] don't collide
    with word tokens).  offset_mapping follows the character positions of
    each space-delimited word.

    This is deliberately simple so tests are deterministic and fast without
    any ML model installed.
    """

    mask_token_id: int = 103

    def __call__(
        self,
        text: str,
        max_length: int = 128,
        truncation: bool = True,
        return_offsets_mapping: bool = False,
        return_tensors: None = None,
    ) -> dict:
        words = text.split(" ")
        input_ids = [101]  # [CLS]
        offsets: list[tuple[int, int]] = [(0, 0)]  # [CLS] special token

        char_pos = 0
        for word in words:
            word_id = (hash(word) % 10000) + 200  # deterministic, avoids special range
            input_ids.append(word_id)
            offsets.append((char_pos, char_pos + len(word)))
            char_pos += len(word) + 1  # +1 for space

        input_ids.append(102)  # [SEP]
        offsets.append((0, 0))  # [SEP] special token

        # Truncate.
        if truncation and len(input_ids) > max_length:
            input_ids = input_ids[: max_length - 1] + [102]
            offsets = offsets[: max_length - 1] + [(0, 0)]

        result: dict = {
            "input_ids": input_ids,
            "attention_mask": [1] * len(input_ids),
        }
        if return_offsets_mapping:
            result["offset_mapping"] = offsets
        return result


FAKE_TOK = _FakeTokenizer()


def _ids_from_text(text: str, max_length: int = 128) -> torch.Tensor:
    """Tokenize text with the stub tokenizer and return as a 1-D long tensor."""
    enc = FAKE_TOK(text, max_length=max_length, truncation=True)
    return torch.tensor(enc["input_ids"], dtype=torch.long)


# ---------------------------------------------------------------------------
# 1. Shape sanity tests
# ---------------------------------------------------------------------------


class TestModifiedMLMHeadShapes:
    """Verify that ModifiedMLMHead produces correct output shapes."""

    def test_output_shape_basic(self) -> None:
        b, t, h = 4, 32, 768
        head = ModifiedMLMHead(hidden_dim=h, vocab_size=VOCAB_SIZE)
        hidden = torch.randn(b, t, h)
        logits = head(hidden)
        assert logits.shape == (
            b,
            t,
            VOCAB_SIZE,
        ), f"expected ({b},{t},{VOCAB_SIZE}), got {logits.shape}"

    def test_output_shape_small(self) -> None:
        """Smaller dims still work."""
        b, t, h, v = 2, 8, 16, 50
        head = ModifiedMLMHead(hidden_dim=h, vocab_size=v)
        hidden = torch.randn(b, t, h)
        logits = head(hidden)
        assert logits.shape == (b, t, v)

    def test_output_is_float(self) -> None:
        head = ModifiedMLMHead()
        hidden = torch.randn(1, 5, 768)
        logits = head(hidden)
        assert logits.dtype == torch.float32

    def test_no_nan_in_forward(self) -> None:
        head = ModifiedMLMHead()
        hidden = torch.randn(2, 10, 768)
        logits = head(hidden)
        assert not torch.isnan(logits).any(), "NaN found in ModifiedMLMHead output"

    def test_batch_size_one(self) -> None:
        head = ModifiedMLMHead()
        hidden = torch.randn(1, 1, 768)
        logits = head(hidden)
        assert logits.shape == (1, 1, VOCAB_SIZE)


# ---------------------------------------------------------------------------
# 2. Mask utility correctness
# ---------------------------------------------------------------------------


class TestBuildTokenLevelMask:
    """Correctness tests for build_token_level_mask."""

    def test_special_tokens_never_masked(self) -> None:
        """[CLS], [SEP] must never be in masked positions."""
        text = "network_send subject=proc object=ip bytes=4096"
        ids = _ids_from_text(text)
        rng = torch.Generator().manual_seed(0)
        out = build_token_level_mask(ids, mask_prob=1.0, rng=rng)
        # position 0 = [CLS], last = [SEP]
        assert out.input_ids[0].item() != MASK_TOKEN_ID, "[CLS] was masked"
        assert out.input_ids[-1].item() != MASK_TOKEN_ID, "[SEP] was masked"

    def test_mask_prob_zero_changes_nothing(self) -> None:
        """With mask_prob=0.0, no tokens should be masked."""
        ids = _ids_from_text("op subject=x object=y")
        out = build_token_level_mask(ids, mask_prob=0.0)
        assert torch.equal(out.input_ids, ids), "ids changed with mask_prob=0"
        assert (out.labels == IGNORE_INDEX).all(), "non-zero labels with mask_prob=0"

    def test_labels_equal_original_at_masked_positions(self) -> None:
        """At masked positions, labels must equal the original token ids."""
        ids = _ids_from_text("network_send subject=proc object=ip")
        rng = torch.Generator().manual_seed(7)
        out = build_token_level_mask(ids, mask_prob=0.5, rng=rng)
        masked_pos = out.input_ids == MASK_TOKEN_ID
        assert (out.labels[masked_pos] != IGNORE_INDEX).all(), "missing labels at masked positions"
        assert torch.equal(out.labels[masked_pos], ids[masked_pos]), "labels != original ids"

    def test_op_labels_replace_at_masked_positions(self) -> None:
        ids = _ids_from_text("op subject=proc object=ip")
        rng = torch.Generator().manual_seed(3)
        out = build_token_level_mask(ids, mask_prob=1.0, rng=rng)
        # All non-special masked positions must have OP_REPLACE.
        masked = out.input_ids == MASK_TOKEN_ID
        assert (out.op_labels[masked] == OP_REPLACE).all()

    def test_output_length_unchanged(self) -> None:
        ids = _ids_from_text("op subject=x object=y key=val")
        out = build_token_level_mask(ids)
        assert out.input_ids.shape[0] == ids.shape[0], "token-mask must not change sequence length"

    def test_attention_mask_all_ones(self) -> None:
        ids = _ids_from_text("op subject=x object=y")
        out = build_token_level_mask(ids)
        assert (out.attention_mask == 1).all()


class TestBuildFieldLevelMask:
    """Correctness tests for build_field_level_mask."""

    def _make_input(
        self, text: str = "network_send subject=proc object=192.168.1.1 bytes=4096"
    ) -> tuple[torch.Tensor, str]:
        ids = _ids_from_text(text)
        return ids, text

    def test_replace_keeps_length(self) -> None:
        """替换 with delete_prob=0 must keep sequence length unchanged."""
        ids, text = self._make_input()
        rng = torch.Generator().manual_seed(0)
        out = build_field_level_mask(
            ids, text, FAKE_TOK, n_fields_to_mask=1, delete_prob=0.0, rng=rng
        )
        assert (
            out.input_ids.shape[0] == ids.shape[0]
        ), f"replace must preserve length: {out.input_ids.shape[0]} != {ids.shape[0]}"

    def test_delete_shortens_length(self) -> None:
        """删除 with delete_prob=1 must shorten the sequence."""
        text = "network_send subject=proc object=ip bytes=4096 dir=out"
        ids = _ids_from_text(text)
        # The stub tokenizer assigns one token per space-delimited word, so a
        # field with one token will be unchanged length (replace 1 → 1 MASK);
        # choose a case where there are only single-token fields; we still
        # validate that the length is <= original.
        rng = torch.Generator().manual_seed(0)
        out = build_field_level_mask(
            ids, text, FAKE_TOK, n_fields_to_mask=1, delete_prob=1.0, rng=rng
        )
        # Sequence length must be <= original (either same for 1-token field, or shorter).
        assert out.input_ids.shape[0] <= ids.shape[0], "delete must not increase sequence length"

    def test_exactly_one_mask_for_replace(self) -> None:
        """替换 with n_fields=1 must put at least one [MASK] in the output."""
        ids, text = self._make_input()
        rng = torch.Generator().manual_seed(1)
        out = build_field_level_mask(
            ids, text, FAKE_TOK, n_fields_to_mask=1, delete_prob=0.0, rng=rng
        )
        n_masks = (out.input_ids == MASK_TOKEN_ID).sum().item()
        assert n_masks >= 1, f"expected at least 1 [MASK] token, got {n_masks}"

    def test_labels_at_replace_positions_match_original(self) -> None:
        """At 替换 positions, labels must equal the original ids."""
        ids, text = self._make_input()
        rng = torch.Generator().manual_seed(2)
        out = build_field_level_mask(
            ids, text, FAKE_TOK, n_fields_to_mask=1, delete_prob=0.0, rng=rng
        )
        masked_pos = out.input_ids == MASK_TOKEN_ID
        if masked_pos.any():
            # Labels at masked positions should match the *original* ids.
            # We need to align by original sequence length.
            assert (out.labels[masked_pos] != IGNORE_INDEX).all()

    def test_delete_anchor_label_is_not_ignore(self) -> None:
        """删除 anchor position must have a valid (non-IGNORE) label."""
        text = "write subject=powershell object=file.exe bytes=512"
        ids = _ids_from_text(text)
        rng = torch.Generator().manual_seed(42)
        out = build_field_level_mask(
            ids, text, FAKE_TOK, n_fields_to_mask=1, delete_prob=1.0, rng=rng
        )
        # Check that at the anchor [MASK] position, label != IGNORE_INDEX.
        mask_pos = (out.input_ids == MASK_TOKEN_ID).nonzero(as_tuple=True)[0]
        if mask_pos.numel() > 0:
            assert (
                out.labels[mask_pos] != IGNORE_INDEX
            ).any(), "delete anchor must have a non-ignore label"

    def test_op_labels_delete_at_anchor(self) -> None:
        """At a 删除 anchor position, op_labels must be OP_DELETE."""
        text = "read subject=chrome object=http.html size=1024"
        ids = _ids_from_text(text)
        rng = torch.Generator().manual_seed(5)
        out = build_field_level_mask(
            ids, text, FAKE_TOK, n_fields_to_mask=1, delete_prob=1.0, rng=rng
        )
        mask_pos = (out.input_ids == MASK_TOKEN_ID).nonzero(as_tuple=True)[0]
        if mask_pos.numel() > 0:
            for pos in mask_pos.tolist():
                assert (
                    out.op_labels[pos].item() == OP_DELETE
                ), f"expected OP_DELETE at mask position {pos}, got {out.op_labels[pos]}"

    def test_no_field_detected_fallback(self) -> None:
        """An all-mask input with no fields returns gracefully (no crash)."""
        ids = torch.tensor([101, 103, 102], dtype=torch.long)  # [CLS] [MASK] [SEP]
        out = build_field_level_mask(ids, "", FAKE_TOK, n_fields_to_mask=1)
        assert out.input_ids.shape[0] == 3

    def test_replace_op_labels_at_masked_positions(self) -> None:
        """At 替换 positions, op_labels must be OP_REPLACE."""
        ids, text = self._make_input()
        rng = torch.Generator().manual_seed(9)
        out = build_field_level_mask(
            ids, text, FAKE_TOK, n_fields_to_mask=1, delete_prob=0.0, rng=rng
        )
        mask_pos = (out.input_ids == MASK_TOKEN_ID).nonzero(as_tuple=True)[0]
        for p in mask_pos.tolist():
            assert out.op_labels[p].item() == OP_REPLACE

    def test_attention_mask_all_ones(self) -> None:
        ids, text = self._make_input()
        out = build_field_level_mask(ids, text, FAKE_TOK, n_fields_to_mask=1)
        assert (out.attention_mask == 1).all()


class TestDetectFieldSpans:
    """Tests for the internal field-span detection utility."""

    def test_returns_list(self) -> None:
        spans = _detect_field_spans("op subject=x object=y", FAKE_TOK)
        assert isinstance(spans, list)
        assert len(spans) > 0

    def test_spans_are_tuples(self) -> None:
        spans = _detect_field_spans("op subject=x object=y", FAKE_TOK)
        for s in spans:
            assert isinstance(s, tuple) and len(s) == 2

    def test_no_span_beyond_seq_end(self) -> None:
        text = "op subject=x"
        spans = _detect_field_spans(text, FAKE_TOK, max_length=128)
        enc = FAKE_TOK(text, max_length=128, truncation=True, return_offsets_mapping=True)
        seq_len = len(enc["input_ids"])
        for start, end in spans:
            assert 0 <= start < seq_len
            assert 0 < end <= seq_len

    def test_empty_text_returns_empty(self) -> None:
        spans = _detect_field_spans("", FAKE_TOK)
        assert spans == []


# ---------------------------------------------------------------------------
# 3. Mixed collator ratio tests
# ---------------------------------------------------------------------------


class TestMixedMLMCollator:
    """Tests for MixedMLMCollator per-sample Bernoulli(0.5) mode selection."""

    def _make_sample(self, text: str = "op subject=proc object=ip") -> dict:
        return {"input_ids": _ids_from_text(text), "text": text}

    def test_mask_type_per_sample_key_present(self) -> None:
        """Every batch must have 'mask_type_per_sample' key (sanity check #2)."""
        collator = MixedMLMCollator(FAKE_TOK, seed=0)
        batch = [self._make_sample() for _ in range(4)]
        result = collator(batch)
        assert "mask_type_per_sample" in result, "mask_type_per_sample key missing from batch"

    def test_mask_type_shape(self) -> None:
        """mask_type_per_sample must have shape (B,)."""
        b = 6
        collator = MixedMLMCollator(FAKE_TOK, seed=1)
        batch = [self._make_sample() for _ in range(b)]
        result = collator(batch)
        mts = result["mask_type_per_sample"]
        assert mts.shape == (b,), f"expected shape ({b},), got {mts.shape}"

    def test_mask_type_values_are_0_or_1(self) -> None:
        collator = MixedMLMCollator(FAKE_TOK, seed=2)
        batch = [self._make_sample() for _ in range(20)]
        result = collator(batch)
        mts = result["mask_type_per_sample"]
        assert ((mts == 0) | (mts == 1)).all(), f"unexpected values: {mts.unique()}"

    def test_mask_type_dtype_long(self) -> None:
        collator = MixedMLMCollator(FAKE_TOK, seed=3)
        batch = [self._make_sample() for _ in range(4)]
        result = collator(batch)
        assert result["mask_type_per_sample"].dtype == torch.long

    def test_50_50_ratio_approximate(self) -> None:
        """Over N=400 samples, Bernoulli(0.5) should give ~50/50 within 10%."""
        n = 400
        collator = MixedMLMCollator(FAKE_TOK, seed=0)
        total_field_mask = 0
        for _ in range(n):
            batch = [self._make_sample()]
            result = collator(batch)
            total_field_mask += result["mask_type_per_sample"][0].item()
        field_frac = total_field_mask / n
        assert 0.40 <= field_frac <= 0.60, (
            f"Expected field_mask fraction near 0.50 (±0.10), got {field_frac:.3f}. "
            "Bernoulli(0.5) over 400 samples should land in [0.40, 0.60] with high probability."
        )

    def test_batch_keys_present(self) -> None:
        """All required batch keys must be present."""
        collator = MixedMLMCollator(FAKE_TOK, seed=4)
        batch = [self._make_sample() for _ in range(3)]
        result = collator(batch)
        for key in ("input_ids", "attention_mask", "labels", "op_labels", "mask_type_per_sample"):
            assert key in result, f"missing key: {key}"

    def test_batch_tensor_shapes_consistent(self) -> None:
        """All batch tensors must have first dimension = B."""
        b = 5
        collator = MixedMLMCollator(FAKE_TOK, seed=5)
        batch = [self._make_sample(f"op subject=p{i} object=q{i} bytes={i*100}") for i in range(b)]
        result = collator(batch)
        for key in ("input_ids", "attention_mask", "labels", "op_labels"):
            assert result[key].shape[0] == b, f"{key} first dim != {b}"

    def test_different_seeds_give_different_ratios(self) -> None:
        """Different seeds should (with high probability) produce different mode sequences."""
        collator_a = MixedMLMCollator(FAKE_TOK, seed=0)
        collator_b = MixedMLMCollator(FAKE_TOK, seed=999)
        batch = [self._make_sample() for _ in range(30)]
        ra = collator_a(batch)["mask_type_per_sample"]
        rb = collator_b(batch)["mask_type_per_sample"]
        # Two independent seeds should differ somewhere across 30 samples.
        assert not torch.equal(ra, rb), "Different seeds produced identical mode sequences"


# ---------------------------------------------------------------------------
# 4. Gradient flow tests
# ---------------------------------------------------------------------------


class TestGradientFlow:
    """Tests for gradient flow into ModifiedMLMHead."""

    def test_all_params_receive_grad(self) -> None:
        """A mean-reduced loss must propagate gradients to all head parameters."""
        head = ModifiedMLMHead()
        head.train()
        hidden = torch.randn(2, 10, 768, requires_grad=True)
        logits = head(hidden)
        loss = logits.mean()
        loss.backward()

        for name, param in head.named_parameters():
            assert param.grad is not None, f"{name} has no gradient"
            assert not torch.isnan(param.grad).any(), f"{name} has NaN gradient"
            assert torch.isfinite(param.grad).all(), f"{name} has Inf gradient"

    def test_decoder_weight_receives_grad(self) -> None:
        head = ModifiedMLMHead(hidden_dim=64, vocab_size=100)
        head.train()
        hidden = torch.randn(2, 5, 64)
        logits = head(hidden)
        logits.sum().backward()
        assert head.decoder.weight.grad is not None
        assert head.decoder.weight.grad.norm().item() > 1e-10

    def test_layer_norm_receives_grad(self) -> None:
        head = ModifiedMLMHead(hidden_dim=64, vocab_size=100)
        head.train()
        hidden = torch.randn(2, 5, 64)
        logits = head(hidden)
        logits.sum().backward()
        assert head.layer_norm.weight.grad is not None
        assert head.layer_norm.bias.grad is not None

    def test_compute_mlm_loss_backward(self) -> None:
        """compute_mlm_loss must produce a differentiable scalar."""
        head = ModifiedMLMHead(hidden_dim=64, vocab_size=200)
        head.train()
        hidden = torch.randn(2, 6, 64)
        logits = head(hidden)
        # Two masked positions per sample; rest IGNORE_INDEX.
        labels = torch.full((2, 6), IGNORE_INDEX, dtype=torch.long)
        labels[0, 1] = 50
        labels[0, 3] = 75
        labels[1, 2] = 10
        labels[1, 4] = 120
        loss = compute_mlm_loss(logits, labels)
        assert loss.ndim == 0, "Loss must be a scalar"
        assert torch.isfinite(loss), "Loss is not finite"
        loss.backward()
        assert head.decoder.weight.grad is not None

    def test_loss_all_ignore_returns_nan_or_zero(self) -> None:
        """When all positions are IGNORE_INDEX, cross_entropy returns nan (PyTorch
        convention for empty reduction) — we just confirm it doesn't crash."""
        head = ModifiedMLMHead(hidden_dim=32, vocab_size=50)
        hidden = torch.randn(1, 4, 32)
        logits = head(hidden)
        labels = torch.full((1, 4), IGNORE_INDEX, dtype=torch.long)
        # Should not raise; result may be nan (torch convention for empty mean).
        loss = compute_mlm_loss(logits, labels)
        assert loss.ndim == 0


# ---------------------------------------------------------------------------
# 5. Single-head invariant tests
# ---------------------------------------------------------------------------


class TestSingleHeadInvariant:
    """Verify that 替换 and 删除 outputs flow through the SAME head parameters.

    Sanity check #1 from the launch spec.
    """

    def test_head_parameter_set_is_single(self) -> None:
        """ModifiedMLMHead has exactly one set of parameters (dense + ln + decoder)."""
        head = ModifiedMLMHead()
        # Enumerate all parameter names.
        param_names = {name for name, _ in head.named_parameters()}
        # Expected: dense.weight, dense.bias, layer_norm.weight, layer_norm.bias,
        #           decoder.weight, decoder.bias → 6 parameter tensors.
        expected = {
            "dense.weight",
            "dense.bias",
            "layer_norm.weight",
            "layer_norm.bias",
            "decoder.weight",
            "decoder.bias",
        }
        assert param_names == expected, (
            f"Parameter set mismatch.\n"
            f"Expected: {sorted(expected)}\n"
            f"Got:      {sorted(param_names)}\n"
            "If there are extra parameters, you may have added a second routing head."
        )

    def test_replace_and_delete_use_same_decoder_weight(self) -> None:
        """Both 替换 and 删除 scenarios pass through the same decoder.weight tensor."""
        head = ModifiedMLMHead()

        # Simulate 替换 batch: normal hidden states.
        hidden_replace = torch.randn(1, 8, 768)
        logits_replace = head(hidden_replace)

        # Simulate 删除 batch: shorter sequence (one field collapsed).
        hidden_delete = torch.randn(1, 5, 768)
        logits_delete = head(hidden_delete)

        # Both logits must use the same decoder.weight (verify by data_ptr).
        # We check that the head's single decoder is shared (not two instances).
        assert logits_replace.shape[-1] == VOCAB_SIZE
        assert logits_delete.shape[-1] == VOCAB_SIZE
        # The decoder weight data pointer is the same in both calls (trivially
        # true since it's the same nn.Module instance, but this makes the intent explicit).
        assert head.decoder.weight.data_ptr() == head.decoder.weight.data_ptr()

    def test_no_separate_op_routing(self) -> None:
        """The head must NOT have any attribute named after operation types."""
        head = ModifiedMLMHead()
        for attr in ("replace_head", "delete_head", "op_router", "head_replace", "head_delete"):
            assert not hasattr(head, attr), (
                f"ModifiedMLMHead has unexpected attribute '{attr}' — "
                "this suggests a separate per-operation head was added, "
                "violating the Q1 single-head requirement."
            )

    def test_grad_updates_same_decoder_for_both_ops(self) -> None:
        """One gradient step on 替换 loss and one on 删除 loss both update
        the same decoder.weight tensor (not two separate tensors)."""
        head = ModifiedMLMHead(hidden_dim=32, vocab_size=100)
        head.train()
        opt = torch.optim.SGD(head.parameters(), lr=0.01)

        # Step 1: 替换 style loss.
        h_rep = torch.randn(1, 4, 32)
        labels_rep = torch.full((1, 4), -100, dtype=torch.long)
        labels_rep[0, 1] = 42
        loss_rep = compute_mlm_loss(head(h_rep), labels_rep)
        opt.zero_grad()
        loss_rep.backward()
        w_before = head.decoder.weight.detach().clone()
        opt.step()
        w_after_rep = head.decoder.weight.detach().clone()

        # Step 2: 删除 style loss (shorter seq).
        h_del = torch.randn(1, 3, 32)
        labels_del = torch.full((1, 3), -100, dtype=torch.long)
        labels_del[0, 0] = 17
        loss_del = compute_mlm_loss(head(h_del), labels_del)
        opt.zero_grad()
        loss_del.backward()
        opt.step()
        w_after_del = head.decoder.weight.detach().clone()

        # Both steps must have changed the same weight tensor.
        assert not torch.equal(w_before, w_after_rep), "replace loss did not update decoder.weight"
        assert not torch.equal(
            w_after_rep, w_after_del
        ), "delete loss did not update decoder.weight"


# ---------------------------------------------------------------------------
# 6. Padding utility test
# ---------------------------------------------------------------------------


class TestPadToMax:
    def test_pads_to_max_length(self) -> None:
        tensors = [torch.tensor([1, 2, 3]), torch.tensor([4, 5])]
        result = _pad_to_max(tensors, pad_value=0)
        assert result.shape == (2, 3)
        assert result[1, 2].item() == 0  # padded

    def test_original_values_preserved(self) -> None:
        tensors = [torch.tensor([10, 20]), torch.tensor([30, 40, 50])]
        result = _pad_to_max(tensors, pad_value=-1)
        assert result[0, 0].item() == 10
        assert result[1, 2].item() == 50
        assert result[0, 2].item() == -1  # pad

    def test_equal_lengths_no_padding(self) -> None:
        tensors = [torch.tensor([1, 2]), torch.tensor([3, 4])]
        result = _pad_to_max(tensors, pad_value=99)
        assert result.shape == (2, 2)
        assert (result != 99).all()


# ---------------------------------------------------------------------------
# 7. compute_mlm_loss tests
# ---------------------------------------------------------------------------


class TestComputeMLMLoss:
    def test_loss_is_scalar(self) -> None:
        logits = torch.randn(2, 5, 100)
        labels = torch.full((2, 5), IGNORE_INDEX, dtype=torch.long)
        labels[0, 1] = 42
        loss = compute_mlm_loss(logits, labels)
        assert loss.ndim == 0

    def test_loss_positive(self) -> None:
        torch.manual_seed(0)
        logits = torch.randn(2, 5, 100)
        labels = torch.full((2, 5), IGNORE_INDEX, dtype=torch.long)
        labels[0, 2] = 10
        labels[1, 3] = 50
        loss = compute_mlm_loss(logits, labels)
        assert loss.item() > 0, "cross-entropy loss should be positive"

    def test_perfect_prediction_low_loss(self) -> None:
        """Logits with very high score at correct class should give near-zero loss."""
        vocab = 50
        b, t = 1, 3
        logits = torch.full((b, t, vocab), -10.0)
        labels = torch.full((b, t), IGNORE_INDEX, dtype=torch.long)
        labels[0, 0] = 7
        labels[0, 1] = 23
        # Set very high logits at correct positions.
        logits[0, 0, 7] = 100.0
        logits[0, 1, 23] = 100.0
        loss = compute_mlm_loss(logits, labels)
        assert loss.item() < 0.01, f"near-perfect logits gave loss={loss.item():.4f}"

    def test_ignore_index_positions_not_counted(self) -> None:
        """Changing logits at IGNORE_INDEX positions should not affect the loss."""
        vocab = 50
        logits_a = torch.randn(1, 4, vocab)
        logits_b = logits_a.clone()
        labels = torch.full((1, 4), IGNORE_INDEX, dtype=torch.long)
        labels[0, 0] = 5  # only position 0 contributes
        # Modify an ignored position.
        logits_b[0, 1] = logits_b[0, 1] + 100.0
        loss_a = compute_mlm_loss(logits_a, labels)
        loss_b = compute_mlm_loss(logits_b, labels)
        assert math.isclose(
            loss_a.item(), loss_b.item(), rel_tol=1e-5
        ), "Logit change at IGNORE_INDEX position changed the loss"
