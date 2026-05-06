"""Phase 4 / Checkpoint 13 MLM objectives."""

from loghetero.models.objectives.modified_mlm import (
    IGNORE_INDEX,
    MASK_TOKEN_ID,
    OP_DELETE,
    OP_REPLACE,
    TOKEN_MASK_PROB,
    VOCAB_SIZE,
    FieldMaskOutput,
    MixedMLMCollator,
    ModifiedMLMHead,
    TokenMaskOutput,
    build_field_level_mask,
    build_token_level_mask,
    compute_mlm_loss,
)

__all__ = [
    "IGNORE_INDEX",
    "MASK_TOKEN_ID",
    "OP_DELETE",
    "OP_REPLACE",
    "TOKEN_MASK_PROB",
    "VOCAB_SIZE",
    "FieldMaskOutput",
    "MixedMLMCollator",
    "ModifiedMLMHead",
    "TokenMaskOutput",
    "build_field_level_mask",
    "build_token_level_mask",
    "compute_mlm_loss",
]
