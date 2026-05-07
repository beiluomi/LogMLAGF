"""Unit tests for Phase 4 / Checkpoint 14.5 + Phase 5 / Checkpoint 15 ATT&CK TTP attack templates.

Tests verify:
  - All 5 TTP templates produce correct event types (no external API calls)
  - Events respect ALLOWED_EDGE_TRIPLES schema (or documented workaround)
  - Node IDs follow the shared-seed + atk_-prefix design (RFC-14.5-4)
  - SyntheticInjector produces correct event counts (RFC-14.5-9: 5x100=500 attack)
  - ProbeClassifier has correct architecture per RFC-14.5-8
  - Phase 5 / Checkpoint 15: dual-node svchost workaround (T1055) + module-level
    constants pattern + 6-7 tests per new TTP
  - Phase 5 / Checkpoint 15 Cycle B: T1068 priv-grant workaround (seed_user as
    subject of USER_PRIV_GRANT, inventory entry #2) + vuln_driver.sys file node

These tests are pure Python + loghetero imports; no ATLAS data required.
"""

from __future__ import annotations

import random

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _make_template_call(template_cls: type, seed: int = 42, iid: int = 0) -> list:
    """Call template.generate with canonical shared-seed args."""
    template = template_cls()
    t_start = int(1.5e18)  # realistic ns value
    t_end = t_start + int(3.6e12)  # 1h window
    return template.generate(
        seed_subject="victim_user",
        seed_subject_type="user",
        t_start_ns=t_start,
        t_end_ns=t_end,
        rng=_make_rng(seed),
        instance_id=iid,
    )


# ---------------------------------------------------------------------------
# Template import smoke tests
# ---------------------------------------------------------------------------


def test_all_templates_import() -> None:
    """ALL_TEMPLATES must contain exactly 7 templates (5 Phase 4 + 2 Phase 5: T1055 + T1068)."""
    from loghetero.data.attack_templates import ALL_TEMPLATES

    assert len(ALL_TEMPLATES) == 7, f"Expected 7 templates, got {len(ALL_TEMPLATES)}"


def test_all_template_ttp_ids() -> None:
    """Each template must have the correct TTP id."""
    from loghetero.data.attack_templates import ALL_TEMPLATES

    expected_ids = {"T1059.001", "T1003.001", "T1071.001", "T1547.001", "T1041", "T1055", "T1068"}
    actual_ids = {t.ttp_id for t in ALL_TEMPLATES}
    assert actual_ids == expected_ids


# ---------------------------------------------------------------------------
# T1059.001 PowerShell
# ---------------------------------------------------------------------------


def test_t1059_001_generates_7_events() -> None:
    """T1059.001 must generate exactly 7 events."""
    from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell

    events = _make_template_call(T1059001PowerShell)
    assert len(events) == 7


def test_t1059_001_event_types() -> None:
    """T1059.001 events must use allowed schema operations."""
    from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1059001PowerShell)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1059.001"


def test_t1059_001_seed_anchor() -> None:
    """First event must have subject=seed_user (shared-seed design, RFC-14.5-4)."""
    from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1059001PowerShell)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1059_001_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must have atk_ prefix."""
    from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell

    events = _make_template_call(T1059001PowerShell)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1059_001_timestamps_in_window() -> None:
    """All event timestamps must be in [t_start, t_end]."""
    from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1059001PowerShell()
    events = template.generate(
        seed_subject="victim_user",
        seed_subject_type="user",
        t_start_ns=t_start,
        t_end_ns=t_end,
        rng=_make_rng(),
        instance_id=0,
    )
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end, f"Timestamp {ev.timestamp_ns} outside window"


def test_t1059_001_labels_are_1() -> None:
    """All attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell

    events = _make_template_call(T1059001PowerShell)
    for ev in events:
        assert ev.attributes.get("label") == 1


# ---------------------------------------------------------------------------
# T1003.001 LSASS Memory
# ---------------------------------------------------------------------------


def test_t1003_001_generates_7_events() -> None:
    from loghetero.data.attack_templates.t1003_001_lsass_memory import T1003001LsassMemory

    events = _make_template_call(T1003001LsassMemory)
    assert len(events) == 7


