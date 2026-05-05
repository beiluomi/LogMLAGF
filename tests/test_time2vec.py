"""Phase 3 / Checkpoint 7 Time2Vec edge-time encoder tests.

Covers the four launch-spec acceptance tests for
:class:`loghetero.models.encoders.time2vec.Time2Vec`:

1. Forward shape ``[N, 1] -> [N, dim]`` for ``dim`` in ``{16, 32, 64}``.
2. Determinism: feeding the same timestamp twice yields cosine-similarity
   exactly 1.0 (within float tolerance).
3. Discrimination: distinct timestamps yield cosine-similarity < 1.0.
4. Gradient flow: forward + backward reaches all four learnable parameter
   groups (``omega``, ``phi``, ``omega_0``, ``phi_0``) with at least one
   non-zero element each.

These run in the default pytest lane (no ``@pytest.mark.integration``);
torch is already a hard install requirement of the project's dev env.
"""

from __future__ import annotations

import pytest
import torch

from loghetero.models.encoders.time2vec import Time2Vec

# ---------------------------------------------------------------------------
# 1. Forward shape
# ---------------------------------------------------------------------------


class TestForwardShape:
    @pytest.mark.parametrize("dim", [16, 32, 64])
    def test_forward_shape_n8(self, dim: int) -> None:
        """``[N, 1]`` in -> ``[N, dim]`` out, for N=8 and the three sweep dims."""
        torch.manual_seed(0)
        encoder = Time2Vec(dim=dim)
        t = torch.arange(8, dtype=torch.float32).unsqueeze(-1)  # [8, 1]
        out = encoder(t)
        assert out.shape == (8, dim), f"expected (8, {dim}), got {tuple(out.shape)}"
        assert out.dtype == torch.float32


# ---------------------------------------------------------------------------
# 2. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_timestamp_twice_identical_output(self) -> None:
        """Passing the same timestamp twice must yield identical encodings.

        We check via cosine similarity (== 1.0 within float tolerance), which
        is the metric that downstream contrastive losses care about.
        """
        torch.manual_seed(0)
        encoder = Time2Vec(dim=32)
        t = torch.tensor([[1.5]], dtype=torch.float32)  # [1, 1]
        out_a = encoder(t)
        out_b = encoder(t)
        cos = torch.nn.functional.cosine_similarity(out_a, out_b, dim=-1)
        assert torch.allclose(
            cos, torch.ones_like(cos), atol=1e-6
        ), f"expected cosine sim == 1.0 for identical inputs, got {cos.item()}"


# ---------------------------------------------------------------------------
# 3. Discrimination (distinct inputs -> distinct encodings)
# ---------------------------------------------------------------------------


class TestDiscrimination:
    def test_distinct_timestamps_distinct_encodings(self) -> None:
        """Different timestamps must yield cosine similarity strictly < 1.0.

        Given the small uniform init, two timestamps separated by a
        meaningful delta should produce distinguishable embeddings; if
        they didn't, downstream temporal attention would have nothing to
        bite on.
        """
        torch.manual_seed(0)
        encoder = Time2Vec(dim=32)
        t1 = torch.tensor([[1.0]], dtype=torch.float32)
        t2 = torch.tensor([[100.0]], dtype=torch.float32)
        out_1 = encoder(t1)
        out_2 = encoder(t2)
        cos = torch.nn.functional.cosine_similarity(out_1, out_2, dim=-1)
        assert (
            cos.item() < 1.0 - 1e-6
        ), f"expected cosine sim < 1 for distinct timestamps, got {cos.item()}"


# ---------------------------------------------------------------------------
# 4. Gradient flow
# ---------------------------------------------------------------------------


class TestGradientFlow:
    def test_all_four_param_groups_receive_nonzero_grad(self) -> None:
        """Forward + backward must populate ``.grad`` on every learnable param.

        We use the squared-norm of the encoder output as a stand-in loss.
        That loss depends on every component (linear and sin) of the
        Time2Vec output, so each of ``omega_0``, ``phi_0``, ``omega``,
        ``phi`` should receive a non-zero gradient.
        """
        torch.manual_seed(0)
        encoder = Time2Vec(dim=32)
        # Small batch of distinct timestamps so the sin arguments cover
        # different parts of the curve and ``cos`` (the d/dphi of sin) is
        # not uniformly zero.
        t = torch.tensor([[0.25], [1.0], [3.5], [10.0]], dtype=torch.float32)
        out = encoder(t)  # [4, 32]
        loss = (out**2).sum()
        loss.backward()

        for name in ("omega_0", "phi_0", "omega", "phi"):
            param = getattr(encoder, name)
            assert param.grad is not None, f"param {name!r} has no .grad after backward"
            assert torch.any(
                param.grad != 0
            ), f"param {name!r} has all-zero gradient; expected at least one non-zero element"
