"""Phase 4 / Checkpoint 12 cross-modal attention tests.

Five required test groups per the Checkpoint 12 launch spec:

1. **Shape tests** — forward returns expected shapes for B=4, T=32, N=64.
2. **Mask utility tests** — ``build_event_attention_mask`` correctness.
3. **Mask honored in forward** — masked positions have near-zero attention weight.
4. **Gradient flow sanity** — all three parameter categories receive finite,
   non-zero gradients: input projections, QKV cross-attention layers, output
   projections.
5. **Independence test** — Text→Graph and Graph→Text params do not alias.
"""

from __future__ import annotations

import pytest
import torch

from loghetero.models.fusion import CrossModalAttention, build_event_attention_mask

# ---------------------------------------------------------------------------
# Default test dimensions (from launch spec)
# ---------------------------------------------------------------------------

B, T, N = 4, 32, 64
TEXT_DIM = 768
GRAPH_DIM = 256
ATTN_DIM = 256
NUM_HEADS = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_inputs(
    b: int = B,
    t: int = T,
    n: int = N,
    text_dim: int = TEXT_DIM,
    graph_dim: int = GRAPH_DIM,
    seed: int = 42,
    requires_grad: bool = False,
) -> tuple[torch.Tensor, torch.Tensor]:
    g = torch.Generator().manual_seed(seed)
    text = torch.randn(b, t, text_dim, generator=g, requires_grad=requires_grad)
    graph = torch.randn(b, n, graph_dim, generator=g, requires_grad=requires_grad)
    return text, graph


def _make_module(seed: int = 0) -> CrossModalAttention:
    torch.manual_seed(seed)
    return CrossModalAttention(
        text_dim=TEXT_DIM,
        graph_dim=GRAPH_DIM,
        attn_dim=ATTN_DIM,
        num_heads=NUM_HEADS,
        dropout=0.0,  # deterministic for tests
    )


# ---------------------------------------------------------------------------
# 1. Shape tests
# ---------------------------------------------------------------------------


class TestShapes:
    def test_fused_text_shape(self) -> None:
        model = _make_module()
        text, graph = _make_inputs()
        fused_text, _, _ = model(text, graph)
        assert fused_text.shape == (
            B,
            T,
            TEXT_DIM,
        ), f"fused_text shape mismatch: got {fused_text.shape}"

    def test_fused_graph_shape(self) -> None:
        model = _make_module()
        text, graph = _make_inputs()
        _, fused_graph, _ = model(text, graph)
        assert fused_graph.shape == (
            B,
            N,
            GRAPH_DIM,
        ), f"fused_graph shape mismatch: got {fused_graph.shape}"

    def test_attn_weights_text_to_graph_shape(self) -> None:
        model = _make_module()
        text, graph = _make_inputs()
        _, _, weights = model(text, graph)
        tg = weights["text_to_graph"]
        assert tg.shape == (
            B,
            NUM_HEADS,
            T,
            N,
        ), f"text_to_graph weights shape mismatch: got {tg.shape}"

    def test_attn_weights_graph_to_text_shape(self) -> None:
        model = _make_module()
        text, graph = _make_inputs()
        _, _, weights = model(text, graph)
        gt = weights["graph_to_text"]
        assert gt.shape == (
            B,
            NUM_HEADS,
            N,
            T,
        ), f"graph_to_text weights shape mismatch: got {gt.shape}"

    def test_attn_weights_dict_keys(self) -> None:
        model = _make_module()
        text, graph = _make_inputs()
        _, _, weights = model(text, graph)
        assert set(weights.keys()) == {"text_to_graph", "graph_to_text"}

    def test_forward_no_masks_runs(self) -> None:
        """Bare forward (no masks) must not raise."""
        model = _make_module()
        text, graph = _make_inputs()
        out = model(text, graph)
        assert len(out) == 3

    def test_forward_with_all_masks(self) -> None:
        """Forward with all three optional masks provided must not raise and shapes match."""
        model = _make_module()
        text, graph = _make_inputs()

        g = torch.Generator().manual_seed(7)
        # Random event ids; -1 for some padding
        text_event_ids = torch.randint(0, 3, (B, T), generator=g)
        graph_event_ids = torch.randint(0, 3, (B, N), generator=g)
        # Mark last 4 text and last 8 graph positions as padding
        text_event_ids[:, -4:] = -1
        graph_event_ids[:, -8:] = -1
        text_pad = text_event_ids >= 0  # (B, T)
        graph_pad = graph_event_ids >= 0  # (B, N)
        mask = build_event_attention_mask(text_event_ids, graph_event_ids, text_pad, graph_pad)

        fused_text, fused_graph, weights = model(
            text,
            graph,
            attention_mask=mask,
            text_padding_mask=text_pad,
            graph_padding_mask=graph_pad,
        )
        assert fused_text.shape == (B, T, TEXT_DIM)
        assert fused_graph.shape == (B, N, GRAPH_DIM)

    def test_constructor_bad_attn_dim_raises(self) -> None:
        with pytest.raises(ValueError, match="attn_dim"):
            CrossModalAttention(text_dim=768, graph_dim=256, attn_dim=257, num_heads=8)