def test_t1003_001_schema_workaround() -> None:
    """lsass.exe must be modeled as a file node (RFC-14.5-1 schema workaround)."""
    from loghetero.data.attack_templates.t1003_001_lsass_memory import T1003001LsassMemory
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    events = _make_template_call(T1003001LsassMemory)
    # Event index 2: HANDLE_REQUEST to lsass.exe (modeled as file node).
    ev = events[2]
    assert ev.operation == EdgeType.HANDLE_REQUEST.value
    assert ev.obj_type == NodeType.file
    assert "lsass" in ev.obj.lower()
    # Verify ALLOWED_EDGE_TRIPLES contains (process, HANDLE_REQUEST, file).
    triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
    assert triple in ALLOWED_EDGE_TRIPLES


def test_t1003_001_all_triples_allowed() -> None:
    from loghetero.data.attack_templates.t1003_001_lsass_memory import T1003001LsassMemory
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1003001LsassMemory)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1003.001"


# ---------------------------------------------------------------------------
# T1071.001 Web Protocols
# ---------------------------------------------------------------------------


def test_t1071_001_generates_7_events() -> None:
    from loghetero.data.attack_templates.t1071_001_web_protocols import T1071001WebProtocols

    events = _make_template_call(T1071001WebProtocols)
    assert len(events) == 7


def test_t1071_001_dns_modeled_as_net_connect() -> None:
    """DNS resolution must use NET_CONNECT to a network node (RFC-14.5-2)."""
    from loghetero.data.attack_templates.t1071_001_web_protocols import T1071001WebProtocols
    from loghetero.data.parsers.base import EdgeType, NodeType

    events = _make_template_call(T1071001WebProtocols)
    # Event index 1: DNS NET_CONNECT.
    ev = events[1]
    assert ev.operation == EdgeType.NET_CONNECT.value
    assert ev.obj_type == NodeType.network
    assert "53" in ev.obj  # DNS port


def test_t1071_001_all_triples_allowed() -> None:
    from loghetero.data.attack_templates.t1071_001_web_protocols import T1071001WebProtocols
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1071001WebProtocols)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1071.001"


# ---------------------------------------------------------------------------
# T1547.001 Registry Run Keys
# ---------------------------------------------------------------------------


def test_t1547_001_generates_7_events() -> None:
    from loghetero.data.attack_templates.t1547_001_registry_run_keys import T1547001RegistryRunKeys

    events = _make_template_call(T1547001RegistryRunKeys)
    assert len(events) == 7


def test_t1547_001_registry_as_file_node() -> None:
    """Registry key write must be modeled as FILE_WRITE to a file node (RFC-14.5-1)."""
    from loghetero.data.attack_templates.t1547_001_registry_run_keys import T1547001RegistryRunKeys
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    events = _make_template_call(T1547001RegistryRunKeys)
    # Event index 3: reg.exe writes to registry key modeled as file.
    ev = events[3]
    assert ev.operation == EdgeType.FILE_WRITE.value
    assert ev.obj_type == NodeType.file
    assert "Registry" in ev.obj or "registry" in ev.obj.lower()
    triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
    assert triple in ALLOWED_EDGE_TRIPLES


def test_t1547_001_all_triples_allowed() -> None:
    from loghetero.data.attack_templates.t1547_001_registry_run_keys import T1547001RegistryRunKeys
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1547001RegistryRunKeys)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1547.001"


# ---------------------------------------------------------------------------
# T1041 Exfiltration
# ---------------------------------------------------------------------------


def test_t1041_generates_7_events() -> None:
    from loghetero.data.attack_templates.t1041_exfiltration import T1041Exfiltration

    events = _make_template_call(T1041Exfiltration)
    assert len(events) == 7


def test_t1041_all_triples_allowed() -> None:
    from loghetero.data.attack_templates.t1041_exfiltration import T1041Exfiltration
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1041Exfiltration)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1041"


def test_t1041_cleanup_file_deletes() -> None:
    """T1041 must have FILE_DELETE events for cleanup (events 5 and 6)."""
    from loghetero.data.attack_templates.t1041_exfiltration import T1041Exfiltration
    from loghetero.data.parsers.base import EdgeType

    events = _make_template_call(T1041Exfiltration)
    assert events[5].operation == EdgeType.FILE_DELETE.value
    assert events[6].operation == EdgeType.FILE_DELETE.value


