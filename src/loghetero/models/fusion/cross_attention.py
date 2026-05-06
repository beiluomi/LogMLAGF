"""Bidirectional cross-modal attention fusion block (Phase 4 / Checkpoint 12).

Fuses BERT text-token representations with HTGN graph-node representations via
two independent multi-head cross-attention operations:

* **Text→Graph**: text tokens attend to graph nodes (text queries, graph keys/values).
* **Graph→Text**: graph nodes attend to text tokens (graph queries, text keys/values).

The caller instantiates **4 independent copies** of :class:`CrossModalAttention`,
one per BERT fusion injection layer (3 / 6 / 9 / 12).  This module is the
standalone fusion block; integration with real BERT hidden states and real HTGN
node embeddings is deferred to Checkpoint 14.

Design decisions locked by the Phase 4 launch spec
====================================================
* text_dim = 768  (BERT-base hidden size)
* graph_dim = 256  (HTGN hidden_dim)
* attn_dim = 256  (unified attention space; head_dim = attn_dim / num_heads = 32)
* num_heads = 8
* dropout = 0.1
* Bidirectional attention with independent QKV / output projections — `tg_attn`
  and `gt_attn` are separate `MultiheadAttention` instances with no weight sharing,
  and each has its own output projection (`tg_out_proj`, `gt_out_proj`). The two
  per-modality input projections (`text_proj`, `graph_proj`) and LayerNorms
  (`text_norm`, `graph_norm`) are shared across directions: a single linear projection
  is direction-agnostic and adding per-direction projections would only duplicate
  parameters without giving the two attention paths any directional capacity that
  `tg_attn` / `gt_attn` cannot already learn. (Phase 7 ablation may revisit this if
  the two paths develop conflicting gradient signals.)
* Pre-LayerNorm style: LN before the cross-attention, residual after.
* batch_first=True throughout; the (T, B, H) convention is NOT used.

Attention mask conventions
===========================
``CrossModalAttention.forward`` accepts an ``attention_mask`` of shape
``(B, T, N)`` where **True = allowed to attend**.  This is the *logically
positive* convention (opposite to ``nn.MultiheadAttention``'s attn_mask where
True = block).  Conversion happens internally.

``build_event_attention_mask`` implements the Phase-4 strict policy: a text
token may attend to a graph node only if they share the same event_id.
Phase 5+ relaxations (e.g. k-hop neighbourhood, temporal windows) are a
single-point change in that utility — the ``attention_mask`` API is stable.
"""

from __future__ import annotations

import torch
from torch import nn

# ---------------------------------------------------------------------------
# Cross-modal attention mask utility
# ---------------------------------------------------------------------------


def build_event_attention_mask(
    text_event_ids: torch.Tensor,
    graph_event_ids: torch.Tensor,
    text_padding_mask: torch.Tensor | None = None,
    graph_padding_mask: torch.Tensor | None = None,
) -> torch.Tensor:
    """Build a per-event attention mask for cross-modal attention.

    Phase-4 strict policy: a text token attends to a graph node if and only if
    they share the same *event_id*.  Padding positions (event_id == -1, or
    explicitly zeroed by the padding masks) yield ``False`` on both axes.

    Args:
        text_event_ids: ``(B, T)`` long tensor.  -1 marks padding positions.
        graph_event_ids: ``(B, N)`` long tensor.  -1 marks padding positions.
        text_padding_mask: optional ``(B, T)`` bool; ``True`` = real token.
            When provided, text positions with ``False`` are forced to
            ``False`` in the output mask regardless of event_id equality.
        graph_padding_mask: optional ``(B, N)`` bool; ``True`` = real node.
            Same semantics as ``text_padding_mask``.

    Returns:
        ``(B, T, N)`` bool tensor where ``True`` means the (text, graph)
        pair is allowed to attend.
    """
    # text_event_ids: (B, T) → (B, T, 1)
    # graph_event_ids: (B, N) → (B, 1, N)
    # equality check broadcasts to (B, T, N)
    mask: torch.Tensor = text_event_ids.unsqueeze(2) == graph_event_ids.unsqueeze(1)

    # -1 padding sentinel — a -1 == -1 match must NOT be treated as valid.
    padding_match = (text_event_ids.unsqueeze(2) == -1) | (graph_event_ids.unsqueeze(1) == -1)
    mask = mask & ~padding_match

    # Apply explicit padding masks if provided.
    if text_padding_mask is not None:
        # (B, T) → (B, T, 1) broadcast
        mask = mask & text_padding_mask.unsqueeze(2)
    if graph_padding_mask is not None:
        # (B, N) → (B, 1, N) broadcast
        mask = mask & graph_padding_mask.unsqueeze(1)

    return mask


