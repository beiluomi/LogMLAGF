"""Phase 4 / Checkpoint 14 unit tests for Phase4Model.

Tests are intentionally lightweight (synthetic data, CPU, batch=2) so they
finish in seconds without requiring a GPU or real M3_h2 data.

Coverage:
    - Phase4Model instantiates correctly.
    - Forward pass returns expected output keys and tensor shapes.
    - Backward pass (loss.backward()) succeeds with no exception.
    - param_groups() covers all three RFC-3 categories with non-empty lists.
    - No gradient leaks from frozen BERT into fusion or HTGN parameters.
"""

from __future__ import annotations

import pytest
import torch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_minimal_htgn(device: torch.device) -> object:
    """Construct a minimal HTGN with 1-layer on a trivial 2-node graph."""
    from loghetero.data.parsers.base import NodeType
    from loghetero.models.graph.htgn import HTGN

    node_types = ["file", "process"]
    edge_types = [("process", "access", "file")]
    metadata = (node_types, edge_types)

    num_nodes: dict[NodeType, int] = {nt: 4 for nt in NodeType}

    htgn = HTGN(
        in_channels=32,
        metadata=metadata,
        num_nodes_per_type=num_nodes,
        hidden_dim=256,
        n_layers=1,
        num_heads=4,
        dropout=0.0,
        time2vec_dim=16,
        residual_alpha=0.5,
        layer_decay_gamma=(1.0,),
        memory_node_types=(NodeType.process,),
        raw_msg_dim=32,
    ).to(device)
    return htgn


def _make_synthetic_batch(
    batch_size: int = 2,
    seq_len: int = 16,
    n_nodes: int = 6,
    device: torch.device = torch.device("cpu"),
) -> tuple[
    torch.Tensor,
    torch.Tensor,
    dict[str, torch.Tensor],
    dict[tuple[str, str, str], torch.Tensor],
    dict[tuple[str, str, str], torch.Tensor],
]:
    """Build minimal synthetic inputs for Phase4Model.forward."""
    input_ids = torch.randint(1000, 29000, (batch_size, seq_len), device=device)
    # First/last positions = CLS/SEP
    input_ids[:, 0] = 101
    input_ids[:, -1] = 102
    attention_mask = torch.ones(batch_size, seq_len, dtype=torch.long, device=device)
    # Second sample has 2 padding tokens at the end.
    attention_mask[1, -2:] = 0

    x_dict = {
        "process": torch.randn(3, 32, device=device),
        "file": torch.randn(3, 32, device=device),
    }
    edge_index = torch.tensor([[0, 1, 2], [0, 1, 2]], dtype=torch.long, device=device)
    edge_time = torch.randint(int(1e12), int(2e12), (3,), dtype=torch.long, device=device)

    edge_index_dict = {("process", "access", "file"): edge_index}
    edge_time_dict_ns = {("process", "access", "file"): edge_time}

    return input_ids, attention_mask, x_dict, edge_index_dict, edge_time_dict_ns


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_phase4_model_instantiates() -> None:
    """Phase4Model can be constructed with a minimal HTGN."""
    from loghetero.models.phase4_model import Phase4Model

    device = torch.device("cpu")
    htgn = _make_minimal_htgn(device)
    model = Phase4Model(htgn=htgn)  # type: ignore[arg-type]
    assert isinstance(model, Phase4Model)
    # 4 fusion layers expected.
    assert len(model.fusion_layers) == 4


@pytest.mark.integration
def test_phase4_model_forward_shapes() -> None:
    """Forward pass returns correct tensor shapes."""
    from loghetero.models.phase4_model import Phase4Model

    device = torch.device("cpu")
    htgn = _make_minimal_htgn(device)
    model = Phase4Model(htgn=htgn)  # type: ignore[arg-type]
    model.train()

    batch_size = 2
    seq_len = 16

    input_ids, attention_mask, x_dict, edge_index_dict, edge_time_dict_ns = _make_synthetic_batch(
        batch_size=batch_size, seq_len=seq_len, device=device
    )

    # Build labels: -100 everywhere except 3 positions.
    labels = torch.full((batch_size, seq_len), -100, dtype=torch.long)
    labels[:, 5] = input_ids[:, 5]
    labels[:, 8] = input_ids[:, 8]

    out = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        x_dict=x_dict,
        edge_index_dict=edge_index_dict,
        edge_time_dict_ns=edge_time_dict_ns,
        labels=labels,
    )

    # Output keys.
    assert "loss" in out
    assert "logits" in out
    assert "fused_text" in out
    assert "fused_graph" in out
    assert "attn_weights" in out

    # Shape checks.
    assert out["loss"] is not None
    assert out["loss"].ndim == 0, "loss should be scalar"

    logits = out["logits"]
    assert logits.shape == (batch_size, seq_len, 30678), f"logits shape mismatch: {logits.shape}"

    fused_text = out["fused_text"]
    assert fused_text.shape == (
        batch_size,
        seq_len,
        768,
    ), f"fused_text shape mismatch: {fused_text.shape}"

    fused_graph = out["fused_graph"]
    # N_total = 3 process + 3 file = 6
    assert fused_graph.ndim == 3
    assert fused_graph.shape[0] == batch_size
    assert fused_graph.shape[2] == 256

    # 4 fusion-point attn_weights.
    assert len(out["attn_weights"]) == 4  # type: ignore[arg-type]