# ---------------------------------------------------------------------------
# 2. Mask utility tests
# ---------------------------------------------------------------------------


class TestBuildEventAttentionMask:
    def _small_ids(self) -> tuple[torch.Tensor, torch.Tensor]:
        # B=2, T=5, N=4
        text_event_ids = torch.tensor(
            [
                [0, 0, 1, 1, -1],
                [0, 1, 2, -1, -1],
            ],
            dtype=torch.long,
        )
        graph_event_ids = torch.tensor(
            [
                [0, 0, 1, -1],
                [0, 1, 2, -1],
            ],
            dtype=torch.long,
        )
        return text_event_ids, graph_event_ids

    def test_output_shape(self) -> None:
        te, ge = self._small_ids()
        mask = build_event_attention_mask(te, ge)
        assert mask.shape == (2, 5, 4)

    def test_dtype_is_bool(self) -> None:
        te, ge = self._small_ids()
        mask = build_event_attention_mask(te, ge)
        assert mask.dtype == torch.bool

    def test_same_event_allows_attention(self) -> None:
        te, ge = self._small_ids()
        mask = build_event_attention_mask(te, ge)
        # batch 0: text[0] (event 0) → graph[0] (event 0): True
        assert mask[0, 0, 0].item() is True
        # batch 0: text[2] (event 1) → graph[2] (event 1): True
        assert mask[0, 2, 2].item() is True

    def test_different_event_blocks_attention(self) -> None:
        te, ge = self._small_ids()
        mask = build_event_attention_mask(te, ge)
        # batch 0: text[0] (event 0) → graph[2] (event 1): False
        assert mask[0, 0, 2].item() is False
        # batch 1: text[0] (event 0) → graph[1] (event 1): False
        assert mask[1, 0, 1].item() is False

    def test_text_padding_position_is_false(self) -> None:
        te, ge = self._small_ids()
        mask = build_event_attention_mask(te, ge)
        # batch 0: text[4] is padding (-1); any graph column should be False
        assert mask[0, 4, :].any().item() is False

    def test_graph_padding_position_is_false(self) -> None:
        te, ge = self._small_ids()
        mask = build_event_attention_mask(te, ge)
        # batch 0: graph[3] is padding (-1); any text row should be False
        assert mask[0, :, 3].any().item() is False

    def test_negative_one_to_negative_one_is_false(self) -> None:
        """Two padding tokens with id=-1 must NOT be allowed to attend each other."""
        te = torch.tensor([[-1, 0]], dtype=torch.long)
        ge = torch.tensor([[-1, 0]], dtype=torch.long)
        mask = build_event_attention_mask(te, ge)
        # te[0,0]=-1 vs ge[0,0]=-1: must be False
        assert mask[0, 0, 0].item() is False
        # te[0,1]=0 vs ge[0,1]=0: must be True
        assert mask[0, 1, 1].item() is True

    def test_explicit_padding_masks_applied(self) -> None:
        """Padding mask overrides event-id match."""
        # Construct a case where two positions share event_id=5 but one is in
        # the explicit padding mask → should still be False.
        te = torch.tensor([[5, 5]], dtype=torch.long)
        ge = torch.tensor([[5, 5]], dtype=torch.long)
        text_pad = torch.tensor([[True, False]], dtype=torch.bool)  # token 1 is padding
        graph_pad = torch.tensor([[True, True]], dtype=torch.bool)
        mask = build_event_attention_mask(te, ge, text_pad, graph_pad)
        # text[0] (real) → graph[0] (real), same event → True
        assert mask[0, 0, 0].item() is True
        # text[1] (padding) → graph[0] (real) → False (text is padding)
        assert mask[0, 1, 0].item() is False

    def test_all_padding_yields_all_false(self) -> None:
        te = torch.full((2, 5), -1, dtype=torch.long)
        ge = torch.full((2, 4), -1, dtype=torch.long)
        mask = build_event_attention_mask(te, ge)
        assert not mask.any().item()


# ---------------------------------------------------------------------------
# 3. Mask honored in forward
# ---------------------------------------------------------------------------


