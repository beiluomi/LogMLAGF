# LogHetero — Project Progress（单一真相源）

> **新会话起步**：如果你是新接手本项目的 AI 代理或合作者，本文件是你的入口。读完它你应对项目当前阶段、已生效决策、下一步要做什么、如何复现都有完整认知。然后按需查 `docs/design_decisions.md`（宪法）/ `docs/CHECKPOINT_LOG.md`（演进 audit trail）/ `docs/known_issues.md`（已知问题）。本文件每完成一个 checkpoint 整体覆写一次，**绝不允许落后于实际状态**。

---

## 1. 项目当前阶段与 Checkpoint

- **当前 Phase**：Phase 1（数据流水线）— **已完成全部 5 个 checkpoint**
- **最新 Checkpoint**：Checkpoint 5（Phase 1.6 LogHetero DataModule）— 已通过 sanity check
- **Phase 1 收尾状态**：feat/01-data-pipeline 待 merge 到 main + 打 tag `v0.1-data`
- **下一阶段**：Phase 2（文本编码器集成与 Sanity Check），预计 1–2 天，工程性任务，非创新点

## 2. 最新 Checkpoint Commit

- **Hash**：`4b8dd6a`
- **Message**：`feat(datamodule): Phase 1.6 / Checkpoint 5 LogHetero DataModule`
- **Date**：2026-05-05

(注：`b606a5c` 与本 PROGRESS.md 创建 commit 是 Phase 1 收尾的工具/文档 commit，非 checkpoint commit；最新 *checkpoint* commit 仍是 `4b8dd6a`。)

## 3. 累计 Commit 链（按时间顺序）

| # | Hash | Type | Message |
|---|---|---|---|
| 1 | `d9ff51e` | scaffold | chore(scaffold): initialize LogHetero project structure |
| 2 | `d66450c` | docs | docs(constitution): add decisions 5-7 + ATLAS validation + split CI |
| 3 | `008cbff` | docs | docs(citations): verified prior work for decision 2 (drop hallucinated PLATO) |
| 4 | `aa184f4` | merge | merge: Phase 0 scaffold + design decisions constitution |
| 5 | `79f78be` | checkpoint 1 | feat(data): Phase 1.1 ATLAS download + integrity manifest |
| 6 | `c224eb8` | checkpoint 2 | feat(parsers): Phase 1.2 ATLAS + DARPA E3 CDM parser implementation |
| 7 | `40dbbca` | checkpoint 3 | feat(graph): Phase 1.3+1.4 cleaner + tokenizer + heterogeneous graph builder |
| 8 | `246ee95` | Q-1 mini | feat(parsers): add user-logon dispatch for 4 EventIDs (4624/4625/4672/4648) |
| 9 | `ba456a0` | checkpoint 4 | feat(window): Phase 1.5 / Checkpoint 4 events-per-window density artifact |
| 10 | `f67d845` | docs | docs(constitution): finalize window granularity (1.0h) + add decision 9 on sample unit |
| 11 | `4b8dd6a` | checkpoint 5 | feat(datamodule): Phase 1.6 / Checkpoint 5 LogHetero DataModule |
| 12 | `b606a5c` | Q-2 mini | feat(scripts): persist synonym init regression check as standing script |

(本 PROGRESS.md 创建 commit + 后续 commits 在下一次 checkpoint 完成时追加到此表。)

## 4. 已生效的决策清单（决策 1–9）

详见 `docs/design_decisions.md` 完整论证；下方仅一行简述。任何与下列冲突的实现必须先 RFC 改宪法再写代码。

