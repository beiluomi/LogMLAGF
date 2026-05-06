"""Checkpoint 12 synthetic attention case study.

Demonstrates bidirectional cross-modal attention on a small fixed-seed batch.
Prints:
 - top-3 graph nodes per text token by attention weight (text→graph direction)
 - per-token attention entropy (higher entropy = more diffuse attention)

Run with:
    uv run python notebooks/checkpoint12_attention_case_study.py
"""

from __future__ import annotations

import math

import torch

from loghetero.models.fusion import CrossModalAttention, build_event_attention_mask

# ---------------------------------------------------------------------------
# Reproducible setup
# ---------------------------------------------------------------------------
SEED = 42
torch.manual_seed(SEED)

BATCH = 1
NUM_TEXT = 8   # T: number of text tokens
NUM_GRAPH = 12  # N: number of graph nodes

TEXT_DIM = 768
GRAPH_DIM = 256
ATTN_DIM = 256
NUM_HEADS = 8

# ---------------------------------------------------------------------------
# Build a tiny fixed-seed batch
# ---------------------------------------------------------------------------
g = torch.Generator().manual_seed(SEED)
text_hidden = torch.randn(BATCH, NUM_TEXT, TEXT_DIM, generator=g)
graph_hidden = torch.randn(BATCH, NUM_GRAPH, GRAPH_DIM, generator=g)

# Assign event ids: text tokens 0-3 → event 0, tokens 4-6 → event 1, token 7 = padding
# Graph nodes 0-4 → event 0, nodes 5-9 → event 1, nodes 10-11 = padding
text_event_ids = torch.tensor([[0, 0, 0, 0, 1, 1, 1, -1]], dtype=torch.long)
graph_event_ids = torch.tensor([[0, 0, 0, 0, 0, 1, 1, 1, 1, 1, -1, -1]], dtype=torch.long)

text_padding_mask = text_event_ids >= 0   # (1, 8)
graph_padding_mask = graph_event_ids >= 0  # (1, 12)

attention_mask = build_event_attention_mask(
    text_event_ids, graph_event_ids, text_padding_mask, graph_padding_mask
)

# ---------------------------------------------------------------------------
# Run forward (no dropout during case study)
# ---------------------------------------------------------------------------
torch.manual_seed(SEED)
module = CrossModalAttention(
    text_dim=TEXT_DIM,
    graph_dim=GRAPH_DIM,
    attn_dim=ATTN_DIM,
    num_heads=NUM_HEADS,
    dropout=0.0,
)
module.eval()

with torch.no_grad():
    fused_text, fused_graph, weights = module(
        text_hidden,
        graph_hidden,
        attention_mask=attention_mask,
        text_padding_mask=text_padding_mask,
        graph_padding_mask=graph_padding_mask,
    )

# ---------------------------------------------------------------------------
# Analysis: text→graph direction (averaged over heads for readability)
# ---------------------------------------------------------------------------
tg = weights["text_to_graph"]  # (1, num_heads, T, N)
tg_mean = tg[0].mean(dim=0)    # (T, N) — mean across heads

print("=" * 60)
print("Checkpoint 12 — Synthetic cross-modal attention case study")
print("=" * 60)
print(f"Batch: {BATCH}, Text tokens: {NUM_TEXT}, Graph nodes: {NUM_GRAPH}")
print(f"Event-0 text tokens: 0-3  |  Event-0 graph nodes: 0-4")
print(f"Event-1 text tokens: 4-6  |  Event-1 graph nodes: 5-9")
print(f"Padding text: token 7      |  Padding graph: nodes 10-11")
print()
print("--- Text→Graph: top-3 graph nodes per text token (mean attention weight) ---")

for t_idx in range(NUM_TEXT):
    row = tg_mean[t_idx]  # (N,)
    top3_vals, top3_idxs = row.topk(min(3, NUM_GRAPH))
    top3_str = ", ".join(
        f"node {idx.item()}:{val.item():.4f}" for idx, val in zip(top3_idxs, top3_vals)
    )
    pad_flag = " [PAD]" if text_event_ids[0, t_idx].item() == -1 else ""
    eid = text_event_ids[0, t_idx].item()
    event_label = f"(event {eid})" if eid != -1 else "(padding)"
    print(f"  text[{t_idx}] {event_label}{pad_flag}: {top3_str}")

print()
print("--- Text→Graph: per-token attention entropy (nats) ---")
print("  (higher = more diffuse; lower = more focused)")

for t_idx in range(NUM_TEXT):
    row = tg_mean[t_idx]  # (N,)
    # Compute entropy over non-zero weights only (avoid log(0) at masked positions).
    nonzero = row[row > 0]
    if nonzero.numel() == 0:
        entropy_val = 0.0
    else:
        # Renormalise to ensure valid distribution.
        p = nonzero / nonzero.sum()
        entropy_val = -(p * p.log()).sum().item()
    pad_flag = " [PAD]" if text_event_ids[0, t_idx].item() == -1 else ""
    print(f"  text[{t_idx}]{pad_flag}: entropy = {entropy_val:.4f} nats")

print()
print("--- Output shapes ---")
print(f"  fused_text:  {tuple(fused_text.shape)}")
print(f"  fused_graph: {tuple(fused_graph.shape)}")

# Quick sanity: residual connection preserved magnitudes roughly.
text_delta = (fused_text - text_hidden).norm().item()
graph_delta = (fused_graph - graph_hidden).norm().item()
print()
print(f"  ||fused_text - text_hidden||:   {text_delta:.4f}")
print(f"  ||fused_graph - graph_hidden||: {graph_delta:.4f}")

print()
print("--- Mask sanity ---")
event0_graph_nodes = graph_event_ids[0] == 0  # (12,) — nodes 0-4
event1_graph_nodes = graph_event_ids[0] == 1  # (12,) — nodes 5-9
for t_idx in range(NUM_TEXT - 1):  # skip padding token
    eid = text_event_ids[0, t_idx].item()
    allowed_nodes = (graph_event_ids[0] == eid).nonzero(as_tuple=True)[0]
    blocked_nodes = (graph_event_ids[0] != eid).nonzero(as_tuple=True)[0]
    allowed_w = tg_mean[t_idx, allowed_nodes].sum().item()
    blocked_w = tg_mean[t_idx, blocked_nodes].sum().item()
    print(
        f"  text[{t_idx}] event {eid}: "
        f"weight on same-event nodes={allowed_w:.4f}, "
        f"weight on other nodes={blocked_w:.6f}"
    )

print()
print("Case study complete.")

# Minimum expected: max gradient norm for reference
params_norm = sum(p.norm().item() ** 2 for p in module.parameters()) ** 0.5
print(f"\n  Total parameter L2 norm: {params_norm:.2f}")
print(f"  Parameter breakdown: {module.parameter_breakdown()}")

# max entropy possible over N=5 event-0 graph nodes = ln(5)
max_entropy = math.log(5)
print(f"\n  Max possible entropy (event-0, 5 nodes): {max_entropy:.4f} nats")