class TestMaskHonoredInForward:
    def test_blocked_positions_near_zero_weight(self) -> None:
        """When attention_mask blocks certain (text, graph) pairs, their
        attention weights should be ~0 after softmax."""
        model = _make_module()
        model.eval()

        text, graph = _make_inputs(b=2, t=4, n=6, seed=99)

        # Construct a mask that blocks ALL positions for batch 0.
        # Only batch 1, text[0], graph[0] is allowed.
        mask = torch.zeros(2, 4, 6, dtype=torch.bool)
        mask[1, 0, 0] = True  # exactly one allowed pair in batch 1

        with torch.no_grad():
            _, _, weights = model(text, graph, attention_mask=mask)

        tg = weights["text_to_graph"]  # (B, num_heads, T, N) = (2, 8, 4, 6)

        # Batch 1, text token 0 → graph node 1..5: should be ~0
        blocked_weights = tg[1, :, 0, 1:]  # (num_heads, 5)
        assert (
            blocked_weights < 1e-6
        ).all(), f"Expected ~0 weights at blocked positions; max={blocked_weights.max().item():.2e}"

    def test_all_blocked_mask_does_not_produce_nan(self) -> None:
        """A row with all positions blocked produces 0 attention weights (softmax of all -inf
        returns uniform or is handled gracefully — we just check no NaN)."""
        model = _make_module()
        model.eval()
        text, graph = _make_inputs(b=1, t=2, n=3, seed=7)
        # Block everything.
        mask = torch.zeros(1, 2, 3, dtype=torch.bool)
        with torch.no_grad():
            fused_text, fused_graph, weights = model(text, graph, attention_mask=mask)
        assert not torch.isnan(fused_text).any(), "NaN in fused_text with all-blocked mask"
        assert not torch.isnan(fused_graph).any(), "NaN in fused_graph with all-blocked mask"


# ---------------------------------------------------------------------------
# 4. Gradient flow sanity
# ---------------------------------------------------------------------------


class TestGradientFlow:
    def test_input_projections_receive_grad(self) -> None:
        model = _make_module()
        model.train()
        text, graph = _make_inputs(requires_grad=False)
        fused_text, fused_graph, _ = model(text, graph)
        loss = fused_text.sum() + fused_graph.sum()
        loss.backward()

        for name, param in [
            ("text_proj.weight", model.text_proj.weight),
            ("graph_proj.weight", model.graph_proj.weight),
        ]:
            assert param.grad is not None, f"{name} has no gradient"
            grad_norm = param.grad.norm().item()
            assert grad_norm > 1e-8, f"{name} grad norm too small: {grad_norm}"
            # Loss is fused_text.sum() / fused_graph.sum() over a (B, T, D) tensor;
            # .sum() reduction inflates gradient norms by ~sqrt(B*T*D) compared to a
            # mean-reduced loss. Observed norms are O(2k-4k); 1e6 is the explosion guard
            # (would catch true NaN/Inf or 100x growth without false-positives at scale).
            assert grad_norm < 1e6, f"{name} grad norm too large: {grad_norm}"
            assert not torch.isnan(param.grad).any(), f"{name} has NaN gradient"

    def test_cross_attention_qkv_receive_grad(self) -> None:
        model = _make_module()
        model.train()
        text, graph = _make_inputs(requires_grad=False)
        fused_text, fused_graph, _ = model(text, graph)
        (fused_text.sum() + fused_graph.sum()).backward()

        # nn.MultiheadAttention stores in_proj_weight (combined QKV) and
        # out_proj.weight.
        for mha_name, mha in [("tg_attn", model.tg_attn), ("gt_attn", model.gt_attn)]:
            w = mha.in_proj_weight
            assert w is not None
            assert w.grad is not None, f"{mha_name}.in_proj_weight has no gradient"
            grad_norm = w.grad.norm().item()
            assert grad_norm > 1e-8, f"{mha_name}.in_proj_weight grad norm too small: {grad_norm}"
            assert (
                grad_norm < 1e6
            ), (
                f"{mha_name}.in_proj_weight grad norm too large: {grad_norm}"
            )  # explosion guard, see comment above
            assert not torch.isnan(w.grad).any()

    def test_output_projections_receive_grad(self) -> None:
        model = _make_module()
        model.train()
        text, graph = _make_inputs(requires_grad=False)
        fused_text, fused_graph, _ = model(text, graph)
        (fused_text.sum() + fused_graph.sum()).backward()

        for name, param in [
            ("tg_out_proj.weight", model.tg_out_proj.weight),
            ("gt_out_proj.weight", model.gt_out_proj.weight),
        ]:
            assert param.grad is not None, f"{name} has no gradient"
            grad_norm = param.grad.norm().item()
            assert grad_norm > 1e-8, f"{name} grad norm too small: {grad_norm}"
            assert (
                grad_norm < 1e6
            ), f"{name} grad norm too large: {grad_norm}"  # explosion guard, see comment above
            assert not torch.isnan(param.grad).any(), f"{name} has NaN gradient"

    def test_layer_norm_params_receive_grad(self) -> None:
        model = _make_module()
        model.train()
        text, graph = _make_inputs(requires_grad=False)
        fused_text, fused_graph, _ = model(text, graph)
        (fused_text.sum() + fused_graph.sum()).backward()

        for name, param in [
            ("text_norm.weight", model.text_norm.weight),
            ("graph_norm.weight", model.graph_norm.weight),
        ]:
            assert param.grad is not None, f"{name} has no gradient"
            assert not torch.isnan(param.grad).any()

    def test_all_params_have_finite_grad(self) -> None:
        """Comprehensive: every named parameter must have a finite, non-NaN gradient."""
        model = _make_module()
        model.train()
        text, graph = _make_inputs(requires_grad=False)
        fused_text, fused_graph, _ = model(text, graph)
        (fused_text.sum() + fused_graph.sum()).backward()

        for name, param in model.named_parameters():
            assert param.grad is not None, f"{name} has no gradient"
            assert not torch.isnan(param.grad).any(), f"{name} has NaN gradient"
            assert torch.isfinite(param.grad).all(), f"{name} has Inf gradient"


