# LogHetero — Project Progress（单一真相源）

> **新会话起步**：如果你是新接手本项目的 AI 代理或合作者，本文件是你的入口。读完它你应对项目当前阶段、已生效决策、下一步要做什么、如何复现都有完整认知。然后按需查 `docs/design_decisions.md`（宪法）/ `docs/CHECKPOINT_LOG.md`（演进 audit trail）/ `docs/known_issues.md`（已知问题）。本文件每完成一个 checkpoint 整体覆写一次，**绝不允许落后于实际状态**。

---

## 1. 项目当前阶段与 Checkpoint

- **当前 Phase**：Phase 2（文本编码器集成与 Sanity Check）— **已完成单 checkpoint 6**
- **最新 Checkpoint**：Checkpoint 6（Phase 2 BERT text encoder integration）— 已通过本地验证
- **Phase 2 状态**：feat/02-bert-integration 待 merge 到 main + 打 tag `v0.2-bert`
- **已完成 Phase**：Phase 0（scaffold，tag `v0.0-scaffold`）+ Phase 1（数据流水线，tag `v0.1-data`）
- **下一阶段**：**Phase 3（HTGN 异构时序图编码器）— 创新点 1 第一部分**，预计 5-6 天，论文真正卖点起点

## 2. 最新 Checkpoint Commit

- **Hash**：（本 PROGRESS.md commit 自身；最新 Phase 2 实现 commit 的 hash 在 git log 可见）
- **Phase 2 单 checkpoint 实现包含**：`src/loghetero/models/encoders/bert_text.py` + `tests/test_bert_text.py` + `scripts/bert_sanity_check.py` + `data/bert_sanity_check.json` + 本 PROGRESS.md / CHECKPOINT_LOG.md 更新

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
| 13 | `a620de9` | docs | docs(handoff): introduce PROGRESS.md and CHECKPOINT_LOG.md for cross-session continuity |
| 14 | `5bafb4e` | merge / tag v0.1-data | merge: Phase 1 data pipeline (10 commits incl. handoff infra) |
| 15 | `<this commit>` | checkpoint 6 | feat(bert): Phase 2 BERT text encoder + sanity check (3 modes, vocab 30522→30678) |

## 4. 已生效的决策清单（决策 1–9）

详见 `docs/design_decisions.md` 完整论证；下方仅一行简述。

1. **决策 1** — 不复现任何已有论文作为方法主线
2. **决策 2** — 两条创新点精确措辞 + verified 先验工作（GraphFormers / GreaseLM / Patton / THLM / ConGraT / HGT）
3. **决策 3** — 双盲匿名化策略（Phase 12 git filter-repo）
4. **决策 4** — 工程不变量（BERT 冻结默认 / HTGN day 1 / 双向跨模态 day 1 / 对比学习端到端 / 模块化）
5. **决策 5** — DARPA TC E3 CDM → 5 类节点映射（UnnamedPipeObject → file 等）
6. **决策 6** — Leave-one-attack-out 切分协议，时间窗粒度 final = 1.0h，全局统一不分档
7. **决策 7** — AI 协作披露策略（保留 Co-Authored-By: Claude，Phase 12 mailmap 重写匿名）
8. **决策 8** — 孤立节点保留策略（degree=0 标 isolated=True，不静默过滤）
9. **决策 9** — 训练样本单位 = (target_event, subgraph_at_target, label) 三元组（不是 per-window）

## 5. 下一步预期工作（Phase 3）

**Phase 3：HTGN 异构时序图神经网络（创新点 1 第一部分）**，预计 5-6 天。审查节奏将重新拧紧（Time2Vec 维度 / TGN memory 更新策略 / HGT 层数堆叠 等关键决策需用户参与）。核心交付物（按 v3 prompt §6 Phase 3）：

- **3.1 Time2Vec 时间编码** (`src/loghetero/models/encoders/time2vec.py`)：把边 / 节点时间戳映射到 d 维向量，公式 `φ(t) = [ω₀t + φ₀, sin(ω₁t + φ₁), ..., sin(ω_{d-1}t + φ_{d-1})]`，`ω_i, φ_i` 可学习。单元测试验证周期性。
- **3.2 HGT 层封装** (`src/loghetero/models/graph/hgt_layer.py`)：包装 PyG `HGTConv`，支持 Time2Vec 边特征。
- **3.3 TGN-style 节点记忆** (`src/loghetero/models/graph/tgn_memory.py`)：process / socket 节点维护 GRU-update memory vector。
- **3.4 HTGN 主模块** (`src/loghetero/models/graph/htgn.py`)：3 层堆叠 [Time2Vec → HGTConv → memory update → 残差 + LayerNorm]。
- **3.5 玩具图回归测试**：5 类节点 / 7 种边的小异构图上验证节点分类 loss 收敛到 ~0。
- **3.6 ATLAS 链路预测预热**：在 ATLAS 一个 scenario 良性子图上 link prediction，AUC > 0.85。

## 6. 当前 Active 待回答问题

无（Phase 2 完成无 blocking question；Phase 3 启动会有 Time2Vec / TGN 等设计决策需用户参与）。

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

# Phase 1 数据流水线复现
bash scripts/download_atlas.sh                          # ~2 min
uv run python scripts/verify_data_integrity.py          # 校验 atlas_manifest.json 幂等
uv run python scripts/parse_atlas_all.py --workers 8    # 全量解析（~40s）
uv run python scripts/build_atlas_graphs.py --workers 8 # 异构图构建（~55s）
uv run python scripts/build_window_density_histograms.py --workers 8  # 直方图 (Checkpoint 4)
uv run python scripts/build_fold_stats_report.py        # leave-one-out fold 统计 (Checkpoint 5)
uv run python scripts/tokenizer_nn_sanity.py            # tokenizer NN sanity (Checkpoint 3)
uv run python scripts/check_synonym_init.py             # SYNONYM_INIT regression (Q-2 standing)

# Phase 2 BERT 集成验证
uv run python scripts/bert_sanity_check.py              # BERT NN sanity on real ATLAS (Checkpoint 6)
```
