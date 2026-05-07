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
  - Phase 5 / Checkpoint 15 Cycle C: T1021.001 RDP single-host approximation
    workaround #3 (source-host-only view, USER_EXPLICIT_LOGON seed event)
  - Phase 5 / Checkpoint 15 Cycle D: T1566.001, T1078, T1057, T1083 (no schema
    workarounds; all triples in ALLOWED_EDGE_TRIPLES natively)

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
    """ALL_TEMPLATES must contain exactly 20 templates (5 Phase 4 + 15 Phase 5: Cycles A-F)."""
    from loghetero.data.attack_templates import ALL_TEMPLATES

    assert len(ALL_TEMPLATES) == 20, f"Expected 20 templates, got {len(ALL_TEMPLATES)}"


def test_all_template_ttp_ids() -> None:
    """Each template must have the correct TTP id."""
    from loghetero.data.attack_templates import ALL_TEMPLATES

    expected_ids = {
        "T1059.001",
        "T1003.001",
        "T1071.001",
        "T1547.001",
        "T1041",
        "T1055",
        "T1068",
        "T1021.001",
        "T1566.001",
        "T1078",
        "T1057",
        "T1083",
        "T1027",
        "T1070.004",
        "T1053.005",
        "T1543.003",
        "T1190",
        "T1560.001",
        "T1486",
        "T1490",
    }
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
    )  # 20 * 100 = 2000 (Phase 5 Cycles A-F adds T1055+T1068+T1021.001+T1566.001+T1078+T1057+T1083+T1027+T1070.004+T1053.005+T1543.003+T1190+T1560.001+T1486+T1490)
    assert attack_count == expected_attack, f"Attack count {attack_count} != {expected_attack}"
    assert (
        benign_count == NUM_BENIGN_MATCHED
    ), f"Benign count {benign_count} != {NUM_BENIGN_MATCHED}"


def test_injector_train_test_split_ratio() -> None:
    """80/20 split: total events = 8*100 + 500 = 1300; train ~1040, test ~260."""
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
    for _ in range(1300):
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
    """SyntheticInjector must produce entries for all 20 TTP ids (Phase 4 x5 + Phase 5 Cycles A-F)."""
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

    expected_ids = {
        "T1059.001",
        "T1003.001",
        "T1071.001",
        "T1547.001",
        "T1041",
        "T1055",
        "T1068",
        "T1021.001",
        "T1566.001",
        "T1078",
        "T1057",
        "T1083",
        "T1027",
        "T1070.004",
        "T1053.005",
        "T1543.003",
        "T1190",
        "T1560.001",
        "T1486",
        "T1490",
    }
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

    # All 8 templates must work without network access.
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


# ---------------------------------------------------------------------------
# T1021.001 RDP (Phase 5 / Checkpoint 15 Cycle C)
# ---------------------------------------------------------------------------


def test_t1021_001_generates_8_events() -> None:
    """T1021.001 must generate exactly 8 events."""
    from loghetero.data.attack_templates.t1021_001_rdp import T1021001RDP

    events = _make_template_call(T1021001RDP)
    assert len(events) == 8, f"Expected 8 events, got {len(events)}"


def test_t1021_001_event_types() -> None:
    """T1021.001 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    Specifically verifies that event 1 (USER_EXPLICIT_LOGON) uses the triple
    (user, USER_EXPLICIT_LOGON, process) which IS in ALLOWED_EDGE_TRIPLES (Q-1
    mini-checkpoint addition, line 139 of parsers/base.py).
    """
    from loghetero.data.attack_templates.t1021_001_rdp import T1021001RDP
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    events = _make_template_call(T1021001RDP)

    # Confirm the triple used by the seed event IS in ALLOWED_EDGE_TRIPLES before looping.
    seed_triple = (NodeType.user, EdgeType.USER_EXPLICIT_LOGON, NodeType.process)
    assert seed_triple in ALLOWED_EDGE_TRIPLES, (
        "(user, USER_EXPLICIT_LOGON, process) not in ALLOWED_EDGE_TRIPLES -- "
        "Q-1 mini-checkpoint addition may be missing."
    )

    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1021.001"


def test_t1021_001_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1021_001_rdp import T1021001RDP
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1021001RDP)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1021_001_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1021_001_rdp import T1021001RDP

    events = _make_template_call(T1021001RDP)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1021_001_timestamps_in_window() -> None:
    """All T1021.001 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1021_001_rdp import T1021001RDP

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1021001RDP()
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


def test_t1021_001_single_host_approximation() -> None:
    """Validate schema workaround #3: single-host approximation (inventory entry #3).

    Workaround #3 (docs/known_issues.md "Checkpoint 17 schema workaround inventory
    tracking", entry #3):
      T1021.001 RDP spans source + target hosts; ATLAS schema is single-host.
      This template models only the SOURCE host perspective.
      Lateral execution on TARGET host is NOT modeled (Phase 9 DARPA TC E3 deferral).

    This test verifies three properties of the workaround implementation:
      1. Event 1 uses USER_EXPLICIT_LOGON (4648), not USER_LOGON (4624).
         USER_EXPLICIT_LOGON is the correct EventID for RDP with explicit credentials
         and distinguishes T1021.001 from T1078 (interactive 4624 logon).
      2. All 8 events share the same host_id field (single-host modeling, not multi-host).
         If multi-host were modeled, some events would have a different host_id for
         the target host -- the workaround ensures a consistent source-host host_id.
      3. The target_host node is modeled as NodeType.network (IP:3389), not as a
         separate host graph -- consistent with the single-host approximation.
    """
    from loghetero.data.attack_templates.t1021_001_rdp import T1021001RDP
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 3
    template = T1021001RDP()
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

    # Property 1: seed event must use USER_EXPLICIT_LOGON (not USER_LOGON).
    ev_seed = events[0]
    assert ev_seed.operation == EdgeType.USER_EXPLICIT_LOGON.value, (
        f"Event 1 must use USER_EXPLICIT_LOGON (4648 RDP explicit credentials), "
        f"got {ev_seed.operation!r}. Using USER_LOGON would conflate T1021.001 "
        f"with T1078 (4624 interactive logon)."
    )
    assert (
        ev_seed.operation != EdgeType.USER_LOGON.value
    ), "Event 1 must NOT use USER_LOGON; T1021.001 uses explicit credentials (4648)."

    # Property 2: all 8 events share consistent host_id (single-host modeling).
    host_ids = {ev.host_id for ev in events}
    assert len(host_ids) == 1, (
        f"All 8 events must share the same host_id (single-host approximation, "
        f"workaround #3). Got distinct host_ids: {host_ids}. "
        f"Lateral execution on TARGET host is NOT modeled (Phase 9 deferral)."
    )

    # Property 3: target_host is modeled as network node (IP:port), not a host graph.
    ev_net_connect = events[1]
    assert ev_net_connect.operation == EdgeType.NET_CONNECT.value
    assert ev_net_connect.obj_type == NodeType.network, (
        f"target_host_3389 must be NodeType.network (IP:3389 notation), "
        f"got {ev_net_connect.obj_type}. Single-host approximation models the "
        f"target as a remote network endpoint, not a separate host subgraph."
    )
    assert (
        "3389" in ev_net_connect.obj
    ), f"target_host network node must contain port 3389, got {ev_net_connect.obj!r}"


def test_t1021_001_labels_are_1() -> None:
    """All T1021.001 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1021_001_rdp import T1021001RDP

    events = _make_template_call(T1021001RDP)
    for ev in events:
        assert ev.attributes.get("label") == 1


# ---------------------------------------------------------------------------
# T1566.001 Spearphishing Attachment (Phase 5 / Checkpoint 15 Cycle D)
# ---------------------------------------------------------------------------