# ---------------------------------------------------------------------------
# Cross-template: instance_id uniqueness
# ---------------------------------------------------------------------------


def test_different_instance_ids_produce_distinct_node_ids() -> None:
    """Different instance_ids must produce distinct atk_-prefixed node IDs."""
    from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell

    template = T1059001PowerShell()
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)

    events_0 = template.generate("victim_user", "user", t_start, t_end, _make_rng(), 0)
    events_1 = template.generate("victim_user", "user", t_start, t_end, _make_rng(), 1)

    nodes_0 = {ev.subject for ev in events_0 if ev.subject != "victim_user"} | {
        ev.obj for ev in events_0
    }
    nodes_1 = {ev.subject for ev in events_1 if ev.subject != "victim_user"} | {
        ev.obj for ev in events_1
    }
    # No overlap (except victim_user which is shared by design).
    overlap = nodes_0 & nodes_1
    assert len(overlap) == 0, f"Unexpected shared atk_ nodes across instance_ids: {overlap}"


# ---------------------------------------------------------------------------
# SyntheticInjector: event count checks (RFC-14.5-9)
# ---------------------------------------------------------------------------


def test_injector_total_event_count() -> None:
    """SyntheticInjector must produce exactly len(ALL_TEMPLATES)*EVENTS_PER_TTP attack + 500 benign."""
    from loghetero.data.attack_templates import ALL_TEMPLATES
    from loghetero.data.parsers.base import EdgeType, Event, NodeType
    from loghetero.data.synthetic_injector import (
        EVENTS_PER_TTP,
        NUM_BENIGN_MATCHED,
        SyntheticInjector,
    )

    # Create minimal synthetic benign events (no real data needed).
    t_start = int(1.5e18)
    benign_events = []
    rng = random.Random(999)
    procs = [f"proc_{i}" for i in range(10)]
    files = [f"file_{i}.txt" for i in range(10)]
    for _ in range(NUM_BENIGN_MATCHED * 2):
        ev = Event(
            timestamp_ns=t_start + rng.randint(0, int(3.6e12)),
            subject=rng.choice(procs),
            subject_type=NodeType.process,
            obj=rng.choice(files),
            obj_type=NodeType.file,
            operation=EdgeType.FILE_READ.value,
            log_type="synthetic_benign",
            scenario_id="syn",
            host_id="h1",
            attributes={},
        )
        benign_events.append(ev)
    # Add a user node for seed anchoring.
    for _ in range(10):
        ev = Event(
            timestamp_ns=t_start + rng.randint(0, int(3.6e10)),
            subject="victim_user",
            subject_type=NodeType.user,
            obj=rng.choice(procs),
            obj_type=NodeType.process,
            operation=EdgeType.USER_LOGON.value,
            log_type="synthetic_benign",
            scenario_id="syn",
            host_id="h1",
            attributes={},
        )
        benign_events.append(ev)

    injector = SyntheticInjector(
        benign_events=benign_events,
        templates=ALL_TEMPLATES,
        seed=42,
        events_per_ttp=EVENTS_PER_TTP,
        num_benign=NUM_BENIGN_MATCHED,
    )
    dataset = injector.build()

    attack_count = sum(1 for _, lbl in dataset.events_with_labels if lbl == 1)
    benign_count = sum(1 for _, lbl in dataset.events_with_labels if lbl == 0)

    expected_attack = (
        len(ALL_TEMPLATES) * EVENTS_PER_TTP
    )  # 7 * 100 = 700 (Phase 5 adds T1055 + T1068)
    assert attack_count == expected_attack, f"Attack count {attack_count} != {expected_attack}"
    assert (
        benign_count == NUM_BENIGN_MATCHED
    ), f"Benign count {benign_count} != {NUM_BENIGN_MATCHED}"


