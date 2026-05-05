"""HGT layer wrapper with Option-C temporal-residual channel (Phase 3 Checkpoint 7).

PyG 2.7's :class:`HGTConv` does not accept ``edge_attr`` in its forward
signature -- empirically verified at Checkpoint 7 startup. The Phase 3 launch
spec assumed the canonical "Time2Vec || EdgeType-one-hot -> Linear(57, 32) ->
HGTConv(edge_attr)" path was available; it is not. The project owner pulled
an RFC and locked **Option C** as the resolution:

    y_dst[v] = HGTConv(x_dict)[v]
             + residual_alpha * sum_{(u,v) ∈ E_r}
                                    MLP(concat(time2vec(t_uv), eid_onehot_r))

That is, run stock HGTConv for the heterogeneous-attention path AND compute
a parallel temporal-residual channel that scatter-adds an MLP(edge feature)
contribution onto the destination nodes. Time information thus has its own
pathway, decoupled from the attention computation itself; combined with the
TGN node memory (Checkpoint 8) and the cross-modal attention queries
(Phase 4), this gives the "multi-pathway temporal modeling" story we want
in the paper.

Full RFC text + four-option analysis: see ``docs/known_issues.md`` ::
"HGTConv edge_attr 接口限制 + Option C 残差通道决议".

Design knobs (all sourced from ``configs/model/graph/htgn.yaml``):

* ``hidden_dim``       (256)  - HGTConv out_channels and residual MLP output.
* ``num_heads``        (8)    - HGTConv heads.
* ``dropout``          (0.1)  - applied on HGTConv output.
* ``time2vec_dim``     (32)   - time encoding dimension.
* ``residual_alpha``   (0.5)  - **fixed** residual scale; sweep [0.1, 0.3,
                                 0.5, 1.0] reserved for Phase 11. NOT learnable.
                                 ``residual_alpha=0`` short-circuits the
                                 residual path entirely (decision-4.2 footnote
                                 ablation B5 switch #1).

Implementation note on the EdgeType one-hot dimension: the launch spec said
"EdgeType one-hot 25 维 → concat 57 维"; the actual count of EdgeType enum
members at Checkpoint 7 is **29** (after the Q-1 mini-checkpoint added 3
USER_* edges plus the UNKNOWN bottom). Concat dim = 32 + 29 = 61. The
residual MLP is therefore ``Linear(61, 64) + GELU + Linear(64, 256)``.
"""

from __future__ import annotations

import torch
from torch import nn
from torch_geometric.nn import HGTConv

from loghetero.data.parsers.base import EdgeType
from loghetero.models.encoders.time2vec import Time2Vec

# Module-level constant: enum order is stable (Python preserves declaration
# order). We materialise the lookup once so per-edge encoding is O(1).
_EDGE_TYPE_INDEX: dict[str, int] = {et.value: i for i, et in enumerate(EdgeType)}
_N_EDGE_TYPES: int = len(EdgeType)  # 29 at Checkpoint 7