def test_t1566_001_generates_7_events() -> None:
    """T1566.001 must generate exactly 7 events."""
    from loghetero.data.attack_templates.t1566_001_spearphishing_attachment import (
        T1566001SpearphishingAttachment,
    )

    events = _make_template_call(T1566001SpearphishingAttachment)
    assert len(events) == 7, f"Expected 7 events, got {len(events)}"


def test_t1566_001_event_types() -> None:
    """T1566.001 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    No schema workaround needed: all 7 triples are natively in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1566_001_spearphishing_attachment import (
        T1566001SpearphishingAttachment,
    )
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1566001SpearphishingAttachment)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1566.001"


def test_t1566_001_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1566_001_spearphishing_attachment import (
        T1566001SpearphishingAttachment,
    )
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1566001SpearphishingAttachment)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1566_001_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1566_001_spearphishing_attachment import (
        T1566001SpearphishingAttachment,
    )

    events = _make_template_call(T1566001SpearphishingAttachment)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1566_001_timestamps_in_window() -> None:
    """All T1566.001 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1566_001_spearphishing_attachment import (
        T1566001SpearphishingAttachment,
    )

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1566001SpearphishingAttachment()
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


def test_t1566_001_labels_are_1() -> None:
    """All T1566.001 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1566_001_spearphishing_attachment import (
        T1566001SpearphishingAttachment,
    )

    events = _make_template_call(T1566001SpearphishingAttachment)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1566_001_macro_execution_chain() -> None:
    """Validate the spearphishing macro execution chain.

    Verifies the characteristic parent-process ancestry:
    - Event 3 (index 2): outlook.exe spawns winword.exe (PROCESS_CREATE)
    - Event 4 (index 3): winword.exe spawns cmd.exe (PROCESS_CREATE)
    - Event 5 (index 4): cmd.exe spawns dropper.exe (PROCESS_CREATE)
    This ancestry chain distinguishes T1566.001 from other Initial Access TTPs.
    """
    from loghetero.data.attack_templates.t1566_001_spearphishing_attachment import (
        T1566001SpearphishingAttachment,
    )
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 4
    template = T1566001SpearphishingAttachment()
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

    # Event 3 (index 2): outlook.exe -> PROCESS_CREATE -> winword.exe
    ev_outlook_winword = events[2]
    assert ev_outlook_winword.operation == EdgeType.PROCESS_CREATE.value
    assert f"atk_{iid}_outlook.exe" in ev_outlook_winword.subject
    assert f"atk_{iid}_winword.exe" in ev_outlook_winword.obj
    assert ev_outlook_winword.subject_type == NodeType.process
    assert ev_outlook_winword.obj_type == NodeType.process

    # Event 4 (index 3): winword.exe -> PROCESS_CREATE -> cmd.exe (macro shell)
    ev_winword_cmd = events[3]
    assert ev_winword_cmd.operation == EdgeType.PROCESS_CREATE.value
    assert f"atk_{iid}_winword.exe" in ev_winword_cmd.subject
    assert f"atk_{iid}_cmd.exe" in ev_winword_cmd.obj

    # Event 5 (index 4): cmd.exe -> PROCESS_CREATE -> dropper.exe
    ev_cmd_dropper = events[4]
    assert ev_cmd_dropper.operation == EdgeType.PROCESS_CREATE.value
    assert f"atk_{iid}_cmd.exe" in ev_cmd_dropper.subject
    assert f"atk_{iid}_dropper.exe" in ev_cmd_dropper.obj


# ---------------------------------------------------------------------------
# T1078 Valid Accounts (Phase 5 / Checkpoint 15 Cycle D)
# ---------------------------------------------------------------------------


def test_t1078_generates_7_events() -> None:
    """T1078 must generate exactly 7 events."""
    from loghetero.data.attack_templates.t1078_valid_accounts import T1078ValidAccounts

    events = _make_template_call(T1078ValidAccounts)
    assert len(events) == 7, f"Expected 7 events, got {len(events)}"


def test_t1078_event_types() -> None:
    """T1078 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    Specifically verifies that USER_LOGON_FAIL triple is in ALLOWED_EDGE_TRIPLES
    (added Q-1, similar to USER_LOGON).
    """
    from loghetero.data.attack_templates.t1078_valid_accounts import T1078ValidAccounts
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    events = _make_template_call(T1078ValidAccounts)

    # Confirm the USER_LOGON_FAIL triple is in ALLOWED_EDGE_TRIPLES before looping.
    fail_triple = (NodeType.user, EdgeType.USER_LOGON_FAIL, NodeType.process)
    assert fail_triple in ALLOWED_EDGE_TRIPLES, (
        "(user, USER_LOGON_FAIL, process) not in ALLOWED_EDGE_TRIPLES -- "
        "Q-1 mini-checkpoint addition may be missing."
    )

    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1078"


def test_t1078_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1078_valid_accounts import T1078ValidAccounts
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1078ValidAccounts)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1078_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1078_valid_accounts import T1078ValidAccounts

    events = _make_template_call(T1078ValidAccounts)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1078_timestamps_in_window() -> None:
    """All T1078 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1078_valid_accounts import T1078ValidAccounts

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1078ValidAccounts()
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


def test_t1078_labels_are_1() -> None:
    """All T1078 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1078_valid_accounts import T1078ValidAccounts

    events = _make_template_call(T1078ValidAccounts)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1078_logon_fail_then_success() -> None:
    """Validate the fail-fail-success logon pattern characteristic of T1078.

    Verifies:
    - Events 1 and 2 (index 0, 1) are USER_LOGON_FAIL with seed_user as subject.
    - Event 3 (index 2) is USER_LOGON with seed_user as subject (successful stolen creds).
    - Event 4 (index 3) is USER_PRIV_GRANT with seed_user as subject.
    - Events 5-7 (index 4-6) use target_svc.exe as subject (post-auth activity).
    """
    from loghetero.data.attack_templates.t1078_valid_accounts import T1078ValidAccounts
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 6
    template = T1078ValidAccounts()
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

    # Events 1 and 2: USER_LOGON_FAIL with seed_user subject
    for idx in (0, 1):
        ev = events[idx]
        assert (
            ev.operation == EdgeType.USER_LOGON_FAIL.value
        ), f"Event {idx + 1} must be USER_LOGON_FAIL, got {ev.operation!r}"
        assert (
            ev.subject == "victim_user"
        ), f"Event {idx + 1} subject must be seed_user, got {ev.subject!r}"
        assert ev.subject_type == NodeType.user

    # Event 3: USER_LOGON (successful) with seed_user subject
    ev_logon = events[2]
    assert (
        ev_logon.operation == EdgeType.USER_LOGON.value
    ), f"Event 3 must be USER_LOGON (success), got {ev_logon.operation!r}"
    assert ev_logon.subject == "victim_user"

    # Event 4: USER_PRIV_GRANT with seed_user subject
    ev_priv = events[3]
    assert (
        ev_priv.operation == EdgeType.USER_PRIV_GRANT.value
    ), f"Event 4 must be USER_PRIV_GRANT, got {ev_priv.operation!r}"
    assert ev_priv.subject == "victim_user"

    # Events 5-7: target_svc.exe as subject (post-auth service activity)
    target_svc = f"atk_{iid}_target_svc.exe"
    for idx in (4, 5, 6):
        ev = events[idx]
        assert ev.subject == target_svc, (
            f"Event {idx + 1} subject must be {target_svc!r} (post-auth), " f"got {ev.subject!r}"
        )
        assert ev.subject_type == NodeType.process


# ---------------------------------------------------------------------------
# T1057 Process Discovery (Phase 5 / Checkpoint 15 Cycle D)
# ---------------------------------------------------------------------------


def test_t1057_generates_7_events() -> None:
    """T1057 must generate exactly 7 events."""
    from loghetero.data.attack_templates.t1057_process_discovery import T1057ProcessDiscovery

    events = _make_template_call(T1057ProcessDiscovery)
    assert len(events) == 7, f"Expected 7 events, got {len(events)}"


def test_t1057_event_types() -> None:
    """T1057 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    No schema workaround needed: all 7 triples are natively in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1057_process_discovery import T1057ProcessDiscovery
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1057ProcessDiscovery)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1057"