# ---------------------------------------------------------------------------
# 5. Independence test
# ---------------------------------------------------------------------------


class TestParameterIndependence:
    def test_tg_and_gt_attn_in_proj_do_not_alias(self) -> None:
        """Text→Graph and Graph→Text in_proj_weight must be separate tensors."""
        model = _make_module()
        assert (
            model.tg_attn.in_proj_weight is not model.gt_attn.in_proj_weight
        ), "tg_attn and gt_attn share in_proj_weight — parameters are aliased!"
        assert (
            model.tg_attn.in_proj_weight.data_ptr() != model.gt_attn.in_proj_weight.data_ptr()
        ), "tg_attn and gt_attn in_proj_weight share storage — aliased!"

    def test_tg_and_gt_out_proj_do_not_alias(self) -> None:
        """Output projection weights must be separate tensors."""
        model = _make_module()
        assert model.tg_out_proj.weight is not model.gt_out_proj.weight
        assert model.tg_out_proj.weight.data_ptr() != model.gt_out_proj.weight.data_ptr()

    def test_independent_params_diverge_after_update(self) -> None:
        """After one gradient step with different losses, tg and gt params differ."""
        model = _make_module()
        model.train()
        opt = torch.optim.SGD(model.parameters(), lr=0.1)

        text, graph = _make_inputs(requires_grad=False)
        fused_text, fused_graph, _ = model(text, graph)
        # Use only fused_text so only tg path is strongly updated.
        loss = fused_text.sum()
        opt.zero_grad()
        loss.backward()

        tg_w_before = model.tg_attn.in_proj_weight.detach().clone()
        gt_w_before = model.gt_attn.in_proj_weight.detach().clone()

        opt.step()

        tg_w_after = model.tg_attn.in_proj_weight.detach()
        gt_w_after = model.gt_attn.in_proj_weight.detach()

        tg_changed = not torch.allclose(tg_w_before, tg_w_after)
        gt_changed = not torch.allclose(gt_w_before, gt_w_after)

        # loss = fused_text.sum() only flows through the Text→Graph path, so tg should
        # have changed and gt should NOT have changed. If the two in_proj_weight tensors
        # were aliased (shared storage), updating tg would also update gt, causing
        # gt_changed to be True and failing this assertion — which is exactly what we
        # want to catch.
        assert tg_changed and not gt_changed, (
            f"Expected tg_changed=True and gt_changed=False (loss flows only through tg path); "
            f"got tg_changed={tg_changed}, gt_changed={gt_changed}. "
            f"If gt_changed=True, in_proj_weight tensors may be aliased."
        )

    def test_tg_and_gt_attn_out_proj_do_not_alias(self) -> None:
        """MHA internal out_proj (inside tg_attn / gt_attn) must not alias."""
        model = _make_module()
        assert model.tg_attn.out_proj.weight is not model.gt_attn.out_proj.weight
        assert model.tg_attn.out_proj.weight.data_ptr() != model.gt_attn.out_proj.weight.data_ptr()
