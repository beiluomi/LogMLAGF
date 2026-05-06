# LogHetero — Project Progress（单一真相源）

> **新会话起步**：如果你是新接手本项目的 AI 代理或合作者，本文件是你的入口。读完它你应对项目当前阶段、已生效决策、下一步要做什么、如何复现都有完整认知。然后按需查 `docs/design_decisions.md`（宪法）/ `docs/CHECKPOINT_LOG.md`（演进 audit trail）/ `docs/known_issues.md`（已知问题）。本文件每完成一个 checkpoint 整体覆写一次，**绝不允许落后于实际状态**。

---

## 1. 项目当前阶段与 Checkpoint

- **当前 Phase**：Phase 4（双向跨模态融合，**创新点 1 第二部分**）— **进行中（1/4 sub-checkpoints 已完成）**
- **最新 Checkpoint**：Checkpoint 11（Phase 4 入口前置 RFC + Phase 3 sanity AUC re-validation）— 已通过（**informationally complete**，详见下方 §4 决策清单与 §6 active 待回答问题章节）
- **Phase 4 进度**：Checkpoint 11（前置 RFC 消化 + 11.1 Option B benign-only 决议 + 11.2-γ-1 BERT informational null finding）已 done。下一个：Checkpoint 12（双向跨模态注意力实施）→ Checkpoint 13（改造 MLM 集成）→ Checkpoint 14（端到端集成 + smoke test）→ tag `v0.4-fusion`。
- **已完成 Phase**：Phase 0（tag `v0.0-scaffold`）+ Phase 1（tag `v0.1-data`）+ Phase 2（tag `v0.2-bert`）+ Phase 3（tag `v0.3-htgn`，conditional pass 后变更为 informationally complete via Checkpoint 11.2-γ-1）

## 2. 最新 Checkpoint Commit

- **Hash**：（本 commit，docs-only Phase 4 launch spec 严谨化补丁；前置 Checkpoint 11 commit 为 `c9796a8` 含 11.2-γ-1 决议 + 4 ablation artifacts + 决策 4.2 footnote + PROGRESS / CHECKPOINT_LOG 同步；Checkpoint 11.1 Option B 三条件 docs 在 `cae7216` 落档；本 commit 是 Phase 4 主体启动前的 docs-only 措辞收紧 + Phase 12 论文素材边界条件 note + 下一步计划扩展同步）
- **Message**：`docs(constitution): tighten link prediction task characterization (structure-dominated not structure-determined)`
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
| 27 | `c9796a8` | checkpoint 11.2-γ-1 | feat(phase4): Phase 4 / Checkpoint 11 RFC resolution + sanity null finding (γ-1) |
| 28 | `9f9ab17` | docs / handoff | docs(handoff): add 2026-05-06 session switch marker for next-window onboarding |
| 29 | `<this commit>` | docs / Phase 4 launch prep | docs(constitution): tighten link prediction task characterization (structure-dominated not structure-determined) |

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

**Phase 4 主体 4 sub-checkpoint 推进（2026-05-06 launch spec 严谨化升级版，预计 13-14 天）**：

**Checkpoint 12（Phase 4.1 双向跨模态注意力实施，预计 3 天）**：实施 `src/loghetero/models/fusion/cross_attention.py`。设计参数预先锁定避免 RFC 触发：

- 双向独立参数（Text→Graph 与 Graph→Text 各自独立 attention 参数不共享）
- text token 768 维与 graph node 256 维通过线性投影对齐到统一 attention dim 256
- attention head 数 8（与 BERT-base 对齐）
- BERT hidden state 通过 output_hidden_states=True 暴露每层 hidden states，融合层选第 3 / 6 / 9 / 12 共 4 个融合点
- Attention mask 严格限制为"每条 text token 只能 attend 到与其所在日志事件直接相关的图节点"，mask 构造逻辑写成独立 utility 便于后续放宽

**Checkpoint 12 报告必须包含**：跨模态 attention forward shape 测试、attention 权重在一个具体 case 上的可视化（notebook 里展示哪些 graph node 被哪些 text token 高权重 attend）、端到端梯度回传 sanity（loss.backward() 后 BERT 投影 / graph 投影 / cross-attention 三套参数全部收到非零梯度且梯度范数在合理量级）。

**Checkpoint 13（Phase 4.2 改造 MLM 任务集成，预计 2 天）**：v3 prompt §6 Phase 4.3 字段级 mask 任务（目标字段替换 / 删除 / 添加机制）；融合后隐藏状态预测 mask token 而非原始 BERT 输出；混合训练比初值 50/50；与传统 MLM perplexity 对比验证融合后预测确实利用图信息。

**Checkpoint 14（Phase 4 整体集成 + 七项 gate 验证，预计 2.5 天）**：原 forward 不报错 + 梯度正常两项 gate 升级为以下七项硬性 checklist 全部 pass：