1. **决策 1** — 不复现任何已有论文作为方法主线（独立研究项目，MLAGF 非基线）
2. **决策 2** — 两条创新点精确措辞 + verified 先验工作（Innovation 1: GraphFormers / GreaseLM / Patton / THLM；Innovation 2: ConGraT；HGT 作为 building block）
3. **决策 3** — 双盲匿名化策略（开发期真名，Phase 12 用 `git filter-repo` 镜像匿名）
4. **决策 4** — 工程不变量（BERT 冻结默认 / HTGN day 1 / 双向跨模态 day 1 / 对比学习端到端 / 模块化 / uv + DVC + W&B）
5. **决策 5** — DARPA TC E3 CDM → 5 类节点映射（UnnamedPipeObject → file 与 KAIROS / MAGIC / FLASH 对齐；SrcSinkObject → socket 灰色地带；ATLAS user-node 数量偏低脚注）
6. **决策 6** — Leave-one-attack-out 切分协议，时间窗粒度 **final = 1.0h**，全局统一不分档（基于 Checkpoint 4 16+1 直方图无 bimodal）
7. **决策 7** — AI 协作披露策略（保留 `Co-Authored-By: Claude`，Phase 12 mailmap 重写匿名）
8. **决策 8** — 孤立节点保留策略（degree=0 标 `isolated=True`，不静默过滤；APT C2 / staging endpoints 常呈孤立）
9. **决策 9** — 训练样本单位 = `(target_event, subgraph_at_target, label)` 三元组（不是 per-window；benign cap 1000 / 攻击事件全保留）

## 5. 下一步预期工作（Phase 2）

**Phase 2：文本编码器集成与 Sanity Check** — 预计 1–2 天上限，**不允许做任何训练**。核心交付物：

- `src/loghetero/models/encoders/bert_text.py`：封装 `bert-base-uncased`，提供三种训练模式开关
  - 完全冻结（默认，CLIP-style）
  - LoRA 后 4 层（peft）
  - 全参数微调
  - 统一 forward 接口暴露所有层 hidden states，供 Phase 4 双向跨模态融合使用
- Tokenizer 集成：词表从 30,522 → **30,678**（追加决策 9 的 156 special token，已在 `loghetero.data.tokenizer` 准备好），resize embedding 层
- 同义词平均初始化：复用 `loghetero.data.tokenizer.init_special_token_embeddings`
- Sanity check（在 holdout 日志上做最近邻检索）：取一条良性日志看 BERT 编码近邻是否同语义；取一条已知恶意日志看是否能与同类聚类
- **Phase 2 报告必须证明**：三种模式 forward 都不报错；vocab size 30522 → 30678；NN sanity 通过；PROGRESS.md + CHECKPOINT_LOG.md 同步更新

Phase 2 完成后等用户审视 → 进入 Phase 3（HTGN 实现，论文真正的卖点起点，审查节奏会重新拧紧）。

## 6. 当前 Active 待回答问题

无。Phase 1 全部 Q 已 close，Phase 2 启动条件齐备。

## 7. 快速复现指令

```bash
# 一键环境
git clone https://github.com/beiluomi/LogMLAGF.git
cd LogMLAGF
pip install --user uv && export PATH="$HOME/.local/bin:$PATH"
uv sync --extra dev --extra ml      # ~5 min cold install

# 验证门
make lint test                       # ruff + mypy + pytest（非 integration），<10s
make integration-test                # pytest -m integration（要 BERT 下载，~30s）

# Phase 1 数据流水线复现
bash scripts/download_atlas.sh                          # ~2 min（shallow clone + unzip）
uv run python scripts/verify_data_integrity.py          # 校验 atlas_manifest.json 幂等
uv run python scripts/parse_atlas_all.py --workers 8    # 全量解析（~40s）
uv run python scripts/build_atlas_graphs.py --workers 8 # 异构图构建（~55s）
uv run python scripts/build_window_density_histograms.py --workers 8  # Checkpoint 4 直方图
uv run python scripts/build_fold_stats_report.py        # leave-one-out fold 统计
uv run python scripts/tokenizer_nn_sanity.py            # tokenizer NN sanity
uv run python scripts/check_synonym_init.py             # SYNONYM_INIT regression check（exit 0 = OK）
```

每个脚本都有完整 docstring 说明输入 / 输出 / 设计意图。
