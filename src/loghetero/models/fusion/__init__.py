"""Phase 4 cross-modal fusion modules."""

from loghetero.models.fusion.cross_attention import (
    CrossModalAttention,
    build_event_attention_mask,
)

__all__ = [
    "CrossModalAttention",
    "build_event_attention_mask",
]
