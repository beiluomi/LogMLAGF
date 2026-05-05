"""Phase 3 / Checkpoint 7 HGT layer tests (Option-C residual channel).

Per the Checkpoint 7 RFC resolution and the project owner's three explicit
test requirements:

1. The residual is correctly added: forward output equals stock HGTConv
   output + ``residual_alpha`` * residual; ``residual_alpha=0`` degenerates
   to stock HGTConv (Phase 11 ablation B5 switch #1).
2. Zero-timestamp edges (e.g. self-loops at ``t=0``) produce a finite
   (non-NaN, non-Inf) residual.
3. Gradient flows through both the HGTConv attention path AND the
   residual MLP path: backward populates ``.grad`` on parameters from
   both sub-modules.

Plus standard Phase-1-style coverage: forward shape, edge-type one-hot
correctness, empty-edge-index handling, and constructor input validation.
"""

from __future__ import annotations

import pytest
import torch

from loghetero.data.parsers.base import EdgeType, NodeType
from loghetero.models.encoders.time2vec import Time2Vec
from loghetero.models.graph.hgt_layer import HGTLayer

# --- Fixtures ---------------------------------------------------------------

# Minimal heterogeneous schema: process / file / network nodes with
# (process, file_read, file), (process, net_connect, network) edges.
_METADATA: tuple[list[str], list[tuple[str, str, str]]] = (
    [NodeType.process.value, NodeType.file.value, NodeType.network.value],
    [
        (NodeType.process.value, EdgeType.FILE_READ.value, NodeType.file.value),
        (NodeType.process.value, EdgeType.NET_CONNECT.value, NodeType.network.value),
    ],
)
_IN_DIM = 16
_HIDDEN = 32  # smaller than prod 256 for fast tests


def _toy_inputs(
    seed: int = 0,
) -> tuple[
    dict[str, torch.Tensor],
    dict[tuple[str, str, str], torch.Tensor],
    dict[tuple[str, str, str], torch.Tensor],
]:
    """Build a tiny heterogeneous batch:
    3 processes, 2 files, 1 network. Two edge types each with 2 edges.
    """
    g = torch.Generator().manual_seed(seed)
    x_dict = {
        NodeType.process.value: torch.randn(3, _IN_DIM, generator=g),
        NodeType.file.value: torch.randn(2, _IN_DIM, generator=g),
        NodeType.network.value: torch.randn(1, _IN_DIM, generator=g),
    }
    edge_index_dict = {
        (NodeType.process.value, EdgeType.FILE_READ.value, NodeType.file.value): torch.tensor(
            [[0, 1], [0, 1]], dtype=torch.long
        ),  # p0->f0, p1->f1
        (NodeType.process.value, EdgeType.NET_CONNECT.value, NodeType.network.value): torch.tensor(
            [[0, 2], [0, 0]], dtype=torch.long
        ),  # p0->n0, p2->n0
    }
    # Times in normalised hours; use small ints to keep things readable.
    edge_time_dict = {
        (NodeType.process.value, EdgeType.FILE_READ.value, NodeType.file.value): torch.tensor(
            [1.0, 2.0]
        ),
        (NodeType.process.value, EdgeType.NET_CONNECT.value, NodeType.network.value): torch.tensor(
            [3.0, 4.0]
        ),
    }
    return x_dict, edge_index_dict, edge_time_dict


def _build_layer(*, residual_alpha: float = 0.5, time2vec_dim: int = 32) -> HGTLayer:
    return HGTLayer(
        in_channels=_IN_DIM,
        metadata=_METADATA,
        hidden_dim=_HIDDEN,
        num_heads=2,
        dropout=0.0,
        time2vec_dim=time2vec_dim,
        residual_alpha=residual_alpha,
    )


# --- Forward shape ----------------------------------------------------------


class TestForwardShape:
    def test_output_shape_per_node_type(self) -> None:
        layer = _build_layer()
        t2v = Time2Vec(dim=32)
        x, ei, et = _toy_inputs()
        out = layer(x, ei, et, t2v)
        assert out[NodeType.process.value].shape == (3, _HIDDEN)
        assert out[NodeType.file.value].shape == (2, _HIDDEN)
        assert out[NodeType.network.value].shape == (1, _HIDDEN)


# --- The three project-owner-required tests ---------------------------------