def test_t1057_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1057_process_discovery import T1057ProcessDiscovery
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1057ProcessDiscovery)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1057_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1057_process_discovery import T1057ProcessDiscovery

    events = _make_template_call(T1057ProcessDiscovery)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1057_timestamps_in_window() -> None:
    """All T1057 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1057_process_discovery import T1057ProcessDiscovery

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1057ProcessDiscovery()
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


def test_t1057_labels_are_1() -> None:
    """All T1057 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1057_process_discovery import T1057ProcessDiscovery

    events = _make_template_call(T1057ProcessDiscovery)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1057_findstr_reads_process_list() -> None:
    """Validate the findstr.exe AV-evasion discovery pattern.

    Verifies:
    - Event 4 (index 3): tasklist.exe spawns findstr.exe (PROCESS_CREATE).
    - Event 5 (index 4): findstr.exe reads process_list.txt (FILE_READ).
    - Event 6 (index 5): findstr.exe writes av_processes.txt (FILE_WRITE).
    The findstr search-and-filter pattern is the key behavioral signature of T1057.
    """
    from loghetero.data.attack_templates.t1057_process_discovery import T1057ProcessDiscovery
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 2
    template = T1057ProcessDiscovery()
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

    tasklist = f"atk_{iid}_tasklist.exe"
    findstr = f"atk_{iid}_findstr.exe"
    process_list = f"atk_{iid}_process_list.txt"
    av_processes = f"atk_{iid}_av_processes.txt"

    # Event 4 (index 3): tasklist.exe -> PROCESS_CREATE -> findstr.exe
    ev_spawn = events[3]
    assert ev_spawn.operation == EdgeType.PROCESS_CREATE.value
    assert ev_spawn.subject == tasklist
    assert ev_spawn.obj == findstr
    assert ev_spawn.obj_type == NodeType.process

    # Event 5 (index 4): findstr.exe -> FILE_READ -> process_list.txt
    ev_read = events[4]
    assert ev_read.operation == EdgeType.FILE_READ.value
    assert ev_read.subject == findstr
    assert ev_read.obj == process_list
    assert ev_read.obj_type == NodeType.file

    # Event 6 (index 5): findstr.exe -> FILE_WRITE -> av_processes.txt
    ev_write = events[5]
    assert ev_write.operation == EdgeType.FILE_WRITE.value
    assert ev_write.subject == findstr
    assert ev_write.obj == av_processes
    assert ev_write.obj_type == NodeType.file


# ---------------------------------------------------------------------------
# T1083 File and Directory Discovery (Phase 5 / Checkpoint 15 Cycle D)
# ---------------------------------------------------------------------------


def test_t1083_generates_8_events() -> None:
    """T1083 must generate exactly 8 events."""
    from loghetero.data.attack_templates.t1083_file_discovery import T1083FileDiscovery

    events = _make_template_call(T1083FileDiscovery)
    assert len(events) == 8, f"Expected 8 events, got {len(events)}"


def test_t1083_event_types() -> None:
    """T1083 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    Specifically verifies that event 3 uses FILE_ACCESS (ATLAS EventID 4663) with
    triple (process, FILE_ACCESS, file) which IS in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1083_file_discovery import T1083FileDiscovery
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    events = _make_template_call(T1083FileDiscovery)

    # Confirm the FILE_ACCESS triple is present before looping.
    access_triple = (NodeType.process, EdgeType.FILE_ACCESS, NodeType.file)
    assert access_triple in ALLOWED_EDGE_TRIPLES, (
        "(process, FILE_ACCESS, file) not in ALLOWED_EDGE_TRIPLES -- "
        "ATLAS EventID 4663 FILE_ACCESS entry may be missing."
    )

    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1083"


def test_t1083_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1083_file_discovery import T1083FileDiscovery
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1083FileDiscovery)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1083_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1083_file_discovery import T1083FileDiscovery

    events = _make_template_call(T1083FileDiscovery)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1083_timestamps_in_window() -> None:
    """All T1083 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1083_file_discovery import T1083FileDiscovery

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1083FileDiscovery()
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


def test_t1083_labels_are_1() -> None:
    """All T1083 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1083_file_discovery import T1083FileDiscovery

    events = _make_template_call(T1083FileDiscovery)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1083_file_access_c_drive_root() -> None:
    """Validate FILE_ACCESS (ATLAS 4663) for C: drive root traversal in T1083.

    Event 3 (index 2) must use FILE_ACCESS (not FILE_READ/FILE_OPEN) to model
    ATLAS EventID 4663 generic file system access for the directory traversal
    start point. This is the key schema distinction for T1083.
    """
    from loghetero.data.attack_templates.t1083_file_discovery import T1083FileDiscovery
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 9
    template = T1083FileDiscovery()
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

    dir_enum = f"atk_{iid}_dir_enum.exe"
    c_drive_root = f"atk_{iid}_C_drive_root"

    # Event 3 (index 2): dir_enum.exe -> FILE_ACCESS -> C_drive_root (ATLAS 4663)
    ev_access = events[2]
    assert ev_access.operation == EdgeType.FILE_ACCESS.value, (
        f"Event 3 must use FILE_ACCESS (ATLAS EventID 4663) for C: drive root traversal, "
        f"got {ev_access.operation!r}. FILE_ACCESS (not FILE_READ/FILE_OPEN) is the "
        f"correct ATLAS event for generic directory object access."
    )
    assert (
        ev_access.subject == dir_enum
    ), f"Event 3 subject must be {dir_enum!r}, got {ev_access.subject!r}"
    assert (
        ev_access.obj == c_drive_root
    ), f"Event 3 object must be {c_drive_root!r}, got {ev_access.obj!r}"
    assert ev_access.subject_type == NodeType.process
    assert ev_access.obj_type == NodeType.file

    # Verify event 7 (index 6): cmd.exe reads file_listing.txt (post-processing)
    file_listing = f"atk_{iid}_file_listing.txt"
    ev_cmd_read = events[6]
    assert ev_cmd_read.operation == EdgeType.FILE_READ.value
    assert f"atk_{iid}_cmd.exe" in ev_cmd_read.subject
    assert ev_cmd_read.obj == file_listing


# ---------------------------------------------------------------------------
# T1027 Obfuscated Files (Phase 5 / Checkpoint 15 Cycle E)
# ---------------------------------------------------------------------------


def test_t1027_generates_7_events() -> None:
    """T1027 must generate exactly 7 events."""
    from loghetero.data.attack_templates.t1027_obfuscated_files import T1027ObfuscatedFiles

    events = _make_template_call(T1027ObfuscatedFiles)
    assert len(events) == 7, f"Expected 7 events, got {len(events)}"


def test_t1027_event_types() -> None:
    """T1027 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    No schema workaround needed: all 7 triples are natively in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1027_obfuscated_files import T1027ObfuscatedFiles
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1027ObfuscatedFiles)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1027"


