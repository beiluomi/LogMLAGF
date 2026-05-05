# LogHetero — Project Progress（单一真相源）

> **新会话起步**：如果你是新接手本项目的 AI 代理或合作者，本文件是你的入口。读完它你应对项目当前阶段、已生效决策、下一步要做什么、如何复现都有完整认知。然后按需查 `docs/design_decisions.md`（宪法）/ `docs/CHECKPOINT_LOG.md`（演进 audit trail）/ `docs/known_issues.md`（已知问题）。本文件每完成一个 checkpoint 整体覆写一次，**绝不允许落后于实际状态**。

---

## 1. 项目当前阶段与 Checkpoint

- **当前 Phase**：Phase 3（HTGN 异构时序图神经网络，**创新点 1 核心**）— **进行中（2/4 sub-checkpoints 已完成）**
- **最新 Checkpoint**：Checkpoint 8（Phase 3.3 HeteroTGNMemory）— 已通过本地验证
- **Phase 3 进度**：Checkpoint 7（Time2Vec + HGT layer Option-C）+ Checkpoint 8（TGN memory）已 done。下一个：Checkpoint 9（HTGN 主模块组装）→ Checkpoint 10（玩具图分类 + ATLAS 链路预测预热 AUC > 0.85 硬门槛）→ tag `v0.3-htgn`。
- **已完成 Phase**：Phase 0（tag `v0.0-scaffold`）+ Phase 1（tag `v0.1-data`）+ Phase 2（tag `v0.2-bert`）

## 2. 最新 Checkpoint Commit

- **Hash**：（本 commit；Checkpoint 8 单 commit 含 HeteroTGNMemory + 9 测试 + Hydra config 已存在 + lesson 文档）
- **Message**：`feat(htgn): Phase 3 / Checkpoint 8 HeteroTGNMemory (PyG TGNMemory composed per process/socket)`
- **Date**：2026-05-05

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
| 19 | `<this commit>` | checkpoint 8 | feat(htgn): Phase 3 / Checkpoint 8 HeteroTGNMemory (PyG TGNMemory composed per process/socket) |

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

**Phase 3 设计偏离记录**（`docs/known_issues.md`）：HGTConv edge_attr 接口限制 + Option C 残差通道决议（Checkpoint 7 RFC）。

**经验启发式校准记录**（`docs/known_issues.md`）：(a) 早期 GNN [10, 10000] events/window heuristic 不适用；(b) **Spec 与代码常数同步纪律**——Checkpoint 7 lesson，EdgeType 25→29 drift 处理标准范式（代码即真相 / 四处同步 / commit 显式记录）。

## 5. 下一步预期工作

**Checkpoint 9（Phase 3.4）：HTGN 主模块组装**，预计 2 天。所有设计参数 user 已在 Phase 3 launch spec 锁定：

- 3 层堆叠（PyG HGT 经验值，再多过拟合）
- 每层结构 [Time2Vec 边编码 → HGTConv → 记忆更新（仅 process/socket，调用 HeteroTGNMemory）→ 残差 + LayerNorm]
- 层间 γ 衰减 [1.0, 0.7, 0.4]（GraphSAGE 衰减实践）
- 输出格式 `dict[NodeType, Tensor[num_nodes_of_type, 256]]` 供 Phase 4 跨模态注意力使用

**Checkpoint 9 报告必须包含**：完整 HTGN forward 在 ATLAS 子图上的 shape + 时间测量（128 节点子图 RTX 4090 < 50ms forward）；端到端梯度回传验证（Time2Vec / HGT / TGN memory 三套参数全部收梯度）；总参数量 + 显存占用（batch=32）用于 Phase 7 batch size 估算。

**之后**：Checkpoint 10（玩具图分类 + ATLAS 链路预测预热 AUC > 0.85 硬门槛）→ tag `v0.3-htgn`。

## 6. 当前 Active 待回答问题

无（Checkpoint 9 所有参数已 launch-spec 锁定，无 RFC 触发预期）。

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

# Phase 3 模块单元测试（current branch）
uv run pytest tests/test_time2vec.py tests/test_hgt_layer.py tests/test_tgn_memory.py -v
```