1. **forward / backward 不抛**——batch=8 ATLAS 真实数据
2. **梯度三套全非零**——BERT 投影 / HTGN / cross-attention 任一 `.grad` 全零触发 RFC
3. **fusion 参数非退化**——cross-attention normalized entropy = H(attention) / log(n_keys) ∈ [0.3, 0.95]，下界防 single-token hard mask 退化，上界防均匀分布退化，两端越界触发 RFC
4. **modality dropout 显著影响**——BERT 输出置零后 forward 输出与正常 forward cos-sim < 0.95
5. **小 batch overfit sanity**——8 固定样本训 50 epoch，loss 收敛接近零
6. **random text ablation**——random token 替换真实日志文本输入，hidden states 与真实输入 hidden states 在 cosine 距离上显著差异（排除 cross-attention 学成对任意 text 给固定 summary 的 subtle failure）
7. **memory & time profile**——batch=16 真实 PyG batched HeteroData 实测 VRAM < 16 GB on RTX 4090，单步 forward+backward < 500 ms

**Checkpoint 14.5（异常检测前置 probe，Phase 4 真正最后一关，预计 4-5 天）**：

- 5 个 ATT&CK TTP 模板（T1059.001 PowerShell / T1003.001 LSASS Memory / T1071.001 Web Protocols / T1547.001 Registry Run Keys / T1041 Exfiltration over C2 Channel），覆盖 5 个不同战术阶段
- **TTP 模板必须 agent 直接基于 MITRE ATT&CK 公开 STIX 数据 + 现有 ATLAS 解析器手写实现，禁止调用 ChatGPT 或任何外部 LLM API 协助生成**——理由：可复现性（外部 API 输出不同时间漂移）+ 双盲投稿风险（API 日志可追溯）+ 论文可信度（依赖外部服务的研究工程在论文中可信度低于纯本地实现）
- 200-500 条合成攻击事件注入良性 ATLAS 子图 + 同等数量未注入良性事件作为对照
- 任务：事件级二分类（给定一条事件加其异构子图上下文预测是否合成攻击）
- 数据切分：**within-TTP 80/20 event-level holdout**（每 TTP 各自抽 20% 事件作 test，剩 80% 训练，5 TTP 合并报总 F1）；leave-one-TTP-out 留给 Phase 8
- 三配置对比：HTGN-only embedding / BERT-only embedding / Phase 4 fusion embedding；每配置 + simple MLP head 训 30 epoch 4 seed 重复
- **必须并列报三种配置 F1**——BERT-only 防 ATT&CK TTP 名称（"powershell.exe -enc"、"lsass.exe"、"reg add ...\\Run"）词面攻击信号污染论证；BERT-only ≈ fusion 触发 RFC 而非通过
- **通过门槛双条件**：(a) fusion 比 HTGN-only 平均 F1 lift ≥ 0.03 且 (b) 4 seed 配对 t-test p < 0.1（4 seed 样本太小用 0.1 而非严格 0.05）；同时满足才通过；只满足 (a) 不满足 (b) 写成"方向性正向但样本不足判定"作为弱信号推进 Phase 5-7 但 Phase 8 严格复验
- 14.5 通过后申请 v0.4-fusion tag 完成 Phase 4；Phase 5 RAPA 模板正式实施会复用 14.5 实现的 5 个原型再扩展到 20 个完整覆盖

**Phase 4 整体目标（2026-05-06 launch spec 严谨化升级版）**：Phase 4 主交付物是"跨模态融合架构落地 + 七项 gate 全过 + Checkpoint 14.5 异常检测前置 probe 双条件通过"。原"forward 不报错 + 梯度回传正常"两项扩展为七项 gate 防止"代码不报错就算通过"被审稿人质疑放水；新增 14.5 probe 提供跨模态融合方向性早期诊断证据，避免 Phase 8 才发现 fusion 不工作回退三个 phase 的代价。AUC-style 单点验证撤销不变，深层验证留 Phase 7-8。

**任一 gate 不通过 + Checkpoint 14.5 双条件不通过 + BERT-only F1 ≈ 或 ≥ fusion F1 都触发 RFC**。Phase 5 RAPA 模板与 Phase 11 消融矩阵扩展议程（含 hard negative benign admin behaviors 与 modality utilization 严格 ablation）作为 known_issues.md 待办保留，Phase 4 不前置实施。

## 6. 当前 Active 待回答问题

无（Checkpoint 11.1 Option B + Checkpoint 11.2-γ-1 双决议落地完成；Phase 4 待办::Phase 3 sanity AUC re-validation 标 informationally complete；Phase 4 launch spec 严谨化升级版已于 2026-05-06 在本会话窗口下达完成，含 4 sub-checkpoint + 七项 gate + Checkpoint 14.5 异常检测前置 probe + 禁外部 LLM API 五项硬性纪律；本 commit 是 Phase 4 主体启动前的 docs-only 措辞收紧补丁，下一动作为 Checkpoint 12 跨模态注意力模块实施）。

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
