"""Anomaly detection probe MLP head (Phase 4 / Checkpoint 14.5).

Shared MLP architecture across all three probe configurations (HTGN-only,
BERT-only, and fusion).  Only the input_dim differs between configs.

MLP head architecture (RFC-14.5-8):

    nn.Sequential(
        nn.Linear(input_dim, 128),
        nn.ReLU(),
        nn.Dropout(0.1),
        nn.Linear(128, 1),
    )

Input dims (RFC-14.5-8):
    - HTGN-only:  256  (subject node's HTGN output embedding)
    - BERT-only:  768  (CLS token from final BERT hidden state)
    - fusion:     768  (fused_text[:, 0, :] CLS from Phase4Model output)

Event-level prediction rationale (RFC-14.5-3):

    event-level prediction 用 subject node embedding 是因为 HTGN 异构 attention
    已让 subject node 的 256-dim output 编码邻居 object 与 action 信息, 不需要
    显式 concat.

    For BERT-only and fusion configs: the CLS token (position 0) aggregates
    sequence-level information by BERT's pre-training design; it serves as a
    natural event-level representation for the binary classification head.

Three probe configs:
    - ``ProbeConfig.HTGN_ONLY``:  input_dim=256, embedding = HTGN subject-node output
    - ``ProbeConfig.BERT_ONLY``:  input_dim=768, embedding = BERT last-layer CLS token
    - ``ProbeConfig.FUSION``:     input_dim=768, embedding = Phase4Model fused_text CLS
"""

from __future__ import annotations

from enum import Enum

import torch
from torch import nn


class ProbeConfig(str, Enum):
    """Three probe configurations for the Checkpoint 14.5 experiment."""

    HTGN_ONLY = "htgn_only"
    BERT_ONLY = "bert_only"
    FUSION = "fusion"


# Input dimensionalities per config (RFC-14.5-8).
PROBE_INPUT_DIMS: dict[ProbeConfig, int] = {
    ProbeConfig.HTGN_ONLY: 256,
    ProbeConfig.BERT_ONLY: 768,
    ProbeConfig.FUSION: 768,
}


class ProbeClassifier(nn.Module):
    """Binary anomaly detection MLP head (shared template per RFC-14.5-8).

    Args:
        config: which of the three probe configurations this instance serves.
            Determines the input dimension (256 for HTGN-only; 768 for BERT/fusion).
        input_dim: override input dimension (default: taken from PROBE_INPUT_DIMS).
    """

    def __init__(
        self,
        config: ProbeConfig,
        *,
        input_dim: int | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self._input_dim: int = input_dim if input_dim is not None else PROBE_INPUT_DIMS[config]

        # RFC-14.5-8 locked architecture: same template across 3 configs.
        self.mlp = nn.Sequential(
            nn.Linear(self._input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 1),
        )

    @property
    def input_dim(self) -> int:
        return self._input_dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Compute binary logit from an event embedding.

        Args:
            x: event embedding tensor of shape ``(batch, input_dim)``
               or ``(input_dim,)`` for a single event.

        Returns:
            Raw logit tensor of shape ``(batch, 1)`` or ``(1,)`` (unsqueezed
            if needed).  Caller applies BCEWithLogitsLoss.
        """
        if x.dim() == 1:
            x = x.unsqueeze(0)  # (1, D)
        return self.mlp(x)  # (batch, 1)

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """Return sigmoid probability for positive class (label=1).

        Args:
            x: event embedding, shape ``(batch, input_dim)`` or ``(input_dim,)``.

        Returns:
            Probability tensor, shape ``(batch,)``.
        """
        with torch.no_grad():
            logit = self.forward(x)  # (batch, 1)
            return torch.sigmoid(logit).squeeze(-1)  # (batch,)

    def extra_repr(self) -> str:
        return f"config={self.config.value!r}, input_dim={self._input_dim}"