class TestOptionCResidual:
    def test_alpha_zero_degenerates_to_stock_hgt(self) -> None:
        # Counter-test for Phase 11 ablation B5 switch #1.
        # alpha=0 must produce exactly the HGTConv output (modulo dropout=0).
        torch.manual_seed(0)
        layer = _build_layer(residual_alpha=0.0)
        layer.eval()
        t2v = Time2Vec(dim=32).eval()
        x, ei, et = _toy_inputs()

        out_with_residual_off = layer(x, ei, et, t2v)
        # Compute stock HGTConv directly (same module instance, same weights).
        with torch.no_grad():
            stock_raw = layer.hgt(x, ei)
        for ntype, expected in stock_raw.items():
            actual = out_with_residual_off[ntype]
            if expected is None:
                # HGTConv returns None for orphan node types -> our wrapper
                # fills with zeros.
                assert torch.allclose(actual, torch.zeros_like(actual))
            else:
                assert torch.allclose(
                    actual, expected, atol=1e-6
                ), f"alpha=0 should be identical to stock HGTConv for {ntype}"

    def test_residual_alpha_scales_contribution(self) -> None:
        # Output should equal stock HGT + alpha * residual.
        # We verify by running the layer twice with different alpha values
        # (sharing the SAME HGTConv weights and edge_mlp weights) and
        # checking the difference scales with alpha.
        torch.manual_seed(0)
        layer = _build_layer(residual_alpha=0.0)
        layer.eval()
        t2v = Time2Vec(dim=32).eval()
        x, ei, et = _toy_inputs()
        out_alpha0 = layer(x, ei, et, t2v)

        layer.residual_alpha = 1.0
        out_alpha1 = layer(x, ei, et, t2v)

        layer.residual_alpha = 0.5
        out_alpha_half = layer(x, ei, et, t2v)

        # residual = out_alpha1 - out_alpha0; out_alpha_half should equal
        # out_alpha0 + 0.5 * residual.
        for ntype in out_alpha0:
            residual = out_alpha1[ntype] - out_alpha0[ntype]
            expected = out_alpha0[ntype] + 0.5 * residual
            assert torch.allclose(out_alpha_half[ntype], expected, atol=1e-5), (
                f"residual scaling broken for {ntype}: alpha=0.5 output "
                "should equal alpha=0 output + 0.5 * (alpha=1 output - alpha=0 output)"
            )

    def test_zero_timestamp_edges_produce_finite_residual(self) -> None:
        # Self-loop-style edges with t=0; output must be finite (no NaN/Inf).
        layer = _build_layer(residual_alpha=0.5)
        t2v = Time2Vec(dim=32)
        x, ei, _et_real = _toy_inputs()
        zero_time_dict = {rel: torch.zeros(idx.shape[1]) for rel, idx in ei.items()}
        out = layer(x, ei, zero_time_dict, t2v)
        for ntype, val in out.items():
            assert torch.isfinite(val).all(), f"non-finite values in {ntype} output"

    def test_gradient_flows_through_both_paths(self) -> None:
        # Both stock HGTConv parameters AND edge_mlp parameters must
        # receive non-zero gradients after backward.
        torch.manual_seed(1)
        layer = _build_layer(residual_alpha=0.5)
        t2v = Time2Vec(dim=32)
        x, ei, et = _toy_inputs()
        out = layer(x, ei, et, t2v)
        # Loss summed over all node types so every output element contributes.
        loss = sum(v.sum() for v in out.values())
        loss.backward()

        # HGT attention path: at least one HGTConv parameter has a gradient.
        hgt_grads = [
            p.grad for p in layer.hgt.parameters() if p.grad is not None and p.grad.abs().sum() > 0
        ]
        assert len(hgt_grads) > 0, "no gradient reached HGTConv parameters"

        # Residual MLP path: at least one edge_mlp parameter has a gradient.
        mlp_grads = [
            p.grad
            for p in layer.edge_mlp.parameters()
            if p.grad is not None and p.grad.abs().sum() > 0
        ]
        assert len(mlp_grads) > 0, "no gradient reached residual MLP parameters"

        # Time2Vec parameters must also receive gradient (residual path).
        t2v_grads = [
            p.grad for p in t2v.parameters() if p.grad is not None and p.grad.abs().sum() > 0
        ]
        assert len(t2v_grads) > 0, "no gradient reached Time2Vec parameters"


# --- Misc edge-cases --------------------------------------------------------


class TestEdgeCases:
    def test_empty_edge_index_for_one_relation_does_not_crash(self) -> None:
        # If a relation has zero edges in this batch, the residual loop
        # should silently skip it (HGTConv does too).
        layer = _build_layer()
        t2v = Time2Vec(dim=32)
        x, ei, et = _toy_inputs()
        ei[(NodeType.process.value, EdgeType.FILE_READ.value, NodeType.file.value)] = torch.zeros(
            (2, 0), dtype=torch.long
        )
        et[(NodeType.process.value, EdgeType.FILE_READ.value, NodeType.file.value)] = torch.zeros(
            (0,)
        )
        out = layer(x, ei, et, t2v)
        # Output for `file` type should still exist (zeros filled in if HGTConv
        # returned None) and be finite.
        assert torch.isfinite(out[NodeType.file.value]).all()

    def test_constructor_rejects_negative_residual_alpha(self) -> None:
        with pytest.raises(ValueError, match="residual_alpha must be >= 0"):
            HGTLayer(
                in_channels=_IN_DIM,
                metadata=_METADATA,
                residual_alpha=-0.1,
            )

    def test_constructor_rejects_invalid_dropout(self) -> None:
        with pytest.raises(ValueError, match="dropout"):
            HGTLayer(in_channels=_IN_DIM, metadata=_METADATA, dropout=1.5)

    def test_edge_type_one_hot_uses_29_dim(self) -> None:
        # Sanity guard against the off-by-N bug: the residual MLP's first
        # linear should accept time2vec_dim + 29 features = 32 + 29 = 61.
        layer = _build_layer(time2vec_dim=32)
        first_linear = layer.edge_mlp[0]
        assert first_linear.in_features == 61, (
            f"residual MLP in_features = {first_linear.in_features}; "
            "expected 61 (= time2vec 32 + EdgeType one-hot 29). "
            "If EdgeType enum was extended, update _N_EDGE_TYPES tracking."
        )
