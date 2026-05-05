# LogHetero — Project Progress（单一真相源）

> **新会话起步**：如果你是新接手本项目的 AI 代理或合作者，本文件是你的入口。读完它你应对项目当前阶段、已生效决策、下一步要做什么、如何复现都有完整认知。然后按需查 `docs/design_decisions.md`（宪法）/ `docs/CHECKPOINT_LOG.md`（演进 audit trail）/ `docs/known_issues.md`（已知问题）。本文件每完成一个 checkpoint 整体覆写一次，**绝不允许落后于实际状态**。

---

## 1. 项目当前阶段与 Checkpoint

- **当前 Phase**：Phase 3（HTGN 异构时序图神经网络，**创新点 1 核心**）— **进行中（Checkpoint 7 / 4 已完成）**
- **最新 Checkpoint**：Checkpoint 7（Phase 3.1 + 3.2 Time2Vec + HGT layer wrapper with Option-C 残差）— 已通过本地验证
- **Phase 3 进度**：1/4 sub-checkpoints 完成。下一个：Checkpoint 8（TGN-style 节点记忆）。
- **已完成 Phase**：Phase 0（tag `v0.0-scaffold`）+ Phase 1（tag `v0.1-data`）+ Phase 2（tag `v0.2-bert`）
- **下一阶段**：Phase 3 余下 Checkpoint 8 / 9 / 10，然后 tag `v0.3-htgn` 完成 Phase 3。

## 2. 最新 Checkpoint Commit

- **Hash**：（本 commit；Checkpoint 7 单 commit 含 Time2Vec + HGT layer + Hydra config + RFC docs）
- **Message**：`feat(htgn): Phase 3 / Checkpoint 7 Time2Vec + HGT layer wrapper (Option-C residual per RFC)`
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
| 18 | `<this commit>` | checkpoint 7 | feat(htgn): Phase 3 / Checkpoint 7 Time2Vec + HGT layer wrapper (Option-C residual per RFC) |

## 4. 已生效的决策清单（决策 1–9 + Phase 3 设计偏离记录）

详见 `docs/design_decisions.md` 完整论证；下方仅一行简述。

1. **决策 1** — 不复现任何已有论文作为方法主线
2. **决策 2** — 两条创新点精确措辞 + verified 先验工作
3. **决策 3** — 双盲匿名化策略
4. **决策 4** — 工程不变量（BERT 冻结 / HTGN day 1 / 双向跨模态 day 1 / 对比学习端到端 / 模块化）
   - **4.2 footnote (新增)**：Phase 11 消融 B5 实施细节，`residual_alpha=0` + `tgn_memory.enabled=false` 双开关组合
5. **决策 5** — DARPA TC E3 CDM → 5 类节点映射
6. **决策 6** — Leave-one-attack-out + 时间窗 final = 1.0h
7. **决策 7** — AI 协作披露策略
8. **决策 8** — 孤立节点保留策略
9. **决策 9** — 训练样本单位 = (target_event, subgraph_at_target, label) 三元组

**Phase 3 设计偏离记录**（见 `docs/known_issues.md`）：
- **HGTConv edge_attr 接口限制 + Option C 残差通道决议**（Checkpoint 7 RFC）：PyG 2.7 HGTConv 不支持 edge_attr，user 拍板 Option C 走残差通道。`y_dst = HGTConv(x) + α · scatter_add(MLP(time2vec || edge_type_onehot))`，α=0.5 固定不学习。

## 5. 下一步预期工作

**Checkpoint 8（Phase 3.3）：TGN-style 节点记忆**，预计 1.5 天。所有设计参数 user 已锁定：
- 仅 process / socket 两类节点（state-bearing entities）有 memory，file/network/user 无
- 维度 256 与 HTGN hidden_dim 对齐
- GRU 更新（不要 LSTM）
- batched 更新粒度（不要 per-event）
- 同 epoch 同 (host, scenario) 内跨 window 持久，epoch 边界 reset
- 初始 memory zero
- `tgn_memory.enabled=false` 是 Phase 11 ablation B5 switch #2

**Checkpoint 8 报告必须包含**：玩具时序图 5 步事件链 memory 演化测试；记忆 detach 策略验证（避免梯度跨 batch 泄漏）；与 PyG TGNMemory API 对齐说明（PyG TGNMemory 是同构设计，我们扩展到异构必须确保只 process/socket 触发 memory lookup）。

**之后**：Checkpoint 9（HTGN 主模块组装）+ Checkpoint 10（玩具图分类 + ATLAS 链路预测预热 AUC > 0.85 硬门槛）→ tag `v0.3-htgn`。

## 6. 当前 Active 待回答问题

无（Checkpoint 7 RFC 已 closed by user 拍板 Option C；Checkpoint 8 所有参数已预锁定）。

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

# Phase 1 数据流水线复现（v0.1-data tag 完整）
bash scripts/download_atlas.sh                          # ~2 min
uv run python scripts/verify_data_integrity.py          # 校验 manifest 幂等
uv run python scripts/parse_atlas_all.py --workers 8    # 全量解析 ~40s
uv run python scripts/build_atlas_graphs.py --workers 8 # 异构图构建 ~55s
uv run python scripts/build_window_density_histograms.py --workers 8
uv run python scripts/build_fold_stats_report.py        # leave-one-out fold 统计
uv run python scripts/tokenizer_nn_sanity.py            # tokenizer NN sanity
uv run python scripts/check_synonym_init.py             # SYNONYM_INIT regression（exit 0）

# Phase 2 BERT 集成验证（v0.2-bert tag 完整）
uv run python scripts/bert_sanity_check.py              # BERT NN sanity on real ATLAS

# Phase 3 Checkpoint 7 验证（current branch）
uv run pytest tests/test_time2vec.py tests/test_hgt_layer.py -v
```
