"""HTGN main module: 3-layer heterogeneous + temporal graph encoder (Phase 3 / Checkpoint 9).

Composes the three Phase-3 building blocks into the final stack the Phase-4
cross-modal attention will consume:

* :class:`Time2Vec` (Checkpoint 7, encoders/time2vec.py) — shared across
  all layers; one set of (omega, phi) parameters informs every layer's
  Option-C residual edge encoding.
* :class:`HGTLayer` (Checkpoint 7, graph/hgt_layer.py) — stock PyG HGTConv
  + Option-C temporal residual; per-layer ``residual_alpha`` is set to
  ``gamma_k · alpha_global`` so the per-layer decay applies to the residual ONLY,
  not the HGT main attention path.
* :class:`HeteroTGNMemory` (Checkpoint 8, graph/tgn_memory.py) — one PyG
  TGNMemory per memory-bearing node type (``process`` / ``socket`` by
  default); other types neither read nor update memory.

Per-layer formula (per Checkpoint 9 launch-spec clarification):

    y_dst[v] = HGTConv(x_dict)[v]
             + gamma_k · alpha · sum_{(u,v) ∈ E_r}
                              MLP(concat(time2vec(t_uv), eid_onehot_r))
             + memory[v]                       (if dst_type has memory)
             then LayerNorm(per-type)

alpha = ``residual_alpha`` (Checkpoint 7 default 0.5; sweep [0.1, 0.3, 0.5,
1.0] for Phase 11 ablation B5 switch #1).
gamma_k = ``layer_decay_gamma[k]`` (Checkpoint 9 default [1.0, 0.7, 0.4]; per-
layer attenuation prevents deep layers from over-relying on the temporal
residual when the HGT-attention path can already carry high-order
structural information).

alpha and gamma are deliberately decoupled: alpha controls the GLOBAL temporal
residual strength, gamma controls DEPTH-WISE attenuation. Phase 11 ablations
sweep them on independent axes; this is the architectural-clarity
rationale for the dual-coefficient design.

Output Dict Contract
====================
``forward()`` returns ``dict[str, Tensor]`` keyed by node-type value
(e.g. ``"process"``, ``"file"``, etc.). The dict contains an entry for
EVERY node type present in the input ``x_dict`` (including non-memory
types), each shaped ``(num_nodes_of_type, hidden_dim)``. Memory
contributions are added IN-PLACE for memory types (``process`` /
``socket``); non-memory types receive HGT + temporal-residual output
only. Phase 4 caller MUST iterate via ``for ntype in out:`` and
``if ntype == "X"`` rather than indexing fixed names — the set of
present types depends on the input batch, not on a static schema.

Timestamp dtypes (per Checkpoint 9 launch-spec OVERRIDE)
========================================================
Two paths consume edge timestamps with DIFFERENT dtype expectations:

* The Time2Vec → residual MLP path needs FLOAT timestamps (sin/cos
  arithmetic). We normalise nanoseconds to hours-as-float internally so
  sin(omega·t) doesn't overflow. ``edge_time_dict_ns`` accepted as raw
  int64 ns; we cast to float and divide by ``NS_PER_HOUR`` for Time2Vec.
* The HeteroTGNMemory.update_state path needs INT64 LONG timestamps (PyG
  TGNMemory's ``last_update`` buffer is Long; index_put dtype must
  match). The launch-spec OVERRIDE chose **option 1: direct ns cast to
  long** -- int64 range 9.2e18 dwarfs 2018-era ns timestamps (~1.5e18),
  no overflow. Per-event resolution preserved (ns precision); critically
  this AVOIDS the hour-level bucketing that would degenerate TGN's
  within-window ordering ability and silently equalise to Phase 11
  ablation B5 (no-temporal). The unit test
  ``test_long_timestep_preserves_subsecond_ordering`` locks this
  invariant: two events ≥1 ns apart MUST have distinct long timesteps.
"""

from __future__ import annotations

import torch
from torch import nn

from loghetero.data.parsers.base import NodeType
from loghetero.models.encoders.time2vec import Time2Vec
from loghetero.models.graph.hgt_layer import HGTLayer
from loghetero.models.graph.tgn_memory import (
    DEFAULT_MEMORY_NODE_TYPES,
    HeteroTGNMemory,
)

NS_PER_HOUR: float = 3.6e12  # 3600 * 1e9; for float-side normalisation only


