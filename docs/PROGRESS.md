# LogHetero — Project Progress（单一真相源）

> **新会话起步**：如果你是新接手本项目的 AI 代理或合作者，本文件是你的入口。读完它你应对项目当前阶段、已生效决策、下一步要做什么、如何复现都有完整认知。然后按需查 `docs/design_decisions.md`（宪法）/ `docs/CHECKPOINT_LOG.md`（演进 audit trail）/ `docs/known_issues.md`（已知问题）。本文件每完成一个 checkpoint 整体覆写一次，**绝不允许落后于实际状态**。

---

## 1. 项目当前阶段与 Checkpoint

- **当前 Phase**：Phase 3（HTGN 异构时序图神经网络，**创新点 1 核心**）— **完成（4/4 sub-checkpoints done，conditional pass）**
- **最新 Checkpoint**：Checkpoint 10（Phase 3.5+3.6 HTGN validation）— Task A hard-gate pass + Task B **conditional pass** (AUC 0.8144 ± 0.0068 across 4 seeds, 0.85 硬门槛 provisionally relaxed pending Phase 4 BERT 集成后重测)
- **Phase 3 进度**：Checkpoint 7 (Time2Vec + HGT layer Option-C) + Checkpoint 8 (HeteroTGNMemory) + Checkpoint 9 (HTGN 主模块组装) + Checkpoint 10 (验证 sanity + 链路预测) 全部 done。**待 v0.3-htgn tag 收尾**（本 commit 包含 tag 操作）。
- **已完成 Phase**：Phase 0（tag `v0.0-scaffold`）+ Phase 1（tag `v0.1-data`）+ Phase 2（tag `v0.2-bert`）+ Phase 3（tag `v0.3-htgn`，本 commit）

## 2. 最新 Checkpoint Commit

- **Hash**：（本 commit；Checkpoint 10 单 commit 含 Task A 玩具图节点分类 + Task B ATLAS 链路预测 4-seed 聚合 + 三处 known_issues 更新 + PROGRESS / CHECKPOINT_LOG 同步 + 之后 merge to main + tag v0.3-htgn）
- **Message**：`feat(htgn): Phase 3 / Checkpoint 10 HTGN validation (Task A pass; Task B conditional pass AUC 0.8144)`
- **Date**：2026-05-06

## 3. 累计 Commit 链（按时间顺序，到当前 commit）

