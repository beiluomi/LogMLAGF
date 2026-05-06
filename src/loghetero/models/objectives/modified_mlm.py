"""Phase 4 / Checkpoint 13: Modified MLM task on post-fusion hidden states.

Overview
========
This module implements a **field-level masked language modelling** objective
that operates on the ``fused_text`` hidden states produced by
:class:`~loghetero.models.fusion.CrossModalAttention` (Checkpoint 12) rather
than on the raw BERT hidden states.  The prediction head is a single shared
linear layer (vocab=30,678) identical in structure to the standard BERT LM
head.

Two field-level mask operations (Q1 RFC resolution — LOCKED)
=============================================================

**替换 = Operation A**: Replace *every* token in a chosen field with the
``[MASK]`` token, keeping sequence length unchanged (one-to-one substitution).
The model predicts the original token ID at each masked position.

**删除 = Operation B**: Replace an entire field with a SINGLE ``[MASK]``
token.  The sequence shortens by ``field_len - 1`` positions.  The model
predicts a *representative* token for the deleted field at the surviving
``[MASK]`` anchor position.

  Representative token design choice (删除): The first non-``[CLS]``/
  non-``[SEP]`` token of the deleted field is used as the prediction target.
  Rationale: (a) The field's first wordpiece is typically the most semantically
  salient sub-token (the field key or first character of the value);
  (b) it is deterministic given the tokenization, requiring no additional
  hyperparameter; (c) for multi-wordpiece fields the first token is the root
  morpheme, which is what a reader would most naturally expect the model to
  recover.  For single-token fields the representative token is trivially the
  field's only token.  This choice is explicit and is documented here so
  Phase 5+ can revisit it (e.g. switching to the mode or the last sub-token)
  without guesswork.

**添加 = Operation C — DEFERRED to Phase 5+ (NOT implemented here)**

  Checkpoint 13 实施替换与删除两种字段级 mask 操作,添加机制延迟到 Phase 5+ 与
  RAPA 攻击模板实施时一起做。理由是攻击模板本身的语义就是"向良性事件序列中注入
  虚假/异常 field 或 event",与 RAPA-GTCL 的合成攻击逻辑天然耦合,Phase 5 实施时
  复用同一注入框架比 Checkpoint 13 单独造一个轻量添加机制更工程一致也更符合论文叙
  事。Phase 4 launch spec 的"目标字段替换/删除/添加机制"三件事在 Phase 4 完成
  两件,第三件在 Phase 5 完成不构成 spec 偏离。

  The Phase 5 待办 entry is committed in ``docs/known_issues.md`` at
  Checkpoint 13 (commit 1e62fab-era).

50/50 mix granularity (Q2 RFC resolution — LOCKED)
===================================================
Each sample in a batch independently rolls ``Bernoulli(0.5)`` to select
between:

* **Token-mask MLM** (mode=0): standard BERT-style token-level masking,
  15% probability per token.
* **Field-mask MLM** (mode=1): field-level masking (randomly choose 1-2
  fields per event, apply 替换 or 删除 at 50/50 probability each).

The collator records the per-sample mode decision in
``batch["mask_type_per_sample"]: Tensor(B,)`` for debug visibility
(sanity check #2 — the user verifies this key exists in every batch dump).

Single shared prediction head (Q1 sanity check #1)
===================================================
``ModifiedMLMHead`` is a **single** ``nn.Linear(hidden_dim, vocab_size)``
that handles ALL output positions regardless of which operation (替换 or
删除) produced the ``[MASK]``.  There is NO separate head per operation.
The operation-type label per masked position is available in the batch dict
for analysis (``op_labels``) but does NOT route to a different weight matrix.

Field boundary detection
========================
``event_to_text`` produces text of the form::

    "<operation> subject=<subject> object=<obj> <attr=val>..."

Fields are space-delimited at the string level.  We tokenize with
``return_offsets_mapping=True``, then for each space-delimited field span
``[char_start, char_end)`` we include all tokens whose offset overlaps
the field span (excluding ``[CLS]`` at position 0 and ``[SEP]`` at the
last position, which are non-field special tokens).  Tokens at the very
start / end of the sequence that map to offset ``(0, 0)`` (special tokens
inserted by the tokenizer) are always excluded from masking.

Dependency note: this module imports ``torch`` but NOT ``transformers`` at
the module level; ``transformers`` is lazy-imported inside functions that
need it so the module stays importable in the no-ML lint environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from torch import nn

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VOCAB_SIZE: int = 30_678  # bert-base-uncased (30,522) + 156 LogHetero tokens
BERT_HIDDEN_DIM: int = 768  # bert-base-uncased last hidden size
MASK_TOKEN_ID: int = 103  # [MASK] token id in bert-base-uncased
CLS_TOKEN_ID: int = 101  # [CLS]
SEP_TOKEN_ID: int = 102  # [SEP]
PAD_TOKEN_ID: int = 0  # [PAD]
IGNORE_INDEX: int = -100  # standard PyTorch CrossEntropyLoss ignore index
TOKEN_MASK_PROB: float = 0.15  # standard BERT token-masking probability
OP_REPLACE: int = 0  # 替换 operation label
OP_DELETE: int = 1  # 删除 operation label


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FieldMaskOutput:
    """Output of ``build_field_level_mask``.

    Attributes:
        input_ids: token ids with masked positions replaced by MASK_TOKEN_ID
            and (for 删除) shortened by collapsed fields.  Shape ``(T',)``.
        attention_mask: ``1`` for real tokens, ``0`` for pad.  Shape ``(T',)``.
        labels: target token ids at masked positions; ``IGNORE_INDEX`` at
            unmasked positions.  Shape ``(T',)``.
        op_labels: operation-type label at each position: ``OP_REPLACE`` for
            替换-masked positions, ``OP_DELETE`` for 删除-masked anchor
            positions, ``-1`` at unmasked positions.  Shape ``(T',)``.
    """

    input_ids: torch.Tensor
    attention_mask: torch.Tensor
    labels: torch.Tensor
    op_labels: torch.Tensor


@dataclass
class TokenMaskOutput:
    """Output of ``build_token_level_mask``.

    Attributes:
        input_ids: token ids with 15% positions replaced by MASK_TOKEN_ID.
        attention_mask: ``1`` for real tokens, ``0`` for pad.
        labels: target token ids at masked positions; ``IGNORE_INDEX`` elsewhere.
        op_labels: ``OP_REPLACE`` at masked positions, ``-1`` elsewhere
            (token-level masking is always 替换 semantics).
    """

    input_ids: torch.Tensor
    attention_mask: torch.Tensor
    labels: torch.Tensor
    op_labels: torch.Tensor


# ---------------------------------------------------------------------------
# Field boundary utility
# ---------------------------------------------------------------------------


def _detect_field_spans(
    text: str,
    tokenizer: Any,
    max_length: int = 128,
) -> list[tuple[int, int]]:
    """Detect token-index spans for each space-delimited field in ``text``.

    Uses ``offset_mapping`` (character-level) from the HuggingFace tokenizer
    to locate which tokens fall within each space-delimited field.

    Args:
        text: the event string produced by ``event_to_text``.
        tokenizer: the augmented BERT tokenizer (bert-base-uncased +
            LogHetero special tokens).
        max_length: max tokenization length; sequences are truncated to this.

    Returns:
        List of ``(start_tok_idx, end_tok_idx_exclusive)`` tuples, one per
        space-delimited field that has at least one token.  Indices are into
        the tokenized ``input_ids`` (0-indexed, 0 = [CLS], last = [SEP]).
        [CLS] and [SEP] positions are never included in any field span.
    """
    enc = tokenizer(
        text,
        max_length=max_length,
        truncation=True,
        return_offsets_mapping=True,
        return_tensors=None,  # return plain python lists
    )
    offsets: list[tuple[int, int]] = enc["offset_mapping"]  # type: ignore[assignment]
    # offsets[i] = (char_start, char_end) for token i; special tokens = (0, 0)

    # Find character-level field boundaries (split on spaces).
    fields: list[tuple[int, int]] = []
    n = len(text)
    start = 0
    while start < n:
        end = text.find(" ", start)
        if end == -1:
            end = n
        if end > start:
            fields.append((start, end))
        start = end + 1

    # For each field, find the token indices that overlap the char span.
    field_tok_spans: list[tuple[int, int]] = []
    for char_start, char_end in fields:
        tok_start = None
        tok_end = None
        for i, (cs, ce) in enumerate(offsets):
            # Skip special tokens (offset (0, 0)).
            if cs == 0 and ce == 0:
                continue
            # Check overlap with field char span: [cs, ce) ∩ [char_start, char_end)
            if ce > char_start and cs < char_end:
                if tok_start is None:
                    tok_start = i
                tok_end = i + 1  # exclusive
        if tok_start is not None and tok_end is not None:
            field_tok_spans.append((tok_start, tok_end))

    return field_tok_spans


# ---------------------------------------------------------------------------
# Field-level mask builder
# ---------------------------------------------------------------------------


def build_field_level_mask(
    input_ids: torch.Tensor,
    text: str,
    tokenizer: Any,
    *,
    n_fields_to_mask: int = 1,
    delete_prob: float = 0.5,
    max_length: int = 128,
    rng: torch.Generator | None = None,
) -> FieldMaskOutput:
    """Build a field-level masked input (替换 and/or 删除 operations).

    For each sampled field, independently decides 替换 vs 删除 with
    probability ``delete_prob`` for 删除.

    **替换 (replace)**: every token in the field is replaced with
    ``[MASK]``.  Sequence length unchanged.  Labels at masked positions =
    original token ids; ``IGNORE_INDEX`` elsewhere.

    **删除 (delete)**: the entire field is collapsed to a SINGLE ``[MASK]``
    token (sequence shortens by ``field_len - 1``).  Label at the anchor
    ``[MASK]`` = the *first* token of the original field.  ``IGNORE_INDEX``
    elsewhere.

    Both operations set ``op_labels`` at their masked/anchor positions
    (``OP_REPLACE`` / ``OP_DELETE`` respectively).

    Args:
        input_ids: ``(T,)`` long tensor (already tokenized, including [CLS]
            and [SEP]).
        text: the original event string (before tokenization) so we can
            re-detect field spans via ``_detect_field_spans``.
        tokenizer: augmented BERT tokenizer.
        n_fields_to_mask: number of fields to mask (default 1).
        delete_prob: probability of applying 删除 vs 替换 for each chosen
            field (default 0.5).
        max_length: tokenization cap (must match the cap used to produce
            ``input_ids``).
        rng: optional ``torch.Generator`` for reproducibility.

    Returns:
        :class:`FieldMaskOutput` with ``input_ids``, ``attention_mask``,
        ``labels``, and ``op_labels`` tensors.
    """
    seq_len = input_ids.shape[0]
    field_spans = _detect_field_spans(text, tokenizer, max_length=max_length)

    if not field_spans:
        # Fallback: no fields detected (extremely short or empty text).
        # Return input unchanged with all IGNORE_INDEX labels.
        return FieldMaskOutput(
            input_ids=input_ids.clone(),
            attention_mask=torch.ones(seq_len, dtype=torch.long),
            labels=torch.full((seq_len,), IGNORE_INDEX, dtype=torch.long),
            op_labels=torch.full((seq_len,), -1, dtype=torch.long),
        )

    # Sample which fields to mask (without replacement, up to n_fields_to_mask).
    n_available = len(field_spans)
    n_to_mask = min(n_fields_to_mask, n_available)
    perm = torch.randperm(n_available, generator=rng)
    chosen_indices = perm[:n_to_mask].tolist()

    # We'll build the modified sequence as a list of token id segments.
    # Start with a copy of the original ids.
    ids_list = input_ids.tolist()
    labels_list = [IGNORE_INDEX] * seq_len
    op_list = [-1] * seq_len

    # Process chosen fields in reverse order so that token indices remain valid
    # when we shrink the sequence for 删除.
    chosen_spans = sorted(
        [field_spans[i] for i in chosen_indices], key=lambda s: s[0], reverse=True
    )

    for tok_start, tok_end in chosen_spans:
        # Guard: clamp to actual sequence length (truncation may have cut the field).
        tok_end = min(tok_end, len(ids_list) - 1)  # leave [SEP] intact
        if tok_start >= tok_end:
            continue

        # Decide operation.
        use_delete = torch.rand(1, generator=rng).item() < delete_prob

        if not use_delete:
            # --- 替换 (Operation A): one-to-one MASK replacement ---
            for idx in range(tok_start, tok_end):
                labels_list[idx] = ids_list[idx]
                op_list[idx] = OP_REPLACE
                ids_list[idx] = MASK_TOKEN_ID
        else:
            # --- 删除 (Operation B): collapse to single MASK anchor ---
            # Representative token = first token of the field.
            representative = ids_list[tok_start]
            # Splice: replace field tokens with a single MASK.
            ids_list[tok_start:tok_end] = [MASK_TOKEN_ID]
            # Labels and op_list must also shrink: replace field_len entries
            # with a single entry at tok_start.
            labels_list[tok_start:tok_end] = [representative]
            op_list[tok_start:tok_end] = [OP_DELETE]

    new_seq_len = len(ids_list)
    result_ids = torch.tensor(ids_list, dtype=torch.long)
    result_labels = torch.tensor(labels_list, dtype=torch.long)
    result_op = torch.tensor(op_list, dtype=torch.long)
    attn_mask = torch.ones(new_seq_len, dtype=torch.long)

    return FieldMaskOutput(
        input_ids=result_ids,
        attention_mask=attn_mask,
        labels=result_labels,
        op_labels=result_op,
    )


# ---------------------------------------------------------------------------
# Token-level mask builder (standard BERT MLM)
# ---------------------------------------------------------------------------


def build_token_level_mask(
    input_ids: torch.Tensor,
    *,
    mask_prob: float = TOKEN_MASK_PROB,
    rng: torch.Generator | None = None,
) -> TokenMaskOutput:
    """Build a standard BERT token-level MLM mask (替换 semantics only).

    Each non-special token is independently replaced by ``[MASK]`` with
    probability ``mask_prob`` (default 0.15).  Special tokens ([CLS], [SEP],
    [PAD]) are never masked.

    Unlike the canonical BERT implementation, we apply 100% [MASK]
    substitution (no 10% keep / 10% random swap) for simplicity and to
    ensure a clean apples-to-apples comparison with the field-level masking
    in the Q3 perplexity experiment.

    Args:
        input_ids: ``(T,)`` long tensor.
        mask_prob: fraction of non-special tokens to mask (default 0.15).
        rng: optional ``torch.Generator``.

    Returns:
        :class:`TokenMaskOutput`.
    """
    seq_len = input_ids.shape[0]

    # Build a boolean mask: True = eligible for masking (not a special token).
    special_ids = {CLS_TOKEN_ID, SEP_TOKEN_ID, PAD_TOKEN_ID}
    eligible = torch.tensor(
        [int(ids.item()) not in special_ids for ids in input_ids],
        dtype=torch.bool,
    )

    # Sample uniformly from eligible positions.
    rand_vals = torch.rand(seq_len, generator=rng)
    mask_positions = eligible & (rand_vals < mask_prob)

    new_input_ids = input_ids.clone()
    new_input_ids[mask_positions] = MASK_TOKEN_ID

    labels = torch.full((seq_len,), IGNORE_INDEX, dtype=torch.long)
    labels[mask_positions] = input_ids[mask_positions]

    op_labels = torch.full((seq_len,), -1, dtype=torch.long)
    op_labels[mask_positions] = OP_REPLACE

    return TokenMaskOutput(
        input_ids=new_input_ids,
        attention_mask=torch.ones(seq_len, dtype=torch.long),
        labels=labels,
        op_labels=op_labels,
    )


# ---------------------------------------------------------------------------
# Mixed MLM collator
# ---------------------------------------------------------------------------


def _pad_to_max(
    tensors: list[torch.Tensor],
    pad_value: int,
    max_len: int | None = None,
) -> torch.Tensor:
    """Right-pad a list of 1-D tensors to the same length and stack."""
    if max_len is None:
        max_len = max(t.shape[0] for t in tensors)
    result = torch.full((len(tensors), max_len), pad_value, dtype=tensors[0].dtype)
    for i, t in enumerate(tensors):
        length = min(t.shape[0], max_len)
        result[i, :length] = t[:length]
    return result


class MixedMLMCollator:
    """Per-sample Bernoulli(0.5) MLM mode selection collator.

    Each sample independently rolls ``Bernoulli(0.5)`` to decide between:

    * **mode 0** (token-mask): standard BERT 15%-token-level MLM.
    * **mode 1** (field-mask): field-level masking (随机 替换 or 删除).

    The batch output dict includes ``mask_type_per_sample: Tensor(B,)``
    (values 0 or 1) so a developer dumping a batch in a debugger can
    immediately see the per-sample mode assignment.  This satisfies
    sanity check #2.

    Both modes produce ``input_ids``, ``attention_mask``, ``labels``, and
    ``op_labels`` tensors; sequences of different lengths (due to 删除
    collapse) are right-padded with ``[PAD]`` (id=0).

    Args:
        tokenizer: the augmented BERT tokenizer (used for field-boundary
            detection in mode 1).
        max_length: tokenization cap for field-boundary detection.
        n_fields_to_mask: number of fields to mask per sample in mode 1.
        field_delete_prob: probability of 删除 vs 替换 for each chosen
            field in mode 1.
        token_mask_prob: probability per non-special token in mode 0.
        seed: base RNG seed; each collator call advances the RNG state.
    """

    def __init__(
        self,
        tokenizer: Any,
        *,
        max_length: int = 128,
        n_fields_to_mask: int = 1,
        field_delete_prob: float = 0.5,
        token_mask_prob: float = TOKEN_MASK_PROB,
        seed: int = 42,
    ) -> None:
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.n_fields_to_mask = n_fields_to_mask
        self.field_delete_prob = field_delete_prob
        self.token_mask_prob = token_mask_prob
        self._rng = torch.Generator()
        self._rng.manual_seed(seed)

    def __call__(
        self,
        batch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Collate a list of samples.

        Each sample dict must contain:
        * ``"input_ids"`` (torch.Tensor, shape ``(T,)``): tokenized input.
        * ``"text"`` (str): the raw event string (for field-boundary
          detection in mode 1).

        Returns a dict with keys:
        * ``input_ids``: ``(B, T_max)`` long tensor.
        * ``attention_mask``: ``(B, T_max)`` long tensor.
        * ``labels``: ``(B, T_max)`` long tensor.
        * ``op_labels``: ``(B, T_max)`` long tensor (``-1`` at unmasked positions).
        * ``mask_type_per_sample``: ``(B,)`` long tensor, 0 = token-mask,
          1 = field-mask (debug visibility — sanity check #2).
        """
        all_input_ids: list[torch.Tensor] = []
        all_attn_masks: list[torch.Tensor] = []
        all_labels: list[torch.Tensor] = []
        all_op_labels: list[torch.Tensor] = []
        mask_types: list[int] = []

        for sample in batch:
            raw_ids: torch.Tensor = sample["input_ids"]
            text: str = sample["text"]

            # Per-sample mode decision: Bernoulli(0.5).
            mode = int(torch.bernoulli(torch.tensor(0.5), generator=self._rng).item())
            mask_types.append(mode)

            if mode == 0:
                # Token-level masking.
                out = build_token_level_mask(
                    raw_ids,
                    mask_prob=self.token_mask_prob,
                    rng=self._rng,
                )
                all_input_ids.append(out.input_ids)
                all_attn_masks.append(out.attention_mask)
                all_labels.append(out.labels)
                all_op_labels.append(out.op_labels)
            else:
                # Field-level masking.
                out_f = build_field_level_mask(
                    raw_ids,
                    text,
                    self.tokenizer,
                    n_fields_to_mask=self.n_fields_to_mask,
                    delete_prob=self.field_delete_prob,
                    max_length=self.max_length,
                    rng=self._rng,
                )
                all_input_ids.append(out_f.input_ids)
                all_attn_masks.append(out_f.attention_mask)
                all_labels.append(out_f.labels)
                all_op_labels.append(out_f.op_labels)

        # Determine max sequence length across samples (may vary due to 删除).
        max_len = max(t.shape[0] for t in all_input_ids)

        return {
            "input_ids": _pad_to_max(all_input_ids, PAD_TOKEN_ID, max_len),
            "attention_mask": _pad_to_max(all_attn_masks, 0, max_len),
            "labels": _pad_to_max(all_labels, IGNORE_INDEX, max_len),
            "op_labels": _pad_to_max(all_op_labels, -1, max_len),
            # Sanity check #2: always present, (B,) long.
            "mask_type_per_sample": torch.tensor(mask_types, dtype=torch.long),
        }


# ---------------------------------------------------------------------------
# Prediction head (single shared head — sanity check #1)
# ---------------------------------------------------------------------------


class ModifiedMLMHead(nn.Module):
    """Single shared MLM prediction head for fused hidden states.

    Consumes ``fused_text`` from
    :class:`~loghetero.models.fusion.CrossModalAttention` and produces
    logits over the full vocabulary (size ``vocab_size=30,678``).

    The **same weight matrix** is used for both 替换-masked positions and
    删除-masked anchor positions.  There is no routing by operation type:
    the head sees ``(B, T, hidden_dim)`` hidden states and projects to
    ``(B, T, vocab_size)`` regardless of which operation produced any
    given ``[MASK]`` token.  This satisfies sanity check #1.

    Architecture (matching standard BERT LM head):
        Linear(hidden_dim, hidden_dim) → GELU → LayerNorm(hidden_dim) → Linear(hidden_dim, vocab_size)

    The GELU + LayerNorm transform is consistent with BERT's MLM head
    (``BertOnlyMLMHead`` in HuggingFace Transformers) and ensures that
    the loss landscape seen by the head's linear projection is smooth.

    Args:
        hidden_dim: input hidden size (default 768 for BERT-base).
        vocab_size: output vocabulary size (default 30,678 = BERT 30,522
            + 156 LogHetero special tokens).
    """

    def __init__(
        self,
        hidden_dim: int = BERT_HIDDEN_DIM,
        vocab_size: int = VOCAB_SIZE,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.vocab_size = vocab_size

        # Match BERT's MLM head: dense → GELU → norm → decoder.
        self.dense = nn.Linear(hidden_dim, hidden_dim)
        self.gelu = nn.GELU()
        self.layer_norm = nn.LayerNorm(hidden_dim)
        self.decoder = nn.Linear(hidden_dim, vocab_size)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Project hidden states to vocabulary logits.

        Args:
            hidden_states: ``(B, T, hidden_dim)`` — typically ``fused_text``
                from CrossModalAttention.

        Returns:
            ``(B, T, vocab_size)`` logits.
        """
        x = self.dense(hidden_states)
        x = self.gelu(x)
        x = self.layer_norm(x)
        return self.decoder(x)


# ---------------------------------------------------------------------------
# Loss computation
# ---------------------------------------------------------------------------


def compute_mlm_loss(
    logits: torch.Tensor,
    labels: torch.Tensor,
) -> torch.Tensor:
    """Cross-entropy loss over masked positions only.

    Both 替换 and 删除 contribute to the same loss tensor (their labels are
    in the same ``labels`` tensor; non-masked positions have ``IGNORE_INDEX``).

    Args:
        logits: ``(B, T, vocab_size)`` — output of ``ModifiedMLMHead``.
        labels: ``(B, T)`` long tensor with ``IGNORE_INDEX`` at unmasked
            positions.

    Returns:
        Scalar loss tensor (mean over unignored positions).
    """
    vocab_size = logits.shape[-1]
    # Flatten to (B*T, vocab_size) and (B*T,) for F.cross_entropy.
    flat_logits = logits.view(-1, vocab_size)
    flat_labels = labels.view(-1)
    return nn.functional.cross_entropy(
        flat_logits,
        flat_labels,
        ignore_index=IGNORE_INDEX,
        reduction="mean",
    )
