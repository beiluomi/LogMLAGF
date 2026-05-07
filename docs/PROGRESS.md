# LogHetero — Project Progress（单一真相源）

> **新会话起步**：如果你是新接手本项目的 AI 代理或合作者，本文件是你的入口。读完它你应对项目当前阶段、已生效决策、下一步要做什么、如何复现都有完整认知。然后按需查 `docs/design_decisions.md`（宪法）/ `docs/CHECKPOINT_LOG.md`（演进 audit trail）/ `docs/known_issues.md`（已知问题）。本文件每完成一个 checkpoint 整体覆写一次，**绝不允许落后于实际状态**。

---

## 1. 项目当前阶段与 Checkpoint

- **当前 Phase**：Phase 4（双向跨模态融合，**创新点 1 第二部分**）— **完成（5/5 sub-checkpoints 形式闭环 + Phase 4 全 null 闭环路径 + v0.4-fusion tag 申请；fusion validation 推到 Phase 7-8 严格 gate 验证）**
- **最新 Checkpoint**：Checkpoint 14（Phase 4 整体集成 + 七项 gate 验证）— **已通过 Option β 路径（5/7 PASS + 2/7 informational null finding）**：Gates 1/2/5/6/7 PASS（forward+backward batch=8 / 三套参数 grad norm > 1e-6 / 8-sample 50-epoch overfit loss 100% reduction / random text cos-sim p50=0.42 / batch=16 真实 PyG batched VRAM 5.13 GB + 单步 205.2 ms），Gates 3/4 在 Option A trained-state re-measurement 后仍 fail（Gate 3 entropy 6/8 over upper bound、Gate 4 cos-sim 1.0000）记入 Phase 12 论文素材作为 Phase 4 第二个 informational null finding。根因诊断：8-sample MLM overfit 在 frozen BERT + trainable MLMHead 配置下不构成 fusion engagement 的有效 pressure，MLMHead 单独 capacity 充分让 fusion 路径成 redundant。真正 evaluation 推到 Checkpoint 14.5 anomaly probe（loss 结构要求 graph-derived discriminative signal）+ Phase 7-8 联合预训练。
- **Phase 4 进度**：Checkpoint 11 + Checkpoint 12（含真实数据 smoke test audit anchor）+ Checkpoint 13（CrossModalAttention 之上 + build_field_level_mask + MixedMLMCollator + ModifiedMLMHead + 80/20 perplexity 对比 driver）+ Checkpoint 14（Phase4Model 集成 wrapper + deep injection ViLBERT-style + 七项 gate 验证 5/7 PASS + 2/7 informational null Option β 闭环）已 done。下一个：Option α 补充诊断（frozen BERT + frozen MLMHead，30 分钟单 agent 直跑） → Checkpoint 14.5（异常检测前置 probe）→ tag `v0.4-fusion`。
- **已完成 Phase**：Phase 0（tag `v0.0-scaffold`）+ Phase 1（tag `v0.1-data`）+ Phase 2（tag `v0.2-bert`）+ Phase 3（tag `v0.3-htgn`，conditional pass 后变更为 informationally complete via Checkpoint 11.2-γ-1）

## 2. 最新 Checkpoint Commit

