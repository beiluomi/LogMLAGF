"""Heterogeneous TGN-style node memory for LogHetero (Phase 3 / Checkpoint 8).

PyG TGN-Memory adaptation
=========================

PyG ships :class:`torch_geometric.nn.TGNMemory` as a *homogeneous*-graph
module: one memory tensor of shape ``(N, memory_dim)``, one GRU update cell,
no notion of node type. LogHetero's provenance graph has 5 node types
(``process / file / socket / network / user``) per decision 5; only
**state-bearing entities** -- processes (alive, evolving execution context)
and sockets (open IPC channels with read/write history) -- have a meaningful
notion of "memory of past events". File / network / user nodes are stateless
in the time-series sense (the file is a document, the IP is an address;
neither evolves between events the way a process does).

What we reuse from PyG (zero modification)
------------------------------------------
* :class:`torch_geometric.nn.TGNMemory` -- per-memory-type instance owns
  its own memory tensor, GRU cell, message module, aggregator. Battle-tested
  detach + reset_state behaviour.
* :class:`torch_geometric.nn.models.tgn.IdentityMessage` -- default message
  module concatenating ``z_src``, ``z_dst``, ``raw_msg``, ``t_enc``.
* :class:`torch_geometric.nn.models.tgn.LastAggregator` -- "last-message-
  per-node" aggregation; same as TGN paper default.

What we add for heterogeneity (this module's contribution)
----------------------------------------------------------
* **Per-memory-type instantiation**: one PyG ``TGNMemory`` per
  ``memory_node_types`` entry (default: ``(process, socket)``). Other node
  types are NOT instantiated: file / network / user simply have no memory.
* **Heterogeneous update routing**: :meth:`update_state` takes ``dst_type``
  as an explicit argument. If ``dst_type`` is a memory type, the update is
  routed to the corresponding PyG TGNMemory; otherwise it is a silent no-op.
  This is the explicit "non-memory types neither read nor write memory"
  invariant the Phase 3 launch spec calls out.
* **Heterogeneous lookup**: :meth:`forward` accepts a
  ``dict[str, Tensor]`` of node IDs per type, returns a dict (memory,
  last_update) only for memory types. Non-memory types are absent from
  the output dict (caller must handle absence -- typically by skipping the
  memory residual on those node types).
* **Epoch-bounded persistence**: per the launch spec's "same epoch /
  same (host, scenario) cross-window persistent; epoch-boundary reset",
  callers are expected to call :meth:`reset_state` at the start of each
  epoch and :meth:`detach` at every batch boundary inside an epoch.
  This module does NOT manage the epoch lifecycle itself -- that's
  Phase 7 training-loop responsibility.

Phase 12 paper material
=======================
This module's docstring is intentionally written in the form of the Methods
chapter section "How we adapt TGN memory to heterogeneous provenance
graphs": the "what we reuse" / "what we add" headers map directly to the
contribution-vs-base-machinery distinction reviewers want to see.
"""

from __future__ import annotations

import torch
from torch import nn
from torch_geometric.nn import TGNMemory
from torch_geometric.nn.models.tgn import IdentityMessage, LastAggregator

from loghetero.data.parsers.base import NodeType

DEFAULT_MEMORY_NODE_TYPES: tuple[NodeType, ...] = (NodeType.process, NodeType.socket)


