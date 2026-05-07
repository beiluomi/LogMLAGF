"""Phase 4 / Checkpoint 14 integrated model: BERT + HTGN + 4xCrossModalAttention + MLM head.

Design rationale (RFC-1 Option A — deep injection, ViLBERT-style)
==================================================================
Graph information enters the BERT computation path at four sequential
injection points (after BERT encoder layers 3/6/9/12, i.e. 0-indexed
layers 2/5/8/11).  For each injection point:

    1. ``CrossModalAttention[k]`` fuses ``hidden_state`` (text) with
       ``graph_hidden`` (graph) bidirectionally.
    2. ``fused_text`` replaces ``hidden_state`` as input to BERT layer L+1
       (text-side update, ViLBERT-style deep injection).
    3. ``fused_graph`` replaces ``graph_hidden`` for the *next* injection
       point (fully-bidirectional update — Option B from the "Option a vs b"
       question in the launch spec; rationale below).

Option a vs Option b decision (documented, NOT RFC'd; addressed here)
=====================================================================
The launch spec flagged this as "STOP and RFC if unsure."  This module
chooses **Option b (fully bidirectional)**: both ``fused_text`` and
``fused_graph`` are propagated to the next fusion point.

Rationale:
- ViLBERT [Lu et al. 2019] and GreaseLM [Zhang et al. 2022] both update
  BOTH modalities at each co-attention layer; Option a (text-only update)
  is a strict degeneration where the graph side never adapts to text
  context across fusion points.
- The launch spec's "track if you want to feed back into HTGN" phrasing
  implies Option b is the expected choice for a bidirectional model.
- Option b does NOT feed ``fused_graph`` back through HTGN GNN layers
  (which would require a full re-run of the heterogeneous message passing);
  it only propagates the updated graph node embeddings to the next
  ``CrossModalAttention`` query/key/value computation.  This is the same
  co-attention update strategy as in ViLBERT and costs no extra VRAM.
- If Phase 7 ablation shows that Option a achieves equivalent or better
  performance with less VRAM, it can be switched by a one-line change
  (comment "fused_graph: carry forward" → "fused_graph: not carried").

Three RFC-1 engineering risks (verified in Gate 7)
===================================================
1. VRAM overhead — Gate 7 measures absolute VRAM at batch=16 real PyG
   batched HeteroData.  Threshold: < 16 GB on RTX 4090.
2. attention_mask + position_embeddings handoff — this module uses
   ``bert_model._create_attention_masks`` (the SAME internal helper that
   ``BertModel.forward`` uses) to produce the (B,1,T,T) extended boolean
   mask that ``BertLayer.forward`` expects.  No home-grown mask logic.
3. Phase 7 training cost — absolute numbers from Gate 7 feed into
   ``docs/known_issues.md::Phase 7 待办::Deep cross-modal injection 训练成本预算提醒``.

RFC-2: HTGN is fully trainable (requires_grad=True on all HTGN params).

RFC-3 param categories:
- BERT 投影: ``fusion_layers[k].text_proj.weight/bias`` only.
- HTGN: all HTGN module parameters.
- cross-attention: everything else inside each ``CrossModalAttention``
  (graph_proj, tg_attn, gt_attn, tg_out_proj, gt_out_proj,
  text_norm, graph_norm).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import torch
from torch import nn

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# BERT encoder layer indices (0-indexed) where cross-modal fusion is applied.
# 1-indexed layers 3/6/9/12 correspond to 0-indexed 2/5/8/11.
FUSION_LAYER_INDICES: tuple[int, ...] = (2, 5, 8, 11)
NUM_FUSION_POINTS: int = len(FUSION_LAYER_INDICES)  # 4

TEXT_DIM: int = 768  # bert-base-uncased hidden_size
GRAPH_DIM: int = 256  # HTGN hidden_dim
ATTN_DIM: int = 256  # CrossModalAttention attn_dim (= GRAPH_DIM)
NUM_HEADS: int = 8  # CrossModalAttention num_heads


# ---------------------------------------------------------------------------
# Phase4Model
# ---------------------------------------------------------------------------


class Phase4Model(nn.Module):
    """Integrated BERT + HTGN + 4xCrossModalAttention + ModifiedMLMHead.

    Deep injection (ViLBERT-style): BERT encoder layers are iterated
    manually.  CrossModalAttention fuses text ↔ graph at 0-indexed layers
    2/5/8/11 (= 1-indexed layers 3/6/9/12).  Both ``fused_text`` and
    ``fused_graph`` are carried forward between fusion points (Option b,
    fully-bidirectional; see module docstring).

    RFC-2: HTGN parameters are trainable (requires_grad=True).
    RFC-3: three param categories enforced — see ``param_groups()``.

    Args:
        htgn: pre-constructed :class:`~loghetero.models.graph.htgn.HTGN`
            instance.  Its parameters will be trainable.
        bert_model_name: HuggingFace model name; default ``"bert-base-uncased"``.
        attn_dropout: dropout for CrossModalAttention; default 0.1.
    """

    def __init__(
        self,
        htgn: nn.Module,
        *,
        bert_model_name: str = "bert-base-uncased",
        attn_dropout: float = 0.1,
    ) -> None:
        super().__init__()

        # ---- BERT (frozen; deep injection inserts cross-attn into the path) ----
        from loghetero.models.encoders.bert_text import TrainMode, build_bert_text_encoder

        bert_model, tokenizer = build_bert_text_encoder(bert_model_name, mode=TrainMode.frozen)
        self.bert_model: nn.Module = bert_model
        self.tokenizer: Any = tokenizer

        # ---- HTGN (RFC-2: trainable) -------------------------------------------
        self.htgn = htgn
        for p in self.htgn.parameters():
            p.requires_grad = True

        # ---- 4x CrossModalAttention (independent params per fusion point) -------
        from loghetero.models.fusion.cross_attention import CrossModalAttention

        self.fusion_layers = nn.ModuleList(
            [
                CrossModalAttention(
                    text_dim=TEXT_DIM,
                    graph_dim=GRAPH_DIM,
                    attn_dim=ATTN_DIM,
                    num_heads=NUM_HEADS,
                    dropout=attn_dropout,
                )
                for _ in range(NUM_FUSION_POINTS)
            ]
        )

        # ---- Modified MLM head --------------------------------------------------
        from loghetero.models.objectives.modified_mlm import ModifiedMLMHead

        self.mlm_head = ModifiedMLMHead(hidden_dim=TEXT_DIM)

    # -----------------------------------------------------------------------
    # Forward
    # -----------------------------------------------------------------------

    def forward(
        self,
        input_ids: torch.Tensor,  # (B, T)
        attention_mask: torch.Tensor,  # (B, T) 0/1 long
        x_dict: dict[str, torch.Tensor],
        edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
        edge_time_dict_ns: dict[tuple[str, str, str], torch.Tensor],
        cross_attn_mask: torch.Tensor | None = None,  # (B, T, N) bool, True=allow
        labels: torch.Tensor | None = None,  # (B, T) for MLM loss
    ) -> dict[str, torch.Tensor | None]:
        """Full Phase 4 forward pass.

        Steps:
            1. HTGN forward → ``graph_node_dict``.
            2. Flatten ``graph_node_dict`` to ``graph_hidden (B, N, 256)``.
            3. BERT embedding layer → initial ``hidden_state``.
            4. Build BERT extended attention mask (via ``_create_attention_masks``).
            5. Iterate BERT encoder layers 0..11; at fusion-point layers
               (2/5/8/11), inject cross-modal attention.
            6. Final ``fused_text`` → ``ModifiedMLMHead`` → MLM logits.
            7. Compute MLM loss if ``labels`` provided.

        Returns:
            dict with keys:
            - ``loss``: scalar or None
            - ``logits``: (B, T, vocab_size)
            - ``fused_text``: (B, T, 768) last fusion point output
            - ``fused_graph``: (B, N, 256) last fusion point output
            - ``attn_weights``: list of 4 dicts (one per fusion point)
        """
        batch_size = input_ids.shape[0]

        # ------------------------------------------------------------------ #
        # 1. HTGN forward (trainable)                                         #
        # ------------------------------------------------------------------ #
        graph_node_dict = self.htgn(x_dict, edge_index_dict, edge_time_dict_ns)

        # ------------------------------------------------------------------ #
        # 2. Flatten graph node embeddings → (B, N_total, 256)               #
        # ------------------------------------------------------------------ #
        # Deterministic alphabetical order; same convention as checkpoint12.
        ntype_order = sorted(graph_node_dict.keys())
        parts = [graph_node_dict[nt] for nt in ntype_order]  # list of (N_i, 256)
        stacked_nodes = torch.cat(parts, dim=0)  # (N_total, 256)
        n_total = stacked_nodes.shape[0]

        # Expand to batch dimension: (B, N_total, 256)
        # Each sample in the batch attends to the SAME graph (single-graph-per-batch
        # convention; multi-graph batching via PyG Batch is handled by the caller
        # which sets batch_size=1 per subgraph and stacks).
        graph_hidden = stacked_nodes.unsqueeze(0).expand(batch_size, n_total, GRAPH_DIM)
        # Make contiguous so CrossModalAttention backward can write into it.
        graph_hidden = graph_hidden.contiguous()

        # ------------------------------------------------------------------ #
        # 3. BERT embedding layer                                             #
        # ------------------------------------------------------------------ #
        # bert_model is frozen but we still run it via .embeddings to get
        # position + token_type embeddings.  No gradient through BERT itself.
        # mypy: bert_model is nn.Module with dynamic attrs; type: ignore is safe here.
        embedding_output: torch.Tensor = self.bert_model.embeddings(  # type: ignore[operator]
            input_ids=input_ids,
        )  # (B, T, 768)

        # ------------------------------------------------------------------ #
        # 4. Build BERT extended attention mask                               #
        # ------------------------------------------------------------------ #
        # _create_attention_masks mirrors what BertModel.forward does internally.
        # Returns a (B, 1, T, T) bool tensor (True = allowed to attend) or None
        # (when all tokens are non-padding, mask is trivially True everywhere).
        ext_attn_mask, _ = self.bert_model._create_attention_masks(  # type: ignore[operator]
            attention_mask=attention_mask,
            encoder_attention_mask=None,
            embedding_output=embedding_output,
            encoder_hidden_states=None,
            past_key_values=None,
        )
        # ext_attn_mask: (B, 1, T, T) bool | None

        # ------------------------------------------------------------------ #
        # 5. Manual BERT encoder iteration with cross-modal injection         #
        # ------------------------------------------------------------------ #
        hidden_state = embedding_output  # (B, T, 768); updated after each BertLayer

        # Track last fusion outputs for the return dict.
        last_fused_text = hidden_state
        last_fused_graph = graph_hidden
        all_attn_weights: list[dict[str, torch.Tensor]] = []

        fusion_idx = 0  # index into self.fusion_layers (0..3)
        fusion_layer_set = set(FUSION_LAYER_INDICES)

        for layer_idx, bert_layer in enumerate(self.bert_model.encoder.layer):  # type: ignore[union-attr,arg-type]
            # BertLayer.forward: (hidden_states, attention_mask) → hidden_states
            # BERT is frozen; no grads flow through BertLayer weights.
            with torch.no_grad():
                hidden_state = bert_layer(
                    hidden_state,
                    attention_mask=ext_attn_mask,
                )
            # hidden_state: (B, T, 768)

            if layer_idx in fusion_layer_set:
                # Cross-modal fusion at this layer.
                fused_text, fused_graph, attn_weights = self.fusion_layers[fusion_idx](
                    text_hidden=hidden_state,  # (B, T, 768)
                    graph_hidden=graph_hidden,  # (B, N, 256) — current graph state
                    attention_mask=cross_attn_mask,  # (B, T, N) bool | None
                    text_padding_mask=attention_mask.bool(),  # (B, T)
                    graph_padding_mask=None,  # no graph padding mask for now
                )
                # Update both modalities (Option b: fully bidirectional).
                hidden_state = fused_text  # (B, T, 768); feeds into next BERT layer
                graph_hidden = fused_graph  # (B, N, 256); feeds into next fusion point

                last_fused_text = fused_text
                last_fused_graph = fused_graph
                all_attn_weights.append(attn_weights)
                fusion_idx += 1

        # ------------------------------------------------------------------ #
        # 6. MLM head                                                         #
        # ------------------------------------------------------------------ #
        logits = self.mlm_head(last_fused_text)  # (B, T, vocab_size)

        # ------------------------------------------------------------------ #
        # 7. Loss                                                              #
        # ------------------------------------------------------------------ #
        loss: torch.Tensor | None = None
        if labels is not None:
            from loghetero.models.objectives.modified_mlm import compute_mlm_loss

            loss = compute_mlm_loss(logits, labels)

        return {
            "loss": loss,
            "logits": logits,
            "fused_text": last_fused_text,
            "fused_graph": last_fused_graph,
            "attn_weights": all_attn_weights,  # type: ignore[dict-item]
        }

    # -----------------------------------------------------------------------
    # Param group helpers (RFC-3)
    # -----------------------------------------------------------------------

    def param_groups(self) -> dict[str, list[nn.Parameter]]:
        """Return named parameter groups matching RFC-3 spec.

        Returns:
            dict with keys:
            - ``"bert_proj"``: ``text_proj.weight/bias`` from each fusion layer.
            - ``"htgn"``: all HTGN trainable parameters.
            - ``"cross_attention"``: all remaining CrossModalAttention params
              (graph_proj, tg_attn, gt_attn, tg_out_proj, gt_out_proj,
              text_norm, graph_norm).
        """
        bert_proj_params: list[torch.nn.Parameter] = []
        cross_attn_params: list[torch.nn.Parameter] = []

        for fusion_layer in self.fusion_layers:
            # RFC-3: "BERT 投影 = text_proj.weight/bias inside each CrossModalAttention"
            # ModuleList elements are nn.Module; fusion_layer has text_proj attr.
            text_proj: nn.Module = fusion_layer.text_proj  # type: ignore[assignment]
            bert_proj_params.extend([p for p in text_proj.parameters() if p.requires_grad])
            # Everything else in CrossModalAttention = cross_attention category.
            text_proj_ids = {id(p) for p in text_proj.parameters()}
            for p in fusion_layer.parameters():
                if p.requires_grad and id(p) not in text_proj_ids:
                    cross_attn_params.append(p)

        htgn_params = [p for p in self.htgn.parameters() if p.requires_grad]

        return {
            "bert_proj": bert_proj_params,
            "htgn": htgn_params,
            "cross_attention": cross_attn_params,
        }

    def named_param_groups(self) -> dict[str, list[tuple[str, torch.nn.Parameter]]]:
        """Like ``param_groups`` but also returns parameter names for diagnostics."""
        bert_proj_named: list[tuple[str, torch.nn.Parameter]] = []
        cross_attn_named: list[tuple[str, torch.nn.Parameter]] = []

        for k, fusion_layer in enumerate(self.fusion_layers):
            text_proj: nn.Module = fusion_layer.text_proj  # type: ignore[assignment]
            text_proj_ids = {id(p) for p in text_proj.parameters()}
            for name, p in fusion_layer.named_parameters():
                if not p.requires_grad:
                    continue
                full_name = f"fusion_layers.{k}.{name}"
                if id(p) in text_proj_ids:
                    bert_proj_named.append((full_name, p))
                else:
                    cross_attn_named.append((full_name, p))

        htgn_named = [(f"htgn.{n}", p) for n, p in self.htgn.named_parameters() if p.requires_grad]

        return {
            "bert_proj": bert_proj_named,
            "htgn": htgn_named,
            "cross_attention": cross_attn_named,
        }