def test_injector_train_test_split_ratio() -> None:
    """80/20 split: total events = 7*100 + 500 = 1200; train ~960, test ~240."""
    from loghetero.data.attack_templates import ALL_TEMPLATES
    from loghetero.data.parsers.base import EdgeType, Event, NodeType
    from loghetero.data.synthetic_injector import (
        EVENTS_PER_TTP,
        NUM_BENIGN_MATCHED,
        SyntheticInjector,
    )

    t_start = int(1.5e18)
    rng = random.Random(7)
    benign_events = []
    for _ in range(1200):
        ev = Event(
            timestamp_ns=t_start + rng.randint(0, int(3.6e12)),
            subject="victim_user",
            subject_type=NodeType.user,
            obj="proc_x",
            obj_type=NodeType.process,
            operation=EdgeType.USER_LOGON.value,
            log_type="syn",
            scenario_id="syn",
            host_id="h1",
            attributes={},
        )
        benign_events.append(ev)

    injector = SyntheticInjector(
        benign_events=benign_events,
        templates=ALL_TEMPLATES,
        seed=42,
    )
    dataset = injector.build()

    expected_total = len(ALL_TEMPLATES) * EVENTS_PER_TTP + NUM_BENIGN_MATCHED
    total = len(dataset.train_events) + len(dataset.test_events)
    # Allow small rounding tolerance around the expected total.
    assert (
        abs(total - expected_total) <= 50
    ), f"Total events {total} out of expected ~{expected_total} range"
    # Train should be ~80%.
    train_ratio = len(dataset.train_events) / total
    assert 0.70 <= train_ratio <= 0.90, f"Train ratio {train_ratio:.2f} outside [0.70, 0.90]"


def test_injector_per_ttp_entries() -> None:
    """SyntheticInjector must produce entries for all 7 TTP ids (Phase 4 x5 + Phase 5 T1055 + T1068)."""
    from loghetero.data.attack_templates import ALL_TEMPLATES
    from loghetero.data.parsers.base import EdgeType, Event, NodeType
    from loghetero.data.synthetic_injector import SyntheticInjector

    t_start = int(1.5e18)
    rng = random.Random(0)
    benign_events = [
        Event(
            timestamp_ns=t_start + rng.randint(0, int(3.6e12)),
            subject="victim_user",
            subject_type=NodeType.user,
            obj="proc_a",
            obj_type=NodeType.process,
            operation=EdgeType.USER_LOGON.value,
            log_type="syn",
            scenario_id="syn",
            host_id="h1",
            attributes={},
        )
        for _ in range(1000)
    ]

    injector = SyntheticInjector(benign_events=benign_events, templates=ALL_TEMPLATES, seed=42)
    dataset = injector.build()

    expected_ids = {"T1059.001", "T1003.001", "T1071.001", "T1547.001", "T1041", "T1055", "T1068"}
    assert set(dataset.per_ttp_events.keys()) == expected_ids


# ---------------------------------------------------------------------------
# ProbeClassifier architecture (RFC-14.5-8)
# ---------------------------------------------------------------------------


def test_probe_classifier_htgn_only_shape() -> None:
    """HTGN-only probe: input 256 -> output (B, 1)."""
    import torch

    from loghetero.models.heads.probe_classifier import ProbeClassifier, ProbeConfig

    model = ProbeClassifier(ProbeConfig.HTGN_ONLY)
    assert model.input_dim == 256
    x = torch.randn(4, 256)
    out = model(x)
    assert out.shape == (4, 1), f"Expected (4,1), got {out.shape}"


def test_probe_classifier_bert_only_shape() -> None:
    """BERT-only probe: input 768 -> output (B, 1)."""
    import torch

    from loghetero.models.heads.probe_classifier import ProbeClassifier, ProbeConfig

    model = ProbeClassifier(ProbeConfig.BERT_ONLY)
    assert model.input_dim == 768
    x = torch.randn(8, 768)
    out = model(x)
    assert out.shape == (8, 1)


def test_probe_classifier_fusion_shape() -> None:
    """Fusion probe: input 768 -> output (B, 1)."""
    import torch

    from loghetero.models.heads.probe_classifier import ProbeClassifier, ProbeConfig

    model = ProbeClassifier(ProbeConfig.FUSION)
    assert model.input_dim == 768
    x = torch.randn(3, 768)
    out = model(x)
    assert out.shape == (3, 1)


