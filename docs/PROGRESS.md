# LogHetero — Project Progress（单一真相源）

> **新会话起步**：如果你是新接手本项目的 AI 代理或合作者，本文件是你的入口。读完它你应对项目当前阶段、已生效决策、下一步要做什么、如何复现都有完整认知。然后按需查 `docs/design_decisions.md`（宪法）/ `docs/CHECKPOINT_LOG.md`（演进 audit trail）/ `docs/known_issues.md`（已知问题）。本文件每完成一个 checkpoint 整体覆写一次，**绝不允许落后于实际状态**。

---

## 1. 项目当前阶段与 Checkpoint

- **当前 Phase**：Phase 4（双向跨模态融合，**创新点 1 第二部分**）— **进行中（1/4 sub-checkpoints 已完成）**
- **最新 Checkpoint**：Checkpoint 11（Phase 4 入口前置 RFC + Phase 3 sanity AUC re-validation）— 已通过（**informationally complete**，详见下方 §4 决策清单与 §6 active 待回答问题章节）
- **Phase 4 进度**：Checkpoint 11（前置 RFC 消化 + 11.1 Option B benign-only 决议 + 11.2-γ-1 BERT informational null finding）已 done。下一个：Checkpoint 12（双向跨模态注意力实施）→ Checkpoint 13（改造 MLM 集成）→ Checkpoint 14（端到端集成 + smoke test）→ tag `v0.4-fusion`。
- **已完成 Phase**：Phase 0（tag `v0.0-scaffold`）+ Phase 1（tag `v0.1-data`）+ Phase 2（tag `v0.2-bert`）+ Phase 3（tag `v0.3-htgn`，conditional pass 后变更为 informationally complete via Checkpoint 11.2-γ-1）

## 2. 最新 Checkpoint Commit

- **Hash**：（本 commit；Checkpoint 11 单 commit 含 11.1 Option B 三条件 docs **已在 commit `cae7216` 落档** + 11.2-γ-1 决议 + 4 ablation artifacts + 决策 4.2 footnote + PROGRESS / CHECKPOINT_LOG 同步）
- **Message**：`feat(phase4): Phase 4 / Checkpoint 11 RFC resolution + sanity null finding (γ-1)`
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
| 8 | `246ee95` | Q-1 mini | feat(parsers): add user-logon dispatch for 4 EventIDs |
| 9 | `ba456a0` | checkpoint 4 | feat(window): Phase 1.5 / Checkpoint 4 events-per-window density artifact |
| 10 | `f67d845` | docs | docs(constitution): finalize window granularity (1.0h) + add decision 9 on sample unit |
| 11 | `4b8dd6a` | checkpoint 5 | feat(datamodule): Phase 1.6 / Checkpoint 5 LogHetero DataModule |
| 12 | `b606a5c` | Q-2 mini | feat(scripts): persist synonym init regression check |
| 13 | `a620de9` | docs | docs(handoff): introduce PROGRESS.md and CHECKPOINT_LOG.md |
| 14 | `5bafb4e` | merge / tag v0.1-data | merge: Phase 1 data pipeline (10 commits) |
| 15 | `227bfcf` | checkpoint 6 | feat(bert): Phase 2 BERT text encoder + sanity check |
| 16 | `5002aab` | docs | docs(known_issues): Phase 12 论文素材 BERT cos-sim finding |
| 17 | `d4681ad` | merge / tag v0.2-bert | merge: Phase 2 BERT text encoder integration |
| 18 | `6a1f39a` | checkpoint 7 | feat(htgn): Phase 3 / Checkpoint 7 Time2Vec + HGT layer |
| 19 | `ef31e6f` | checkpoint 8 | feat(htgn): Phase 3 / Checkpoint 8 HeteroTGNMemory |
| 20 | `e3a2315` | checkpoint 9 | feat(htgn): Phase 3 / Checkpoint 9 HTGN main module assembly |
| 21 | `0d3c72a` | docs | docs(known_issues): elaborate Phase 7 TGN msg_store fix paths + VRAM batch sanity gate |
| 22 | `b9361ed` | docs | docs(known_issues): Checkpoint 10 RFC + cross-type TGN src memory bug + Phase 4 / 7 待办 |
| 23 | `d0efbdf` | checkpoint 10 | feat(htgn): Phase 3 / Checkpoint 10 HTGN validation (Task A pass; Task B conditional pass AUC 0.8144) |
| 24 | `98b3c1a` | merge / tag v0.3-htgn | merge: Phase 3 HTGN encoder (4 sub-checkpoints) — conditional pass |
| 25 | `901ebbd` | docs | docs(known_issues): Checkpoint 10 lesson (data-following over RFC-form-following) |
| 26 | `cae7216` | docs / checkpoint 11.1 | docs(constitution): Checkpoint 11.1 Option B with three conditions + Phase 12 BERT root-cause investigation entry |
| 27 | `<this commit>` | checkpoint 11.2-γ-1 | feat(phase4): Phase 4 / Checkpoint 11 RFC resolution + sanity null finding (γ-1) |

## 4. 已生效的决策清单（决策 1–9 + Phase 3 / Phase 4 设计偏离 + 经验启发式校准）

详见 `docs/design_decisions.md` + `docs/known_issues.md` 完整论证。