def test_t1027_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1027_obfuscated_files import T1027ObfuscatedFiles
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1027ObfuscatedFiles)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1027_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1027_obfuscated_files import T1027ObfuscatedFiles

    events = _make_template_call(T1027ObfuscatedFiles)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1027_timestamps_in_window() -> None:
    """All T1027 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1027_obfuscated_files import T1027ObfuscatedFiles

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1027ObfuscatedFiles()
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


def test_t1027_labels_are_1() -> None:
    """All T1027 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1027_obfuscated_files import T1027ObfuscatedFiles

    events = _make_template_call(T1027ObfuscatedFiles)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1027_certutil_decode_chain() -> None:
    """Validate the certutil LOLBin decode chain behavioral signature.

    Verifies:
    - Event 2 (index 1): certutil.exe FILE_READ encoded_payload.b64
    - Event 3 (index 2): certutil.exe FILE_WRITE decoded_payload.exe
    - Event 4 (index 3): certutil.exe PROCESS_CREATE decoded_payload.exe
    - Event 5 (index 4): decoded_payload.exe FILE_READ decoded_payload.exe (self-read)
    - Events 6-7 (index 5-6): decoded_payload.exe NET_CONNECT + NET_SEND_NETWORK to c2
    The certutil decode + execute chain distinguishes T1027 from other Defense Evasion TTPs.
    """
    from loghetero.data.attack_templates.t1027_obfuscated_files import T1027ObfuscatedFiles
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 11
    template = T1027ObfuscatedFiles()
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

    certutil = f"atk_{iid}_certutil.exe"
    encoded = f"atk_{iid}_encoded_payload.b64"
    decoded = f"atk_{iid}_decoded_payload.exe"

    # Event 2 (index 1): certutil.exe reads encoded payload
    ev_read_enc = events[1]
    assert ev_read_enc.operation == EdgeType.FILE_READ.value
    assert ev_read_enc.subject == certutil
    assert ev_read_enc.obj == encoded
    assert ev_read_enc.obj_type == NodeType.file

    # Event 3 (index 2): certutil.exe writes decoded binary
    ev_write_dec = events[2]
    assert ev_write_dec.operation == EdgeType.FILE_WRITE.value
    assert ev_write_dec.subject == certutil
    assert ev_write_dec.obj == decoded
    assert ev_write_dec.obj_type == NodeType.file

    # Event 4 (index 3): certutil.exe spawns decoded payload (process)
    ev_create = events[3]
    assert ev_create.operation == EdgeType.PROCESS_CREATE.value
    assert ev_create.subject == certutil
    assert ev_create.obj == decoded
    assert ev_create.obj_type == NodeType.process

    # Event 5 (index 4): decoded_payload self-reads its own image (file node)
    ev_self_read = events[4]
    assert ev_self_read.operation == EdgeType.FILE_READ.value
    assert ev_self_read.subject == decoded
    assert ev_self_read.subject_type == NodeType.process
    assert ev_self_read.obj == decoded
    assert ev_self_read.obj_type == NodeType.file

    # Events 6-7 (index 5-6): C2 connect then send
    ev_net_connect = events[5]
    assert ev_net_connect.operation == EdgeType.NET_CONNECT.value
    assert ev_net_connect.subject == decoded
    assert ev_net_connect.subject_type == NodeType.process
    assert ev_net_connect.obj_type == NodeType.network

    ev_net_send = events[6]
    assert ev_net_send.operation == EdgeType.NET_SEND_NETWORK.value
    assert ev_net_send.subject == decoded
    assert ev_net_send.obj == ev_net_connect.obj


# ---------------------------------------------------------------------------
# T1070.004 File Deletion (Phase 5 / Checkpoint 15 Cycle E)
# ---------------------------------------------------------------------------


def test_t1070_004_generates_7_events() -> None:
    """T1070.004 must generate exactly 7 events."""
    from loghetero.data.attack_templates.t1070_004_file_deletion import T1070004FileDeletion

    events = _make_template_call(T1070004FileDeletion)
    assert len(events) == 7, f"Expected 7 events, got {len(events)}"


def test_t1070_004_event_types() -> None:
    """T1070.004 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    No schema workaround needed: FILE_DELETE is natively in ALLOWED_EDGE_TRIPLES
    (already confirmed present by T1041 Exfiltration tests).
    """
    from loghetero.data.attack_templates.t1070_004_file_deletion import T1070004FileDeletion
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1070004FileDeletion)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1070.004"


def test_t1070_004_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1070_004_file_deletion import T1070004FileDeletion
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1070004FileDeletion)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1070_004_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1070_004_file_deletion import T1070004FileDeletion

    events = _make_template_call(T1070004FileDeletion)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1070_004_timestamps_in_window() -> None:
    """All T1070.004 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1070_004_file_deletion import T1070004FileDeletion

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1070004FileDeletion()
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


def test_t1070_004_labels_are_1() -> None:
    """All T1070.004 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1070_004_file_deletion import T1070004FileDeletion

    events = _make_template_call(T1070004FileDeletion)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1070_004_triple_file_delete_pattern() -> None:
    """Validate the triple file-deletion indicator-removal behavioral signature.

    Verifies:
    - Events 3, 5, 6 (index 2, 4, 5) are FILE_DELETE operations.
    - Event 3 deletes malware.exe (primary artifact).
    - Event 5 deletes attack_log.txt (log artifact).
    - Event 6 deletes cred_dump.dmp (cross-TTP T1003.001 artifact name, see docstring).
    - Event 7 (index 6) is NET_CONNECT (cleanup completion signal to C2).
    The triple FILE_DELETE pattern is the key behavioral signature of T1070.004.
    """
    from loghetero.data.attack_templates.t1070_004_file_deletion import T1070004FileDeletion
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 12
    template = T1070004FileDeletion()
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

    cleanup_tool = f"atk_{iid}_cleanup_tool.exe"
    malware = f"atk_{iid}_malware.exe"
    attack_log = f"atk_{iid}_attack_log.txt"
    cred_dump = f"atk_{iid}_cred_dump.dmp"

    # Event 3 (index 2): FILE_DELETE malware.exe
    ev_del_malware = events[2]
    assert ev_del_malware.operation == EdgeType.FILE_DELETE.value
    assert ev_del_malware.subject == cleanup_tool
    assert ev_del_malware.obj == malware
    assert ev_del_malware.obj_type == NodeType.file

    # Event 5 (index 4): FILE_DELETE attack_log.txt
    ev_del_log = events[4]
    assert ev_del_log.operation == EdgeType.FILE_DELETE.value
    assert ev_del_log.subject == cleanup_tool
    assert ev_del_log.obj == attack_log
    assert ev_del_log.obj_type == NodeType.file

    # Event 6 (index 5): FILE_DELETE cred_dump.dmp (cross-TTP T1003.001 artifact name)
    ev_del_cred = events[5]
    assert ev_del_cred.operation == EdgeType.FILE_DELETE.value
    assert ev_del_cred.subject == cleanup_tool
    assert ev_del_cred.obj == cred_dump
    assert (
        "cred_dump" in ev_del_cred.obj
    ), "Event 6 must reference cred_dump artifact for T1003.001 cross-TTP coherence"

    # Event 7 (index 6): NET_CONNECT (C2 completion signal)
    ev_net = events[6]
    assert ev_net.operation == EdgeType.NET_CONNECT.value
    assert ev_net.subject == cleanup_tool
    assert ev_net.obj_type == NodeType.network


# ---------------------------------------------------------------------------
# T1053.005 Scheduled Task (Phase 5 / Checkpoint 15 Cycle E)
# ---------------------------------------------------------------------------


def test_t1053_005_generates_8_events() -> None:
    """T1053.005 must generate exactly 8 events."""
    from loghetero.data.attack_templates.t1053_005_scheduled_task import T1053005ScheduledTask

    events = _make_template_call(T1053005ScheduledTask)
    assert len(events) == 8, f"Expected 8 events, got {len(events)}"


def test_t1053_005_event_types() -> None:
    """T1053.005 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    Event 3 uses the registry-as-file workaround reused from T1547.001:
    FILE_WRITE to TaskCache registry path (file node) -- triple
    (process, FILE_WRITE, file) IS in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1053_005_scheduled_task import T1053005ScheduledTask
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1053005ScheduledTask)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1053.005"


def test_t1053_005_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1053_005_scheduled_task import T1053005ScheduledTask
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1053005ScheduledTask)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1053_005_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1053_005_scheduled_task import T1053005ScheduledTask

    events = _make_template_call(T1053005ScheduledTask)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1053_005_timestamps_in_window() -> None:
    """All T1053.005 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1053_005_scheduled_task import T1053005ScheduledTask

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1053005ScheduledTask()
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