class HeteroTGNMemory(nn.Module):
    """Heterogeneous TGN node memory; only memory-type nodes have state.

    Args:
        num_nodes_per_type: required upper bound on node count per node type.
            PyG ``TGNMemory`` allocates a fixed-size memory tensor at init,
            so the caller must pre-declare the maximum number of nodes per
            memory-type. For batched windowed training (Phase 1.6 DataModule
            output), this should be the ``max(num_nodes_of_type)`` across
            all batches the model will ever see. Phase 7 picks the value
            from the global statistics in ``data/atlas_graph_summary.json``.
        memory_dim: dimensionality of the per-node memory vector. Default
            256 to align with HTGN ``hidden_dim`` (so the residual added to
            HGT-output requires no extra projection). Sweep space (Phase 11)
            is reserved for future ablation.
        time_dim: time-encoding dimension fed into the message module. Default
            32 to align with the Time2Vec module's default; if the upstream
            ``Time2Vec`` module is reconfigured, update this in lock step.
        raw_msg_dim: dimensionality of the per-edge raw message tensor. Phase
            9 main HTGN module owns the construction of this message; for
            now the wrapper just declares the shape so the GRU can be sized.
            Default 64; Phase 9 may override.
        memory_node_types: tuple of NodeType values that DO get memory.
            Default ``(process, socket)`` -- the two state-bearing entity
            types per launch spec. Other types are silently skipped on
            update_state and absent from forward output.
    """

    def __init__(
        self,
        num_nodes_per_type: dict[NodeType, int],
        *,
        memory_dim: int = 256,
        time_dim: int = 32,
        raw_msg_dim: int = 64,
        memory_node_types: tuple[NodeType, ...] = DEFAULT_MEMORY_NODE_TYPES,
    ) -> None:
        super().__init__()
        self.memory_dim = memory_dim
        self.time_dim = time_dim
        self.raw_msg_dim = raw_msg_dim
        # Stored as set of string values for fast O(1) routing in update_state.
        self._memory_keys: set[str] = {nt.value for nt in memory_node_types}

        # Per-type PyG TGNMemory. We use ModuleDict so PyTorch picks them
        # up for parameter / state-dict introspection.
        self._mem: nn.ModuleDict = nn.ModuleDict()
        for nt in memory_node_types:
            n = num_nodes_per_type.get(nt, 0)
            if n <= 0:
                # Skip types that have zero nodes in this dataset (e.g.,
                # socket = 0 across all 16 ATLAS hosts as of v0.1-data).
                # When DARPA TC E3 lands the Phase 9 caller will rebuild
                # the wrapper with non-zero socket counts.
                continue
            self._mem[nt.value] = TGNMemory(
                num_nodes=n,
                raw_msg_dim=raw_msg_dim,
                memory_dim=memory_dim,
                time_dim=time_dim,
                message_module=IdentityMessage(raw_msg_dim, memory_dim, time_dim),
                aggregator_module=LastAggregator(),
            )

    # ------------------------------------------------------------------
    # Public API (mirrors PyG TGNMemory but with explicit node-type routing)
    # ------------------------------------------------------------------

    def update_state(
        self,
        dst_type: str,
        src: torch.Tensor,
        dst: torch.Tensor,
        t: torch.Tensor,
        raw_msg: torch.Tensor,
    ) -> None:
        """Route a TGN update to the per-type PyG memory if applicable.

        If ``dst_type`` is not in :attr:`memory_node_types` (e.g.
        ``"file"``, ``"network"``, ``"user"``), this is a **silent no-op**
        per the heterogeneity invariant. Caller does not need to filter
        edges by dst type before calling.

        Args:
            dst_type: NodeType value string of the edge destination.
            src: 1-D Long tensor of source node indices.
            dst: 1-D Long tensor of destination node indices.
            t: 1-D Float tensor of event timestamps (caller-normalised; e.g.
                hours rather than nanoseconds).
            raw_msg: ``(num_edges, raw_msg_dim)`` raw message tensor.
        """
        if dst_type not in self._memory_keys or dst_type not in self._mem:
            return
        # mypy: ModuleDict items are Module-typed; we know they are TGNMemory.
        self._mem[dst_type].update_state(src, dst, t, raw_msg)  # type: ignore[operator]

    def forward(  # type: ignore[override]
        self, n_id_dict: dict[str, torch.Tensor]
    ) -> dict[str, tuple[torch.Tensor, torch.Tensor]]:
        """Heterogeneous lookup: ``(memory, last_update)`` per memory type.

        Args:
            n_id_dict: per-node-type tensor of node indices to look up.

        Returns:
            Dict keyed by node type that **has** memory. Non-memory node
            types absent from the output (caller treats absence as
            "no memory contribution for this type"; do NOT add zeros
            silently downstream -- the absence is informative).
        """
        out: dict[str, tuple[torch.Tensor, torch.Tensor]] = {}
        for ntype, n_ids in n_id_dict.items():
            if ntype not in self._memory_keys or ntype not in self._mem:
                continue
            mem, last_update = self._mem[ntype](n_ids)  # type: ignore[operator]
            out[ntype] = (mem, last_update)
        return out

    def detach(self) -> None:
        """Detach all per-type memory tensors from the autograd graph.

        **MUST be called at every batch boundary inside an epoch.** Without
        this, PyG TGNMemory's stored memory keeps a reference to the
        previous batch's compute graph; the second batch's
        ``loss.backward()`` then tries to traverse the previous batch's
        graph -> ``RuntimeError: Trying to backward through the graph
        a second time``.

        Phase 7 training-loop hook: call ``hetero_tgn.detach()`` after
        each ``optimizer.step()``.
        """
        for tgn in self._mem.values():
            tgn.detach()  # type: ignore[operator]

    def reset_state(self) -> None:
        """Zero out every per-type memory tensor + last_update timestamp.

        **Per launch spec: call at every epoch boundary.** Within an epoch,
        memory persists across batches (so a process's history accumulates
        across windows of the same scenario); across epochs we want a clean
        slate so the model doesn't anchor to scenario-specific quirks from
        previous epochs.
        """
        for tgn in self._mem.values():
            tgn.reset_state()  # type: ignore[operator]

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    @property
    def memory_node_types(self) -> set[str]:
        """The set of node-type value strings that have memory."""
        return set(self._memory_keys)

    def has_memory(self, node_type: str) -> bool:
        """Whether ``node_type`` is one of the configured memory types."""
        return node_type in self._memory_keys