@pytest.mark.integration
def test_phase4_model_backward_no_exception() -> None:
    """loss.backward() completes without error."""
    from loghetero.models.phase4_model import Phase4Model

    device = torch.device("cpu")
    htgn = _make_minimal_htgn(device)
    model = Phase4Model(htgn=htgn)  # type: ignore[arg-type]
    model.train()

    input_ids, attention_mask, x_dict, edge_index_dict, edge_time_dict_ns = _make_synthetic_batch(
        device=device
    )
    labels = torch.full((2, 16), -100, dtype=torch.long)
    labels[:, 5] = input_ids[:, 5]

    out = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        x_dict=x_dict,
        edge_index_dict=edge_index_dict,
        edge_time_dict_ns=edge_time_dict_ns,
        labels=labels,
    )
    out["loss"].backward()  # type: ignore[union-attr]

    # Verify no NaN/Inf in fused_text.
    assert not torch.isnan(out["fused_text"]).any(), "NaN in fused_text"
    assert not torch.isinf(out["fused_text"]).any(), "Inf in fused_text"


@pytest.mark.integration
def test_param_groups_rfc3() -> None:
    """param_groups() returns all three RFC-3 categories, each non-empty."""
    from loghetero.models.phase4_model import Phase4Model

    device = torch.device("cpu")
    htgn = _make_minimal_htgn(device)
    model = Phase4Model(htgn=htgn)  # type: ignore[arg-type]

    groups = model.param_groups()
    assert "bert_proj" in groups
    assert "htgn" in groups
    assert "cross_attention" in groups

    assert len(groups["bert_proj"]) > 0, "bert_proj group is empty"
    assert len(groups["htgn"]) > 0, "htgn group is empty"
    assert len(groups["cross_attention"]) > 0, "cross_attention group is empty"

    # bert_proj should NOT contain graph_proj parameters.
    # Verify by checking that bert_proj params are 1D bias or 2D (768, 256) weight.
    for p in groups["bert_proj"]:
        # text_proj is Linear(768, 256, bias=False) so weight shape (256, 768).
        assert p.shape in [(256, 768), (256,)], f"Unexpected bert_proj param shape: {p.shape}"


@pytest.mark.integration
def test_bert_params_have_no_grad() -> None:
    """BERT backbone parameters must NOT receive gradients (frozen)."""
    from loghetero.models.phase4_model import Phase4Model

    device = torch.device("cpu")
    htgn = _make_minimal_htgn(device)
    model = Phase4Model(htgn=htgn)  # type: ignore[arg-type]
    model.train()

    input_ids, attention_mask, x_dict, edge_index_dict, edge_time_dict_ns = _make_synthetic_batch(
        device=device
    )
    labels = torch.full((2, 16), -100, dtype=torch.long)
    labels[:, 5] = input_ids[:, 5]

    out = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        x_dict=x_dict,
        edge_index_dict=edge_index_dict,
        edge_time_dict_ns=edge_time_dict_ns,
        labels=labels,
    )
    out["loss"].backward()  # type: ignore[union-attr]

    # All BERT backbone parameters should have requires_grad=False.
    for name, p in model.bert_model.named_parameters():
        assert not p.requires_grad, f"BERT param {name} unexpectedly requires grad"
        assert p.grad is None, f"BERT param {name} received a gradient"


@pytest.mark.integration
def test_htgn_params_are_trainable() -> None:
    """RFC-2: HTGN parameters must be trainable (requires_grad=True)."""
    from loghetero.models.phase4_model import Phase4Model

    device = torch.device("cpu")
    htgn = _make_minimal_htgn(device)
    model = Phase4Model(htgn=htgn)  # type: ignore[arg-type]

    for name, p in model.htgn.named_parameters():
        assert p.requires_grad, f"HTGN param {name} is frozen (requires_grad=False)"


@pytest.mark.integration
def test_forward_no_labels_returns_none_loss() -> None:
    """When labels=None, loss should be None in the output dict."""
    from loghetero.models.phase4_model import Phase4Model

    device = torch.device("cpu")
    htgn = _make_minimal_htgn(device)
    model = Phase4Model(htgn=htgn)  # type: ignore[arg-type]
    model.eval()

    input_ids, attention_mask, x_dict, edge_index_dict, edge_time_dict_ns = _make_synthetic_batch(
        device=device
    )

    with torch.no_grad():
        out = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            edge_time_dict_ns=edge_time_dict_ns,
        )

    assert out["loss"] is None


@pytest.mark.integration
def test_four_attn_weight_dicts() -> None:
    """Forward returns exactly 4 attn_weight dicts, each with the correct keys."""
    from loghetero.models.phase4_model import Phase4Model

    device = torch.device("cpu")
    htgn = _make_minimal_htgn(device)
    model = Phase4Model(htgn=htgn)  # type: ignore[arg-type]
    model.eval()

    input_ids, attention_mask, x_dict, edge_index_dict, edge_time_dict_ns = _make_synthetic_batch(
        device=device
    )

    with torch.no_grad():
        out = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            x_dict=x_dict,
            edge_index_dict=edge_index_dict,
            edge_time_dict_ns=edge_time_dict_ns,
        )

    weights = out["attn_weights"]
    assert len(weights) == 4  # type: ignore[arg-type]
    for w_dict in weights:  # type: ignore[union-attr]
        assert "text_to_graph" in w_dict
        assert "graph_to_text" in w_dict
