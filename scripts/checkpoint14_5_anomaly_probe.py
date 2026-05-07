"""Phase 4 / Checkpoint 14.5 anomaly detection probe -- three-config fusion engagement test.

PURPOSE
=======
Critical fusion engagement test under anomaly classification loss pressure
(distinct loss structure from the MLM pressure in Checkpoint 14 alpha/alpha').

Runs 3 probe configs x 4 seeds x 30 epochs, then evaluates the DOUBLE-CONDITION
GATE:
  1. Fusion vs HTGN-only mean F1 lift >= 0.03
  2. Paired t-test p < 0.1  (across 4 seeds, fusion vs HTGN-only)
  3. Fusion - BERT-only mean F1 > 0.01  (fusion adds beyond BERT lexical recognition)

Any condition fail -> STOP, report NEEDS_CONTEXT. Do NOT relax thresholds.

PROTOCOL (RFC-14.5 adjudications, all locked):
  - 5 TTP templates x 100 attack events = 500 total attack
  - 500 matched benign events
  - Total = 1000 events; within-TTP shuffle seed=42; 80/20 split (800 train / 200 test)
  - Three configs: HTGN-only (256-dim subject node), BERT-only (768-dim CLS),
    fusion (768-dim Phase4Model fused_text CLS)
  - MLP head: Linear(D,128) -> ReLU -> Dropout(0.1) -> Linear(128,1)
  - 4 seeds: [42, 7, 1, 100]; per-TTP F1 informational; aggregate F1 for gate
  - No external API calls (RFC-14.5-10)

DATA PATH: M3_h2 first 1.0h window (consistent with C10/C11/C12/C13/C14).
           Falls back to all-synthetic if ATLAS data not available.

BERT-only text format (RFC-14.5-3):
    f"{subject_type} {subject} {operation} {obj_type} {obj}"
    e.g.: "process powershell.exe file_write file payload.ps1"
    No anonymization (RFC-14.5-6): lexical leakage intentional as Condition 3
    diagnostic signal.

HTGN-only embedding (RFC-14.5-3 / RFC-14.5-5):
    Subject node's precomputed HTGN output embedding (256-dim).
    Rationale: event-level prediction 用 subject node embedding 是因为 HTGN 异构
    attention 已让 subject node 的 256-dim output 编码邻居 object 与 action 信息,
    不需要显式 concat.

Fusion config MLP input (RFC-14.5-3):
    fused_text[:, 0, :] (CLS token, 768-dim) from Phase4Model output.

HTGN precomputed (RFC-14.5-5 Option B):
    Build one combined HeteroData (benign + injected attack), run HTGN once
    -> precomputed (N_total, 256) embeddings. Per-event HTGN-only embedding =
    subject node's precomputed embedding.

EXEMPT from 4-step multi-agent review pattern per docs/known_issues.md
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import torch
from torch import nn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Constants (locked per RFC adjudications)
# ---------------------------------------------------------------------------

SCENARIO = "M3"
HOST = "M3_h2"
HOST_LOGS = PROJECT_ROOT / "data" / "raw" / "atlas" / "M3" / "h2" / "logs"
WINDOW_NS = int(3.6e12)
SUBGRAPH_MAX_NODES = 2000
SUBGRAPH_KHOP = 3
HIDDEN_DIM = 256
N_LAYERS = 3
NUM_HEADS = 8
DROPOUT = 0.1
TIME2VEC_DIM = 32
RAW_MSG_DIM = 64

BERT_MODEL = "bert-base-uncased"
BERT_MAX_LENGTH = 64  # event strings are short; 64 is ample

# RFC-14.5-9: 500 attack + 500 benign = 1000 events
EVENTS_PER_TTP = 100
NUM_BENIGN = 500
EVENTS_TOTAL = 1000

# RFC-14.5-7: 80/20 aggregate split
TRAIN_RATIO = 0.8

# Training
EPOCHS = 30
LR = 1e-3
PROBE_SEEDS = [42, 7, 1, 100]

# Gate thresholds (locked, do NOT relax)
GATE1_LIFT_THRESHOLD = 0.03  # fusion vs HTGN-only mean F1 lift
GATE2_PVAL_THRESHOLD = 0.1  # paired t-test p < 0.1
GATE3_DELTA_THRESHOLD = 0.01  # fusion - BERT-only mean F1

# Text format (RFC-14.5-3): "{subject_type} {subject} {operation} {obj_type} {obj}"
# No anonymization (RFC-14.5-6).


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _parse_m3_h2() -> list:
    """Parse M3_h2 logs into a sorted Event list. Returns [] if data absent."""
    from loghetero.data.parsers.atlas import DnsParser, FirefoxParser, SecurityEventsParser

    if not HOST_LOGS.is_dir():
        print(
            f"[14.5] M3_h2 data not found at {HOST_LOGS}; using synthetic-only benign.", flush=True
        )
        return []
    events = []
    for fname, parser in [
        ("dns", DnsParser()),
        ("firefox.txt", FirefoxParser()),
        ("security_events.txt", SecurityEventsParser()),
    ]:
        path = HOST_LOGS / fname
        if not path.is_file():
            continue
        events.extend(parser.parse_file(path, scenario_id=SCENARIO, host_id=HOST))
    events.sort(key=lambda e: e.timestamp_ns)
    return events


def _make_synthetic_benign(n: int, t_start: int) -> list:
    """Create minimal synthetic benign events when real data unavailable."""
    from loghetero.data.parsers.base import EdgeType, Event, NodeType

    rng = random.Random(999)
    events = []
    procs = [f"proc_{i}" for i in range(20)]
    files = [f"file_{i}.txt" for i in range(20)]
    for _ in range(n):
        ts = t_start + rng.randint(0, int(WINDOW_NS))
        proc = rng.choice(procs)
        fname = rng.choice(files)
        ev = Event(
            timestamp_ns=ts,
            subject=proc,
            subject_type=NodeType.process,
            obj=fname,
            obj_type=NodeType.file,
            operation=EdgeType.FILE_READ.value,
            log_type="synthetic_benign",
            scenario_id="synthetic_benign",
            host_id="h_synth",
            attributes={"label": 0},
        )
        events.append(ev)
    # Also add a user node to allow shared-seed anchoring.
    for _ in range(min(20, n // 10)):
        ts = t_start + rng.randint(0, int(WINDOW_NS) // 10)
        ev = Event(
            timestamp_ns=ts,
            subject="victim_user",
            subject_type=NodeType.user,
            obj=rng.choice(procs),
            obj_type=NodeType.process,
            operation=EdgeType.USER_LOGON.value,
            log_type="synthetic_benign",
            scenario_id="synthetic_benign",
            host_id="h_synth",
            attributes={"label": 0},
        )
        events.append(ev)
    events.sort(key=lambda e: e.timestamp_ns)
    return events


def _select_first_window(events: list) -> list:
    """Slice events to the first 1.0h window."""
    if not events:
        return []
    t_min = events[0].timestamp_ns
    return [e for e in events if e.timestamp_ns < t_min + WINDOW_NS]


# ---------------------------------------------------------------------------
# Event text renderer for BERT (RFC-14.5-3)
# ---------------------------------------------------------------------------


def _event_to_bert_text(ev: object) -> str:
    """Render event to BERT input text per RFC-14.5-3 (no anonymization, RFC-14.5-6).

    Format: "{subject_type} {subject} {operation} {obj_type} {obj}"
    Example: "process powershell.exe file_write file payload.ps1"
    """
    st = ev.subject_type.value if hasattr(ev.subject_type, "value") else str(ev.subject_type)  # type: ignore[union-attr]
    ot = ev.obj_type.value if hasattr(ev.obj_type, "value") else str(ev.obj_type)  # type: ignore[union-attr]
    op = ev.operation if isinstance(ev.operation, str) else str(ev.operation)
    return f"{st} {ev.subject} {op} {ot} {ev.obj}"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Graph building: one combined HeteroData (benign + attack)
# ---------------------------------------------------------------------------


def _build_combined_graph(all_events: list) -> object:
    """Build one combined HeteroData from benign + attack events (RFC-14.5-5)."""
    from loghetero.data.provenance_graph import build_graph

    graph, _stats = build_graph(all_events)
    print(
        "[14.5] Combined graph: "
        + ", ".join(f"{nt}={graph[nt].num_nodes}" for nt in graph.node_types),
        flush=True,
    )
    total_edges = sum(graph[rel].edge_index.shape[1] for rel in graph.edge_types)
    print(f"[14.5] Total edges: {total_edges}", flush=True)
    return graph


# ---------------------------------------------------------------------------
# HTGN precomputed embeddings (RFC-14.5-5 Option B)
# ---------------------------------------------------------------------------


def _precompute_htgn_embeddings(
    combined_graph: object,
    device: torch.device,
) -> tuple[dict[str, torch.Tensor], dict]:
    """Run HTGN once on combined graph -> precomputed per-node embeddings.

    Returns:
        node_embs: dict[node_type_str -> Tensor(N, 256)]
        n_per_type: dict[NodeType -> int] for reconstructing HTGN
    """
    from loghetero.data.parsers.base import NodeType
    from loghetero.models.graph.htgn import HTGN

    graph = combined_graph  # type: ignore[assignment]
    n_per_type: dict = {}
    for nt in NodeType:
        n = graph[nt.value].num_nodes if nt.value in graph.node_types else 0
        n_per_type[nt] = n

    # Build x_dict with random Gaussian initial features.
    torch.manual_seed(42)
    x_dict: dict[str, torch.Tensor] = {}
    for nt, n in n_per_type.items():
        if n > 0:
            x_dict[nt.value] = torch.randn(n, HIDDEN_DIM, device=device)

    edge_index_dict: dict[tuple[str, str, str], torch.Tensor] = {}
    edge_time_dict_ns: dict[tuple[str, str, str], torch.Tensor] = {}
    for rel in graph.edge_types:
        edge_index_dict[rel] = graph[rel].edge_index.to(device)
        edge_time_dict_ns[rel] = graph[rel].edge_attr_time.to(device)

    metadata = graph.metadata()

    # Workaround: TGN memory node count must accommodate cross-type src indices.
    max_count = max(n_per_type.values()) if n_per_type.values() else 1
    htgn_node_counts: dict = {
        nt: (max_count if nt in (NodeType.process, NodeType.socket) else n_per_type[nt])
        for nt in NodeType
    }

    htgn = HTGN(
        in_channels=HIDDEN_DIM,
        metadata=metadata,
        num_nodes_per_type=htgn_node_counts,
        hidden_dim=HIDDEN_DIM,
        n_layers=N_LAYERS,
        num_heads=NUM_HEADS,
        dropout=DROPOUT,
        time2vec_dim=TIME2VEC_DIM,
        residual_alpha=0.5,
        layer_decay_gamma=(1.0, 0.7, 0.4),
        memory_node_types=(NodeType.process, NodeType.socket),
        raw_msg_dim=RAW_MSG_DIM,
    ).to(device)

    htgn.eval()
    htgn.tgn_memory.reset_state()

    with torch.no_grad():
        out_dict = htgn(x_dict, edge_index_dict, edge_time_dict_ns)

    # Return CPU tensors to save VRAM (embeddings are precomputed once).
    node_embs: dict[str, torch.Tensor] = {k: v.cpu() for k, v in out_dict.items()}
    print(
        "[14.5] HTGN precomputed node types: "
        + ", ".join(f"{k}={v.shape[0]}" for k, v in node_embs.items()),
        flush=True,
    )
    return node_embs, n_per_type


# ---------------------------------------------------------------------------
# Feature extraction per config
# ---------------------------------------------------------------------------


def _get_node_index(graph: object, ntype: str, node_id: str) -> int | None:
    """Look up the integer index of node_id in graph[ntype].node_id."""
    node_ids: list = graph[ntype].node_id  # type: ignore[attr-defined]
    try:
        return node_ids.index(node_id)
    except ValueError:
        return None


def _extract_htgn_only_features(
    events_labeled: list[tuple[object, int]],
    graph: object,
    node_embs: dict[str, torch.Tensor],
) -> tuple[torch.Tensor, torch.Tensor]:
    """Extract HTGN subject-node embeddings for each event (RFC-14.5-3).

    event-level prediction 用 subject node embedding 是因为 HTGN 异构 attention
    已让 subject node 的 256-dim output 编码邻居 object 与 action 信息, 不需要
    显式 concat.

    Returns:
        features: (N_events, 256)
        labels: (N_events,) long
    """
    feat_list = []
    lbl_list = []
    zero_emb = torch.zeros(HIDDEN_DIM)
    for ev, label in events_labeled:
        st = ev.subject_type.value if hasattr(ev.subject_type, "value") else str(ev.subject_type)  # type: ignore[union-attr]
        idx = _get_node_index(graph, st, ev.subject)  # type: ignore[arg-type]
        if idx is not None and st in node_embs and idx < node_embs[st].shape[0]:
            feat_list.append(node_embs[st][idx])
        else:
            feat_list.append(zero_emb)
        lbl_list.append(label)
    features = torch.stack(feat_list, dim=0)  # (N, 256)
    labels = torch.tensor(lbl_list, dtype=torch.long)
    return features, labels


def _extract_bert_only_features(
    events_labeled: list[tuple[object, int]],
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Extract BERT CLS embeddings for each event (RFC-14.5-3).

    Text format (RFC-14.5-3): "{subject_type} {subject} {operation} {obj_type} {obj}"
    No anonymization (RFC-14.5-6).

    Returns:
        features: (N_events, 768) on CPU
        labels: (N_events,) long
    """
    from loghetero.models.encoders.bert_text import TrainMode, build_bert_text_encoder

    print(f"[14.5]   Building frozen BERT for {len(events_labeled)} events ...", flush=True)
    bert_model, tokenizer = build_bert_text_encoder(BERT_MODEL, mode=TrainMode.frozen)
    bert_model = bert_model.to(device)
    bert_model.eval()

    texts = [_event_to_bert_text(ev) for ev, _ in events_labeled]
    lbl_list = [lbl for _, lbl in events_labeled]

    batch_size = 32
    cls_embeds = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            enc = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=BERT_MAX_LENGTH,
                return_tensors="pt",
            )
            enc = {k: v.to(device) for k, v in enc.items()}
            out = bert_model(**enc)
            # CLS token = hidden_states[-1][:, 0, :]
            assert out.hidden_states is not None
            cls = out.hidden_states[-1][:, 0, :]  # (B, 768)
            cls_embeds.append(cls.cpu())

    features = torch.cat(cls_embeds, dim=0)  # (N, 768)
    labels = torch.tensor(lbl_list, dtype=torch.long)
    return features, labels