def test_t1053_005_labels_are_1() -> None:
    """All T1053.005 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1053_005_scheduled_task import T1053005ScheduledTask

    events = _make_template_call(T1053005ScheduledTask)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1053_005_taskcache_registry_as_file_workaround() -> None:
    """Validate the registry-as-file workaround reuse for T1053.005 (T1547.001 pattern).

    Event 3 (index 2) must be FILE_WRITE to a file node whose ID contains the
    TaskCache registry path. This reuses the registry-as-file workaround from
    T1547.001 (no new inventory entry). Verifies:
    - operation == FILE_WRITE
    - obj_type == NodeType.file
    - obj contains 'Schedule' or 'TaskCache' (registry path substring)
    - triple (process, FILE_WRITE, file) IS in ALLOWED_EDGE_TRIPLES
    """
    from loghetero.data.attack_templates.t1053_005_scheduled_task import T1053005ScheduledTask
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    iid = 13
    template = T1053005ScheduledTask()
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

    # Event 3 (index 2): FILE_WRITE to TaskCache registry path (file node)
    ev_reg = events[2]
    assert ev_reg.operation == EdgeType.FILE_WRITE.value, (
        f"Event 3 must be FILE_WRITE (registry-as-file workaround, T1547.001 reuse), "
        f"got {ev_reg.operation!r}"
    )
    assert ev_reg.obj_type == NodeType.file, (
        f"TaskCache registry path must be modeled as file node (registry-as-file workaround), "
        f"got {ev_reg.obj_type}"
    )
    assert "Schedule" in ev_reg.obj or "TaskCache" in ev_reg.obj, (
        f"Event 3 obj must contain TaskCache/Schedule registry path substring, "
        f"got {ev_reg.obj!r}"
    )
    # Verify the workaround triple IS in ALLOWED_EDGE_TRIPLES (legal, not a violation)
    workaround_triple = (NodeType.process, EdgeType.FILE_WRITE, NodeType.file)
    assert (
        workaround_triple in ALLOWED_EDGE_TRIPLES
    ), f"Registry-as-file workaround triple {workaround_triple} not in ALLOWED_EDGE_TRIPLES"

    # Event 5 (index 4): PROCESS_CREATE -> payload.exe (task execution)
    ev_spawn = events[4]
    assert ev_spawn.operation == EdgeType.PROCESS_CREATE.value
    assert f"atk_{iid}_payload.exe" in ev_spawn.obj
    assert ev_spawn.obj_type == NodeType.process


# ---------------------------------------------------------------------------
# T1543.003 Windows Service (Phase 5 / Checkpoint 15 Cycle E)
# ---------------------------------------------------------------------------


def test_t1543_003_generates_7_events() -> None:
    """T1543.003 must generate exactly 7 events."""
    from loghetero.data.attack_templates.t1543_003_windows_service import T1543003WindowsService

    events = _make_template_call(T1543003WindowsService)
    assert len(events) == 7, f"Expected 7 events, got {len(events)}"


def test_t1543_003_event_types() -> None:
    """T1543.003 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    Event 1 uses USER_PRIV_GRANT (4672) seed -- triple (user, USER_PRIV_GRANT, process)
    IS in ALLOWED_EDGE_TRIPLES. Event 3 uses registry-as-file workaround reused
    from T1547.001 -- (process, FILE_WRITE, file) IS in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1543_003_windows_service import T1543003WindowsService
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1543003WindowsService)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1543.003"


def test_t1543_003_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1543_003_windows_service import T1543003WindowsService
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1543003WindowsService)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1543_003_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1543_003_windows_service import T1543003WindowsService

    events = _make_template_call(T1543003WindowsService)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1543_003_timestamps_in_window() -> None:
    """All T1543.003 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1543_003_windows_service import T1543003WindowsService

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1543003WindowsService()
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


def test_t1543_003_labels_are_1() -> None:
    """All T1543.003 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1543_003_windows_service import T1543003WindowsService

    events = _make_template_call(T1543003WindowsService)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1543_003_priv_grant_seed_and_service_registry_workaround() -> None:
    """Validate USER_PRIV_GRANT seed + registry-as-file workaround for T1543.003.

    Verifies three behavioral properties:
    1. Event 1 (index 0): USER_PRIV_GRANT seed (not USER_LOGON). sc.exe requires
       elevated privileges (SeServiceLogonRight); ATLAS EventID 4672 fires on
       privileged logon. Triple (user, USER_PRIV_GRANT, process) IS in ALLOWED_EDGE_TRIPLES.
    2. Event 3 (index 2): FILE_WRITE to Services/MalSvc registry key (file node).
       Registry-as-file workaround REUSED from T1547.001 (no new inventory entry).
    3. Event 4 (index 3): PROCESS_CREATE -> malicious_service.exe (SCM service start).
    """
    from loghetero.data.attack_templates.t1543_003_windows_service import T1543003WindowsService
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    iid = 14
    template = T1543003WindowsService()
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

    # Property 1: Event 1 (index 0) must use USER_PRIV_GRANT (not USER_LOGON)
    ev_seed = events[0]
    assert ev_seed.operation == EdgeType.USER_PRIV_GRANT.value, (
        f"Event 1 must use USER_PRIV_GRANT (4672 privileged session seed), "
        f"got {ev_seed.operation!r}. sc.exe requires elevated privileges to install services."
    )
    assert (
        ev_seed.operation != EdgeType.USER_LOGON.value
    ), "Event 1 must NOT use USER_LOGON; T1543.003 requires privileged session (4672)."
    assert ev_seed.subject == "victim_user"
    assert ev_seed.subject_type == NodeType.user
    assert f"atk_{iid}_sc.exe" in ev_seed.obj
    # Confirm (user, USER_PRIV_GRANT, process) IS in ALLOWED_EDGE_TRIPLES
    seed_triple = (NodeType.user, EdgeType.USER_PRIV_GRANT, NodeType.process)
    assert (
        seed_triple in ALLOWED_EDGE_TRIPLES
    ), f"Seed triple {seed_triple} not in ALLOWED_EDGE_TRIPLES"

    # Property 2: Event 3 (index 2) -- registry-as-file workaround (T1547.001 reuse)
    ev_reg = events[2]
    assert ev_reg.operation == EdgeType.FILE_WRITE.value, (
        f"Event 3 must be FILE_WRITE (registry-as-file workaround, T1547.001 reuse), "
        f"got {ev_reg.operation!r}"
    )
    assert (
        ev_reg.obj_type == NodeType.file
    ), f"Services registry key must be modeled as file node, got {ev_reg.obj_type}"
    assert (
        "Services" in ev_reg.obj or "MalSvc" in ev_reg.obj or "Registry" in ev_reg.obj
    ), f"Event 3 obj must contain Services/MalSvc/Registry substring, got {ev_reg.obj!r}"

    # Property 3: Event 4 (index 3) -- SCM spawns service binary
    ev_start = events[3]
    assert ev_start.operation == EdgeType.PROCESS_CREATE.value
    assert f"atk_{iid}_sc.exe" in ev_start.subject
    assert f"atk_{iid}_malicious_service.exe" in ev_start.obj
    assert ev_start.obj_type == NodeType.process


# ---------------------------------------------------------------------------
# T1190 Exploit Public-Facing Application (Phase 5 / Checkpoint 15 Cycle F)
# ---------------------------------------------------------------------------


def test_t1190_generates_7_events() -> None:
    """T1190 must generate exactly 7 events."""
    from loghetero.data.attack_templates.t1190_exploit_public_facing import T1190ExploitPublicFacing

    events = _make_template_call(T1190ExploitPublicFacing)
    assert len(events) == 7, f"Expected 7 events, got {len(events)}"