- **Hash**：（本 commit Phase 4 全 null 闭环 + 严格 Phase 7-8 fusion engagement gates；前置 commit chain 含 Path B' final `5936107` + protocol violation lesson `aaad0bb` + α' Category 1 `682f819` + Checkpoint 14 Option β closure `8204b4a`）
- **Message**：`feat(phase4): close Phase 4 with four-null finding chain + strict Phase 7-8 fusion engagement gates`
- **Date**：2026-05-07
- **Phase 4 closure decision**：user 否决 Option γ 选 Phase 4 全 null 闭环路径。理由：(1) 四轮 null 共同特征显示 cross-attention 输出 content-quality 问题（零或错），不是 amplitude 不够，λ scaling factor 修不了零或错只会让错变得更错；(2) Option γ 大概率结果 SGD 学到 λ→0 让 fusion 实质 bypass，1-2 周工时换 cleaner 同样 null 信号 ROI 不可接受；(3) 四轮 null 共同特征是任务结构都不是 cross-modal fusion 设计的目标使用场景（structure-determined link prediction / 8-sample MLM overfit / frozen pressure isolation / lexical-rich BERT-saturated anomaly probe），fusion 真实目标是 Phase 7 InfoNCE 跨模态对比损失 + Phase 8 真实异常检测；(4) Phase 4 preliminary tests 全 null 是合理 prior 不是 fusion 不工作最终判定，Phase 7-8 才是 fusion 该 engage 的真实场景。
- **Option α' result**：**Category 1 — Gate 5 FAIL**——pretrained-frozen MLMHead 配置下 epoch1 0.6532 → epoch50 0.1197 reduction 81.7% < 90% 阈值。Gates 3/4 SKIPPED 早退出。**Confound 真实但不充分**：α 原始 epoch50 loss 3.62 vs α' epoch50 loss 0.12 是 30x 改善证明 random-head gradient-noise confound 真实存在但即使消除 confound，HTGN + CrossModalAttention 在 frozen-head pressure 下仍无法 fully converge MLM loss → **真 fusion incapacity 强信号**。按 user 预设解读框架 Category 1 含义：14.5 fail 时直接进架构级 RFC 评估 Option γ + 其他架构修复路径，**不需要再做 root cause 回合**。
- **Checkpoint 14.5 三轮诊断完整闭环（commits `7838ee8` 首轮 + Path B 实施 reverted into Path B' refinement + 本 commit Path B' final + audit-PASS Result B verdict）**：
  - **首轮**（commit `7838ee8`，含 implementer 协议违反保留作为 audit anchor）：Gate 3 FAIL（BERT-only F1 0.995 ≈ fusion F1 0.995 lexical leakage TTP-name tokens 让 BERT 单独 saturate）
  - **Path B**（uncommitted 中间态，已 superseded by B'）：扩 ANONYMIZE_MAP 加 anonymize TTP-name tokens + shared anchor 节点设计，BERT-only F1 1.000 仍通过 `atk_N_` prefix substring 完美识别 attack 节点（implementer's ANONYMIZE_MAP miss `atk_` prefix oversight）→ Result B 但 contaminated
  - **Path B' final**（本 commit）：扩 ANONYMIZE_MAP 加 atk_N_ prefix two-phase normalization (Phase 2a 正则 strip prefix + Phase 2b 节点类型 collapse 到 4 个 canonical token)，attack/benign string-level indistinguishable。**Spec compliance review AUDIT PASS**：anonymization 完整覆盖 23 attack node ID forms 零 oversight，BERT-only F1=0.9697 来自 operation-type co-occurrence patterns（合理 case a 信号——attack 用 NET_CONNECT/NET_SEND_NETWORK/FILE_WRITE/FILE_READ，ATLAS benign parsers 用 NET_DNS_QUERY/RESPONSE/HTTP_REQUEST/FILE_ACCESS——非 lexical leakage）。Fusion F1=0.8699 std=0.0506 underperform BERT-only **-0.0998**（远低于 +0.01 阈值）是 genuine architectural concern。