def ns_to_long_timesteps(t_ns: torch.Tensor) -> torch.Tensor:
    """Convert ns timestamps to int64 Long for PyG TGNMemory consumption.

    Per Checkpoint 9 launch-spec OVERRIDE: option 1 = direct ns cast.
    int64 (9.2e18 max) >> 2018-era ns timestamps (~1.5e18), zero overflow
    risk; per-event ns resolution preserved.
    """
    return t_ns.to(torch.int64)


class HTGN(nn.Module):
    """3-layer Heterogeneous Temporal Graph Network (creation 1 core)."""

    def __init__(
        self,
        in_channels: int | dict[str, int],
        metadata: tuple[list[str], list[tuple[str, str, str]]],
        num_nodes_per_type: dict[NodeType, int],
        *,
        hidden_dim: int = 256,
        n_layers: int = 3,
        num_heads: int = 8,
        dropout: float = 0.1,
        time2vec_dim: int = 32,
        residual_alpha: float = 0.5,
        layer_decay_gamma: tuple[float, ...] = (1.0, 0.7, 0.4),
        memory_node_types: tuple[NodeType, ...] = DEFAULT_MEMORY_NODE_TYPES,
        raw_msg_dim: int = 64,
    ) -> None:
        super().__init__()
        if len(layer_decay_gamma) != n_layers:
            raise ValueError(
                f"layer_decay_gamma has {len(layer_decay_gamma)} entries but "
                f"n_layers={n_layers}; lengths must match."
            )
        for idx, gamma in enumerate(layer_decay_gamma):
            if gamma < 0:
                raise ValueError(f"layer_decay_gamma[{idx}] = {gamma} must be >= 0.")

        self.hidden_dim = hidden_dim
        self.n_layers = n_layers
        self.layer_decay_gamma = tuple(layer_decay_gamma)
        self.residual_alpha = residual_alpha
        self.raw_msg_dim = raw_msg_dim

        self.metadata = metadata

        # Shared Time2Vec across all layers (one parameter set, applied per layer).
        self.time2vec = Time2Vec(dim=time2vec_dim)

        # 3 HGT layers with per-layer effective_alpha = gamma_k · alpha.
        # The HGTLayer constructor applies its `residual_alpha` to the
        # scatter-added residual contribution; we set per-layer alpha at
        # construction to bake gamma_k in. Result: gamma_k decay applies to the
        # residual only, NOT the HGT-attention main path.
        self.layers = nn.ModuleList()
        for k in range(n_layers):
            layer_in = in_channels if k == 0 else hidden_dim
            effective_alpha = float(residual_alpha) * float(layer_decay_gamma[k])
            self.layers.append(
                HGTLayer(
                    in_channels=layer_in,
                    metadata=metadata,
                    hidden_dim=hidden_dim,
                    num_heads=num_heads,
                    dropout=dropout,
                    time2vec_dim=time2vec_dim,
                    residual_alpha=effective_alpha,
                )
            )

        # Per-layer + per-node-type LayerNorm.
        node_types_list = metadata[0]
        self.layer_norms = nn.ModuleList(
            [
                nn.ModuleDict({ntype: nn.LayerNorm(hidden_dim) for ntype in node_types_list})
                for _ in range(n_layers)
            ]
        )

        # Heterogeneous TGN memory (shared across layers).
        self.tgn_memory = HeteroTGNMemory(
            num_nodes_per_type=num_nodes_per_type,
            memory_dim=hidden_dim,
            time_dim=time2vec_dim,
            raw_msg_dim=raw_msg_dim,
            memory_node_types=memory_node_types,
        )

        # Learnable projection from current node embedding to TGN raw_msg.
        # Phase 7 may upgrade to a richer message module if memory updates
        # need stronger signal; for Checkpoint 9 a minimal Linear suffices.
        self.msg_projection = nn.Linear(hidden_dim, raw_msg_dim)

    # ------------------------------------------------------------------
    # Forward path
    # ------------------------------------------------------------------

    def forward(
        self,
        x_dict: dict[str, torch.Tensor],
        edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
        edge_time_dict_ns: dict[tuple[str, str, str], torch.Tensor],
    ) -> dict[str, torch.Tensor]:
        """Run the 3-layer HTGN forward pass.

        Args:
            x_dict: per-type node features. Each tensor is
                ``(num_nodes_of_type, in_channels[node_type] | hidden_dim)``.
            edge_index_dict: ``(src_type, edge_type, dst_type) -> Tensor[2, E]``.
            edge_time_dict_ns: per-edge timestamps in **nanoseconds**
                (raw int64 from the parsers). HTGN normalises internally
                for both Time2Vec (float hours) and TGN memory
                (int64 ns long).

        Returns:
            dict[str, Tensor[num_nodes_of_type, hidden_dim]] -- see "Output
            Dict Contract" in module docstring.
        """
        # --- Convert timestamps for the two consumers ----------------------
        # Time2Vec wants float, normalised to hours so sin(omega·t) is sane.
        edge_time_for_t2v: dict[tuple[str, str, str], torch.Tensor] = {
            rel: t.float() / NS_PER_HOUR for rel, t in edge_time_dict_ns.items()
        }
        # TGN memory wants int64 long ns directly (per launch-spec option 1).
        edge_time_for_tgn: dict[tuple[str, str, str], torch.Tensor] = {
            rel: ns_to_long_timesteps(t) for rel, t in edge_time_dict_ns.items()
        }

        # --- 3-layer stack ------------------------------------------------
        x = x_dict
        for layer, ln_dict in zip(self.layers, self.layer_norms, strict=True):
            # 1. HGT layer with gamma_k · alpha residual baked in.
            x_attn = layer(x, edge_index_dict, edge_time_for_t2v, self.time2vec)

            # 2. Update TGN memory for memory-bearing dst nodes.
            for rel, edge_index in edge_index_dict.items():
                if edge_index.shape[1] == 0:
                    continue
                src_t, _edge_t, dst_t = rel
                if not self.tgn_memory.has_memory(dst_t):
                    continue  # silent no-op (file/network/user have no memory)
                src_idx = edge_index[0]
                dst_idx = edge_index[1]
                t_long = edge_time_for_tgn[rel]
                # raw_msg = learned projection of src node's current embedding.
                src_x = x_attn[src_t][src_idx]  # (E, hidden_dim)
                raw_msg = self.msg_projection(src_x)  # (E, raw_msg_dim)
                self.tgn_memory.update_state(dst_t, src_idx, dst_idx, t_long, raw_msg)

            # 3. Read memory for memory-bearing types and add to embeddings.
            n_id_dict = {
                ntype: torch.arange(
                    x_attn[ntype].shape[0],
                    dtype=torch.long,
                    device=x_attn[ntype].device,
                )
                for ntype in x_attn
            }
            mem_dict = self.tgn_memory(n_id_dict)
            for ntype, (mem, _last_update) in mem_dict.items():
                x_attn[ntype] = x_attn[ntype] + mem

            # 4. Per-type LayerNorm. mypy can't preserve ModuleDict typing
            # through ModuleList iteration, so the indexing complaint is
            # known-safe.
            x = {ntype: ln_dict[ntype](v) for ntype, v in x_attn.items()}  # type: ignore[index,operator]

        return x

    # ------------------------------------------------------------------
    # Diagnostics for the Checkpoint 9 perf report
    # ------------------------------------------------------------------

    def parameter_breakdown(self) -> dict[str, int]:
        """Per-component parameter count (Checkpoint 9 perf report)."""

        def count_params(module: nn.Module) -> int:
            return sum(p.numel() for p in module.parameters())

        time2vec_params = count_params(self.time2vec)
        # mypy can't preserve HGTLayer type through ModuleList iteration;
        # we know each layer is HGTLayer with .hgt and .edge_mlp attrs.
        hgt_internal_params = 0
        residual_mlp_params = 0
        for layer in self.layers:
            hgt_internal_params += count_params(layer.hgt)  # type: ignore[arg-type]
            residual_mlp_params += count_params(layer.edge_mlp)  # type: ignore[arg-type]
        tgn_params = count_params(self.tgn_memory)
        layer_norm_params = sum(count_params(ln_dict) for ln_dict in self.layer_norms)
        msg_proj_params = count_params(self.msg_projection)
        total = sum(p.numel() for p in self.parameters())
        return {
            "time2vec": time2vec_params,
            "hgt_internal": hgt_internal_params,
            "residual_mlp": residual_mlp_params,
            "tgn_memory": tgn_params,
            "layer_norm": layer_norm_params,
            "msg_projection": msg_proj_params,
            "total": total,
        }