def test_t1190_event_types() -> None:
    """T1190 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    Event 2 uses schema workaround #4 (webshell-write): apache.exe FILE_WRITE to
    webshell.php -- triple (process, FILE_WRITE, file) IS in ALLOWED_EDGE_TRIPLES.
    No (network, *, process) triple is used (that triple is NOT in schema).
    """
    from loghetero.data.attack_templates.t1190_exploit_public_facing import T1190ExploitPublicFacing
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1190ExploitPublicFacing)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1190"


def test_t1190_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1190_exploit_public_facing import T1190ExploitPublicFacing
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1190ExploitPublicFacing)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1190_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1190_exploit_public_facing import T1190ExploitPublicFacing

    events = _make_template_call(T1190ExploitPublicFacing)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1190_timestamps_in_window() -> None:
    """All T1190 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1190_exploit_public_facing import T1190ExploitPublicFacing

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1190ExploitPublicFacing()
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


def test_t1190_labels_are_1() -> None:
    """All T1190 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1190_exploit_public_facing import T1190ExploitPublicFacing

    events = _make_template_call(T1190ExploitPublicFacing)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1190_webshell_write_workaround() -> None:
    """Validate schema workaround #4: webshell-write (inventory entry #4).

    Verifies:
    1. Event 2 (index 1) is apache.exe FILE_WRITE to webshell.php (file node).
       This is the pre-adjudicated workaround #4 replacing the (network, *, process)
       ingress event that ALLOWED_EDGE_TRIPLES cannot represent.
    2. No event uses a (network, *, process) triple (i.e., no network-as-subject
       edge to a process object) -- confirms workaround correctly avoids the
       forbidden triple.
    3. The workaround triple (process, FILE_WRITE, file) IS in ALLOWED_EDGE_TRIPLES.
    4. Events 3-4 form the apache.exe -> cmd.exe -> shell.exe PROCESS_CREATE chain.
    """
    from loghetero.data.attack_templates.t1190_exploit_public_facing import T1190ExploitPublicFacing
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    iid = 15
    template = T1190ExploitPublicFacing()
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

    apache = f"atk_{iid}_apache.exe"
    webshell = f"atk_{iid}_webshell.php"
    cmd = f"atk_{iid}_cmd.exe"
    shell = f"atk_{iid}_shell.exe"

    # Property 1: Event 2 (index 1) must be FILE_WRITE to webshell.php (file node).
    ev_webshell = events[1]
    assert ev_webshell.operation == EdgeType.FILE_WRITE.value, (
        f"Event 2 must be FILE_WRITE (schema workaround #4: webshell-write), "
        f"got {ev_webshell.operation!r}. The (network, *, process) ingress event "
        f"cannot be modeled in ALLOWED_EDGE_TRIPLES."
    )
    assert (
        ev_webshell.subject == apache
    ), f"Event 2 subject must be {apache!r} (apache.exe), got {ev_webshell.subject!r}"
    assert (
        ev_webshell.obj == webshell
    ), f"Event 2 obj must be {webshell!r} (webshell.php), got {ev_webshell.obj!r}"
    assert (
        ev_webshell.obj_type == NodeType.file
    ), f"webshell.php must be file node, got {ev_webshell.obj_type}"

    # Property 2: No event uses a network-type subject to a process object.
    for ev in events:
        if ev.subject_type == NodeType.network:
            assert ev.obj_type != NodeType.process, (
                f"Workaround #4 violated: found (network, {ev.operation}, process) triple "
                f"which is NOT in ALLOWED_EDGE_TRIPLES. subject={ev.subject!r}, obj={ev.obj!r}"
            )

    # Property 3: workaround triple IS in ALLOWED_EDGE_TRIPLES (legal, not a violation).
    workaround_triple = (NodeType.process, EdgeType.FILE_WRITE, NodeType.file)
    assert (
        workaround_triple in ALLOWED_EDGE_TRIPLES
    ), f"Workaround #4 triple {workaround_triple} not in ALLOWED_EDGE_TRIPLES"

    # Property 4: events 3-4 form apache.exe -> cmd.exe -> shell.exe PROCESS_CREATE chain.
    ev_apache_cmd = events[2]
    assert ev_apache_cmd.operation == EdgeType.PROCESS_CREATE.value
    assert ev_apache_cmd.subject == apache
    assert ev_apache_cmd.obj == cmd

    ev_cmd_shell = events[3]
    assert ev_cmd_shell.operation == EdgeType.PROCESS_CREATE.value
    assert ev_cmd_shell.subject == cmd
    assert ev_cmd_shell.obj == shell


# ---------------------------------------------------------------------------
# T1560.001 Archive Collected Data via Utility (Phase 5 / Checkpoint 15 Cycle F)
# ---------------------------------------------------------------------------


def test_t1560_001_generates_8_events() -> None:
    """T1560.001 must generate exactly 8 events."""
    from loghetero.data.attack_templates.t1560_001_archive_via_utility import (
        T1560001ArchiveViaUtility,
    )

    events = _make_template_call(T1560001ArchiveViaUtility)
    assert len(events) == 8, f"Expected 8 events, got {len(events)}"


def test_t1560_001_event_types() -> None:
    """T1560.001 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    No schema workaround needed: all 8 triples are natively in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1560_001_archive_via_utility import (
        T1560001ArchiveViaUtility,
    )
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1560001ArchiveViaUtility)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1560.001"


def test_t1560_001_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1560_001_archive_via_utility import (
        T1560001ArchiveViaUtility,
    )
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1560001ArchiveViaUtility)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1560_001_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1560_001_archive_via_utility import (
        T1560001ArchiveViaUtility,
    )

    events = _make_template_call(T1560001ArchiveViaUtility)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1560_001_timestamps_in_window() -> None:
    """All T1560.001 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1560_001_archive_via_utility import (
        T1560001ArchiveViaUtility,
    )

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1560001ArchiveViaUtility()
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