1. **决策 1** — 不复现任何已有论文作为方法主线
2. **决策 2** — 两条创新点精确措辞 + verified 先验工作
3. **决策 3** — 双盲匿名化策略
4. **决策 4** — 工程不变量；4.2 footnote (2026-05-06)：**Checkpoint 11.2-γ-1 决议**——HTGN link prediction sanity 是 structure-determined 任务，BERT 跨模态融合的真实 evaluation 推到 Phase 7-8 anomaly detection；原 Phase 4 BERT 重测 0.88 hard gate **撤销**；详见 决策 4.2 footnote ‡
5. **决策 5** — DARPA TC E3 CDM → 5 类节点映射
6. **决策 6** — Leave-one-attack-out + 时间窗 final = 1.0h
7. **决策 7** — AI 协作披露策略
8. **决策 8** — 孤立节点保留策略
9. **决策 9** — 训练样本单位 = (target_event, subgraph_at_target, label) 三元组；footnote (2026-05-06)：**Checkpoint 11.1 RFC Option B**——Phase 4 用 mixed pretraining 数据作为 unverified-impact baseline，Phase 7 切 benign-only，Phase 11 ablation 必须含 mixed vs benign 二档对比 + 3pp Phase 8 anomaly F1 阈值触发论文叙事调整

**Phase 3 设计偏离记录**（5 条，`docs/known_issues.md`）：(1) Checkpoint 7 HGTConv edge_attr + Option C；(2) Checkpoint 9 γ_k 仅作用残差 + ns-direct timestamp；(3) Checkpoint 10 Task B Option C（benign-only 放宽至 mixed）；(4) Checkpoint 10 HeteroTGNMemory 跨类型 src memory bug + workaround；(5) Checkpoint 10 Task B AUC 0.8144 borderline → Option A conditional pass（**已 informationally complete via 11.2-γ-1**）。

**Phase 4 设计偏离记录**（1 条新增，`docs/known_issues.md`）：(6) Checkpoint 11.2-γ-1：4 档 BERT 集成 ablation 全部 0.811-0.815 区间无统计差异 → link prediction 是 structure-determined 任务，跨模态 evaluation 推到 Phase 7-8 anomaly detection；4-row ablation 数字保留为 Phase 12 论文 negative-result-as-positive-contribution 素材。

**经验启发式校准记录**（`docs/known_issues.md`）：(a) 早期 GNN [10, 10000] events/window 不适用；(b) Spec 与代码常数同步纪律（Checkpoint 7）；(c) PyG TGNMemory msg_store 跨 batch + train→eval transition 双坑（Checkpoint 9 + 10）；(d) Borderline RFC 期间数字与最终 commit 数字不一致时跟随实测（Checkpoint 10）。

## 5. 下一步预期工作

**Checkpoint 12（Phase 4.1 双向跨模态注意力，预计 3 天）**：实施 `src/loghetero/models/fusion/cross_attention.py`，按 v3 prompt §6 Phase 4 推进。设计参数预先锁定：

- 双向独立参数（Text→Graph 与 Graph→Text 各自独立 attention 参数不共享）
- text token 768 维与 graph node 256 维之间通过线性投影对齐到统一 attention dim
- attention head 数 8（与 BERT-base 对齐）
- BERT hidden state 暴露通过 output_hidden_states=True，融合层选第 3 / 6 / 9 / 12 层共 4 个融合点
- Attention mask 严格限制为"每条 text token 只能 attend 到与其所在日志事件直接相关的图节点"，验证可行后再考虑放宽

**Checkpoint 12 报告必须包含**：跨模态 attention forward shape 测试、attention 权重在一个具体案例上的可视化（notebook 里 case study）、端到端梯度回传 sanity。

**之后**：Checkpoint 13（Phase 4.2 改造 MLM 任务集成，2 天）→ Checkpoint 14（Phase 4 整体集成 + 端到端 forward smoke test，1.5 天）→ tag `v0.4-fusion`。

**Phase 4 整体目标变更（2026-05-06）**：Checkpoint 11.2-γ-1 决议把 AUC-style 单点验证撤销，Phase 4 主交付物是"跨模态融合架构落地且 forward 不报错且梯度回传正常"，深层验证留给 Phase 7-8 联合预训练 + anomaly detection 阶段统一进行。

## 6. 当前 Active 待回答问题

无（Checkpoint 11.1 Option B + Checkpoint 11.2-γ-1 双决议落地完成；Phase 4 待办::Phase 3 sanity AUC re-validation 标 informationally complete；Checkpoint 12 launch spec 由 user 在新会话窗口中下达）。

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

# Phase 3 Checkpoint 10 验证（v0.3-htgn tag）
uv run python scripts/checkpoint10_task_a.py --seed 42                              # Task A: loss 0.034 / acc 100%
uv run python scripts/checkpoint10_task_b.py --seed-list 1,7,42,100                 # Task B baseline: AUC 0.8144 ± 0.0068

# Phase 4 Checkpoint 11.2 BERT ablation 4 档（informationally complete via γ-1 决议）
uv run python scripts/checkpoint10_task_b.py --use-bert-features \
    --bert-context-mode entity_identifier --bert-pooling cls \
    --seed-list 1,7,42,100                                                          # [CLS] failed: AUC 0.8126 ± 0.0164
uv run python scripts/checkpoint10_task_b.py --use-bert-features \
    --bert-context-mode entity_event_context --bert-pooling mean \
    --seed-list 1,7,42,100                                                          # β canonical: AUC 0.8147 ± 0.0109

# Phase 4 Checkpoint 12+ 需 user 在新会话下达 launch spec
```