def _extract_fusion_features(
    events_labeled: list[tuple[object, int]],
    graph: object,
    node_embs_dict: dict[str, torch.Tensor],
    n_per_type: dict,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Extract Phase4Model fused_text CLS embeddings (RFC-14.5-3 / RFC-14.5-5).

    Uses Phase4Model forward -> fused_text[:, 0, :] (CLS token, 768-dim).

    Returns:
        features: (N_events, 768) on CPU
        labels: (N_events,) long
    """
    from loghetero.data.parsers.base import NodeType
    from loghetero.models.graph.htgn import HTGN
    from loghetero.models.phase4_model import Phase4Model

    print(f"[14.5]   Building Phase4Model for {len(events_labeled)} events ...", flush=True)

    # Build HTGN instance (same config as precompute step).
    max_count = max(n_per_type.values()) if n_per_type.values() else 1
    htgn_node_counts: dict = {
        nt: (max_count if nt in (NodeType.process, NodeType.socket) else n_per_type[nt])
        for nt in NodeType
    }

    edge_index_dict: dict[tuple[str, str, str], torch.Tensor] = {}
    edge_time_dict_ns: dict[tuple[str, str, str], torch.Tensor] = {}
    for rel in graph.edge_types:  # type: ignore[attr-defined]
        edge_index_dict[rel] = graph[rel].edge_index.to(device)  # type: ignore[attr-defined]
        edge_time_dict_ns[rel] = graph[rel].edge_attr_time.to(device)  # type: ignore[attr-defined]

    metadata = graph.metadata()  # type: ignore[attr-defined]

    htgn = HTGN(
        in_channels=HIDDEN_DIM,
        metadata=metadata,
        num_nodes_per_type=htgn_node_counts,
        hidden_dim=HIDDEN_DIM,
        n_layers=N_LAYERS,
        num_heads=NUM_HEADS,
        dropout=DROPOUT,
        time2vec_dim=TIME2VEC_DIM,
        residual_alpha=0.5,
        layer_decay_gamma=(1.0, 0.7, 0.4),
        memory_node_types=(NodeType.process, NodeType.socket),
        raw_msg_dim=RAW_MSG_DIM,
    )

    phase4 = Phase4Model(htgn=htgn, bert_model_name=BERT_MODEL, attn_dropout=0.1).to(device)
    phase4.eval()

    # Build x_dict for HTGN (use precomputed embeddings as initialization).
    x_dict: dict[str, torch.Tensor] = {}
    for nt in NodeType:
        n = n_per_type.get(nt, 0)
        if n > 0:
            if nt.value in node_embs_dict:
                x_dict[nt.value] = node_embs_dict[nt.value].to(device)
            else:
                x_dict[nt.value] = torch.zeros(n, HIDDEN_DIM, device=device)

    from loghetero.models.encoders.bert_text import TrainMode, build_bert_text_encoder

    _, tokenizer = build_bert_text_encoder(BERT_MODEL, mode=TrainMode.frozen)

    texts = [_event_to_bert_text(ev) for ev, _ in events_labeled]
    lbl_list = [lbl for _, lbl in events_labeled]

    # Run Phase4Model per event (batch=1 for memory safety).
    cls_embeds = []
    with torch.no_grad():
        for text in texts:
            enc = tokenizer(
                [text],
                padding=True,
                truncation=True,
                max_length=BERT_MAX_LENGTH,
                return_tensors="pt",
            )
            input_ids = enc["input_ids"].to(device)
            attn_mask = enc["attention_mask"].to(device)

            out = phase4(
                input_ids=input_ids,
                attention_mask=attn_mask,
                x_dict=x_dict,
                edge_index_dict=edge_index_dict,
                edge_time_dict_ns=edge_time_dict_ns,
            )
            # fused_text: (1, T, 768) -> CLS token -> (768,)
            fused_text = out["fused_text"]  # (1, T, 768)
            assert fused_text is not None
            cls = fused_text[0, 0, :].cpu()  # (768,)
            cls_embeds.append(cls)
            # Reset TGN memory between events for a fair precomputed-graph test.
            phase4.htgn.tgn_memory.reset_state()  # type: ignore[attr-defined]

    features = torch.stack(cls_embeds, dim=0)  # (N, 768)
    labels = torch.tensor(lbl_list, dtype=torch.long)
    return features, labels


# ---------------------------------------------------------------------------
# MLP probe training + evaluation
# ---------------------------------------------------------------------------


def _train_eval_probe(
    feat_train: torch.Tensor,
    lbl_train: torch.Tensor,
    feat_test: torch.Tensor,
    lbl_test: torch.Tensor,
    input_dim: int,
    seed: int,
    config_name: str,
    device: torch.device,
) -> float:
    """Train the probe MLP head and return test F1 score.

    MLP architecture (RFC-14.5-8):
        Linear(input_dim, 128) -> ReLU -> Dropout(0.1) -> Linear(128, 1)
    """
    from loghetero.models.heads.probe_classifier import ProbeClassifier, ProbeConfig

    # Map input_dim to ProbeConfig.
    if input_dim == 256:
        cfg = ProbeConfig.HTGN_ONLY
    elif config_name == "bert_only":
        cfg = ProbeConfig.BERT_ONLY
    else:
        cfg = ProbeConfig.FUSION

    torch.manual_seed(seed)
    model = ProbeClassifier(config=cfg, input_dim=input_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    criterion = nn.BCEWithLogitsLoss()

    feat_tr_d = feat_train.to(device)
    lbl_tr_d = lbl_train.float().to(device)

    model.train()
    for _epoch in range(EPOCHS):
        optimizer.zero_grad()
        logits = model(feat_tr_d).squeeze(-1)  # (N,)
        loss = criterion(logits, lbl_tr_d)
        loss.backward()
        optimizer.step()

    # Evaluate on test set.
    model.eval()
    feat_te_d = feat_test.to(device)
    with torch.no_grad():
        logits_test = model(feat_te_d).squeeze(-1)
        probs = torch.sigmoid(logits_test).cpu()
    preds = (probs >= 0.5).long()
    y_np = lbl_test.numpy()
    p_np = preds.numpy()

    # Compute F1 (binary, positive class = 1).
    from sklearn.metrics import f1_score

    f1 = float(f1_score(y_np, p_np, zero_division=0))
    return f1


# ---------------------------------------------------------------------------
# Per-TTP F1 (informational, RFC-14.5-7 tightening)
# ---------------------------------------------------------------------------


def _compute_per_ttp_f1(
    test_events_labeled: list[tuple[object, int]],
    template_ids: list[str],
    feat_test: torch.Tensor,
    lbl_test: torch.Tensor,
    model: object,
    device: torch.device,
) -> dict[str, float]:
    """Return per-TTP F1 on the test subset for informational reporting."""
    from sklearn.metrics import f1_score

    assert hasattr(model, "forward")

    with torch.no_grad():
        logits_all = model(feat_test.to(device)).squeeze(-1)  # type: ignore[operator]
        preds_all = (torch.sigmoid(logits_all).cpu() >= 0.5).long().numpy()

    y_np = lbl_test.numpy()
    per_ttp_f1: dict[str, float] = {}

    for ttp_id in template_ids:
        # Indices where this TTP event or any benign event appears.
        indices = []
        for i, (ev, lbl) in enumerate(test_events_labeled):
            attrs = getattr(ev, "attributes", {})
            if (lbl == 1 and attrs.get("ttp") == ttp_id) or lbl == 0:
                indices.append(i)

        if not indices:
            per_ttp_f1[ttp_id] = float("nan")
            continue

        y_sub = y_np[indices]
        p_sub = preds_all[indices]
        per_ttp_f1[ttp_id] = float(f1_score(y_sub, p_sub, zero_division=0))

    return per_ttp_f1


# ---------------------------------------------------------------------------
# Main experiment loop
# ---------------------------------------------------------------------------


def main() -> int:
    """Run 3 configs x 4 seeds x 30 epochs; evaluate double-condition gate.

    Returns:
        0 if gate PASS, 1 if NEEDS_CONTEXT (do NOT relax thresholds).
    """
    import scipy.stats as stats

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[14.5] Device: {device}", flush=True)
    t0_total = time.perf_counter()

    # -----------------------------------------------------------------------
    # 1. Load benign data
    # -----------------------------------------------------------------------
    print("[14.5] Step 1: Loading benign data ...", flush=True)
    all_events = _parse_m3_h2()
    window_benign = _select_first_window(all_events)

    t_start_ns: int
    if window_benign:
        t_start_ns = window_benign[0].timestamp_ns
        print(
            f"[14.5]   {len(window_benign):,} real benign events in first 1.0h window.", flush=True
        )
    else:
        # No real data: create synthetic benign events.
        import datetime

        t_start_ns = int(
            (
                datetime.datetime(2018, 11, 4, 0, 0, 0) - datetime.datetime(1970, 1, 1)
            ).total_seconds()
            * 1e9
        )
        window_benign = _make_synthetic_benign(NUM_BENIGN * 2, t_start_ns)
        print(
            f"[14.5]   Using {len(window_benign)} synthetic benign events (no real data).",
            flush=True,
        )

    # -----------------------------------------------------------------------
    # 2. Inject attack events (5 TTPs x 100 = 500 attacks)
    # -----------------------------------------------------------------------
    print("[14.5] Step 2: Injecting 5 TTP attack events ...", flush=True)
    from loghetero.data.attack_templates import ALL_TEMPLATES
    from loghetero.data.synthetic_injector import SyntheticInjector

    injector = SyntheticInjector(
        benign_events=window_benign,
        templates=ALL_TEMPLATES,
        seed=42,
        events_per_ttp=EVENTS_PER_TTP,
        num_benign=NUM_BENIGN,
    )
    dataset = injector.build()

    train_ev = dataset.train_events
    test_ev = dataset.test_events
    attack_in_train = sum(lbl for _, lbl in train_ev)
    attack_in_test = sum(lbl for _, lbl in test_ev)
    print(
        f"[14.5]   Train={len(train_ev)} Test={len(test_ev)} "
        f"(attack_train={attack_in_train}, attack_test={attack_in_test})",
        flush=True,
    )

    # Collect all events for graph building (benign + attack).
    all_injected_events = [ev for ev, _ in dataset.events_with_labels]
    if window_benign:
        graph_events = list(window_benign) + [
            ev for ev, lbl in dataset.events_with_labels if lbl == 1
        ]
    else:
        graph_events = all_injected_events

    template_ids = [t.ttp_id for t in ALL_TEMPLATES]

    # -----------------------------------------------------------------------
    # 3. Build combined HeteroData (RFC-14.5-5 Option B)
    # -----------------------------------------------------------------------
    print("[14.5] Step 3: Building combined provenance graph ...", flush=True)
    try:
        combined_graph = _build_combined_graph(graph_events)
    except Exception as exc:
        print(f"[14.5] WARNING: graph build error: {exc}; using injection-only graph.", flush=True)
        combined_graph = _build_combined_graph(all_injected_events)

    # -----------------------------------------------------------------------
    # 4. Precompute HTGN embeddings (RFC-14.5-5 Option B)
    # -----------------------------------------------------------------------
    print("[14.5] Step 4: Precomputing HTGN embeddings ...", flush=True)
    node_embs, n_per_type = _precompute_htgn_embeddings(combined_graph, device)

    # -----------------------------------------------------------------------
    # 5. Extract features for all 3 configs (done once, reused across seeds)
    # -----------------------------------------------------------------------
    print("[14.5] Step 5: Extracting features (3 configs) ...", flush=True)

    print("[14.5]   Config: HTGN-only ...", flush=True)
    htgn_tr, lbl_htgn_tr = _extract_htgn_only_features(train_ev, combined_graph, node_embs)
    htgn_te, lbl_htgn_te = _extract_htgn_only_features(test_ev, combined_graph, node_embs)
    print(f"[14.5]   HTGN train: {htgn_tr.shape}, test: {htgn_te.shape}", flush=True)

    print("[14.5]   Config: BERT-only ...", flush=True)
    bert_tr, lbl_bert_tr = _extract_bert_only_features(train_ev, device)
    bert_te, lbl_bert_te = _extract_bert_only_features(test_ev, device)
    print(f"[14.5]   BERT train: {bert_tr.shape}, test: {bert_te.shape}", flush=True)

    print("[14.5]   Config: Fusion (Phase4Model fused_text CLS) ...", flush=True)
    print("[14.5]   NOTE: Fusion runs Phase4Model per event; may be slow ...", flush=True)
    fuse_tr, lbl_fuse_tr = _extract_fusion_features(
        train_ev, combined_graph, node_embs, n_per_type, device
    )
    fuse_te, lbl_fuse_te = _extract_fusion_features(
        test_ev, combined_graph, node_embs, n_per_type, device
    )
    print(f"[14.5]   Fusion train: {fuse_tr.shape}, test: {fuse_te.shape}", flush=True)

    # -----------------------------------------------------------------------
    # 6. Train + eval probes: 3 configs x 4 seeds
    # -----------------------------------------------------------------------
    print(
        f"[14.5] Step 6: Training probes "
        f"(3 configs x {len(PROBE_SEEDS)} seeds x {EPOCHS} epochs) ...",
        flush=True,
    )

    configs = [
        ("htgn_only", htgn_tr, lbl_htgn_tr, htgn_te, lbl_htgn_te, 256),
        ("bert_only", bert_tr, lbl_bert_tr, bert_te, lbl_bert_te, 768),
        ("fusion", fuse_tr, lbl_fuse_tr, fuse_te, lbl_fuse_te, 768),
    ]

    results: dict[str, list[float]] = {name: [] for name, *_ in configs}

    for cfg_name, feat_tr, lbl_tr, feat_te, lbl_te, idim in configs:
        print(f"[14.5]   --- Config: {cfg_name} (input_dim={idim}) ---", flush=True)
        for seed in PROBE_SEEDS:
            f1 = _train_eval_probe(
                feat_train=feat_tr,
                lbl_train=lbl_tr,
                feat_test=feat_te,
                lbl_test=lbl_te,
                input_dim=idim,
                seed=seed,
                config_name=cfg_name,
                device=device,
            )
            results[cfg_name].append(f1)
            print(f"[14.5]     seed={seed} -> F1={f1:.4f}", flush=True)

    # -----------------------------------------------------------------------
    # 7. Per-TTP F1 (informational, RFC-14.5-7 tightening)
    # -----------------------------------------------------------------------
    print("[14.5] Step 7: Computing per-TTP F1 (informational) ...", flush=True)

    def _per_ttp_for_config(
        feat_te_arg: torch.Tensor,
        lbl_te_arg: torch.Tensor,
        idim: int,
        cfg_name: str,
    ) -> dict[str, float]:
        """Compute per-TTP F1 using seed=42 trained probe."""
        from loghetero.models.heads.probe_classifier import ProbeClassifier, ProbeConfig

        if idim == 256:
            pcfg = ProbeConfig.HTGN_ONLY
        elif cfg_name == "bert_only":
            pcfg = ProbeConfig.BERT_ONLY
        else:
            pcfg = ProbeConfig.FUSION
        torch.manual_seed(42)
        mdl = ProbeClassifier(config=pcfg, input_dim=idim).to(device)
        opt = torch.optim.Adam(mdl.parameters(), lr=LR)
        crit = nn.BCEWithLogitsLoss()
        # Quick retrain with seed=42 for reproducible per-TTP report.
        feat_map = {"htgn_only": htgn_tr, "bert_only": bert_tr, "fusion": fuse_tr}
        lbl_map = {"htgn_only": lbl_htgn_tr, "bert_only": lbl_bert_tr, "fusion": lbl_fuse_tr}
        feat_tr_d = feat_map[cfg_name].to(device)
        lbl_tr_d = lbl_map[cfg_name].float().to(device)
        mdl.train()
        for _ep in range(EPOCHS):
            opt.zero_grad()
            lg = mdl(feat_tr_d).squeeze(-1)
            ls = crit(lg, lbl_tr_d)
            ls.backward()
            opt.step()
        return _compute_per_ttp_f1(
            test_events_labeled=test_ev,
            template_ids=template_ids,
            feat_test=feat_te_arg,
            lbl_test=lbl_te_arg,
            model=mdl,
            device=device,
        )

    per_ttp_htgn = _per_ttp_for_config(htgn_te, lbl_htgn_te, 256, "htgn_only")
    per_ttp_bert = _per_ttp_for_config(bert_te, lbl_bert_te, 768, "bert_only")
    per_ttp_fuse = _per_ttp_for_config(fuse_te, lbl_fuse_te, 768, "fusion")

    # -----------------------------------------------------------------------
    # 8. Aggregate F1 statistics + gate evaluation
    # -----------------------------------------------------------------------
    import numpy as np

    htgn_f1s = np.array(results["htgn_only"])
    bert_f1s = np.array(results["bert_only"])
    fuse_f1s = np.array(results["fusion"])

    htgn_mean = float(np.mean(htgn_f1s))
    bert_mean = float(np.mean(bert_f1s))
    fuse_mean = float(np.mean(fuse_f1s))

    htgn_std = float(np.std(htgn_f1s, ddof=1)) if len(htgn_f1s) > 1 else 0.0
    bert_std = float(np.std(bert_f1s, ddof=1)) if len(bert_f1s) > 1 else 0.0
    fuse_std = float(np.std(fuse_f1s, ddof=1)) if len(fuse_f1s) > 1 else 0.0

    # Double-condition gate.
    lift = fuse_mean - htgn_mean
    # Paired t-test: fusion vs HTGN-only per-seed F1.
    _t_stat, p_val = stats.ttest_rel(fuse_f1s, htgn_f1s)
    p_val = float(p_val)
    fusion_bert_delta = fuse_mean - bert_mean

    gate1_pass = lift >= GATE1_LIFT_THRESHOLD
    gate2_pass = p_val < GATE2_PVAL_THRESHOLD
    gate3_pass = fusion_bert_delta > GATE3_DELTA_THRESHOLD
    all_pass = gate1_pass and gate2_pass and gate3_pass

    std_warning = ""
    if htgn_std > 0.05 or bert_std > 0.05 or fuse_std > 0.05:
        std_warning = " [WARNING: F1 std > 0.05 detected - consider RFC about scale]"

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    elapsed = time.perf_counter() - t0_total
    print("\n" + "=" * 75, flush=True)
    print("Phase 4 / Checkpoint 14.5 Anomaly Probe Report", flush=True)
    print("=" * 75, flush=True)
    print(flush=True)
    print("Protocol Summary:", flush=True)
    print(
        f"  - 5 TTP x {EVENTS_PER_TTP} attack events = {5*EVENTS_PER_TTP} total attack", flush=True
    )
    print(f"  - {NUM_BENIGN} matched benign events", flush=True)
    print(
        f"  - Total {EVENTS_TOTAL} events, 80/20 split: "
        f"{int(EVENTS_TOTAL*TRAIN_RATIO)} train / {int(EVENTS_TOTAL*0.2)} test",
        flush=True,
    )
    print(f"  - 4 seeds: {PROBE_SEEDS}, {EPOCHS} epochs each", flush=True)
    print(f"  - Device: {device}, elapsed: {elapsed:.1f}s", flush=True)
    print(flush=True)

    print("Aggregate F1 (mean +/- std across 4 seeds):", flush=True)
    print(
        f"  HTGN-only:  {htgn_mean:.4f} +/- {htgn_std:.4f}  "
        f"seeds={[f'{v:.4f}' for v in htgn_f1s.tolist()]}",
        flush=True,
    )
    print(
        f"  BERT-only:  {bert_mean:.4f} +/- {bert_std:.4f}  "
        f"seeds={[f'{v:.4f}' for v in bert_f1s.tolist()]}",
        flush=True,
    )
    print(
        f"  Fusion:     {fuse_mean:.4f} +/- {fuse_std:.4f}  "
        f"seeds={[f'{v:.4f}' for v in fuse_f1s.tolist()]}",
        flush=True,
    )
    if std_warning:
        print(f"  {std_warning}", flush=True)
    print(flush=True)

    print("Per-TTP F1 (informational -- does not affect gate):", flush=True)
    print(f"  {'TTP':<15} {'HTGN-only':>10} {'BERT-only':>10} {'Fusion':>10}", flush=True)
    for ttp_id in template_ids:
        h = per_ttp_htgn.get(ttp_id, float("nan"))
        b = per_ttp_bert.get(ttp_id, float("nan"))
        f = per_ttp_fuse.get(ttp_id, float("nan"))
        print(f"  {ttp_id:<15} {h:>10.4f} {b:>10.4f} {f:>10.4f}", flush=True)
    print(flush=True)

    print("Double-Condition Gate:", flush=True)
    g1_str = "PASS" if gate1_pass else "FAIL"
    g2_str = "PASS" if gate2_pass else "FAIL"
    g3_str = "PASS" if gate3_pass else "FAIL"
    print(
        f"  Gate 1: fusion vs HTGN-only lift = {lift:+.4f} (>= {GATE1_LIFT_THRESHOLD}) -> {g1_str}",
        flush=True,
    )
    print(
        f"  Gate 2: paired t-test p = {p_val:.4f} (< {GATE2_PVAL_THRESHOLD}) -> {g2_str}",
        flush=True,
    )
    print(
        f"  Gate 3: fusion - BERT-only = {fusion_bert_delta:+.4f} (> {GATE3_DELTA_THRESHOLD}) -> {g3_str}",
        flush=True,
    )
    print(flush=True)

    if all_pass:
        print("Overall: DONE -- all 3 gate conditions passed.", flush=True)
    else:
        failures = []
        if not gate1_pass:
            failures.append(f"Gate 1 lift={lift:+.4f} < {GATE1_LIFT_THRESHOLD}")
        if not gate2_pass:
            failures.append(f"Gate 2 p={p_val:.4f} >= {GATE2_PVAL_THRESHOLD}")
        if not gate3_pass:
            failures.append(f"Gate 3 delta={fusion_bert_delta:+.4f} <= {GATE3_DELTA_THRESHOLD}")
        print(f"Overall: NEEDS_CONTEXT -- gate failure(s): {'; '.join(failures)}", flush=True)
        print("DO NOT RELAX THRESHOLDS. Architecture-level RFC required.", flush=True)

    print("=" * 75, flush=True)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
