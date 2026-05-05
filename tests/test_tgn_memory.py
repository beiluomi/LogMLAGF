"""Phase 3 / Checkpoint 8 TGN memory tests.

Per launch spec, three required deliverables (each gets ≥1 test):

1. **Toy 5-step regression** — construct a 5-event chain on a single
   process node with predictable evolution; train a small head on top of
   the per-step memory output and assert the loss converges to near zero.
2. **Detach strategy validation** — without detach the second batch's
   ``loss.backward()`` raises ``RuntimeError`` (gradient leak across
   batches); with detach we run multiple batches cleanly.
3. **Heterogeneity routing** — file / network / user nodes neither
   trigger updates nor return memory in lookups (silent no-op invariant).

Plus standard coverage: reset_state zeros memory, has_memory introspection,
zero-node-count graceful handling.
"""

from __future__ import annotations

import pytest
import torch
from torch import nn

from loghetero.data.parsers.base import NodeType
from loghetero.models.graph.tgn_memory import HeteroTGNMemory

# --- Fixtures ---------------------------------------------------------------

_NUM_NODES = {
    NodeType.process: 8,
    NodeType.file: 5,
    NodeType.network: 3,
    NodeType.socket: 2,
    NodeType.user: 1,
}
_MEMORY_DIM = 16  # smaller than prod 256 for fast tests
_TIME_DIM = 8
_RAW_MSG_DIM = 4