- **三 config aggregate F1 (Path B' final, 4 seeds [1,7,42,100])**：HTGN-only 0.2143 ± 0.0000 / BERT-only 0.9697 ± 0.0000 / Fusion 0.8699 ± 0.0506
- **双条件门槛**：Gate 1 lift +0.6556 ✅ / Gate 2 paired t-test p=0.0001 ✅ / **Gate 3 fusion - BERT-only -0.0998 ❌**
- **Per-TTP F1 informational** (seed=42)：T1059.001 0.48/0.95/0.86 / T1003.001 0.37/0.84/0.82 / T1071.001 0.37/0.95/0.95 / T1547.001 0.24/0.95/0.89 / T1041 0.24/0.95/0.67
- **Result B 触发架构级 RFC for Option γ**：fusion cross-attention 在 fully-anonymized fair conditions 下 actively interfere BERT-only 任务解决能力 ~10pp，是真实架构 concern 不是 noise。Option γ 实施 spec：CrossModalAttention 加可学习 scaling factor `λ` 让 `fused_text = BERT_residual + λ · tg_out_proj(tg_ctx)`，λ init 1.0 强制 fusion 残差从 init 起就有显著量级；复跑 Checkpoint 12 unit tests (28 tests ~5s) + Checkpoint 14 七项 gate (~30 min) + 14.5 Path B' final 协议 (~25 min)。**总工时估算 1-2 周**，含 RFC 决议 + implementer dispatch + 4 步 review pattern + bug 调试 buffer。等 user 裁定是否实施。
- Phase 4 累计 4 个诊断 null finding：C11.2-γ-1 (link prediction) + C14 Gates 3/4 (MLM-overfit) + α' Category 1 (frozen MLMHead) + 14.5 Result B (anonymized anomaly probe)。HTGN-only F1 ≈ 0.21 在 14.5 中是 documented limitation（attack 节点结构嵌入度不足），caveat 已记入 Phase 12 论文素材。

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
| 29 | `ce67209` | docs / Phase 4 launch prep | docs(constitution): tighten link prediction task characterization (structure-dominated not structure-determined) |
| 30 | `cfa4ec6` | checkpoint 12 | feat(fusion): Phase 4 / Checkpoint 12 bidirectional cross-modal attention module |
| 31 | `78c76ee` | checkpoint 12 fix | fix(fusion): Phase 4 / Checkpoint 12 review fixes (docstring + independence test + grad-norm comment) |
| 32 | `6f2410f` | docs / checkpoint 12 close | docs(progress): close Checkpoint 12 — bidirectional cross-modal attention module |
| 33 | `b19d13a` | docs / methodology | docs(methodology): record multi-agent review pattern lesson in Phase 12 论文素材 |
| 34 | `8222e50` | test / checkpoint 12 smoke | test(checkpoint12): real-data smoke test on M3_h2 first window (mean reduction) |
| 35 | `1e62fab` | docs / Phase 5 待办 | docs(known_issues): add Phase 5 待办 entry for 字段级 mask 添加机制延迟决议 |
| 36 | `a3eb147` | checkpoint 13 | feat(objectives): Phase 4 / Checkpoint 13 modified MLM task on fused hidden states |
| 37 | `5cba533` | checkpoint 13 fix | fix(objectives): Phase 4 / Checkpoint 13 review fixes (GELU + driver dedup + misc polish) |
| 38 | `71363e9` | docs / checkpoint 13 close | docs(progress): close Checkpoint 13 — modified MLM on fused hidden states |
| 39 | `2c89cb5` | docs / Phase 5 待办 | docs(known_issues): add Phase 5 待办 hard negative benign admin behaviors agenda |
| 40 | `241f30f` | docs / checkpoint 13 Option C | docs(known_issues): Checkpoint 13 Option C 三条件落档（perplexity fast-iter 接受 + Phase 7 proper-scale 复验占位 + 14.5 临界测试 caveat）|
| 41 | `2eb712e` | docs / Phase 7 deep injection | docs(known_issues): Phase 7 待办 add deep injection 训练成本预算提醒（Checkpoint 14 RFC-1 Option A 触发）|
| 42 | `8204b4a` | checkpoint 14 closure | feat(phase4): Checkpoint 14 closure with 5/7 PASS + 2/7 informational null finding (β) |
| 43 | `1b16d25` | option α diagnostic | test(phase4): Checkpoint 14 supplementary diagnostic (α frozen MLMHead) |
| 44 | `ddf90c8` | docs / α inconclusive | docs(progress): record Option α inconclusive result + 14.5 path RFC pending |
| 45 | `682f819` | option α' refinement | test(phase4): Checkpoint 14 supplementary diagnostic refinement (α' pretrained MLMHead) |
| 46 | `a3fb2b7` | docs / α' Category 1 | docs(progress): record Option α' Category 1 (fusion incapacity strong signal) + Checkpoint 14.5 dispatch |
| 47 | `7838ee8` | checkpoint 14.5 first run (含协议违反保留作为 audit anchor) | feat(probe): Phase 4 / Checkpoint 14.5 anomaly detection probe with 5 ATT&CK TTP templates |
| 48 | `eddb23c` | docs / Phase 5 schema | docs(known_issues): Phase 5 待办 add ALLOWED_EDGE_TRIPLES schema 扩展议程 |
| 49 | `aaad0bb` | docs / protocol violation lesson | docs(phase4): record Checkpoint 14.5 implementer protocol violation lesson |
| 50 | `5936107` | checkpoint 14.5 path B' final (Result B) | feat(phase4): Checkpoint 14.5 Path B' final with full anonymization (audit-clean Result B - architectural-level RFC trigger for Option γ) |
| 51 | `<this commit>` | phase 4 closure | feat(phase4): close Phase 4 with four-null finding chain + strict Phase 7-8 fusion engagement gates |

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

