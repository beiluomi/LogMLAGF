# LogHetero Ablation Plan (Phase 11)

The ablation matrix is designed so that each row attributes a measurable contribution to one component of the two core innovations. Every row is run with **3 random seeds**; we report F1 / Precision / Recall / FPR (mean ± std) and run a paired *t*-test against B0 (LogHetero full) for significance.

| ID | Text encoder | Graph encoder       | Fusion       | Augmentation | Contrastive | Validates                |
|----|--------------|---------------------|--------------|--------------|-------------|--------------------------|
| B0 | BERT frozen  | HTGN                | Cross-attn   | RAPA         | GTCL        | **LogHetero (full)**     |
| B1 | BERT frozen  | HTGN                | Cross-attn   | RAPA         | —           | GTCL contribution        |
| B2 | BERT frozen  | HTGN                | Cross-attn   | Random       | GTCL        | RAPA contribution        |
| B3 | BERT frozen  | HTGN                | Concat       | RAPA         | GTCL        | Cross-attn contribution  |
| B4 | BERT frozen  | Homogeneous GAT     | Cross-attn   | RAPA         | GTCL        | Heterogeneity contrib.   |
| B5 | BERT frozen  | HGT (no temporal)   | Cross-attn   | RAPA         | GTCL        | Temporal contribution    |
| B6 | BERT LoRA-4  | HTGN                | Cross-attn   | RAPA         | GTCL        | Text-encoder strategy    |

**Mapping to innovations.**

- B1, B2 → Innovation 2 (RAPA-GTCL) — together they isolate the contribution of GTCL and RAPA.
- B3, B4, B5 → Innovation 1 (HTGN-LM Co-Pretraining) — they isolate cross-modal fusion, heterogeneity, and temporality respectively.
- B6 → engineering choice (text-encoder freezing strategy).

Detailed Hydra configs land in `configs/experiment/` during Phase 11.