def test_probe_classifier_mlp_architecture() -> None:
    """MLP must follow RFC-14.5-8 template: Linear->ReLU->Dropout->Linear."""
    from loghetero.models.heads.probe_classifier import ProbeClassifier, ProbeConfig

    model = ProbeClassifier(ProbeConfig.HTGN_ONLY)
    layers = list(model.mlp.children())
    assert len(layers) == 4, f"Expected 4 layers, got {len(layers)}"
    from torch import nn

    assert isinstance(layers[0], nn.Linear), f"Layer 0 should be Linear, got {type(layers[0])}"
    assert isinstance(layers[1], nn.ReLU), f"Layer 1 should be ReLU, got {type(layers[1])}"
    assert isinstance(layers[2], nn.Dropout), f"Layer 2 should be Dropout, got {type(layers[2])}"
    assert isinstance(layers[3], nn.Linear), f"Layer 3 should be Linear, got {type(layers[3])}"

    # Linear(256, 128) -> Linear(128, 1)
    assert layers[0].in_features == 256
    assert layers[0].out_features == 128
    assert layers[3].in_features == 128
    assert layers[3].out_features == 1


def test_probe_classifier_predict_proba_range() -> None:
    """predict_proba must return values in [0, 1]."""
    import torch

    from loghetero.models.heads.probe_classifier import ProbeClassifier, ProbeConfig

    model = ProbeClassifier(ProbeConfig.BERT_ONLY)
    x = torch.randn(10, 768)
    proba = model.predict_proba(x)
    assert proba.shape == (10,)
    assert (proba >= 0).all() and (proba <= 1).all()


def test_probe_classifier_single_vector_input() -> None:
    """ProbeClassifier must handle a 1D input (single event) without error."""
    import torch

    from loghetero.models.heads.probe_classifier import ProbeClassifier, ProbeConfig

    model = ProbeClassifier(ProbeConfig.HTGN_ONLY)
    x = torch.randn(256)  # 1D input
    out = model(x)
    assert out.shape == (1, 1)


# ---------------------------------------------------------------------------
# No external API call verification
# ---------------------------------------------------------------------------


def test_attack_templates_no_network_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Attack template generation must not make any network requests (RFC-14.5-10)."""
    import socket

    def _blocked_connect(self: socket.socket, *args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "Network access blocked: attack templates must be offline (RFC-14.5-10)."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)

    from loghetero.data.attack_templates import ALL_TEMPLATES

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    rng = _make_rng()

    # All 7 templates must work without network access.
    for template in ALL_TEMPLATES:
        events = template.generate(
            seed_subject="victim_user",
            seed_subject_type="user",
            t_start_ns=t_start,
            t_end_ns=t_end,
            rng=rng,
            instance_id=0,
        )
        assert len(events) > 0, f"{template.ttp_id} produced no events"


# ---------------------------------------------------------------------------
# T1055 Process Injection (Phase 5 / Checkpoint 15 Cycle A)
# ---------------------------------------------------------------------------


def test_t1055_generates_8_events() -> None:
    """T1055 must generate exactly 8 events."""
    from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection

    events = _make_template_call(T1055ProcessInjection)
    assert len(events) == 8, f"Expected 8 events, got {len(events)}"


def test_t1055_event_types() -> None:
    """T1055 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES)."""
    from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1055ProcessInjection)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1055"


def test_t1055_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1055ProcessInjection)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1055_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection

    events = _make_template_call(T1055ProcessInjection)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1055_timestamps_in_window() -> None:
    """All T1055 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1055ProcessInjection()
    events = template.generate(
        seed_subject="victim_user",
        seed_subject_type="user",
        t_start_ns=t_start,
        t_end_ns=t_end,
        rng=_make_rng(),
        instance_id=0,
    )
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end, f"Timestamp {ev.timestamp_ns} outside window"


