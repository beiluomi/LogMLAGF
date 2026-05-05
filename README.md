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
- [ ] **Phase 1** — Data pipeline (ATLAS + DARPA TC E3 → heterogeneous temporal tensors) *(infra)*
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