| # | Hash | Type | Message |
|---|---|---|---|
| 1 | `d9ff51e` | scaffold | chore(scaffold): initialize LogHetero project structure |
| 2 | `d66450c` | docs | docs(constitution): add decisions 5-7 + ATLAS validation + split CI |
| 3 | `008cbff` | docs | docs(citations): verified prior work for decision 2 (drop hallucinated PLATO) |
| 4 | `aa184f4` | merge / tag v0.0-scaffold | merge: Phase 0 scaffold + design decisions constitution |
| 5 | `79f78be` | checkpoint 1 | feat(data): Phase 1.1 ATLAS download + integrity manifest |
| 6 | `c224eb8` | checkpoint 2 | feat(parsers): Phase 1.2 ATLAS + DARPA E3 CDM parser implementation |
| 7 | `40dbbca` | checkpoint 3 | feat(graph): Phase 1.3+1.4 cleaner + tokenizer + heterogeneous graph builder |
| 8 | `246ee95` | Q-1 mini | feat(parsers): add user-logon dispatch for 4 EventIDs (4624/4625/4672/4648) |
| 9 | `ba456a0` | checkpoint 4 | feat(window): Phase 1.5 / Checkpoint 4 events-per-window density artifact |
| 10 | `f67d845` | docs | docs(constitution): finalize window granularity (1.0h) + add decision 9 on sample unit |
| 11 | `4b8dd6a` | checkpoint 5 | feat(datamodule): Phase 1.6 / Checkpoint 5 LogHetero DataModule |
| 12 | `b606a5c` | Q-2 mini | feat(scripts): persist synonym init regression check as standing script |
| 13 | `a620de9` | docs | docs(handoff): introduce PROGRESS.md and CHECKPOINT_LOG.md |
| 14 | `5bafb4e` | merge / tag v0.1-data | merge: Phase 1 data pipeline (10 commits incl. handoff infra) |
| 15 | `227bfcf` | checkpoint 6 | feat(bert): Phase 2 BERT text encoder + sanity check |
| 16 | `5002aab` | docs | docs(known_issues): add Phase 12 论文素材 entry for BERT cos-sim finding |
| 17 | `d4681ad` | merge / tag v0.2-bert | merge: Phase 2 BERT text encoder integration (1 commit) |
| 18 | `6a1f39a` | checkpoint 7 | feat(htgn): Phase 3 / Checkpoint 7 Time2Vec + HGT layer wrapper (Option-C residual per RFC) |
| 19 | `ef31e6f` | checkpoint 8 | feat(htgn): Phase 3 / Checkpoint 8 HeteroTGNMemory (PyG TGNMemory composed per process/socket) |
| 20 | `e3a2315` | checkpoint 9 | feat(htgn): Phase 3 / Checkpoint 9 HTGN main module assembly |
| 21 | `0d3c72a` | docs | docs(known_issues): elaborate Phase 7 TGN msg_store fix paths + VRAM batch sanity gate; align skip reason |
| 22 | `b9361ed` | docs | docs(known_issues): record Checkpoint 10 RFC (Option C benign-only relax) + cross-type TGN src memory bug; add Phase 4 待办 + Phase 7 fix paths |
| 23 | `<this commit>` | checkpoint 10 | feat(htgn): Phase 3 / Checkpoint 10 HTGN validation (Task A pass; Task B conditional pass AUC 0.8144) |
| 24 | `<merge commit>` | merge / tag v0.3-htgn | merge: Phase 3 HTGN encoder (4 sub-checkpoints) — conditional pass |

## 4. 已生效的决策清单（决策 1–9 + Phase 3 设计偏离 + 经验启发式校准）

详见 `docs/design_decisions.md` + `docs/known_issues.md` 完整论证。

1. **决策 1** — 不复现任何已有论文作为方法主线
2. **决策 2** — 两条创新点精确措辞 + verified 先验工作
3. **决策 3** — 双盲匿名化策略
4. **决策 4** — 工程不变量；4.2 footnote：Phase 11 ablation B5 = `residual_alpha=0` + `tgn_memory.enabled=false` 双 yaml 开关
5. **决策 5** — DARPA TC E3 CDM → 5 类节点映射
6. **决策 6** — Leave-one-attack-out + 时间窗 final = 1.0h
7. **决策 7** — AI 协作披露策略
8. **决策 8** — 孤立节点保留策略
9. **决策 9** — 训练样本单位 = (target_event, subgraph_at_target, label) 三元组

**Phase 3 设计偏离记录**（`docs/known_issues.md`）：四条主要设计偏离构成完整 audit trail：
1. Checkpoint 7 — HGTConv edge_attr 接口限制 + Option C 残差通道决议
2. Checkpoint 9 — γ_k 仅作用 Option-C 残差通道（不衰减 HGT 主路径）+ ns-direct long timestamp（拒绝小时归一化）
3. Checkpoint 10 — Task B "完全 benign 子图" Option C 决议（放宽约束 + Phase 4 重审）
4. Checkpoint 10 — HeteroTGNMemory 跨类型 src 索引语义 bug + workaround（max-across-types num_nodes_per_type） + Phase 7 三 fix paths
5. Checkpoint 10 — Task B AUC 0.8144 borderline → Option A conditional pass（四支柱锁死 + Phase 4 重测 commitment）

**经验启发式校准记录**（`docs/known_issues.md`）：(a) 早期 GNN [10, 10000] events/window heuristic 不适用；(b) **Spec 与代码常数同步纪律**——Checkpoint 7 lesson；(c) **PyG TGNMemory msg_store 跨 batch 持有梯度** + **train→eval transition 在 no_grad 外触发 _update_memory** 双坑（Checkpoint 9 + 10 发现）。