**Phase 4 已闭环（2026-05-07 全 null 闭环路径）**：5/5 sub-checkpoints 形式完成 + 4 个 informational null finding chain（C11.2-γ-1 link prediction + C14 Gates 3/4 MLM-overfit + α' Category 1 frozen pressure + 14.5 Path B' Result B audit-PASS anomaly probe）+ v0.4-fusion tag。Fusion mechanism validation 推到 Phase 7-8 严格 gate 验证（详见 known_issues.md::Phase 7 待办::"fusion engagement small-scale gate" + Phase 8 待办::"strict fusion ablation"）。

**下一阶段 Phase 5 RAPA 攻击模板正式实施（创新点二核心阶段）**：等 user 下达 Phase 5 launch spec。已落 known_issues.md 的 Phase 5 待办 entries 作为 design constraint 输入：
- 字段级 mask 任务的"添加机制"（Phase 4 / Checkpoint 13 RFC 决议延迟到 Phase 5 与 RAPA 共享注入框架实施）
- 20 TTP 模板设计必须含 6 类 hard negative benign admin behaviors（GPT 反思议程，避免合成攻击假可分性陷阱）
- ALLOWED_EDGE_TRIPLES schema 扩展议程（Checkpoint 14.5 RFC-14.5-1 触发，registry + process-handle 边类型工程妥协 Phase 5 统一处理）

Phase 5 与 Phase 4 fusion 状态独立——即使 Phase 7-8 fusion 严格 gate fail 触发 paper pivot，Phase 5 RAPA 实施仍是创新点二的核心 contribution 不浪费工时。

**已 superseded 的 Phase 4 主体 4 sub-checkpoint 推进（2026-05-06 launch spec 严谨化升级版，原计划 13-14 天）保留作为 audit trail**：

**Checkpoint 12（Phase 4.1 双向跨模态注意力实施，预计 3 天）**：实施 `src/loghetero/models/fusion/cross_attention.py`。设计参数预先锁定避免 RFC 触发：

- 双向独立参数（Text→Graph 与 Graph→Text 各自独立 attention 参数不共享）
- text token 768 维与 graph node 256 维通过线性投影对齐到统一 attention dim 256
- attention head 数 8（与 BERT-base 对齐）
- BERT hidden state 通过 output_hidden_states=True 暴露每层 hidden states，融合层选第 3 / 6 / 9 / 12 共 4 个融合点
- Attention mask 严格限制为"每条 text token 只能 attend 到与其所在日志事件直接相关的图节点"，mask 构造逻辑写成独立 utility 便于后续放宽

**Checkpoint 12 报告必须包含**：跨模态 attention forward shape 测试、attention 权重在一个具体 case 上的可视化（notebook 里展示哪些 graph node 被哪些 text token 高权重 attend）、端到端梯度回传 sanity（loss.backward() 后 BERT 投影 / graph 投影 / cross-attention 三套参数全部收到非零梯度且梯度范数在合理量级）。

**Checkpoint 13（Phase 4.2 改造 MLM 任务集成，预计 2 天）**：v3 prompt §6 Phase 4.3 字段级 mask 任务（目标字段替换 / 删除 / 添加机制）；融合后隐藏状态预测 mask token 而非原始 BERT 输出；混合训练比初值 50/50；与传统 MLM perplexity 对比验证融合后预测确实利用图信息。