def test_t1055_dual_node_svchost_schema_workaround() -> None:
    """Validate the dual-node svchost workaround (inventory entry #1).

    svchost_handle (events 3 and 6) must be NodeType.file.
    svchost_injected (events 7 and 8) must be NodeType.process.
    The two IDs must be distinct (not aliased to the same node).
    Both IDs must share the atk_<iid>_ prefix.
    """
    from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 7
    template = T1055ProcessInjection()
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = template.generate(
        seed_subject="victim_user",
        seed_subject_type="user",
        t_start_ns=t_start,
        t_end_ns=t_end,
        rng=_make_rng(),
        instance_id=iid,
    )

    # Event 3 (index 2): HANDLE_REQUEST -> svchost_handle (file node)
    ev_handle_req = events[2]
    assert ev_handle_req.operation == EdgeType.HANDLE_REQUEST.value
    assert (
        ev_handle_req.obj_type == NodeType.file
    ), f"svchost_handle must be file node, got {ev_handle_req.obj_type}"
    assert "svchost_handle" in ev_handle_req.obj

    # Event 6 (index 5): HANDLE_DUPLICATE -> svchost_handle (file node)
    ev_handle_dup = events[5]
    assert ev_handle_dup.operation == EdgeType.HANDLE_DUPLICATE.value
    assert (
        ev_handle_dup.obj_type == NodeType.file
    ), f"svchost_handle must be file node in HANDLE_DUPLICATE, got {ev_handle_dup.obj_type}"
    assert (
        ev_handle_dup.obj == ev_handle_req.obj
    ), "svchost_handle ID inconsistent across events 3 and 6"

    # Event 7 (index 6): svchost_injected (process node) -> NET_CONNECT
    ev_net_connect = events[6]
    assert ev_net_connect.operation == EdgeType.NET_CONNECT.value
    assert (
        ev_net_connect.subject_type == NodeType.process
    ), f"svchost_injected must be process node, got {ev_net_connect.subject_type}"
    assert "svchost_injected" in ev_net_connect.subject

    # Event 8 (index 7): svchost_injected (process node) -> NET_SEND_NETWORK
    ev_net_send = events[7]
    assert ev_net_send.operation == EdgeType.NET_SEND_NETWORK.value
    assert (
        ev_net_send.subject_type == NodeType.process
    ), f"svchost_injected must be process node in NET_SEND_NETWORK, got {ev_net_send.subject_type}"
    assert (
        ev_net_send.subject == ev_net_connect.subject
    ), "svchost_injected ID inconsistent across events 7 and 8"

    # The two virtual svchost node IDs must be DISTINCT (not aliased).
    svchost_handle_id = ev_handle_req.obj
    svchost_injected_id = ev_net_connect.subject
    assert (
        svchost_handle_id != svchost_injected_id
    ), "svchost_handle and svchost_injected must be distinct node IDs"

    # Both must carry the atk_<iid>_ prefix.
    prefix = f"atk_{iid}_"
    assert svchost_handle_id.startswith(prefix), f"{svchost_handle_id!r} lacks prefix {prefix!r}"
    assert svchost_injected_id.startswith(
        prefix
    ), f"{svchost_injected_id!r} lacks prefix {prefix!r}"


def test_t1055_labels_are_1() -> None:
    """All T1055 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection

    events = _make_template_call(T1055ProcessInjection)
    for ev in events:
        assert ev.attributes.get("label") == 1


# ---------------------------------------------------------------------------
# T1068 Exploitation for Privilege Escalation (Phase 5 / Checkpoint 15 Cycle B)
# ---------------------------------------------------------------------------


def test_t1068_generates_8_events() -> None:
    """T1068 must generate exactly 8 events."""
    from loghetero.data.attack_templates.t1068_exploitation_for_privesc import (
        T1068ExploitationForPrivEsc,
    )

    events = _make_template_call(T1068ExploitationForPrivEsc)
    assert len(events) == 8, f"Expected 8 events, got {len(events)}"


def test_t1068_event_types() -> None:
    """T1068 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    Specifically verifies that event 5 (USER_PRIV_GRANT) uses the workaround #2
    triple (user, USER_PRIV_GRANT, process) which IS in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1068_exploitation_for_privesc import (
        T1068ExploitationForPrivEsc,
    )
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1068ExploitationForPrivEsc)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1068"