class HGTLayer(nn.Module):
    """One layer of HTGN: stock HGTConv plus the Option-C temporal residual.

    See module docstring for the full RFC context. The forward signature
    deliberately receives ``time2vec`` as an argument (rather than owning a
    Time2Vec instance) so the same time-encoding module is shared across
    all stacked HGT layers in the Phase-9 main HTGN module -- avoiding
    redundant per-layer Time2Vec parameters.
    """

    def __init__(
        self,
        in_channels: int | dict[str, int],
        metadata: tuple[list[str], list[tuple[str, str, str]]],
        *,
        hidden_dim: int = 256,
        num_heads: int = 8,
        dropout: float = 0.1,
        time2vec_dim: int = 32,
        residual_alpha: float = 0.5,
    ) -> None:
        super().__init__()
        if residual_alpha < 0.0:
            raise ValueError(
                f"residual_alpha must be >= 0; got {residual_alpha}. "
                "Use 0.0 to disable the temporal residual (Phase 11 ablation B5)."
            )
        if not (0.0 <= dropout < 1.0):
            raise ValueError(f"dropout must be in [0, 1); got {dropout}")
        self.hidden_dim = hidden_dim
        self.residual_alpha = float(residual_alpha)
        self.time2vec_dim = time2vec_dim

        self.hgt = HGTConv(
            in_channels=in_channels,
            out_channels=hidden_dim,
            metadata=metadata,
            heads=num_heads,
        )
        self.dropout = nn.Dropout(dropout)

        # Residual MLP: Linear(61 -> 64) + GELU + Linear(64 -> hidden_dim).
        # 61 = time2vec_dim (32) + n_edge_types (29). 2-layer with activation
        # per RFC (better expressivity than single linear) but parameter
        # count stays modest (32+29)*64 + 64 + 64*256 + 256 = ~21k params.
        edge_in = time2vec_dim + _N_EDGE_TYPES
        self.edge_mlp = nn.Sequential(
            nn.Linear(edge_in, 64),
            nn.GELU(),
            nn.Linear(64, hidden_dim),
        )

    def forward(
        self,
        x_dict: dict[str, torch.Tensor],
        edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
        edge_time_dict: dict[tuple[str, str, str], torch.Tensor],
        time2vec: Time2Vec,
    ) -> dict[str, torch.Tensor]:
        """Forward = stock HGTConv path + Option-C temporal residual.

        Args:
            x_dict: node features per type. Each tensor has shape
                ``(num_nodes_of_type, in_channels[node_type])``.
            edge_index_dict: edge connectivity per edge triple
                ``(src_type, edge_type, dst_type) -> Tensor[2, num_edges]``.
            edge_time_dict: per-edge timestamps in some normalised unit
                (e.g. hours, *not* nanoseconds; caller normalises). Each
                tensor has shape ``(num_edges,)``.
            time2vec: the shared :class:`Time2Vec` module.

        Returns:
            Updated node features per type, each tensor has shape
            ``(num_nodes_of_type, hidden_dim)``. Node types receiving zero
            messages have value zero (HGTConv's None-output is replaced
            with zeros so callers can always ``.add_`` safely).
        """
        # --- 1. Stock HGT attention path -----------------------------------
        out_raw = self.hgt(x_dict, edge_index_dict)
        out_dict: dict[str, torch.Tensor] = {}
        # Iterate every input node type, not just HGTConv's output keys --
        # source-only node types (no incoming edges) are absent from out_raw
        # and would otherwise vanish from the output dict, breaking residual
        # accumulation and downstream multi-layer stacking.
        for ntype in x_dict:
            val = out_raw.get(ntype) if isinstance(out_raw, dict) else None
            if val is None:
                out_dict[ntype] = torch.zeros(
                    x_dict[ntype].shape[0], self.hidden_dim, device=x_dict[ntype].device
                )
            else:
                out_dict[ntype] = self.dropout(val)

        # --- 2. Option-C temporal residual (short-circuit on alpha=0) -----
        if self.residual_alpha == 0.0:
            return out_dict  # ablation B5 switch #1: temporal residual off

        for rel, edge_index in edge_index_dict.items():
            if edge_index.numel() == 0:
                continue
            src_t, edge_t, dst_t = rel
            edge_time = edge_time_dict.get(rel)
            if edge_time is None:
                continue

            n_edges = edge_index.shape[1]
            # Time2Vec wants [*, 1] input; we feed the per-edge timestamps.
            t = edge_time.float().reshape(n_edges, 1)
            time_emb = time2vec(t)  # (E, time2vec_dim)

            # EdgeType one-hot, broadcast to all edges of this triple.
            eid = _EDGE_TYPE_INDEX.get(edge_t)
            if eid is None:
                # Disallowed-or-unknown edge type; should be impossible since
                # ALLOWED_EDGE_TRIPLES is exhaustive, but defend defensively.
                continue
            eid_onehot = torch.zeros(n_edges, _N_EDGE_TYPES, device=edge_index.device)
            eid_onehot[:, eid] = 1.0

            # Edge-feature MLP -> per-edge dst-node contribution.
            edge_attr = torch.cat([time_emb, eid_onehot], dim=-1)  # (E, 61)
            edge_msg = self.edge_mlp(edge_attr)  # (E, hidden_dim)

            # Scatter-add onto destination nodes. We cannot import
            # torch_scatter; PyG's index_add_ on a fresh zeros tensor works.
            n_dst = out_dict[dst_t].shape[0]
            residual = torch.zeros(
                n_dst, self.hidden_dim, device=edge_index.device, dtype=edge_msg.dtype
            )
            residual.index_add_(0, edge_index[1], edge_msg)
            out_dict[dst_t] = out_dict[dst_t] + self.residual_alpha * residual

        return out_dict
