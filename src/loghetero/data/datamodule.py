"""Phase 1.6 / Checkpoint 5: Lightning DataModule for LogHetero.

Implements decisions 6 + 9 + 8:

* **Decision 6**: leave-one-attack-out split keyed on ``(host_id, time_window)``;
  the invariant "every events from a (host, window) bucket all go train OR all
  go test" is enforced by a fail-fast ``AssertionError`` in ``setup()``.
* **Decision 9**: training / eval sample unit is the
  ``(target_event, subgraph_at_target, label)`` triple. Per-window sampling
  uniformly down-samples benign events to ``cfg.sample.max_events_per_window``;
  attack events are always kept in full.
* **Decision 8**: subgraph sampler attaches the ``isolated`` mask recomputed
  on subgraph degree (handled by ``subgraph_sampler.sample_khop_subgraph``).

Two ``setup()`` asserts that fire fast and loud (counter-example tests cover
both):

1. ``_assert_no_window_leakage`` -- decision 6 invariant.
2. ``_assert_tz_alignment`` -- the dns (Eastern) and firefox (UTC) first events
   per host must be within ±5 minutes; otherwise the localize_eastern
   assumption in ``parsers/atlas.py`` is wrong and the entire
   ``(host_id, time_window)`` split is silently invalid.

Phase 8 will plug a real ATLAS-ground-truth label loader into
``finetune_anomaly`` mode; today the stub ``benign_only_label_loader`` keeps
the API stable.
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from loghetero.data.log_cleaner import clean
from loghetero.data.parsers.atlas import (
    DnsParser,
    FirefoxParser,
    SecurityEventsParser,
)
from loghetero.data.parsers.base import EdgeType, Event, NodeType
from loghetero.data.provenance_graph import build_graph
from loghetero.data.subgraph_sampler import SeedNode, sample_khop_subgraph
from loghetero.data.window_splitter import window_index

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class DataMode(str, Enum):
    """The three operating modes the DataModule supports (decision 9)."""

    pretrain = "pretrain"
    finetune_anomaly = "finetune_anomaly"
    finetune_compression = "finetune_compression"


# Label loader: maps an Event to its supervised label (0=benign / 1=attack)
# or None for the unsupervised pretrain mode.
LabelLoader = Callable[[Event], int | None]


def benign_only_label_loader(event: Event) -> int:
    """Phase-8 placeholder label loader: returns 0 for every event.

    The real ``AtlasAttackEntityLabelLoader`` will land in Phase 8 driven by
    the ATLAS paper_experiments/* attack-entity lists. The DataModule
    interface keeps this callable swap-pluggable so Phase 8 only changes the
    constructor argument, not any DataModule code.
    """
    return 0


# ---------------------------------------------------------------------------
# (Host, window) bucket abstractions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HostWindowKey:
    """Canonical join key for decision 6's (host_id, time_window) splitting."""

    host_id: str
    window_idx: int


@dataclass(slots=True)
class TargetSample:
    """A single training / eval sample post sampling."""

    host_window: HostWindowKey
    event_idx_in_host: int  # offset into events_by_host[host_id]
    label: int | None        # None in pretrain mode


# ---------------------------------------------------------------------------
# Setup-time invariants (decision 6 + TZ sanity).
# Module-level functions so the counter-example tests can hit them directly
# without spinning up the full DataModule.
# ---------------------------------------------------------------------------


def _assert_no_window_leakage(
    train_keys: set[HostWindowKey], test_keys: set[HostWindowKey]
) -> None:
    """Decision 6 invariant: every (host, window) bucket lives in exactly one
    of {train, test}; cross-set leakage is fatal."""
    overlap = train_keys & test_keys
    if overlap:
        sample = sorted([(k.host_id, k.window_idx) for k in list(overlap)[:5]])
        raise AssertionError(
            f"DECISION 6 VIOLATION: {len(overlap)} (host, window) bucket(s) "
            f"appear in BOTH train and test. Decision 6 requires every bucket "
            f"to live in exactly one split to prevent host-fingerprint leakage "
            f"(KAIROS / MAGIC criticism of original ATLAS protocol). "
            f"First {min(5, len(overlap))} offending keys: {sample}. "
            f"Inspect the partitioning logic in "
            f"loghetero.data.datamodule.LogHeteroDataModule._partition_by_scenario."
        )


def _assert_tz_alignment(
    events_by_host: dict[str, list[Event]], *, max_delta_minutes: float = 5.0
) -> None:
    """TZ sanity: per-host, dns first event vs firefox first event must be
    within ±max_delta_minutes (default 5).

    The two streams are produced on the same VM, so their first observed
    events must be temporally close. dns timestamps are naive and rely on
    ``parsers/atlas.py::localize_eastern`` to convert to UTC; if that
    conversion is wrong (e.g. localize as PST instead of EST), the delta
    blows up to several hours. Failing this assert points the user
    straight at the right call site.
    """
    for host_id, events in events_by_host.items():
        first_by_lt: dict[str, int] = {}
        for ev in events:
            if ev.log_type not in first_by_lt:
                first_by_lt[ev.log_type] = ev.timestamp_ns
            if "atlas.dns" in first_by_lt and "atlas.firefox" in first_by_lt:
                break
        if "atlas.dns" not in first_by_lt or "atlas.firefox" not in first_by_lt:
            continue  # this host doesn't have both streams; skip rather than error
        delta_ns = abs(first_by_lt["atlas.dns"] - first_by_lt["atlas.firefox"])
        delta_min = delta_ns / (60 * 1_000_000_000)
        if delta_min > max_delta_minutes:
            raise AssertionError(
                f"TZ SANITY FAIL for host {host_id!r}: first dns event vs "
                f"first firefox event differ by {delta_min:.1f} minutes "
                f"(threshold = {max_delta_minutes} min). The two streams come "
                f"from the same VM, so this big a gap means the dns -> UTC "
                f"conversion is wrong. Check "
                f"loghetero.data.parsers.atlas::localize_eastern (currently "
                f"assumes America/New_York) -- the dataset's source timezone "
                f"may not match."
            )


# ---------------------------------------------------------------------------
# Sampling (decision 9)
# ---------------------------------------------------------------------------


def sample_target_events(
    events_in_window: list[tuple[int, Event]],
    *,
    max_events_per_window: int,
    label_loader: LabelLoader,
    rng: np.random.Generator,
) -> list[tuple[int, Event, int | None]]:
    """Down-sample target events from a (host, window) bucket per decision 9.

    Args:
        events_in_window: list of ``(event_idx_in_host, event)`` pairs.
        max_events_per_window: cap from ``cfg.sample.max_events_per_window``.
        label_loader: maps an event to its label (or None).
        rng: a *seeded* ``numpy.random.Generator``; the Phase-1.6 contract is
            that two runs with the same seed produce the same target-event
            set (random_state from utils/seed.py).

    Returns:
        ``[(event_idx, event, label), ...]``. Attack events (label == 1) are
        ALWAYS kept in full; benign events are uniformly down-sampled to fit
        the cap once attack events are accounted for.
    """
    attacks: list[tuple[int, Event, int | None]] = []
    benigns: list[tuple[int, Event, int | None]] = []
    for ev_idx, ev in events_in_window:
        label = label_loader(ev)
        if label == 1:
            attacks.append((ev_idx, ev, label))
        else:
            benigns.append((ev_idx, ev, label))

    benign_budget = max(0, max_events_per_window - len(attacks))
    if len(benigns) <= benign_budget:
        kept_benigns = benigns
    else:
        # Uniform random sample without replacement; rng.choice with replace=False
        # is reproducible under the seeded generator.
        idx = rng.choice(len(benigns), size=benign_budget, replace=False)
        kept_benigns = [benigns[int(i)] for i in idx]

    return attacks + kept_benigns


# ---------------------------------------------------------------------------
# Text / subgraph rendering (decision 9 sample format)
# ---------------------------------------------------------------------------


def event_to_text(ev: Event) -> str:
    """Render an Event into the cleaned, single-line text fed to BERT.

    Format: ``"<operation> subject=<subject> object=<obj> <attr=val>..."``,
    then run through :func:`loghetero.data.log_cleaner.clean` so concrete IPs
    / paths / hashes become the special-token placeholders the LogHetero
    tokenizer recognises.
    """
    op = ev.operation.value if hasattr(ev.operation, "value") else str(ev.operation)
    parts = [op, f"subject={ev.subject}", f"object={ev.obj}"]
    for k, v in sorted(ev.attributes.items()):
        if v is None or v == "":
            continue
        parts.append(f"{k}={v}")
    return clean(" ".join(parts))


def event_to_seed_node(ev: Event, host_graph_index: dict[NodeType, dict[str, int]]) -> SeedNode:
    """Resolve an event's subject to its node index within the host graph."""
    name_to_idx = host_graph_index.get(ev.subject_type, {})
    if ev.subject not in name_to_idx:
        raise KeyError(
            f"event subject {ev.subject!r} of type {ev.subject_type} not present "
            f"in host graph index. Did you build the graph from the same Event "
            f"stream you are sampling from?"
        )
    return SeedNode(node_type=ev.subject_type, node_idx=name_to_idx[ev.subject])


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class LogHeteroDataset:
    """Returns ``(text, subgraph, label)`` per sample (decision 9).

    Plain ``__len__`` / ``__getitem__`` interface so it works as a
    ``torch.utils.data.Dataset`` without requiring torch at import time
    (the actual DataLoader integration is in ``LogHeteroDataModule``).
    """

    def __init__(
        self,
        events_by_host: dict[str, list[Event]],
        host_graphs: dict[str, Any],  # HeteroData
        host_graph_indices: dict[str, dict[NodeType, dict[str, int]]],
        target_samples: list[TargetSample],
        *,
        subgraph_max_nodes: int,
        subgraph_khop: int,
        subgraph_edge_ranking: str,
        mode: DataMode,
    ) -> None:
        self.events_by_host = events_by_host
        self.host_graphs = host_graphs
        self.host_graph_indices = host_graph_indices
        self.target_samples = target_samples
        self.subgraph_max_nodes = subgraph_max_nodes
        self.subgraph_khop = subgraph_khop
        self.subgraph_edge_ranking = subgraph_edge_ranking
        self.mode = mode

    def __len__(self) -> int:
        return len(self.target_samples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        sample = self.target_samples[idx]
        host_id = sample.host_window.host_id
        ev = self.events_by_host[host_id][sample.event_idx_in_host]
        graph = self.host_graphs[host_id]
        seed = event_to_seed_node(ev, self.host_graph_indices[host_id])
        sub = sample_khop_subgraph(
            graph,
            seed,
            max_nodes=self.subgraph_max_nodes,
            khop=self.subgraph_khop,
            edge_ranking=self.subgraph_edge_ranking,
            target_timestamp_ns=ev.timestamp_ns
            if self.subgraph_edge_ranking != "weight"
            else None,
        )
        return {
            "text": event_to_text(ev),
            "subgraph": sub,
            "label": None if self.mode is DataMode.pretrain else sample.label,
            "host_window": (sample.host_window.host_id, sample.host_window.window_idx),
            "event_idx": sample.event_idx_in_host,
        }


# ---------------------------------------------------------------------------
# DataModule
# ---------------------------------------------------------------------------


# Map log-file basename to its concrete Parser class. Typed as
# Callable[[], object] to sidestep mypy's "cannot instantiate abstract
# Parser" complaint -- at runtime these are concrete subclasses, but mypy
# lifts to the common base type and then refuses Parser().
_PARSERS_BY_FILENAME: dict[str, Callable[[], Any]] = {
    "dns": DnsParser,
    "firefox.txt": FirefoxParser,
    "security_events.txt": SecurityEventsParser,
}


@dataclass(slots=True)
class FoldStats:
    """Per-leave-one-attack-out fold report fields."""

    leave_out: str
    train_n_target_events: int
    test_n_target_events: int
    train_n_host_window_keys: int
    test_n_host_window_keys: int
    train_attack_count: int
    test_attack_count: int
    train_benign_count: int
    test_benign_count: int


class LogHeteroDataModule:
    """Lightning-style DataModule (without depending on lightning at import).

    The ``setup`` method:

    1. Discovers the (scenario, host) pairs from ``cfg.data_dir`` (16 for
       ATLAS).
    2. Parses each (scenario, host)'s 3 logs into a flat event list.
    3. Runs :func:`_assert_tz_alignment` on the events (fail-fast on TZ bugs).
    4. Buckets events by ``(host, time_window)`` per
       ``cfg.window.time_window_hours``.
    5. Partitions the buckets into ``train`` / ``test`` based on which
       scenarios are left-out.
    6. Runs :func:`_assert_no_window_leakage` (fail-fast on cross-set leakage).
    7. Per bucket samples target events per :func:`sample_target_events`.
    8. Builds per-host HeteroData graphs once (used by all dataset accesses).
    9. Constructs the train / val / test :class:`LogHeteroDataset` objects.

    For ``pretrain`` mode there is no leave-out: all 16 hosts feed the train
    loader and the val/test loaders return small held-out slices for sanity.
    For ``finetune_anomaly`` and ``finetune_compression`` modes,
    ``leave_out_scenario`` selects the test scenario.
    """

    def __init__(
        self,
        cfg: Any,  # OmegaConf DictConfig or dict-like
        *,
        mode: DataMode | str = DataMode.pretrain,
        leave_out_scenario: str | None = None,
        label_loader: LabelLoader | None = None,
        seed: int = 42,
    ) -> None:
        self.cfg = cfg
        self.mode = DataMode(mode) if not isinstance(mode, DataMode) else mode
        self.leave_out_scenario = leave_out_scenario
        self.label_loader = label_loader or benign_only_label_loader
        self.seed = seed

        # Populated by setup()
        self.train_dataset: LogHeteroDataset | None = None
        self.val_dataset: LogHeteroDataset | None = None
        self.test_dataset: LogHeteroDataset | None = None
        self.fold_stats: FoldStats | None = None

        # Internal state
        self._events_by_host: dict[str, list[Event]] = {}
        self._host_graphs: dict[str, Any] = {}
        self._host_graph_indices: dict[str, dict[NodeType, dict[str, int]]] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def setup(self, stage: str | None = None) -> None:
        """Lightning calls this once per fit/validate/test."""
        if (
            self.mode is not DataMode.pretrain
            and self.leave_out_scenario is None
        ):
            raise ValueError(
                f"mode={self.mode} requires leave_out_scenario to be set "
                "(one of the ATLAS scenario ids, e.g. 'M1' or 'S2')."
            )

        # 1-2: parse all events for every host
        data_dir = Path(self.cfg.data_dir)
        for host_id, events in self._iter_host_events(data_dir):
            self._events_by_host[host_id] = events

        # 3: TZ sanity (fail-fast on parsers/atlas.py::localize_eastern bugs)
        _assert_tz_alignment(self._events_by_host)

        # 4: bucket events by (host, time_window)
        window_hours = float(self.cfg.window.time_window_hours)
        bucketed = self._bucket_events_by_window(window_hours)

        # 5: partition (host, window) keys into train / test
        train_keys, test_keys = self._partition_by_scenario(bucketed)

        # 6: decision 6 leakage assert (fail-fast)
        _assert_no_window_leakage(train_keys, test_keys)

        # 7-8: sample target events + build per-host graphs
        rng = np.random.default_rng(self.seed)
        max_per_window = int(self.cfg.sample.max_events_per_window)
        train_samples = self._sample(bucketed, train_keys, rng, max_per_window)
        test_samples = self._sample(bucketed, test_keys, rng, max_per_window)

        for host_id, events in self._events_by_host.items():
            graph, _ = build_graph(events)
            self._host_graphs[host_id] = graph
            self._host_graph_indices[host_id] = self._build_index(graph)

        # 9: construct datasets
        sub_cfg = self.cfg.subgraph
        max_nodes = int(sub_cfg.max_nodes)
        khop = int(sub_cfg.khop)
        edge_ranking = str(sub_cfg.edge_ranking)

        def _make_dataset(samples: list[TargetSample]) -> LogHeteroDataset:
            return LogHeteroDataset(
                events_by_host=self._events_by_host,
                host_graphs=self._host_graphs,
                host_graph_indices=self._host_graph_indices,
                target_samples=samples,
                subgraph_max_nodes=max_nodes,
                subgraph_khop=khop,
                subgraph_edge_ranking=edge_ranking,
                mode=self.mode,
            )

        self.train_dataset = _make_dataset(train_samples)
        self.test_dataset = _make_dataset(test_samples)

        # val: random slice of train (10%) for cheap sanity during pretrain
        n_val = max(1, len(train_samples) // 10)
        rng_val = np.random.default_rng(self.seed + 1)
        val_idx = rng_val.choice(len(train_samples), size=n_val, replace=False)
        val_samples = [train_samples[int(i)] for i in val_idx]
        self.val_dataset = _make_dataset(val_samples)

        self.fold_stats = self._compute_fold_stats(train_samples, test_samples, train_keys, test_keys)

    def train_dataloader(self) -> Any:
        return self._make_loader(self.train_dataset, shuffle=True)

    def val_dataloader(self) -> Any:
        return self._make_loader(self.val_dataset, shuffle=False)

    def test_dataloader(self) -> Any:
        return self._make_loader(self.test_dataset, shuffle=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _iter_host_events(self, data_dir: Path):
        """Yield ``(host_id, [Event, ...])`` for each (scenario, host) pair."""
        for scenario_dir in sorted(data_dir.iterdir()):
            if not scenario_dir.is_dir():
                continue
            scenario = scenario_dir.name
            if (scenario_dir / "logs").is_dir():
                host_units = [(scenario_dir / "logs", scenario)]
            else:
                host_units = []
                for sub in sorted(scenario_dir.iterdir()):
                    if sub.is_dir() and (sub / "logs").is_dir():
                        host_units.append((sub / "logs", f"{scenario}_{sub.name}"))
            for logs_dir, host_id in host_units:
                events: list[Event] = []
                for fname, parser_cls in _PARSERS_BY_FILENAME.items():
                    p = logs_dir / fname
                    if not p.is_file():
                        continue
                    parser = parser_cls()
                    events.extend(
                        parser.parse_file(p, scenario_id=scenario, host_id=host_id)
                    )
                events.sort(key=lambda e: e.timestamp_ns)
                yield host_id, events

    def _bucket_events_by_window(
        self, window_hours: float
    ) -> dict[HostWindowKey, list[tuple[int, Event]]]:
        bucketed: dict[HostWindowKey, list[tuple[int, Event]]] = defaultdict(list)
        for host_id, events in self._events_by_host.items():
            for ev_idx, ev in enumerate(events):
                w = window_index(ev.timestamp_ns, window_hours)
                bucketed[HostWindowKey(host_id, w)].append((ev_idx, ev))
        return bucketed

    def _partition_by_scenario(
        self, bucketed: dict[HostWindowKey, list[tuple[int, Event]]]
    ) -> tuple[set[HostWindowKey], set[HostWindowKey]]:
        if self.mode is DataMode.pretrain:
            # All buckets feed train; small held-out slice for val constructed
            # later; no test split needed (pretrain is unsupervised).
            return set(bucketed.keys()), set()

        leave_out = self.leave_out_scenario
        assert leave_out is not None  # checked in setup()
        train_keys: set[HostWindowKey] = set()
        test_keys: set[HostWindowKey] = set()
        for key in bucketed:
            scen = self._scenario_of_host(key.host_id)
            if scen == leave_out:
                test_keys.add(key)
            else:
                train_keys.add(key)
        return train_keys, test_keys

    @staticmethod
    def _scenario_of_host(host_id: str) -> str:
        # Multi-host: 'M1_h1' -> 'M1'. Single-host: 'S1' -> 'S1'.
        return host_id.split("_")[0] if "_" in host_id else host_id

    def _sample(
        self,
        bucketed: dict[HostWindowKey, list[tuple[int, Event]]],
        keys: set[HostWindowKey],
        rng: np.random.Generator,
        max_per_window: int,
    ) -> list[TargetSample]:
        out: list[TargetSample] = []
        for key in sorted(keys, key=lambda k: (k.host_id, k.window_idx)):
            kept = sample_target_events(
                bucketed[key],
                max_events_per_window=max_per_window,
                label_loader=self.label_loader,
                rng=rng,
            )
            for ev_idx, _ev, label in kept:
                out.append(TargetSample(host_window=key, event_idx_in_host=ev_idx, label=label))
        return out

    @staticmethod
    def _build_index(graph: Any) -> dict[NodeType, dict[str, int]]:
        idx: dict[NodeType, dict[str, int]] = {}
        for ntype in NodeType:
            if ntype.value not in graph.node_types:
                continue
            ids = graph[ntype.value].node_id
            idx[ntype] = {name: i for i, name in enumerate(ids)}
        return idx

    @staticmethod
    def _compute_fold_stats(
        train_samples: list[TargetSample],
        test_samples: list[TargetSample],
        train_keys: set[HostWindowKey],
        test_keys: set[HostWindowKey],
    ) -> FoldStats:
        def attack_count(samples: list[TargetSample]) -> int:
            return sum(1 for s in samples if s.label == 1)

        return FoldStats(
            leave_out="(set externally)",
            train_n_target_events=len(train_samples),
            test_n_target_events=len(test_samples),
            train_n_host_window_keys=len(train_keys),
            test_n_host_window_keys=len(test_keys),
            train_attack_count=attack_count(train_samples),
            test_attack_count=attack_count(test_samples),
            train_benign_count=len(train_samples) - attack_count(train_samples),
            test_benign_count=len(test_samples) - attack_count(test_samples),
        )

    @staticmethod
    def _make_loader(dataset: LogHeteroDataset | None, *, shuffle: bool) -> Any:
        """Lazy-import torch.utils.data.DataLoader so the DataModule can be
        imported in environments without torch (e.g. the lint / fast CI lane)."""
        if dataset is None:
            raise RuntimeError("DataModule.setup() must be called before *_dataloader()")
        from torch.utils.data import DataLoader

        # collate_fn returns the list-of-dicts batch as-is; the model side
        # tokenizes text and PyG-batches the subgraphs (Phase 2+).
        return DataLoader(
            dataset,  # type: ignore[arg-type]
            batch_size=1,
            shuffle=shuffle,
            collate_fn=lambda items: items,
            num_workers=0,
        )