def test_t1560_001_labels_are_1() -> None:
    """All T1560.001 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1560_001_archive_via_utility import (
        T1560001ArchiveViaUtility,
    )

    events = _make_template_call(T1560001ArchiveViaUtility)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1560_001_archive_chain() -> None:
    """Validate the multi-file READ -> archive WRITE -> exfil ordering.

    Verifies the characteristic T1560.001 collection-then-compress-then-exfil chain:
    - Events 2-4 (index 1-3): FILE_READ to three distinct sensitive files (collection).
    - Event 5 (index 4): FILE_WRITE to collected_archive.7z (compression).
    - Event 6 (index 5): FILE_READ of collected_archive.7z (integrity verification).
    - Events 7-8 (index 6-7): NET_CONNECT + NET_SEND_NETWORK (exfiltration).
    The multi-file READ -> archive WRITE -> exfil chain distinguishes T1560.001
    from T1041 (direct exfil without local archival).
    """
    from loghetero.data.attack_templates.t1560_001_archive_via_utility import (
        T1560001ArchiveViaUtility,
    )
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 16
    template = T1560001ArchiveViaUtility()
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

    sevenzip = f"atk_{iid}_7zip.exe"
    doc1 = f"atk_{iid}_sensitive_doc1.docx"
    doc2 = f"atk_{iid}_sensitive_doc2.xlsx"
    db = f"atk_{iid}_sensitive_db.sqlite"
    archive = f"atk_{iid}_collected_archive.7z"

    # Events 2-4 (index 1-3): multi-file FILE_READ (collection phase)
    for idx, expected_file in ((1, doc1), (2, doc2), (3, db)):
        ev = events[idx]
        assert (
            ev.operation == EdgeType.FILE_READ.value
        ), f"Event {idx + 1} must be FILE_READ (collection), got {ev.operation!r}"
        assert ev.subject == sevenzip, f"Event {idx + 1} subject must be 7zip.exe"
        assert (
            ev.obj == expected_file
        ), f"Event {idx + 1} obj must be {expected_file!r}, got {ev.obj!r}"
        assert ev.obj_type == NodeType.file

    # Event 5 (index 4): FILE_WRITE -> collected_archive.7z (compression phase)
    ev_write = events[4]
    assert (
        ev_write.operation == EdgeType.FILE_WRITE.value
    ), f"Event 5 must be FILE_WRITE to archive, got {ev_write.operation!r}"
    assert ev_write.subject == sevenzip
    assert ev_write.obj == archive
    assert ev_write.obj_type == NodeType.file

    # Event 6 (index 5): FILE_READ of archive (integrity verification)
    ev_read_archive = events[5]
    assert ev_read_archive.operation == EdgeType.FILE_READ.value
    assert ev_read_archive.subject == sevenzip
    assert ev_read_archive.obj == archive

    # Events 7-8 (index 6-7): NET_CONNECT + NET_SEND_NETWORK (exfiltration)
    ev_connect = events[6]
    assert ev_connect.operation == EdgeType.NET_CONNECT.value
    assert ev_connect.subject == sevenzip
    assert ev_connect.obj_type == NodeType.network

    ev_send = events[7]
    assert ev_send.operation == EdgeType.NET_SEND_NETWORK.value
    assert ev_send.subject == sevenzip
    assert ev_send.obj == ev_connect.obj  # same C2 network node


# ---------------------------------------------------------------------------
# T1486 Data Encrypted for Impact / Ransomware (Phase 5 / Checkpoint 15 Cycle F)
# ---------------------------------------------------------------------------


def test_t1486_generates_9_events() -> None:
    """T1486 must generate exactly 9 events."""
    from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware

    events = _make_template_call(T1486Ransomware)
    assert len(events) == 9, f"Expected 9 events, got {len(events)}"


def test_t1486_event_types() -> None:
    """T1486 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    No schema workaround needed: all 9 triples are natively in ALLOWED_EDGE_TRIPLES.
    """
    from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1486Ransomware)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1486"


def test_t1486_seed_anchor() -> None:
    """First event must have subject=seed_user and subject_type=NodeType.user."""
    from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware
    from loghetero.data.parsers.base import NodeType

    events = _make_template_call(T1486Ransomware)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user


def test_t1486_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware

    events = _make_template_call(T1486Ransomware)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1486_timestamps_in_window() -> None:
    """All T1486 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1486Ransomware()
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


