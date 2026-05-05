"""LogHetero BERT text encoder (Phase 2 deliverable).

Wraps ``bert-base-uncased`` and exposes three training-mode switches that
correspond to the ablation matrix B6 in ``docs/ablation_plan.md`` plus the
default frozen setup that decision 4.1 in ``docs/design_decisions.md``
mandates:

* ``"frozen"`` (default, CLIP-style) — every BERT parameter is frozen.
* ``"lora"`` — LoRA adapters on the last 4 transformer layers' query+value
  projections (PEFT 0.10+); rest of BERT frozen.
* ``"full"`` — full-parameter fine-tune; nothing is frozen.

Tokenizer is the augmented one from :mod:`loghetero.data.tokenizer`
(BERT vocab + 156 LogHetero special tokens), and the model's input
embedding matrix is resized + initialised via the synonym-mean strategy
already implemented in ``loghetero.data.tokenizer.init_special_token_embeddings``.

Forward returns the full ``BaseModelOutputWithPoolingAndCrossAttentions``
(with ``output_hidden_states=True``), so Phase 4's bidirectional cross-modal
attention can attach at layers 3 / 6 / 9 / 12 without further wiring.

Phase 2 contract: this module is integration only. No training, no losses,
no optimiser. The sanity check script in ``scripts/bert_sanity_check.py``
exercises the forward path against real ATLAS samples to verify the
nearest-neighbour retrieval makes semantic sense.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import torch


DEFAULT_BERT_MODEL = "bert-base-uncased"


class TrainMode(str, Enum):
    """Three Phase-7 ablation-matrix mode switches."""

    frozen = "frozen"
    lora = "lora"
    full = "full"


@dataclass(frozen=True, slots=True)
class LoRAConfig:
    """LoRA hyperparameters used in ``TrainMode.lora``.

    Defaults match the post-Checkpoint-3 sweep space; Phase 7 ablation B6
    will tune ``r`` if Phase-7 OOM permits.
    """

    r: int = 8
    alpha: int = 16
    dropout: float = 0.1
    target_modules: tuple[str, ...] = ("query", "value")
    layers_to_transform: tuple[int, ...] = (8, 9, 10, 11)  # last 4 of bert-base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_bert_text_encoder(
    model_name: str = DEFAULT_BERT_MODEL,
    *,
    mode: TrainMode | str = TrainMode.frozen,
    lora_config: LoRAConfig | None = None,
) -> tuple[Any, Any]:
    """Build the augmented BERT model + tokenizer used by LogHetero.

    Returns:
        ``(model, tokenizer)``.

        * ``model`` is the BERT (or PEFT-wrapped LoRA-BERT) instance with
          ``output_hidden_states=True`` configured. Already
          embedding-resized and synonym-mean-initialised for the 156
          LogHetero special tokens.
        * ``tokenizer`` is the augmented :class:`PreTrainedTokenizerBase`
          from :func:`loghetero.data.tokenizer.build_tokenizer`.
    """
    from transformers import AutoConfig, AutoModel

    from loghetero.data.tokenizer import (
        SPECIAL_TOKENS,
        build_tokenizer,
        init_special_token_embeddings,
    )

    mode = TrainMode(mode) if not isinstance(mode, TrainMode) else mode

    tokenizer = build_tokenizer(model_name)
    config = AutoConfig.from_pretrained(model_name)
    config.output_hidden_states = True
    model = AutoModel.from_pretrained(model_name, config=config)

    # Vocab expansion: 30,522 (BERT) + 156 (LogHetero) = 30,678.
    expected_added = len(SPECIAL_TOKENS)
    new_vocab = len(tokenizer)
    model.resize_token_embeddings(new_vocab)
    statuses = init_special_token_embeddings(model, tokenizer)
    n_init = sum(1 for v in statuses.values() if v == "initialised")
    if n_init < int(0.95 * expected_added):
        # Loud guard: the synonym-init invariant from Checkpoint 3 must hold.
        raise RuntimeError(
            f"Special-token init regression: {n_init}/{expected_added} initialised "
            f"(<95% threshold). Run scripts/check_synonym_init.py to diagnose."
        )

    _apply_train_mode(model, mode, lora_config or LoRAConfig())
    return model, tokenizer


def _apply_train_mode(model: Any, mode: TrainMode, lora_config: LoRAConfig) -> None:
    """Mutate ``model`` so its trainable parameter set matches ``mode``."""
    if mode is TrainMode.frozen:
        for p in model.parameters():
            p.requires_grad = False
        return

    if mode is TrainMode.full:
        for p in model.parameters():
            p.requires_grad = True
        return

    if mode is TrainMode.lora:
        from peft import LoraConfig, TaskType, get_peft_model

        # Freeze first; PEFT wrapper will unfreeze the LoRA adapters only.
        for p in model.parameters():
            p.requires_grad = False
        peft_cfg = LoraConfig(
            r=lora_config.r,
            lora_alpha=lora_config.alpha,
            lora_dropout=lora_config.dropout,
            target_modules=list(lora_config.target_modules),
            layers_to_transform=list(lora_config.layers_to_transform),
            bias="none",
            task_type=TaskType.FEATURE_EXTRACTION,
        )
        # PEFT mutates `model` in place but also returns the wrapped object;
        # we rely on the side-effect (caller already holds `model`). We do
        # NOT re-bind here so the caller's variable still points at the same
        # underlying nn.Module (PEFT installs hooks on the existing instance).
        get_peft_model(model, peft_cfg)
        return

    raise ValueError(f"unknown TrainMode: {mode!r}")


def count_trainable_parameters(model: Any) -> tuple[int, int]:
    """Return ``(trainable, total)`` parameter counts for the model.

    Used by the Phase 2 sanity report to verify each TrainMode reports the
    expected fraction of the BERT-base 110M parameters as trainable.
    """
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return trainable, total


def encode_texts(
    model: Any,
    tokenizer: Any,
    texts: list[str],
    *,
    pooling: str = "cls",
    max_length: int = 256,
) -> torch.Tensor:
    """Encode a batch of cleaned log-event texts into a fixed-size vector.

    Args:
        model: a model returned by :func:`build_bert_text_encoder`.
        tokenizer: matching tokenizer.
        texts: list of pre-cleaned event strings (use
            :func:`loghetero.data.datamodule.event_to_text`).
        pooling: ``"cls"`` (the [CLS] token) or ``"mean"`` (mean-pool the last
            hidden state with the attention mask).
        max_length: BERT input cap; long event strings are truncated.

    Returns:
        Tensor of shape ``(len(texts), hidden_size)``; for bert-base-uncased
        ``hidden_size == 768``.
    """
    import torch

    if pooling not in {"cls", "mean"}:
        raise ValueError(f"pooling must be 'cls' or 'mean', got {pooling!r}")
    enc = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    device = next(model.parameters()).device
    enc = {k: v.to(device) for k, v in enc.items()}
    with torch.no_grad():
        out = model(**enc)
    last_hidden = out.last_hidden_state  # (B, L, H)
    if pooling == "cls":
        return last_hidden[:, 0, :]
    mask = enc["attention_mask"].unsqueeze(-1).float()  # (B, L, 1)
    summed = (last_hidden * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp_min(1.0)
    return summed / counts
