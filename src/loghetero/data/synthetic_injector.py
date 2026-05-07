"""Synthetic attack event injector (Phase 4 / Checkpoint 14.5 Path B).

Injects synthetic ATT&CK TTP attack events into a benign event stream
using a shared-seed anchoring design (RFC-14.5-4) and produces a mixed
dataset suitable for the three-config anomaly detection probe experiment.

Path B Change 2 (shared anchor node extension):
    Each TTP chain now anchors on TWO existing benign nodes (seed=42,
    deterministic): (1) the seed user node (event 1 subject, unchanged from
    prior run) and (2) one benign process node that spawns the first
    atk_-prefixed process in the chain via a bridging PROCESS_CREATE event.
    This removes the "trivial graph isolation" that caused HTGN-only F1=0.23
    in the first 14.5 run by creating denser K-hop connectivity from benign
    nodes to attack chain nodes.

    Anchor process selection: most-frequent process node in the benign event
    stream, deterministic given seed=42.  Falls back to user node if no
    process nodes are available.

Shared-seed APT-realistic injection design (RFC-14.5-4):

    shared-seed 注入设计反映真实 APT 场景即合法账号被 compromise 后行动.
    关于 "K-hop 子图从 benign 节点经过 seed 触及攻击节点会让 HTGN 学到
    seed-has-many-atk-neighbors-equals-attack 这种 node-level 而非
    event-level 信号" 的潜在质疑预先回应即这正是真实攻击检测应该利用的 context
    信号而非作弊, 是 model 学到正确的事而非 ground-truth leakage.

Configuration (locked per RFC-14.5-9):
    - 5 TTP templates x 100 attack events = 500 total attack events.
    - 500 matched benign events.
    - Total = 1000 events, 80/20 split: 800 train + 200 test.
    - Within each TTP, random shuffle with seed=42, 80/20 split.
    - Timestamps: attack events are randomly interleaved within the benign
      window [t_start, t_start + 3.6e12] ns (RFC-14.5-4, Option C).

Usage::

    from loghetero.data.synthetic_injector import SyntheticInjector
    from loghetero.data.attack_templates import ALL_TEMPLATES

    injector = SyntheticInjector(
        benign_events=benign_events,
        templates=ALL_TEMPLATES,
        seed=42,
    )
    result = injector.build()
    # result.events_with_labels: list of (Event, label: int) pairs
    # result.train_events / result.test_events: 80/20 split
    # result.anchor_user: benign user node used as seed
    # result.anchor_proc: benign process node used as second anchor (Path B)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

# RFC-14.5-9: 5 TTPs x 100 events = 500 attack events total.
EVENTS_PER_TTP: int = 100
NUM_BENIGN_MATCHED: int = 500  # matched benign events
TRAIN_RATIO: float = 0.8
WITHIN_TTP_SEED: int = 42  # RFC-14.5-7: within-TTP shuffle fixed seed


@dataclass
class InjectedDataset:
    """Output of :class:`SyntheticInjector.build`.

    Attributes:
        events_with_labels: all 1000 (Event, label) pairs, shuffled.
        train_events: 80% split (800 events) with labels.
        test_events: 20% split (200 events) with labels.
        per_ttp_events: dict mapping TTP id to list of (Event, label=1) pairs.
        benign_events_sampled: the 500 benign events selected (label=0).
        anchor_user: benign user node id used as seed for all TTP chains.
        anchor_proc: benign process node id used as second anchor (Path B
            Change 2); empty string if no process node was available in
            benign stream.
    """

    events_with_labels: list[tuple[Event, int]] = field(default_factory=list)
    train_events: list[tuple[Event, int]] = field(default_factory=list)
    test_events: list[tuple[Event, int]] = field(default_factory=list)
    per_ttp_events: dict[str, list[tuple[Event, int]]] = field(default_factory=dict)
    benign_events_sampled: list[Event] = field(default_factory=list)
    anchor_user: str = ""
    anchor_proc: str = ""


class SyntheticInjector:
    """Inject synthetic ATT&CK events into a benign event stream.

    Args:
        benign_events: sorted list of real benign :class:`Event` objects from
            the M3_h2 first 1.0h window (or similar window).
        templates: list of :class:`AttackTemplate` instances; must have length 5
            for the Checkpoint 14.5 spec (5 TTPs x 100 events = 500 attack total).
        seed: master RNG seed for reproducible injection.  Within-TTP shuffle
            uses the fixed ``WITHIN_TTP_SEED=42`` per RFC-14.5-7.
        events_per_ttp: number of synthetic attack events to generate per TTP
            (default 100, locked by RFC-14.5-9).
        num_benign: number of benign events to sample and include (default 500).
        shared_seed_user: user node ID to use as the shared seed across all TTP
            chains.  If None, the injector selects the most common ``user`` node
            from the benign event stream.

    shared-seed design (RFC-14.5-4):
        Attack chains are anchored at an existing benign user node (the seed).
        The first event of each TTP chain has subject=<seed_user> which is also
        present in the benign graph.  This models the APT scenario where a
        legitimate account is compromised and used as the initial foothold.
        Subsequent events involve atk_-prefixed node IDs that are new to the
        graph (not present in benign data).
    """

    def __init__(
        self,
        benign_events: list[Event],
        templates: list[AttackTemplate],
        *,
        seed: int = 42,
        events_per_ttp: int = EVENTS_PER_TTP,
        num_benign: int = NUM_BENIGN_MATCHED,
        shared_seed_user: str | None = None,
    ) -> None:
        self.benign_events = benign_events
        self.templates = templates
        self.seed = seed
        self.events_per_ttp = events_per_ttp
        self.num_benign = num_benign
        self.shared_seed_user = shared_seed_user

    def _pick_seed_user(self) -> str:
        """Select the most-frequent user node from the benign event stream."""
        if self.shared_seed_user is not None:
            return self.shared_seed_user
        user_counts: dict[str, int] = {}
        for ev in self.benign_events:
            if ev.subject_type == NodeType.user:
                user_counts[ev.subject] = user_counts.get(ev.subject, 0) + 1
            if ev.obj_type == NodeType.user:
                user_counts[ev.obj] = user_counts.get(ev.obj, 0) + 1
        if not user_counts:
            # Fallback: use a canonical name if no user nodes found.
            return "victim_user"
        return max(user_counts, key=lambda k: user_counts[k])

    def _pick_anchor_process(self) -> str:
        """Select the most-frequent process node from benign stream as a second anchor.

        Path B Change 2: Deterministic selection with seed=42 (matching the
        rest of the protocol).  Returns the top-frequency process node name.
        Falls back to empty string if no process nodes found in benign stream.

        Empty string signals the caller to skip the second-anchor bridging event.
        """
        proc_counts: dict[str, int] = {}
        for ev in self.benign_events:
            if ev.subject_type == NodeType.process:
                proc_counts[ev.subject] = proc_counts.get(ev.subject, 0) + 1
            if ev.obj_type == NodeType.process:
                proc_counts[ev.obj] = proc_counts.get(ev.obj, 0) + 1
        if not proc_counts:
            return ""
        # Deterministic: pick by count descending, then name alphabetically for
        # tie-breaking (no randomness beyond what the benign stream provides).
        return max(proc_counts, key=lambda k: (proc_counts[k], k))

    def _get_window_bounds(self) -> tuple[int, int]:
        """Return [t_start, t_end] of the benign event window."""
        if not self.benign_events:
            raise ValueError("benign_events is empty; cannot determine window bounds.")
        t_start = min(ev.timestamp_ns for ev in self.benign_events)
        t_end = t_start + int(3.6e12)  # 1.0h in ns (RFC-14.5-4 Option C window)
        return t_start, t_end

    def _generate_ttp_events(
        self,
        template: AttackTemplate,
        seed_user: str,
        t_start: int,
        t_end: int,
        master_rng: random.Random,
        global_instance_offset: int,
        anchor_proc: str = "",
    ) -> list[Event]:
        """Generate events_per_ttp events for one TTP by calling generate() repeatedly.

        Each TTP chain typically produces 7 events (see template modules).
        We call generate() enough times to accumulate events_per_ttp events,
        using unique instance_id per chain to avoid node ID collisions.

        Path B Change 2: If anchor_proc is non-empty, prepend one bridging event
        per chain instance (anchor_proc -> PROCESS_CREATE -> first_atk_proc_obj)
        to create an additional K-hop connection from the benign process into
        the attack chain.  The bridging event is labeled 1 (attack) because it
        is part of the injected TTP chain and is not a legitimate benign event.

        The first_atk_proc_obj is inferred from the first generated event's
        object (which is always the first atk_-prefixed process in each chain).
        If the first event's object is not a process, no bridging event is added
        to avoid type mismatches.
        """
        events: list[Event] = []
        chain_idx = 0
        while len(events) < self.events_per_ttp:
            iid = global_instance_offset + chain_idx
            chain_events = template.generate(
                seed_subject=seed_user,
                seed_subject_type="user",
                t_start_ns=t_start,
                t_end_ns=t_end,
                rng=master_rng,
                instance_id=iid,
            )
            # Path B Change 2: insert bridging event from benign anchor_proc to
            # the first atk_-prefixed process object in this chain.
            if anchor_proc and chain_events:
                first_ev = chain_events[0]
                # All templates have event 1 obj as a process node (cmd.exe,
                # mimikatz.exe, implant.exe, dropper.exe, exfil_tool.exe).
                if first_ev.obj_type == NodeType.process:
                    # Timestamp: 1 ns before first event (must be < first_ev.timestamp_ns).
                    bridge_ts = max(t_start, first_ev.timestamp_ns - 1)
                    bridge_ev = Event(
                        timestamp_ns=bridge_ts,
                        subject=anchor_proc,
                        subject_type=NodeType.process,
                        obj=first_ev.obj,  # first atk_ process node
                        obj_type=NodeType.process,
                        operation=EdgeType.PROCESS_CREATE.value,
                        log_type="synthetic_atlas",
                        scenario_id="synthetic_apt",
                        host_id="h2",
                        attributes={
                            "ttp": template.ttp_id,
                            "instance_id": iid,
                            "label": 1,
                            "anchor_bridge": True,
                        },
                    )
                    chain_events = [bridge_ev, *chain_events]
            events.extend(chain_events)
            chain_idx += 1
        # Trim to exact target (within-TTP shuffle will handle later).
        return events[: self.events_per_ttp]

    def build(self) -> InjectedDataset:
        """Build the mixed benign + attack dataset.

        Returns:
            :class:`InjectedDataset` with train/test splits per RFC-14.5-7.
        """
        master_rng = random.Random(self.seed)
        within_ttp_rng = random.Random(WITHIN_TTP_SEED)

        seed_user = self._pick_seed_user()
        anchor_proc = self._pick_anchor_process()
        t_start, t_end = self._get_window_bounds()

        # --- 1. Generate attack events per TTP ----------------------------------
        per_ttp_events: dict[str, list[tuple[Event, int]]] = {}
        all_attack_labeled: list[tuple[Event, int]] = []

        # Per-TTP 80/20 split: within each TTP, shuffle with seed=42, then split.
        per_ttp_train: list[tuple[Event, int]] = []
        per_ttp_test: list[tuple[Event, int]] = []

        for ttp_offset, template in enumerate(self.templates):
            global_offset = ttp_offset * 1000  # ensure unique iids across TTPs
            ttp_events = self._generate_ttp_events(
                template=template,
                seed_user=seed_user,
                t_start=t_start,
                t_end=t_end,
                master_rng=master_rng,
                global_instance_offset=global_offset,
                anchor_proc=anchor_proc,
            )
            labeled = [(ev, 1) for ev in ttp_events]

            # Within-TTP shuffle (RFC-14.5-7): seed=42 per TTP.
            within_ttp_rng.shuffle(labeled)

            split_idx = int(len(labeled) * TRAIN_RATIO)
            ttp_train = labeled[:split_idx]
            ttp_test = labeled[split_idx:]

            per_ttp_events[template.ttp_id] = labeled
            all_attack_labeled.extend(labeled)
            per_ttp_train.extend(ttp_train)
            per_ttp_test.extend(ttp_test)

        # --- 2. Sample benign events ---------------------------------------------
        # Sample num_benign events uniformly from the benign stream.
        benign_pool = list(self.benign_events)
        master_rng.shuffle(benign_pool)
        sampled_benign = benign_pool[: self.num_benign]
        benign_labeled = [(ev, 0) for ev in sampled_benign]

        # Benign 80/20 split (global shuffle, same master seed).
        benign_rng = random.Random(WITHIN_TTP_SEED)
        benign_rng.shuffle(benign_labeled)
        benign_split = int(len(benign_labeled) * TRAIN_RATIO)
        benign_train = benign_labeled[:benign_split]
        benign_test = benign_labeled[benign_split:]

        # --- 3. Pool and shuffle (RFC-14.5-7: pool all 5 TTPs + benign) ----------
        # Aggregate pools (attack train + benign train) then shuffle.
        train_pool = per_ttp_train + benign_train
        test_pool = per_ttp_test + benign_test

        pool_rng = random.Random(self.seed + 1)
        pool_rng.shuffle(train_pool)
        pool_rng.shuffle(test_pool)

        all_events = list(all_attack_labeled) + list(benign_labeled)

        return InjectedDataset(
            events_with_labels=all_events,
            train_events=train_pool,
            test_events=test_pool,
            per_ttp_events=per_ttp_events,
            benign_events_sampled=sampled_benign,
            anchor_user=seed_user,
            anchor_proc=anchor_proc,
        )