def _build_memory(**overrides: object) -> HeteroTGNMemory:
    kwargs: dict = {
        "memory_dim": _MEMORY_DIM,
        "time_dim": _TIME_DIM,
        "raw_msg_dim": _RAW_MSG_DIM,
    }
    kwargs.update(overrides)
    return HeteroTGNMemory(num_nodes_per_type=_NUM_NODES, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. TOY 5-STEP REGRESSION TEST (user-required #1)
# ---------------------------------------------------------------------------


class TestToyRegression:
    def test_memory_can_learn_event_count_evolution(self) -> None:
        """5-step chain on process node 0; train a tiny head to predict the
        event index k from the memory state after k updates. Loss must
        converge to near zero (model has enough capacity for this trivial
        task; if it doesn't, the memory pipeline is broken)."""
        torch.manual_seed(42)
        mem = _build_memory()
        # Tiny linear head: memory -> scalar prediction of event index k
        head = nn.Linear(_MEMORY_DIM, 1)
        params = list(mem.parameters()) + list(head.parameters())
        opt = torch.optim.Adam(params, lr=0.05)

        # 5 events arriving at process p=0 from process p=1 at times 1..5.
        # raw_msg slot 0 carries the event index (so the GRU has a usable
        # signal); slots 1..3 are zero.
        n_steps = 5
        targets = torch.arange(1, n_steps + 1, dtype=torch.float32)  # [1,2,3,4,5]

        last_loss = float("inf")
        for _epoch in range(200):
            mem.reset_state()
            preds: list[torch.Tensor] = []
            for k in range(1, n_steps + 1):
                src = torch.tensor([1], dtype=torch.long)
                dst = torch.tensor([0], dtype=torch.long)
                t = torch.tensor([k], dtype=torch.long)
                raw = torch.zeros(1, _RAW_MSG_DIM)
                raw[0, 0] = float(k)
                mem.update_state("process", src, dst, t, raw)
                # Look up p=0's memory after this update
                lookup = mem({NodeType.process.value: torch.tensor([0], dtype=torch.long)})
                m, _ = lookup[NodeType.process.value]  # shape (1, _MEMORY_DIM)
                preds.append(head(m).squeeze())  # scalar
            pred_tensor = torch.stack(preds)  # (5,)
            loss = (pred_tensor - targets).pow(2).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            mem.detach()  # standard detach at "batch end" (here = epoch end)
            last_loss = float(loss.item())

        assert last_loss < 0.5, (
            f"toy 5-step regression failed to converge: final MSE = {last_loss:.4f}; "
            "expected < 0.5. Memory pipeline likely broken."
        )


# ---------------------------------------------------------------------------
# 2. DETACH STRATEGY VALIDATION (user-required #2)
# ---------------------------------------------------------------------------


class TestDetachStrategy:
    def _run_one_batch(self, mem: HeteroTGNMemory, head: nn.Linear, t_offset: int) -> torch.Tensor:
        """Single batch: one update + one lookup + scalar loss."""
        src = torch.tensor([1], dtype=torch.long)
        dst = torch.tensor([0], dtype=torch.long)
        t = torch.tensor([1 + t_offset], dtype=torch.long)
        raw = torch.randn(1, _RAW_MSG_DIM)
        mem.update_state("process", src, dst, t, raw)
        lookup = mem({NodeType.process.value: torch.tensor([0], dtype=torch.long)})
        m, _ = lookup[NodeType.process.value]
        return head(m).pow(2).sum()

    def test_without_detach_second_batch_backward_raises(self) -> None:
        """Counter-example: NOT calling detach between batches should make
        the second batch's loss.backward() raise (graph already freed by
        the first batch's backward)."""
        torch.manual_seed(0)
        mem = _build_memory()
        head = nn.Linear(_MEMORY_DIM, 1)
        opt = torch.optim.SGD(list(mem.parameters()) + list(head.parameters()), lr=0.01)

        # Batch 1: succeeds.
        loss1 = self._run_one_batch(mem, head, t_offset=0.0)
        opt.zero_grad()
        loss1.backward()
        opt.step()
        # *** intentionally skip mem.detach() here ***

        # Batch 2: must raise because PyG TGNMemory's internal memory tensor
        # still references the freed graph from batch 1.
        with pytest.raises(RuntimeError, match="(?i)backward.*through.*graph"):
            loss2 = self._run_one_batch(mem, head, t_offset=1)
            opt.zero_grad()
            loss2.backward()

    def test_with_detach_runs_multiple_batches_cleanly(self) -> None:
        """Happy path: calling detach between batches lets training proceed."""
        torch.manual_seed(0)
        mem = _build_memory()
        head = nn.Linear(_MEMORY_DIM, 1)
        opt = torch.optim.SGD(list(mem.parameters()) + list(head.parameters()), lr=0.01)

        # Run 3 batches in sequence; each must succeed.
        for batch_idx in range(3):
            loss = self._run_one_batch(mem, head, t_offset=batch_idx)
            opt.zero_grad()
            loss.backward()
            opt.step()
            mem.detach()  # standard recipe after every batch
        # If we got here without RuntimeError, the detach worked.


# ---------------------------------------------------------------------------
# 3. HETEROGENEITY ROUTING (user-required #3)
# ---------------------------------------------------------------------------


class TestHeterogeneityRouting:
    def test_non_memory_dst_type_is_no_op(self) -> None:
        """update_state with dst_type in {file, network, user} must NOT
        modify any memory state -- silent no-op per the launch spec."""
        torch.manual_seed(0)
        mem = _build_memory()
        # Capture a reference to process memory before the no-op call.
        proc_mem_before = mem._mem[NodeType.process.value].memory.clone()
        # Call update_state with dst_type=file (NOT a memory type).
        src = torch.tensor([0], dtype=torch.long)
        dst = torch.tensor([0], dtype=torch.long)
        t = torch.tensor([1], dtype=torch.long)
        raw = torch.randn(1, _RAW_MSG_DIM)
        mem.update_state("file", src, dst, t, raw)
        # Process memory must be unchanged (no cross-type pollution).
        assert torch.allclose(mem._mem[NodeType.process.value].memory, proc_mem_before)

    def test_lookup_skips_non_memory_node_types(self) -> None:
        """forward() must NOT return entries for file / network / user."""
        mem = _build_memory()
        n_ids = {
            NodeType.process.value: torch.tensor([0, 1], dtype=torch.long),
            NodeType.file.value: torch.tensor([0, 1, 2], dtype=torch.long),
            NodeType.network.value: torch.tensor([0], dtype=torch.long),
            NodeType.user.value: torch.tensor([0], dtype=torch.long),
            NodeType.socket.value: torch.tensor([0, 1], dtype=torch.long),
        }
        out = mem(n_ids)
        # Memory types present
        assert NodeType.process.value in out
        assert NodeType.socket.value in out
        # Non-memory types absent (NOT present with zero tensors -- absent)
        assert NodeType.file.value not in out
        assert NodeType.network.value not in out
        assert NodeType.user.value not in out

    def test_has_memory_introspection(self) -> None:
        mem = _build_memory()
        assert mem.has_memory("process")
        assert mem.has_memory("socket")
        assert not mem.has_memory("file")
        assert not mem.has_memory("network")
        assert not mem.has_memory("user")


# ---------------------------------------------------------------------------
# Standard coverage
# ---------------------------------------------------------------------------


class TestStandardCoverage:
    def test_reset_state_zeros_memory(self) -> None:
        """After update_state then reset_state, memory should be zeros again."""
        mem = _build_memory()
        src = torch.tensor([1], dtype=torch.long)
        dst = torch.tensor([0], dtype=torch.long)
        t = torch.tensor([1], dtype=torch.long)
        raw = torch.randn(1, _RAW_MSG_DIM)
        mem.update_state("process", src, dst, t, raw)
        # Memory should be non-zero after the update is "flushed" by a lookup.
        # NB: PyG TGNMemory only commits queued messages on the next forward.
        _ = mem({NodeType.process.value: torch.tensor([0], dtype=torch.long)})
        # Now reset and verify zero.
        mem.reset_state()
        assert torch.allclose(
            mem._mem[NodeType.process.value].memory,
            torch.zeros_like(mem._mem[NodeType.process.value].memory),
        )

    def test_zero_node_count_node_type_skipped(self) -> None:
        """If a memory node type has 0 nodes in the dataset, it's skipped at
        construction time -- no PyG TGNMemory is allocated. (As of v0.1-data,
        socket = 0 across all 16 ATLAS hosts -- this would happen in practice.)"""
        # Override num_nodes to make socket = 0
        mem = HeteroTGNMemory(
            num_nodes_per_type={
                NodeType.process: 4,
                NodeType.socket: 0,  # zero
                NodeType.file: 5,
                NodeType.network: 3,
                NodeType.user: 1,
            },
            memory_dim=_MEMORY_DIM,
            time_dim=_TIME_DIM,
            raw_msg_dim=_RAW_MSG_DIM,
        )
        # process has memory; socket is configured as a memory type but
        # has 0 nodes so no internal TGN was instantiated.
        assert mem.has_memory("socket")  # configured
        assert "socket" not in mem._mem  # but not allocated
        # Calling update_state on socket is a silent no-op.
        mem.update_state(
            "socket",
            torch.tensor([0], dtype=torch.long),
            torch.tensor([0], dtype=torch.long),
            torch.tensor([1], dtype=torch.long),
            torch.randn(1, _RAW_MSG_DIM),
        )

    def test_uses_pyg_tgnmemory_internally(self) -> None:
        """PyG-API-alignment introspection: each per-type memory IS a PyG
        TGNMemory instance (Phase 12 paper-ready evidence)."""
        from torch_geometric.nn import TGNMemory

        mem = _build_memory()
        for ntype, tgn in mem._mem.items():
            assert isinstance(tgn, TGNMemory), (
                f"per-type memory for {ntype!r} is not a PyG TGNMemory instance "
                f"(got {type(tgn).__name__}); the heterogeneous wrapper is supposed "
                "to compose PyG TGNMemory rather than reimplement it."
            )