## 5. 下一步预期工作

**Phase 4（跨模态注意力与联合预训练）即将启动**。Phase 4 第一个 commit 前必须开两个 RFC（已工程化在 known_issues.md "Phase 4 待办"）：

1. **Pretraining 数据 benign-only 约束重审**（Checkpoint 10 Option C 决议触发的）：(a) 跨模态联合预训练阶段是否需要纯 benign 数据；(b) 如需，是否依赖 Phase 8 真实 label loader 才能切；(c) 如 Phase 8 滞后是否走 ATLAS 论文 timeline 启发式 stop-gap。三选一拍板写进 docs。

2. **Phase 3 sanity AUC re-validation**（Checkpoint 10 Option A 决议触发的）：用 `scripts/checkpoint10_task_b.py --use-bert-features --seed-list 1,7,42,100` 重测，4 seed 平均 AUC ≥ 0.88 是 Phase 4 第一个硬门槛。失败触发架构级 RFC，禁止再放过。

之后是 Phase 4 跨模态注意力实施（HTGN dst node embedding 作 query / BERT dst-node textual context embedding 作 key+value），双向。launch spec 待 user 拍板。

## 6. 当前 Active 待回答问题

无（Checkpoint 10 launch spec 全部参数已实现并测试，Option C + Option A 两个 RFC 决议已落地。Phase 4 launch spec 由 user 在 sanity check 通过后单独发布）。

## 7. 快速复现指令

```bash
# 一键环境
git clone https://github.com/beiluomi/LogMLAGF.git
cd LogMLAGF
pip install --user uv && export PATH="$HOME/.local/bin:$PATH"
uv sync --extra dev --extra ml      # ~5 min cold install

# 验证门
make lint test                       # ruff + mypy + pytest（非 integration），<10s
make integration-test                # pytest -m integration（含 BERT 加载，~60s）

# Phase 1 数据流水线复现（v0.1-data tag）
bash scripts/download_atlas.sh                          # ~2 min
uv run python scripts/verify_data_integrity.py
uv run python scripts/parse_atlas_all.py --workers 8    # ~40s
uv run python scripts/build_atlas_graphs.py --workers 8 # ~55s
uv run python scripts/build_window_density_histograms.py --workers 8
uv run python scripts/build_fold_stats_report.py
uv run python scripts/tokenizer_nn_sanity.py
uv run python scripts/check_synonym_init.py             # exit 0

# Phase 2 BERT 集成（v0.2-bert tag）
uv run python scripts/bert_sanity_check.py

# Phase 3 模块单元测试（v0.3-htgn tag）
uv run pytest tests/test_time2vec.py tests/test_hgt_layer.py tests/test_tgn_memory.py tests/test_htgn.py -v

# Phase 3 HTGN 性能 benchmark（real ATLAS S1, 128-node K-hop subgraph, RTX 4090）
uv run python scripts/bench_htgn.py
# 输出 data/htgn_bench.json：forward median ~30ms / params 4.94M / VRAM 0.19 GB per-sample

# Phase 3 Checkpoint 10 验证（v0.3-htgn tag）
# Task A — 玩具异构图节点分类 sanity（Hard-gate pass: loss 0.034 / acc 100%）
uv run python scripts/checkpoint10_task_a.py --seed 42

# Task B — ATLAS M3_h2 链路预测，4 seed 聚合（Conditional pass: AUC 0.8144 ± 0.0068, 4 seed mean）
uv run python scripts/checkpoint10_task_b.py --seed-list 1,7,42,100
# 输出 data/checkpoint10_taskB_summary.json (4-seed aggregated)
# 输出 data/processed/checkpoint10_taskB_loss_auc_seed{N}.png + roc_seed{N}.png (gitignored)

# Phase 4 入口 sanity AUC re-validation（待 Phase 4 实施 BERT feature 接线）
# uv run python scripts/checkpoint10_task_b.py --use-bert-features --seed-list 1,7,42,100
# 当前 raise NotImplementedError，引用 known_issues.md::Phase 4 待办::Phase 3 sanity AUC re-validation
```