**Checkpoint 14（Phase 4 整体集成 + 七项 gate 验证，已通过 Option β 路径 5/7 PASS + 2/7 informational null finding 2026-05-07）**：原 forward 不报错 + 梯度正常两项 gate 升级为七项硬性 checklist：

1. ✅ **forward / backward 不抛**——batch=8 ATLAS 真实数据，loss 9.72，无 NaN/Inf
2. ✅ **梯度三套全非零 grad norm > 1e-6**——bert_proj 4.5e-1 / htgn 2.0e+14（注：Phase 7 必须启用 gradient clipping max_norm=5.0，详见 known_issues.md::Phase 7 待办）/ cross_attention 3.6e+0
3. ⚠️ **fusion 参数非退化** entropy ∈ [0.3, 0.95]——**informational null finding**：8 个标量 6/8 over upper bound（trained-state 与 init-state 一致），根因 8-sample MLM overfit 不构成 fusion engagement pressure，详见 known_issues.md::Phase 12 论文素材::"MLM-overfit informational null finding"
4. ⚠️ **modality dropout 显著影响**——**informational null finding**：cos-sim mean = p10 = p50 = p90 = 1.0000 trained-state 与 init-state 一致，同根因（fusion 路径在 frozen BERT + trainable MLMHead 配置下 redundant）
5. ✅ **小 batch overfit sanity**——8 固定样本训 50 epoch，loss 10.52 → 0.000224 reduction 100%
6. ✅ **random text ablation**——cos-sim mean 0.43，p10/50/90 = 0.33/0.42/0.53 全部 < 0.9
7. ✅ **memory & time profile**——batch=16 真实 PyG batched HeteroData VRAM **5.126 GB** < 16 GB，单步 **205.2 ms** < 500 ms（数字作为 Phase 7 batch size 设计 single source of truth）

**Phase 4 收尾路径 Option β**：5/7 PASS + 2/7 informational null finding 状态闭环。Gates 3/4 informational null 与 Checkpoint 11.2-γ-1（Phase 4 入口 BERT input-feature injection on link prediction）形成 Phase 4 双 informational null pattern，论文 Methods 章节作为 negative-result-as-positive-contribution 工程方法论 contribution evidence。真正 fusion 效用判定推到 Checkpoint 14.5 anomaly detection 前置 probe（loss 结构要求 graph-derived discriminative signal）+ Phase 7-8 大规模联合预训练。

**Option α 补充诊断**（30 分钟级，单 agent 直跑非 4 步 pattern）：在进入 14.5 之前跑一次 frozen BERT + frozen MLMHead 配置的 Gate 5 + Gate 3/4 重测。仅 HTGN + CrossModalAttention 可训练，强迫 fusion 路径承担 MLM overfit 学习责任。两种结果都不影响 Phase 4 形式闭环也不影响 14.5 启动，仅影响 14.5 fail 时的回退路径决策速度（α PASS → 进 14.5 时融合机制健康度信心增强；α FAIL → 14.5 fail 时直接进架构级 RFC 评估 Option γ 不需要额外诊断回合）。

**Option γ（推迟到 14.5 之后视情况启用）**：在 CrossModalAttention 加可学习 scaling factor `λ` 让 `fused_text = BERT_residual + λ · tg_out_proj(tg_ctx)`。如 14.5 通过双条件门槛 γ 永久不需要实施；如 14.5 fail 结合 α 结果启动架构级 RFC 评估 γ 与其他路径例如 BERT 解冻或 cross-attention 容量增强。

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

无（Phase 4 全 null 闭环路径完成 2026-05-07，5/5 sub-checkpoints 形式闭环 + 4 个 informational null finding chain + 严格 Phase 7-8 fusion engagement gates 落档 + 诚实性契约落 Phase 12 论文素材；v0.4-fusion tag 申请 in flight；下一动作为 Phase 5 RAPA 攻击模板正式实施 launch spec 等 user 下达）。

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