def test_t1486_labels_are_1() -> None:
    """All T1486 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware

    events = _make_template_call(T1486Ransomware)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1486_encrypt_delete_cycle() -> None:
    """Validate the (READ, WRITE.locked, DELETE) triplet pattern for T1486 ransomware.

    Verifies the characteristic encrypt-delete cycle repeats for both target documents:
    - Events 2-4 (index 1-3): READ important_doc.docx, WRITE .locked, DELETE original.
    - Events 5-7 (index 4-6): READ financial_data.xlsx, WRITE .locked, DELETE original.
    - Event 8 (index 7): FILE_WRITE RANSOM_NOTE.txt (ransom demand).
    - Event 9 (index 8): NET_CONNECT (C2 key reporting / beacon).
    This READ->WRITE.locked->DELETE triplet is the key behavioral signature of
    T1486, distinguishing it from T1070.004 (deletion only) and T1560.001 (archival).
    """
    from loghetero.data.attack_templates.t1486_ransomware import T1486Ransomware
    from loghetero.data.parsers.base import EdgeType, NodeType

    iid = 17
    template = T1486Ransomware()
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

    ransom = f"atk_{iid}_ransom.exe"
    doc = f"atk_{iid}_important_doc.docx"
    doc_locked = f"atk_{iid}_important_doc.docx.locked"
    financial = f"atk_{iid}_financial_data.xlsx"
    financial_locked = f"atk_{iid}_financial_data.xlsx.locked"
    ransom_note = f"atk_{iid}_RANSOM_NOTE.txt"

    # First encrypt-delete cycle (events 2-4, index 1-3): important_doc.docx
    ev_read1 = events[1]
    assert ev_read1.operation == EdgeType.FILE_READ.value
    assert ev_read1.subject == ransom
    assert ev_read1.obj == doc

    ev_write_locked1 = events[2]
    assert ev_write_locked1.operation == EdgeType.FILE_WRITE.value
    assert ev_write_locked1.subject == ransom
    assert ev_write_locked1.obj == doc_locked
    assert "locked" in ev_write_locked1.obj, "Encrypted file must have .locked suffix"

    ev_delete1 = events[3]
    assert ev_delete1.operation == EdgeType.FILE_DELETE.value
    assert ev_delete1.subject == ransom
    assert ev_delete1.obj == doc  # deletes ORIGINAL (not locked file)

    # Second encrypt-delete cycle (events 5-7, index 4-6): financial_data.xlsx
    ev_read2 = events[4]
    assert ev_read2.operation == EdgeType.FILE_READ.value
    assert ev_read2.subject == ransom
    assert ev_read2.obj == financial

    ev_write_locked2 = events[5]
    assert ev_write_locked2.operation == EdgeType.FILE_WRITE.value
    assert ev_write_locked2.subject == ransom
    assert ev_write_locked2.obj == financial_locked
    assert "locked" in ev_write_locked2.obj, "Encrypted file must have .locked suffix"

    ev_delete2 = events[6]
    assert ev_delete2.operation == EdgeType.FILE_DELETE.value
    assert ev_delete2.subject == ransom
    assert ev_delete2.obj == financial  # deletes ORIGINAL (not locked file)

    # Event 8 (index 7): RANSOM_NOTE.txt write (demand delivery)
    ev_note = events[7]
    assert ev_note.operation == EdgeType.FILE_WRITE.value
    assert ev_note.subject == ransom
    assert ev_note.obj == ransom_note
    assert ev_note.obj_type == NodeType.file

    # Event 9 (index 8): NET_CONNECT (C2 key reporting / beacon to operator)
    ev_c2 = events[8]
    assert ev_c2.operation == EdgeType.NET_CONNECT.value
    assert ev_c2.subject == ransom
    assert ev_c2.obj_type == NodeType.network


# ---------------------------------------------------------------------------
# T1490 Inhibit System Recovery (Phase 5 / Checkpoint 15 Cycle F)
# ---------------------------------------------------------------------------


def test_t1490_generates_8_events() -> None:
    """T1490 must generate exactly 8 events."""
    from loghetero.data.attack_templates.t1490_inhibit_system_recovery import (
        T1490InhibitSystemRecovery,
    )

    events = _make_template_call(T1490InhibitSystemRecovery)
    assert len(events) == 8, f"Expected 8 events, got {len(events)}"


def test_t1490_event_types() -> None:
    """T1490 events must use only allowed schema triples (ALLOWED_EDGE_TRIPLES).

    Event 1 uses USER_PRIV_GRANT seed -- (user, USER_PRIV_GRANT, process) IS in
    ALLOWED_EDGE_TRIPLES. Events 3-4 use system-object-as-file reuse for shadow copy.
    Events 6-7 use registry-as-file reuse (BCD store) from T1547.001.
    """
    from loghetero.data.attack_templates.t1490_inhibit_system_recovery import (
        T1490InhibitSystemRecovery,
    )
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType

    events = _make_template_call(T1490InhibitSystemRecovery)
    for ev in events:
        triple = (ev.subject_type, EdgeType(ev.operation), ev.obj_type)
        assert triple in ALLOWED_EDGE_TRIPLES, f"Disallowed triple {triple} in T1490"


def test_t1490_seed_anchor() -> None:
    """First event must have subject=seed_user, subject_type=NodeType.user, and operation=USER_PRIV_GRANT.

    Tier 2 fix from Cycle F code quality review: the operation assertion
    is added to make this test the complete single-point gatekeeper for
    seed identity, consistent with T1543.003's seed test pattern. T1490
    requires privileged session for vssadmin/bcdedit, so seed event must
    be USER_PRIV_GRANT not USER_LOGON.
    """
    from loghetero.data.attack_templates.t1490_inhibit_system_recovery import (
        T1490InhibitSystemRecovery,
    )
    from loghetero.data.parsers.base import EdgeType, NodeType

    events = _make_template_call(T1490InhibitSystemRecovery)
    assert events[0].subject == "victim_user"
    assert events[0].subject_type == NodeType.user
    assert events[0].operation == EdgeType.USER_PRIV_GRANT.value


def test_t1490_attack_nodes_have_atk_prefix() -> None:
    """All non-seed nodes must start with atk_ prefix."""
    from loghetero.data.attack_templates.t1490_inhibit_system_recovery import (
        T1490InhibitSystemRecovery,
    )

    events = _make_template_call(T1490InhibitSystemRecovery)
    for ev in events:
        if ev.subject != "victim_user":
            assert ev.subject.startswith("atk_"), f"Subject {ev.subject!r} lacks atk_ prefix"
        assert ev.obj.startswith("atk_"), f"Object {ev.obj!r} lacks atk_ prefix"


def test_t1490_timestamps_in_window() -> None:
    """All T1490 event timestamps must lie within [t_start_ns, t_end_ns]."""
    from loghetero.data.attack_templates.t1490_inhibit_system_recovery import (
        T1490InhibitSystemRecovery,
    )

    t_start = int(1.5e18)
    t_end = t_start + int(3.6e12)
    template = T1490InhibitSystemRecovery()
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


def test_t1490_labels_are_1() -> None:
    """All T1490 attack events must have label=1 in attributes."""
    from loghetero.data.attack_templates.t1490_inhibit_system_recovery import (
        T1490InhibitSystemRecovery,
    )

    events = _make_template_call(T1490InhibitSystemRecovery)
    for ev in events:
        assert ev.attributes.get("label") == 1


def test_t1490_recovery_disablement() -> None:
    """Validate vssadmin shadow-delete + bcdedit BCD-write recovery disablement chain.

    Verifies three behavioral properties:
    1. Event 1 (index 0): USER_PRIV_GRANT seed (not USER_LOGON). vssadmin and
       bcdedit require elevated privileges; ATLAS EventID 4672 fires on privileged logon.
    2. Events 3-4 (index 2-3): vssadmin.exe FILE_READ + FILE_DELETE shadow_copy_volume.
       Shadow copy modeled as file node (system-object-as-file reuse; no new entry #5).
    3. Events 6-7 (index 5-6): bcdedit.exe FILE_WRITE + FILE_READ BCD registry store.
       BCD store modeled as file node (registry-as-file reuse from T1547.001; no new entry).
    4. Event 8 (index 7): bcdedit.exe FILE_WRITE recovery_disabled_marker (completion flag).
    """
    from loghetero.data.attack_templates.t1490_inhibit_system_recovery import (
        T1490InhibitSystemRecovery,
    )
    from loghetero.data.parsers.base import ALLOWED_EDGE_TRIPLES, EdgeType, NodeType

    iid = 18
    template = T1490InhibitSystemRecovery()
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

    vssadmin = f"atk_{iid}_vssadmin.exe"
    shadow_copy = f"atk_{iid}_shadow_copy_volume"
    bcdedit = f"atk_{iid}_bcdedit.exe"
    recovery_marker = f"atk_{iid}_recovery_disabled_marker"

    # Property 1: Event 1 (index 0) must use USER_PRIV_GRANT (not USER_LOGON).
    ev_seed = events[0]
    assert ev_seed.operation == EdgeType.USER_PRIV_GRANT.value, (
        f"Event 1 must use USER_PRIV_GRANT (4672 privileged seed), "
        f"got {ev_seed.operation!r}. vssadmin/bcdedit require elevated privileges."
    )
    assert (
        ev_seed.operation != EdgeType.USER_LOGON.value
    ), "Event 1 must NOT use USER_LOGON; T1490 requires privileged session (4672)."
    assert ev_seed.subject == "victim_user"
    assert ev_seed.subject_type == NodeType.user
    assert f"atk_{iid}_cmd.exe" in ev_seed.obj
    seed_triple = (NodeType.user, EdgeType.USER_PRIV_GRANT, NodeType.process)
    assert (
        seed_triple in ALLOWED_EDGE_TRIPLES
    ), f"Seed triple {seed_triple} not in ALLOWED_EDGE_TRIPLES"

    # Property 2: Events 3-4 (index 2-3): vssadmin shadow copy FILE_READ + FILE_DELETE.
    ev_shadow_read = events[2]
    assert (
        ev_shadow_read.operation == EdgeType.FILE_READ.value
    ), f"Event 3 must be FILE_READ (shadow enumeration), got {ev_shadow_read.operation!r}"
    assert ev_shadow_read.subject == vssadmin
    assert ev_shadow_read.obj == shadow_copy
    assert (
        ev_shadow_read.obj_type == NodeType.file
    ), "shadow_copy_volume must be modeled as file node (system-object-as-file reuse)"

    ev_shadow_delete = events[3]
    assert (
        ev_shadow_delete.operation == EdgeType.FILE_DELETE.value
    ), f"Event 4 must be FILE_DELETE (shadow deletion), got {ev_shadow_delete.operation!r}"
    assert ev_shadow_delete.subject == vssadmin
    assert ev_shadow_delete.obj == shadow_copy
    assert (
        ev_shadow_delete.obj_type == NodeType.file
    ), "shadow_copy_volume must be file node for FILE_DELETE (system-object-as-file reuse)"

    # Property 3: Events 6-7 (index 5-6): bcdedit BCD store FILE_WRITE + FILE_READ.
    ev_bcd_write = events[5]
    assert ev_bcd_write.operation == EdgeType.FILE_WRITE.value, (
        f"Event 6 must be FILE_WRITE to BCD store (registry-as-file reuse, T1547.001), "
        f"got {ev_bcd_write.operation!r}"
    )
    assert ev_bcd_write.subject == bcdedit
    assert (
        ev_bcd_write.obj_type == NodeType.file
    ), "BCD store must be modeled as file node (registry-as-file reuse from T1547.001)"
    assert (
        "BCD" in ev_bcd_write.obj or "Registry" in ev_bcd_write.obj
    ), f"Event 6 obj must contain BCD/Registry substring, got {ev_bcd_write.obj!r}"

    ev_bcd_read = events[6]
    assert ev_bcd_read.operation == EdgeType.FILE_READ.value
    assert ev_bcd_read.subject == bcdedit
    assert ev_bcd_read.obj == ev_bcd_write.obj  # same BCD store node

    # Property 4: Event 8 (index 7): recovery_disabled_marker FILE_WRITE.
    ev_marker = events[7]
    assert ev_marker.operation == EdgeType.FILE_WRITE.value
    assert ev_marker.subject == bcdedit
    assert ev_marker.obj == recovery_marker
    assert ev_marker.obj_type == NodeType.file


# ---------------------------------------------------------------------------
# Cycle F closure: ALL_TEMPLATES count + TTP ID set
# ---------------------------------------------------------------------------


def test_all_templates_count_20_after_cycle_f() -> None:
    """ALL_TEMPLATES must contain exactly 20 templates after Cycle F (5 Phase 4 + 15 Phase 5)."""
    from loghetero.data.attack_templates import ALL_TEMPLATES

    assert (
        len(ALL_TEMPLATES) == 20
    ), f"Expected 20 templates after Cycle F, got {len(ALL_TEMPLATES)}"
