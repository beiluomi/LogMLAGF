# LogHetero

> HTGN-LM Co-Pretraining for APT Detection on Provenance Graphs.

LogHetero is an independent research framework for APT (Advanced Persistent Threat) anomaly detection on system provenance graphs. The work targets top-tier security and software-engineering venues.

## Two Core Innovations

### 1. HTGN-LM Co-Pretraining *(Phases 3–4, 7)*

> The first framework, for provenance-graph APT detection, that deeply fuses heterogeneous + temporal GNNs and a language model in the **pretraining stage** through bidirectional cross-modal attention.

The provenance graph is modeled as a heterogeneous graph (process / file / socket / network / user). The graph encoder is HGT + Time2Vec edge-time encoding + TGN-style node memory ("HTGN"). Text tokens and graph nodes mutually attend to each other through bidirectional cross-modal attention layers injected into BERT (layers 3 / 6 / 9 / 12).

### 2. RAPA-GTCL: Real-Attack-Pattern-Augmented Graph–Text Contrastive Learning *(Phases 5–6, 7)*

> The first framework to use MITRE ATT&CK templates as **graph-augmentation samples** paired with a **graph–text contrastive objective** during the pretraining stage.

≥20 ATT&CK TTPs (covering ≥8 of the 12 tactics) are encoded as executable subgraph templates and injected into benign provenance graphs to synthesize realistic anomalies. The InfoNCE-style graph–text contrastive loss is trained with a three-class negative mix: 50% in-batch random + 30% in-window hard + 20% RAPA-synthetic.

The two innovations are wired into a single end-to-end joint pretraining objective; ablation matrix B0–B6 toggles HTGN and RAPA-GTCL independently to attribute their respective contributions.

## Implementation Progress Tracker

- [x] **Phase 0** — Scaffold *(infra)*
- [x] **Phase 1** — Data pipeline (ATLAS + DARPA TC E3 → heterogeneous temporal tensors) *(infra)*
- [ ] **Phase 2** — Text-encoder integration (`bert-base-uncased`, frozen by default) *(infra)*
- [ ] **Phase 3** — HTGN encoder ⭐️ *(Innovation 1, part 1)*
- [ ] **Phase 4** — Bidirectional cross-modal fusion ⭐️ *(Innovation 1, part 2)*
- [ ] **Phase 5** — MITRE ATT&CK template library (≥20 TTPs) ⭐️ *(Innovation 2, part 1)*
- [ ] **Phase 6** — Graph–Text Contrastive Learning ⭐️ *(Innovation 2, part 2)*
- [ ] **Phase 7** — LogHetero joint pretraining
- [ ] **Phase 8** — Anomaly-detection fine-tune + 7 SOTA baselines
- [ ] **Phase 9** — DARPA TC E3 cross-dataset generalization
- [ ] **Phase 10** — Log compression *(deferred to rebuttal)*
- [ ] **Phase 11** — Ablation matrix (B0–B6)
- [ ] **Phase 12** — Paper-ready release + double-blind anonymization

⭐️ marks phases that directly implement one of the two core innovations.

## 新会话起步指引 (For new AI agents / collaborators)

If you are a new AI agent or human collaborator picking up this project, **read these documents in order before doing anything else**:

1. [`docs/PROGRESS.md`](docs/PROGRESS.md) — single source of truth for the project's current Phase / Checkpoint, latest checkpoint commit, full commit chain, active decisions (1–N), what's next, and one-shot reproduction commands. **Read this first.** Pasting this file into a new chat session brings any new agent up to speed in seconds without manual re-introduction.
2. [`docs/design_decisions.md`](docs/design_decisions.md) — the project constitution. All implementation must respect these decisions; modifying any of them requires an RFC PR reviewed by the project owner.
3. [`docs/CHECKPOINT_LOG.md`](docs/CHECKPOINT_LOG.md) — append-only audit trail. Every completed checkpoint has one entry covering deliverables, metrics, key decisions resolved (including user-override / agent-pushback events), and triggered known-issues entries. Phase 12 paper-writing will mine this log for the Methodology / Limitation timeline.
4. [`docs/known_issues.md`](docs/known_issues.md) — known issues, Phase-specific TODOs, and historical revisions (e.g. the Phase 1.2 修订记录 explaining why a -8k success delta was a bug fix not data loss).

After reading 1+2 you have enough context to start work; 3+4 are reference. **From Phase 2 onwards, every checkpoint commit MUST update PROGRESS.md (overwrite) AND append to CHECKPOINT_LOG.md** — a checkpoint that fails to do so does not pass sanity check.

### 2026-05-06 会话切换标记 (session switch marker)

**This handoff marker exists because the previous chat session ended at Checkpoint 11 closure (v0.3-htgn tag was set, Phase 4 was started, and Option γ-1 for Checkpoint 11.2 was decided). The new session you (a new AI agent) are starting in must follow this exact onboarding sequence before doing any feature work, to avoid losing the complex Phase 3-4 boundary context.**

**Five-step reading sequence (mandatory)**:

1. Read [`docs/PROGRESS.md`](docs/PROGRESS.md) in full — covers current Phase 4 progress (1/4 sub-checkpoints done), the full commit chain through `c9796a8`, the active 9 design decisions including the **two new 2026-05-06 footnotes (decision 4.2 γ-1 + decision 9 Option B)**, the next-step Checkpoint 12 outline, and reproducibility commands.
2. Read [`docs/design_decisions.md`](docs/design_decisions.md) — the constitution, all 9 decisions. **Pay extra attention to decision 4.2 footnote ‡ (Checkpoint 11.2-γ-1) and decision 9 footnote (Checkpoint 11.1 Option B)** because these two 2026-05-06 footnotes redefine Phase 4's scope and pretraining-data semantics.
3. Read [`docs/known_issues.md`](docs/known_issues.md) — specifically the `Phase 4 待办` (both items now marked completed/resolved with closure annotations linking back to Checkpoint 11.1 / 11.2-γ-1) + `Phase 7 待办` (three preset items: TGN msg_store fix; mixed-vs-benign quick A/B; **new BERT-fused-attention vs HTGN-only quick A/B**) + `Phase 11 消融扩展` (B7-α/β cells preset) + `Phase 12 论文素材` (especially the 4-row ablation table on Phase 3 sanity AUC evolution + the BERT integration root-cause investigation entry; both are paper Methods chapter material).
4. Read [`docs/CHECKPOINT_LOG.md`](docs/CHECKPOINT_LOG.md) **last three entries** — Checkpoint 10 (Phase 3 conditional pass), Checkpoint 11.1 (already in commit `cae7216`, Option B + three conditions), and Checkpoint 11.2-γ-1 (the latest, BERT informational null finding + Phase 4 scope reframe).
5. After completing steps 1-4, **send the project owner a single-sentence summary** as your first reply (in Chinese, this owner's preference) covering: (a) current project Phase + last checkpoint, (b) the most recent decision and why it was non-trivial, (c) what the next checkpoint should produce. The owner will validate this summary's correctness as the **handoff completeness gate** before issuing the Checkpoint 12 launch spec. **Do NOT begin Checkpoint 12 implementation work until your summary is approved.**

**Common misunderstanding traps that fail the handoff gate**:

- Describing Phase 3 as "passed" — wrong. It's "conditional pass redefined as informationally complete via Checkpoint 11.2-γ-1".
- Describing the BERT null result as "BERT integration bug" — wrong. The integration code is verified correct; the finding is that the link prediction task itself is structure-determined, so BERT input-feature injection cannot help regardless of how it's wired.
- Describing the original 0.88 hard gate as "still pending" — wrong. It is **revoked** because the premise it was based on was disproved (literature on +0.05-0.10 lift was for sentence-classification tasks, not structure-determined link prediction).
- Describing Phase 4 as "needs to verify cross-modal lift on link prediction" — wrong. Phase 4's scope changed: cross-modal evaluation moves to Phase 7-8 anomaly detection where attack events have semantic anomaly signatures.

If your one-sentence summary contains any of these traps, the project owner will ask you to reread and resummarize before any Checkpoint 12 work begins.

## Datasets and Baselines

**Datasets.** ATLAS (10 scenarios) + DARPA TC E3 (CADETS / THEIA / TRACE / FiveDirections); Engagement 5 stretch.

**Anomaly-detection baselines (post-2020 top-tier).** AirTag (USENIX Security '23) · KAIROS (S&P '24) · MAGIC (USENIX Security '24) · FLASH (NDSS '24) · PROGRAPHER (USENIX Security '23) · Unicorn (NDSS '20) · ProvDetector (NDSS '20).

**Compression baselines (secondary).** CPR (CCS '16) · NodeMerge (CCS '18) · LogShrink (ICSE '24).

## Reproduce (Phase 0 sanity)

```bash
git clone https://github.com/beiluomi/LogMLAGF.git
cd LogMLAGF
pip install --user uv
export PATH="$HOME/.local/bin:$PATH"
uv sync --extra dev
make lint test hello
```

Phase 1+ reproduction recipes will land in [`docs/reproduce.md`](docs/reproduce.md).

## Tech Stack

Python 3.10 · PyTorch 2.1 + CUDA 12.x · PyTorch Lightning 2.x · PyTorch Geometric 2.4 · Transformers 4.40+ + PEFT 0.10 · Hydra 1.3+ · Weights & Biases · uv · DVC.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system architecture (Phase 12)
- [`docs/design_decisions.md`](docs/design_decisions.md) — locked-in engineering decisions (the constitution)
- [`docs/reproduce.md`](docs/reproduce.md) — reproduction guide (Phase 12)
- [`docs/ablation_plan.md`](docs/ablation_plan.md) — ablation matrix B0–B6 (Phase 11)
- [`docs/attack_templates.md`](docs/attack_templates.md) — MITRE ATT&CK template registry (Phase 5)
- [`docs/known_issues.md`](docs/known_issues.md) — known issues and environment notes

## License

MIT. See [`LICENSE`](LICENSE).