# ---------------------------------------------------------------------------
# Main module
# ---------------------------------------------------------------------------


class CrossModalAttention(nn.Module):
    """Single bidirectional cross-modal attention fusion block.

    Caller instantiates 4 copies, one per BERT fusion layer (3 / 6 / 9 / 12).

    Architecture (pre-LN style, both directions):

    Text→Graph path::

        q = LN(text_hidden) @ W_q_tg      (B, T, attn_dim)
        k = LN(graph_hidden) @ W_k_tg     (B, N, attn_dim)
        v = LN(graph_hidden) @ W_v_tg     (B, N, attn_dim)
        ctx_text = MultiheadAttn(q, k, v)  (B, T, attn_dim)
        fused_text = text_hidden + dropout(ctx_text @ W_o_tg)

    Graph→Text path (symmetric with independent parameters)::

        q = LN(graph_hidden) @ W_q_gt      (B, N, attn_dim)
        k = LN(text_hidden) @ W_k_gt       (B, T, attn_dim)
        v = LN(text_hidden) @ W_v_gt       (B, T, attn_dim)
        ctx_graph = MultiheadAttn(q, k, v)  (B, N, attn_dim)
        fused_graph = graph_hidden + dropout(ctx_graph @ W_o_gt)

    Mask convention: ``attention_mask`` is ``True`` where attention is
    *allowed*; internally converted for ``nn.MultiheadAttention``.
    """

    def __init__(
        self,
        text_dim: int = 768,
        graph_dim: int = 256,
        attn_dim: int = 256,
        num_heads: int = 8,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if attn_dim % num_heads != 0:
            raise ValueError(f"attn_dim ({attn_dim}) must be divisible by num_heads ({num_heads}).")

        self.text_dim = text_dim
        self.graph_dim = graph_dim
        self.attn_dim = attn_dim
        self.num_heads = num_heads

        # ---- Input projections ------------------------------------------------
        # Both text and graph are projected into the shared attn_dim space.
        self.text_proj = nn.Linear(text_dim, attn_dim, bias=False)
        self.graph_proj = nn.Linear(graph_dim, attn_dim, bias=False)

        # ---- Pre-LN norms (one per modality, shared across directions) --------
        self.text_norm = nn.LayerNorm(text_dim)
        self.graph_norm = nn.LayerNorm(graph_dim)

        # ---- Text→Graph cross-attention (independent params) ------------------
        # queries = projected text, keys/values = projected graph
        self.tg_attn = nn.MultiheadAttention(
            embed_dim=attn_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True,
        )
        self.tg_out_proj = nn.Linear(attn_dim, text_dim)

        # ---- Graph→Text cross-attention (independent params) ------------------
        # queries = projected graph, keys/values = projected text
        self.gt_attn = nn.MultiheadAttention(
            embed_dim=attn_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True,
        )
        self.gt_out_proj = nn.Linear(attn_dim, graph_dim)

        # ---- Output dropout ---------------------------------------------------
        self.dropout = nn.Dropout(dropout)

    # -----------------------------------------------------------------------

    def forward(
        self,
        text_hidden: torch.Tensor,
        graph_hidden: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        text_padding_mask: torch.Tensor | None = None,
        graph_padding_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, dict[str, torch.Tensor]]:
        """Bidirectional cross-modal attention forward pass.

        Args:
            text_hidden: ``(B, T, text_dim)`` — BERT hidden states at this layer.
            graph_hidden: ``(B, N, graph_dim)`` — graph node features (already padded).
            attention_mask: optional ``(B, T, N)`` bool; ``True`` = allowed to attend.
                When ``None`` every (text, graph) pair can attend.
            text_padding_mask: optional ``(B, T)`` bool; ``True`` = real token.
                Used to build the key-padding-mask for the Graph→Text direction.
            graph_padding_mask: optional ``(B, N)`` bool; ``True`` = real graph node.
                Used to build the key-padding-mask for the Text→Graph direction.

        Returns:
            ``(fused_text, fused_graph, attn_weights_dict)`` where:

            * ``fused_text``: ``(B, T, text_dim)`` — residual-added text output.
            * ``fused_graph``: ``(B, N, graph_dim)`` — residual-added graph output.
            * ``attn_weights_dict``: ``{'text_to_graph': (B, num_heads, T, N),
              'graph_to_text': (B, num_heads, N, T)}``.
        """
        batch_size, seq_len, _ = text_hidden.shape
        _, num_nodes, _ = graph_hidden.shape

        # ---- Pre-LN projections ----------------------------------------------
        text_ln = self.text_norm(text_hidden)  # (B, T, text_dim)
        graph_ln = self.graph_norm(graph_hidden)  # (B, N, graph_dim)

        text_proj = self.text_proj(text_ln)  # (B, T, attn_dim)
        graph_proj = self.graph_proj(graph_ln)  # (B, N, attn_dim)

        # ---- Build MHA-compatible masks ---------------------------------------
        # nn.MultiheadAttention attn_mask: True = block (additive -inf).
        # Our attention_mask: True = allow.  Convert: mha_mask = ~attention_mask.
        # Shape expected by MHA: (B*num_heads, T, N) or (T, N) for attn_mask.
        # We use the (B*H, T, N) form to support per-sample masks.

        tg_attn_mask: torch.Tensor | None = None  # for text→graph
        gt_attn_mask: torch.Tensor | None = None  # for graph→text

        if attention_mask is not None:
            # attention_mask: (B, T, N) bool, True = allow
            # expand over heads: (B, T, N) → (B, 1, T, N) → (B*H, T, N)
            block_mask = ~attention_mask  # True = block
            tg_attn_mask = block_mask.unsqueeze(1).expand(
                batch_size, self.num_heads, seq_len, num_nodes
            )
            tg_attn_mask = tg_attn_mask.reshape(batch_size * self.num_heads, seq_len, num_nodes)
            # Transpose for graph→text direction: (B*H, N, T)
            gt_attn_mask = tg_attn_mask.transpose(1, 2).contiguous()

        # Key-padding masks (True = ignore key in MHA convention).
        tg_key_padding: torch.Tensor | None = None  # keys are graph nodes
        gt_key_padding: torch.Tensor | None = None  # keys are text tokens

        if graph_padding_mask is not None:
            tg_key_padding = ~graph_padding_mask  # (B, N)
        if text_padding_mask is not None:
            gt_key_padding = ~text_padding_mask  # (B, T)

        # ---- Text→Graph cross-attention --------------------------------------
        # query = text_proj (B, T, attn_dim)
        # key/value = graph_proj (B, N, attn_dim)
        tg_ctx, tg_weights = self.tg_attn(
            query=text_proj,
            key=graph_proj,
            value=graph_proj,
            attn_mask=tg_attn_mask,
            key_padding_mask=tg_key_padding,
            need_weights=True,
            average_attn_weights=False,  # keep per-head weights
        )
        # tg_ctx: (B, T, attn_dim), tg_weights: (B, num_heads, T, N)
        # Guard: rows where ALL keys are masked produce nan (softmax of all -inf);
        # replace with 0 so those query tokens contribute nothing to the residual.
        tg_ctx = torch.nan_to_num(tg_ctx, nan=0.0)
        tg_weights = torch.nan_to_num(tg_weights, nan=0.0)

        fused_text = text_hidden + self.dropout(self.tg_out_proj(tg_ctx))

        # ---- Graph→Text cross-attention --------------------------------------
        # query = graph_proj (B, N, attn_dim)
        # key/value = text_proj (B, T, attn_dim)
        gt_ctx, gt_weights = self.gt_attn(
            query=graph_proj,
            key=text_proj,
            value=text_proj,
            attn_mask=gt_attn_mask,
            key_padding_mask=gt_key_padding,
            need_weights=True,
            average_attn_weights=False,  # keep per-head weights
        )
        # gt_ctx: (B, N, attn_dim), gt_weights: (B, num_heads, N, T)
        # Same nan-guard for fully-masked graph query rows.
        gt_ctx = torch.nan_to_num(gt_ctx, nan=0.0)
        gt_weights = torch.nan_to_num(gt_weights, nan=0.0)

        fused_graph = graph_hidden + self.dropout(self.gt_out_proj(gt_ctx))

        attn_weights_dict: dict[str, torch.Tensor] = {
            "text_to_graph": tg_weights,
            "graph_to_text": gt_weights,
        }

        return fused_text, fused_graph, attn_weights_dict

    # -----------------------------------------------------------------------
    # Diagnostics
    # -----------------------------------------------------------------------

    def parameter_breakdown(self) -> dict[str, int]:
        """Return per-component parameter count for checkpoint perf reports."""

        def _count(m: nn.Module) -> int:
            return sum(p.numel() for p in m.parameters())

        return {
            "text_proj": _count(self.text_proj),
            "graph_proj": _count(self.graph_proj),
            "text_norm": _count(self.text_norm),
            "graph_norm": _count(self.graph_norm),
            "tg_attn": _count(self.tg_attn),
            "tg_out_proj": _count(self.tg_out_proj),
            "gt_attn": _count(self.gt_attn),
            "gt_out_proj": _count(self.gt_out_proj),
            "total": sum(p.numel() for p in self.parameters()),
        }