def test_t1068_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1068_exploitation_for_privesc import (
        T1068ExploitationForPrivEsc,
    )
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1068ExploitationForPrivEsc)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1068_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1068_exploitation_for_privesc import (
        T1068ExploitationForPrivEsc,
    )

    events = _make_template_call(T1068ExploitationForPrivEsc)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1068_timestamps_in_window() -> None:
    """All T1068 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1068_exploitation_for_privesc import (
        T1068ExploitationForPrivEsc,
    )

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1068ExploitationForPrivEsc()
    events = template.generate(
        seed_subject="victim_user",
        seed_subject_type="user",
        t_start_ns=t_start,
        t_end_ns=t_end,
        rng=_make_rng(),
        instance_id=0,
    )
    for ev in events:
        assert t_start <= ev.timestamp_ns <= t_end, f"Timestamp {ev.timestamp_ns} outside window"


def test_t1068_priv_grant_workaround() -> None:
    """Validate schema workaround #2 for USER_PRIV_GRANT (inventory entry #2).

    Event 5 (USER_PRIV_GRANT) must use seed_user as subject (NOT exploit_elevated),
    because ALLOWED_EDGE_TRIPLES only has (user, USER_PRIV_GRANT, process), not
    (process, USER_PRIV_GRANT, process). Verifies:
      - subject == seed_subject (workaround applied correctly)
      - subject_type == NodeType.user
      - obj == atk_{iid}_exploit_elevated.exe (the elevated process object)
      - obj_type == NodeType.process
      - the triple (user, USER_PRIV_GRANT, process) IS in ALLOWED_EDGE_TRIPLES
    """
    from loghetero.data.attack_templates.t1068_exploitation_for_privesc import (
        T1068ExploitationForPrivEsc,
    )
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    iid = 5
    template = T1068ExploitationForPrivEsc()
    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    events = template.generate(
        seed_subject="victim_user",
        seed_subject_type="user",
        t_start_ns=t_start,
        t_end_ns=t_end,
        rng=_make_rng(),
        instance_id=iid,
    )

    # Event 5 (index 4): USER_PRIV_GRANT
    ev_priv = events[4]
    assert (
        ev_priv.operation == EdgeType.USER_PRIV_GRANT.value
    ), f"Expected USER_PRIV_GRANT at event 5, got {ev_priv.operation}"

    # Workaround #2: subject must be seed_user (not exploit_elevated)
    assert ev_priv.subject == "victim_user", (
        f"Event 5 subject must be seed_user 'victim_user', got {ev_priv.subject!r}. "
        "Workaround #2 requires seed_user as subject because ALLOWED_EDGE_TRIPLES "
        "only has (user, USER_PRIV_GRANT, process)."
    )
    assert (
        ev_priv.subject_type == NodeType.user
    ), f"Event 5 subject_type must be NodeType.user, got {ev_priv.subject_type}"

    # Object must be the elevated process
    expected_elevated = f"atk_{iid}_exploit_elevated.exe"
    assert (
        ev_priv.obj == expected_elevated
    ), f"Event 5 obj must be {expected_elevated!r}, got {ev_priv.obj!r}"
    assert (
        ev_priv.obj_type == NodeType.process
    ), f"Event 5 obj_type must be NodeType.process, got {ev_priv.obj_type}"

    # Verify the workaround triple IS in ALLOWED_EDGE_TRIPLES (legal, not a violation)
    workaround_triple = (NodeType.user, EdgeType.USER_PRIV_GRANT, NodeType.process)
    assert workaround_triple in ALLOWED_EDGE_TRIPLES, (
        f"Workaround triple {workaround_triple} not in ALLOWED_EDGE_TRIPLES; "
        "inventory entry #2 may have a bug."
    )

    # Confirm the natural (process, USER_PRIV_GRANT, process) is NOT in schema
    # (this is WHY the workaround exists)
    forbidden_triple = (NodeType.process, EdgeType.USER_PRIV_GRANT, NodeType.process)
    assert forbidden_triple not in ALLOWED_EDGE_TRIPLES, (
        "Expected (process, USER_PRIV_GRANT, process) to NOT be in ALLOWED_EDGE_TRIPLES "
        "but it is -- workaround #2 may no longer be necessary."
    )


def test_t1068_labels_are_1() -> None:
    """All T1068 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1068_exploitation_for_privesc import (
        T1068ExploitationForPrivEsc,
    )

    events = _make_template_call(T1068ExploitationForPrivEsc)
    for ev in events:
        assert ev.attributes.get("label") == 1
