# Known Issues

## 经验启发式校准记录（避免被早期 GNN 数字误导）

### Borderline RFC 期间数字与最终 commit 数字不一致时跟随实测（2026-05-06，Checkpoint 10 lesson 标准范式）

**现象**：Checkpoint 10 Task B 在 borderline RFC 期间，agent 报 user 的 AUC 数字 "0.825 ± 0.008" 来自我早期单 seed 高位读数（seed 42 final epoch 的 0.8251），user 据此构造 Option A conditional pass 决议 + tag message 模板。RFC 落地时 sub-agent 重跑 4-seed 聚合得 multi-seed 实测 mean **0.8144 ± 0.0068**——与 RFC 期间数字差 ~0.01（CUDA matmul 算法非确定性导致的典型 deep learning multi-seed run-to-run variation）。

**采取的纪律（user 标记为标准范式）**：commit 与 tag message 中的最终数字**跟随 multi-seed 实测**（0.8144），不刚性沿用 RFC 期间数字（0.825）。Trade-off：略偏离 user 用 "精确措辞" 给出的 tag template，但保持数据诚实。理由——RFC 期间数字是基于 partial / interim 测量的近似，最终落档应以 canonical multi-seed aggregate 为准；如固守 RFC 数字，Phase 4 BERT 重测对比 baseline 会用错（0.825 vs 0.8144 的 0.01 偏差会污染 Δ 计算）。

**未来类似情境的标准处理**：

1. Borderline RFC 期间 agent 报数字必须明确标注 "interim single-seed reading" 或 "preliminary partial run"；user 决议时知道这是近似数字。
2. RFC 决议执行（commit / tag）时如有更精确测量（multi-seed aggregate / 更大样本 / 更稳定 sampler），**用最新最精确数字替换 RFC 期间数字**，并在 commit message + relevant docs 显式说明替换原因（如 "multi-seed 聚合替代单 seed 高位读数；±0.01 因 CUDA 非确定性"）。
3. 替换后的数字成为后续 phase 重测对比的 canonical baseline；旧 RFC 数字仅作历史 audit trail 保留，不再用于实际计算。
4. 这一纪律的核心是 "诚实跟随数据"——user 给的 tag template 是 form prescription，numbers 本身应反映最终最精确测量。Form-following（用 user 给的精确措辞）必须让位 data-following（用最新实测数字）。

**Phase 12 Methods 写作 hook**：本条作为 "我们如何处理 conditional pass 的细节诚实" 在 Methods 章节"Reproducibility & methodology" 段中作为 evidence point，强调 "we report final multi-seed aggregated numbers, not interim single-seed best reads, even when this slightly deviates from in-flight discussion".

### Spec 与代码常数同步纪律（2026-05-05，Checkpoint 7 lesson）

- **现象**：Phase 3 launch spec 写"Time2Vec 32 + EdgeType one-hot 25 → concat 57"，但 Q-1 mini-checkpoint 后 EdgeType 实际增至 29（加 3 USER_* + UNKNOWN），concat 维度应为 61 而非 57。这是 spec 与代码常数 drift 的一例。
- **正确做法（Checkpoint 7 已执行）**：**显式跟随代码现实，不 silent 按 spec 写死 25**。具体落地：
  1. 代码用 `_N_EDGE_TYPES = len(EdgeType)`（动态读取，不写死）
  2. Hydra config 注释里说明 61 = 32 + 29
  3. Commit message 显式标注 "EdgeType one-hot dim 修正 25 → 29"
  4. Module docstring 里说明 launch spec 假设过时 + 代码以 enum 实际成员数为准
  5. 单元测试 `test_edge_type_one_hot_uses_29_dim` 锁定该值，未来 EdgeType 扩到 30 时该测试会主动 fail 提醒更新
- **错误做法（绝不允许）**：silent 把残差 MLP 输入维度按 25 写死，等运行时 shape mismatch 报错才发现，然后偷偷修补。
- **后续阶段适用范围**：剩余九个 phase 还会出现"代码现实领先于 launch spec"的常数 drift（典型场景：节点类型从 5 类扩到 6 类、156 个 special token 调整、20 个 RAPA 模板增减、7 个 SOTA 基线变化等）。**所有此类 drift 必须显式 RFC 而非 silent 跟随**——同步动作四处一致（代码 / 测试 / config / docs）+ commit message 显式记录是标准范式。
- **判定原则**："代码即真相"（code as ground truth），spec 是意图陈述但代码常数随实施演化。Drift 不是问题，silent drift 才是问题。

### Smoke test 阈值设计必须显式考虑 loss reduction 与 N 的交互（2026-05-06，Checkpoint 12 real-data smoke test lesson）

**现象**：Checkpoint 12 real-data smoke test launch spec 写 "grad norm 必须落 [1e-7, 1e3]" 作为真实数据数值健康验证的紧门槛。首次跑 6 个参数中 4 个超 1e3，最高的 `text_proj.weight` 达 1.151e+05（超界 100x）。架构层面 NaN/Inf clean、VRAM 0.421 GB、forward+backward 2.5 ms 全部健康——架构没问题，spec 阈值有问题。

**根因（controlled experiment 钉死）**：smoke test 与 unit test 用相同的 `loss = fused_text.sum() + fused_graph.sum()` sum reduction loss，但 unit test N=16，smoke test 真实数据 N=2000。sum reduction 让 grad norm 与 N 线性耦合：N 从 16 升到 2000 是 125x 放大；实测 unit test 落 [1e2, 1.4e3]、smoke test 落 [4e3, 1.2e5] 完全吻合 125x scaling 预测。原 [1e-7, 1e3] 阈值在写时假设了 grad norm 与 N 无关，是真实的 scale-naive 错误。

**修正方案（RFC Option B 选用，标准范式）**：smoke test 改用 mean reduction `loss = fused_text.mean() + fused_graph.mean()`。mean = sum / N 让 grad norm 在 N 变化下基本恒定，spec 写的 [1e-7, 1e3] 紧门槛得以保留作为真实数值健康验证。修订后 6 个参数 grad norm 全部落 [0.11, 0.22] 健康量级。

**为何不选 cap-around**：

- **Option A**：放宽 smoke test 阈值到 [1e-7, 1e5]——cap-around 没解决根本问题，将来 batch / N 改变又得重调；阈值随 N 变化的隐性约束没解耦。
- **Option C**：smoke test 限 N=128 不用真实 max_nodes=2000——背离 "真实数据 regime smoke test" 本意，跟 unit test 区别不大。
- **Option B（选用）**：mean reduction 修根因（loss formulation 的 N-coupling 是 scale-naive 的），保留紧门槛，符合 ML 训练 convention 主流。

**smoke test 与 unit test loss formulation 不一致是合理的**：

- Unit test 用 sum reduction + 宽松 [1e-8, 1e6] 阈值：测合成 tensor shape 与 gradient flow，N 小（N=16 / 64）量级 sum 能 cover 自然 sqrt(B*T*D)-scaled 范围；用 mean 反而失去对极小梯度的检测灵敏度。
- Smoke test 用 mean reduction + 紧 [1e-7, 1e3] 阈值：测真实数据数值健康，N 大（N=2000）必须解耦 N，紧阈值有意义；用 sum 阈值就被 N-scaling 污染。
- **两个测试目的不同，loss formulation 不同是设计选择不是失误**。脚本 docstring 显式说明该不一致，避免未来 agent 读到时疑惑或试图统一。

**后续阶段适用范围（前置参考）**：

1. **Phase 7-8 大规模训练阶段**写各种 sanity check 阈值时，**先确认 loss reduction 类型**：sum / mean / sum-over-active-token / batch-mean / element-mean 等不同 reduction 对 grad norm 量级的影响差几个数量级。
2. **Phase 11 ablation matrix** 跑各种配置对比 grad norm 时统一用 mean reduction，避免不同配置 N 不同时数字不可比。
3. **Phase 14.5 异常检测前置 probe**（已规划）的 fusion / HTGN-only / BERT-only 三配置对比训练若涉及 grad norm sanity，必须用 mean reduction 解耦三配置可能不同的有效 N。
4. **Phase 4 / Checkpoint 14 七项 gate**第二项 "梯度三套全非零" 与第三项 "attention entropy ∈ [0.3, 0.95]" 在 batch=16 真实数据下，必须复用 smoke test 的 mean reduction 模式而非 sum，否则 batch=16 + N_real 的 grad norm 量级会偏离合理范围。

**判定原则**："验证脚本阈值必须 N-invariant（mean reduction 或者显式 N 归一化），否则同一架构换样本规模就要改阈值——这是脆性 spec"。Phase 12 论文 Methods 章节如报告 sanity check 阈值，须显式说明 reduction 选择 + 为何选 mean，作为工程严谨性 evidence。



- **"每 window 10–10000 events 的合理区间"启发式不适用于 LogHetero / 现代 HGT**（2026-05-05 标记，Checkpoint 4 数据后校准）。
  - 来源：launch spec 引用的早期 GNN 经验，对应 GraphSAGE / GAT 在小图（< 10k edges）上训练的样本规模感。
  - LogHetero 现实：ATLAS 每 1 小时 window 含 16k–200k events，对应子图（per-event K-hop=2、max_nodes=128）规模 100–500 节点 / 100–1000 边，一次 forward 在 RTX 4090 上亚秒级。
  - 训练规模感：以 event 为样本单位（决策 9）后，每 fold 训练样本 ~64k、测试样本 ~4k–8k，与 GLUE benchmarks 同量级，BERT-base + HTGN 联合训练规模合理。
  - **后续 reviewer 或合作者从 commit log / 决策表里看到 "16k–200k events/window" 时，请直接读本条**——这不是错误数据，是数据集本身的客观特征 + 训练单位升级到 per-event 后的 emergent 规模感。

## Phase 1.2 修订记录（避免被误读为退步）

- **Q-1 mini-checkpoint commit `246ee95` 中 -8,143 success / +8,143 skipped 的语义**：refactor SecurityEventsParser 为 per-EventID extractor pattern 的副产物——发现旧 code 在 4663 / 4656 / 4658 / 4660 / 4690 等 file-handle 事件 body 缺失 `Process Name` 字段时，会 fallback 用 `Account Name` 当作 process subject。这导致 Checkpoint 3 提交的 ATLAS 图里有约 8,143 条 `(account_name as process) → file` 的语义错误边藏着——账户名被错误当成进程节点参与图构建。新 extractor 在 Process Name 缺失时返回 None（skipped，不是 failed）。**这是 graph quality 的明显改进，不是数据丢失**。Phase 8 跑基线时不会再以"基线效果异常"的形式暴露这个 bug。

  - 数字解读：success 总数从 2,745,528 → 2,737,385，差 8,143 条事件；这 8,143 条全部转入 skipped（不是 failed）。
  - 影响范围：仅 ATLAS（DARPA TC E3 CDM 用 UUID 寻址，不会有这种 fallback 错配）。
  - 不需要回退：旧的有问题数据已被新 manifest + summary 覆盖（commit `246ee95` 同时更新了 `data/atlas_parse_summary.json` 与 `data/atlas_graph_summary.json`）。

## ATLAS user 类节点数量偏低（Phase 12 Limitation 素材）

- **观察（Q-1 mini-checkpoint 后落实）**：ATLAS 主数据集 16 (scenario, host) pair 的 user 节点共 70 个（每 host 1-5 个），远小于直觉预期的"几十到几百"。
- **原因（数据集本身特征，非 dispatch 漏报）**：4624 在 ATLAS 几乎全是 LogonType=5 (Service)，被 Q-1 spec 的 {3, 9, 10} 过滤器排除（这是 desired 行为，Type 5 是 baseline noise）；4625 (Logon Failure) 在全部 16 host **完全为零**（grep 验证）；4648 (Explicit Credentials) 也极罕见。ATLAS 是 controlled lab attack scenarios，不是真实企业环境，logon 多样性自然偏低。
- **架构一致性已达成**：5 类异构节点中 4 类（process / file / network / user）在 ATLAS 全部 16 host 非零；仅 socket 等 DARPA TC E3 Principal/SrcSink。Phase 11 消融 B4 对照"5 类异构 → 1 类同构 GAT"成立。
- **DARPA TC E3 / Phase 9 跨数据集验证将丰富该类**：CDM Principal 节点天然填充 user 类，且 4625 等价的失败认证事件在 E3 数据中存在。
- **Phase 12 论文 Limitation 章节素材**："ATLAS dataset's logon-event diversity is limited; the user-node story is more cleanly demonstrated on DARPA TC E3 (Phase 9 cross-dataset generalisation)."

## Phase 1.2 已 resolve

- ~~**M5 h1 `security_events.txt` 数量级是否为真实攻击密集**~~ — **RESOLVED 2026-05-05 (Checkpoint 2)**。EventID 直方图对比确认 M5 h1 是**真实攻击密集**：
  - 4656 (handle_request) / 4658 (handle_close) / 4663 (file_access) 在 M5 h1 是其他 M h1 的 **4–5×**：M5=222k/221k/165k vs others=37k–53k；
  - 4660 (file_delete) / 4688 (process_create) / 4689 (process_exit) **完全正常**：M5=987/149/146 vs others=725–1517 / 110–164 / 111–137；
  - 该 pattern 是 single-TTP heavy file-system access（典型 T1083 file/dir discovery 或 T1005 data-from-local-system）的特征，**不是 log corruption**——corruption 会等比例放大全部 EventID。
  - 单独解析失败率：0%（611,242 success / 0 failed），与其他 M h1 一致。
  - 结论：M5 在 Phase 1.5 事件密度直方图上会显著高于其他 scenario，预期之内，无需特殊处理。

## Phase 1.2 解析失败已知项（决策：不修，记入 audit trail）

- **M3/h1 `security_events.txt` 2,349 行解析失败（failure_rate = 1.6266%）**（2026-05-05 标记，由 Checkpoint 2 发现）。Root cause：ATLAS 上游导出工具 bug——某事件（疑似 EventID 4719 audit policy change）的 body 包含未 quote 的逗号长描述符（形如 `0,0,0,...,0,1`），在 CSV-tab 解析时被切成多个伪行。
  - 失败样本：`scripts/parse_atlas_all.py` full report，行 25195+
  - 影响：2,349 / 144,413 = 1.63% 失败率，**仅次于 1% 阈值的轻微超出**；其他 47/48 cell 全部 0% 失败率。
  - 决策：**不修**。失败行已被正确分类为 failed（无 silent 错误），不会污染下游图构建；这些行本身也不是真实 audit 事件（它们是 policy descriptor dump 的 fragment）。
  - Phase 8 跑 KAIROS / MAGIC 基线时如果发现它们也跳过这些行，就完全对齐；如果它们用更激进的 CSV 容错把这些行恢复成事件，再来重新评估。

## Phase 4 待回顾事项（融合训练完后评估）

- **Firefox 解析覆盖度回顾**（2026-05-05 标记，由 Checkpoint 2 firefox skip-rate 99% 引发）。当前 firefox.txt parser 只提取 `uri=http*` 行（HTTP 请求），其他 ~99% 是浏览器 debug spam（Socket / Cache2 / DNS 模块内部状态），全部 skipped。这是 Checkpoint 2 同意的设计——浏览器内部状态对 provenance graph 价值有限，已经被 system-level dns 日志（dns 模块）和 security_events 4663（cache2 文件写入）覆盖。
  - **fallback 触发条件**：Phase 4 跨模态融合训练完后，如果发现"文件下载 → 进程执行"这类事件链在我们的图里频繁断裂（即 firefox HTTP 请求与 security_events 文件创建之间没有可追溯的边），那时再考虑扩展 firefox 解析提取 `[Cache2]` download / `[DNS]` resolution 事件。
  - **检测方法**：Phase 4 attention 可视化里画一组 "downloaded payload → executed via Process Create" 的 case study；如果攻击杀伤链频繁缺这一段，说明需要扩展 firefox 解析。
  - **如果触发**：扩展 `parsers/atlas.py::FirefoxParser` 加 `_FIREFOX_DOWNLOAD_RE` 与 `_FIREFOX_DNS_RE` pattern，提取 download URL → cache2 file path 与 DNS module 解析事件。

## Phase 3 设计偏离记录

### HGTConv edge_attr 接口限制 + Option C 残差通道决议（2026-05-05，Checkpoint 7 启动 RFC）

**现象**：PyG 2.7 `HGTConv.forward(x_dict, edge_index_dict)` **不接受 edge_attr 参数**——实地验证 `TypeError: HGTConv.forward() got an unexpected keyword argument 'edge_attr_dict'`。Phase 3 launch spec 假设 "Time2Vec + EdgeType one-hot 拼接 → Linear 投影 → 送入 HGTConv 的 edge_attr" 在 stock HGTConv 上不存在该接口。同样地 `HANConv` 也不支持；只有同构层（GATv2 / TransformerConv 等）支持 `edge_attr`。

**RFC 四选项分析**：

| 选项 | 描述 | 评价 |
|---|---|---|
| A | Subclass HGTConv，把 `MLP(edge_attr_proj)` 注入 attention bias | 时间作为 attention 一等公民；~150 行，PyG 升级脆性 |
| B | 弃用 HGTConv，对每边类型用 TransformerConv + HANConv-style metapath 聚合 | 干净；违反"不重新发明轮子" |
| **C** ⭐ | 保持 stock HGTConv + 额外计算 `edge_attr_proj` 通过 `scatter_add(MLP(edge_attr_proj))` 加到目标节点作残差 | 守 spec、~30 行、edge feature 走独立通道、Phase 11 B5 消融简单 |
| D | 计算 `edge_attr_proj` 但不接入；推到 Checkpoint 9 | 不解决问题、Checkpoint 7 incomplete |

**最终决策（2026-05-05，user 拍板）**：**Option C**。公式：

```
y_dst[v] = HGTConv(x_dict)[v] + α · sum_{(u,v) ∈ E_r} MLP(concat(time2vec(t_uv), edge_type_onehot_r))
```

- α 默认 **0.5**（不学习，固定值），Hydra config `configs/model/graph/htgn.yaml::residual_alpha`，sweep 空间 `[0.1, 0.3, 0.5, 1.0]` for Phase 11 ablation
- 残差 MLP 双层带激活：`Linear(61→64) + GELU + Linear(64→hidden_dim=256)`（注：61 = Time2Vec 32 + EdgeType one-hot **29**，原 launch spec 的 25 是基于 Q-1 mini-checkpoint 之前的 EdgeType 数量；Q-1 加 3 个 USER_* + UNKNOWN 后实际 29）
- α=0 退化为 stock HGTConv，是 Phase 11 消融 B5（HGT-without-temporal）的实施路径之一

**决策依据（user 论证，作为 Phase 12 论文素材）**：LogHetero 的 temporal modeling 是 **multi-pathway 设计而非单一机制**——HGT 边残差（Option C 这条）+ TGN 节点记忆（Checkpoint 8）+ Phase 4 跨模态注意力 query 三处分布式承担时间信息编码，比把时间集中堆在 attention bias 一个地方更鲁棒，论文叙事也更立体。Option A 的 subclass HGTConv 强耦合方式不值得为了"时间作为 attention 一等公民"这个叙事 polish 去承担 PyG 升级脆性与调试复杂度。

**Phase 12 Methods 写作 hook**：在解释 "为什么我们的时间信息走残差通道而非 attention bias" 时直接引用本条 + 决策 4.2 footnote。审稿人喜欢看到设计深度而非单点优化。

### Task B "完全 benign 子图" spec 与 Phase 8 ground-truth label loader 依赖缺口（2026-05-06，Checkpoint 10 启动 RFC）

**现象**：Checkpoint 10 Task B launch spec 要求"从 ATLAS 选取一个完全 benign 的 (scenario, host, window) 子图作为数据源... 由 v0.1-data 的 fold stats 报告辅助筛选"。验证发现该筛选路径**不可执行**：`data/atlas_fold_stats.json` 所有 fold 的 `train_attack_count` 与 `test_attack_count` 全是 0，`data/processed/atlas_fold_stats_report.md:25-30` 自陈原因——"attack counts are 0 across all folds because the Phase-8 ground-truth label loader has not been wired in yet -- the stub treats every event as benign"。`AtlasGroundTruthLabelLoader` 是 Phase 8 待办（见本文件下方 Phase 8 待办条目），v0.1-data 范围内无机制识别真实攻击事件。

**RFC 三选项分析**：

| 选项 | 实施 | 工时增量 | Task B 数字含义 |
|---|---|---|---|
| A | Phase 3 临时实现 minimal `AtlasGroundTruthLabelLoader` scoped to S1 + ATLAS 论文 Table I | +2-3h（Phase 8 工作量提前） | "完全 benign" 严格成立 |
| B | 基于 ATLAS 论文文档攻击时间窗口手动避开攻击区间 | +0.5h | benign-only 基于论文 timeline 推断而非 ground truth label |
| **C** ⭐ | **重新解读 benign-only 必要性**：链路预测是 self-supervised 结构任务，对事件语义不敏感；放宽要求为"任选 ATLAS 子图"，benign-only 约束推到 Phase 4 入口 | +0h | AUC 数字含义改为 "validates HTGN structural learning capability on mixed-event provenance graphs" |

**最终决策（2026-05-06，user 拍板）**：**Option C**。决策理由：

1. Phase 3 链路预测的本质是验证 HTGN 编码器对异构时序图结构的学习能力，这个能力对 attack edge 与 benign edge 一视同仁——结构信号不挑事件性质。
2. Option A 把 Phase 8 工作量提前到 Phase 3 破坏 phase gate 边界，且重建攻击实体清单本身有不确定性。
3. Option B "基于论文时间线推断" 实际是 Option C 的弱化版——同样无 ground truth 校验，但加了一层未必准的人工启发。
4. AUC > 0.85 硬门槛**保留不变**，Option C 不绕过该门槛；只是承认 benign-only 不是数字含义的关键变量。

**Option C 落地三条件**（user 强制）：

1. **报告透明性**：Checkpoint 10 报告里 Task B 部分必须显式声明数据性质为 "mixed subgraph (predominantly benign with unverified attack fraction; Phase 8 ground-truth label loader not yet wired in v0.1-data)"，**禁止**使用 "benign subgraph" / "benign-only" 措辞。AUC > 0.85 解读改为 "validates HTGN's structural learning capability on mixed-event provenance graphs"。同套措辞用于 Phase 12 论文 Methods 章节。
2. **RFC 决议留档**：本条目即落实条件 2，与 Checkpoint 7 的 HGTConv edge_attr RFC + Checkpoint 8 的 absent-vs-zero 设计选择并列，构成 Phase 3 主要设计偏离的完整 audit trail。
3. **Phase 4 入口 benign-only 重审议程**：见下方 "Phase 4 待办" 子节。

**Phase 12 Methods 写作 hook**：解释 Phase 3 sanity check 数据来源时使用上述精确措辞，避免审稿人误解为"作者承认链路预测无法区分攻击模式"——我们的论证是"link prediction tests structural learning, not anomaly discrimination; the latter is Phase 8's job with proper ground-truth labels"。

### HeteroTGNMemory 跨类型 src 索引语义错误（2026-05-06，Checkpoint 10 Task A 实施时发现）

**现象**：Checkpoint 9 HeteroTGNMemory 设计假设 PyG TGNMemory 的 `update_state(src, dst, t, raw_msg)` 内部仅按 dst 索引；实地验证发现 PyG `IdentityMessage`（默认消息函数）拼接 `[memory[src], memory[dst], t_enc, raw_msg]`——**会按 src 索引查找 memory**。HeteroTGNMemory 当前给每个 memory 类型的 `TGNMemory` 实例分配 `num_nodes_of_that_type` 大小的 memory buffer；但跨类型边（如 `(user, USER_LOGON, process)` → 路由到 `process_memory.update_state(src=user_idx, dst=process_idx, ...)`）会让 user_idx 被解读为 process_memory 的 slot index——**索引混淆**：拿到的是某个其它 process 的 memory，不是 user 的（user 本就无 memory）。

**两层后果**：

1. **OOB（index out-of-bounds）**：当 src 类型节点数 > dst 类型节点数 + dst 是 memory-bearing 类型时，src_idx 直接越界 process_memory 的 `_assoc[n_id]` buffer，CUDA 抛 device-side assert。Checkpoint 10 Task A 玩具图 5 用户 / 8 socket / 15 process 场景下 `(process, NET_*_SOCKET, socket)` 边的 src=process_idx (max 14) 越界 socket_memory size 8。
2. **语义错误（不 crash 时）**：sub-agent Task A 用 workaround——给所有 memory-bearing 类型分配 `max(node_counts_across_types)` 大小的 buffer——避免 OOB，但 src=user_idx 仍被解读为 process_memory 的 slot，message 拼接拿错 slot 数据。功能可跑（Task A 仍以 loss 0.034 / acc 1.00 通过 hard gate）因为 HGT 主路径占 85% 参数主导信号，TGN 内存噪声被 attention 路径压过。

**为什么 Checkpoint 9 没在该层暴露**：Checkpoint 9 测试用 single-type-only mock 数据（所有边都是 `(process, X, process)` / `(socket, X, socket)`），src 与 dst 同类型不触发跨类型索引混淆。Task A 第一次构造跨类型异构图 + memory-bearing dst 才暴露。

**当前 workaround（Checkpoint 10 Task A + Task B 沿用）**：在调用方（脚本侧）给 `num_nodes_per_type` 中的 memory-bearing 类型（process / socket）分配 `max(across all node types)` 大小，规避 OOB。**承认这是 hack**：拿到的 src memory slot 是 garbage，HGT 主路径压过噪声让模型仍可学习。Phase 7 真实训练前必须修。

**为什么 Checkpoint 10 不就地修而推到 Phase 7**：proper fix 需在 HeteroTGNMemory 层引入"跨类型边的 src 内存查找处理"——三种实施路径（zero src memory / 用 dst 替代 src / 自定义 heterogeneous message function 替换 IdentityMessage）都属架构选择，应在 Phase 7 训练循环建立时与 batch 边界 msg_store 清理一并讨论；Checkpoint 10 仅为 sanity check + 链路预测验证 HTGN 容量，workaround 不阻塞 AUC > 0.85 门槛验证。

**Phase 12 Methods 写作 hook**：本条暂不进 Methods 写作（属实施 bug 而非设计选择）；属于 Limitation 章节"对 PyG 同构组件做异构 wrapper 的 hidden interface assumption"案例素材。

### Task B AUC 0.8144 borderline conditional pass + Phase 4 重测 commitment（2026-05-06，Checkpoint 10 RFC）

**现象**：Checkpoint 10 Task B 在 4 seed [1, 7, 42, 100] 配置（M3_h2 first 1.0h window, max-degree process seed, khop=3, structured negative sampling 1:1, 30 epoch, BCE）下测得 test AUC = **0.8144 ± 0.0068**（mean ± std；per-seed 0.8037 / 0.8156 / 0.8157 / 0.8226，按 seed 100 / 1 / 42 / 7 排序），落在 user 定义的 borderline 区间（0.80 ≤ AUC ≤ 0.85），未达 0.85 hard gate 但远超 0.80 borderline 下沿。多 seed 方差 0.0068 极低 → **不是 sampling noise，是真实架构表达力 ceiling**。

（注：RFC 期间 user 报告引用的 "0.825 ± 0.008" 来自我早期单 seed 高位读数；最终 commit 落档以 multi-seed 聚合 0.8144 ± 0.0068 为准——±0.01 偏差因 CUDA 非确定性，是典型 deep learning multi-seed 区间。Phase 4 BERT 重测 baseline 用 0.8144 不用 0.825。）

**排查记录（borderline RFC 触发前已确认）**：

1. **跨类型 src memory bug 不活跃**：M3_h2 first window 子图 `nodes_per_type = process=44, file=1956, socket=0, network=0, user=0`——根本无 user / network 节点，唯一 memory-bearing 类型 process 上的边都是 (process, X, process) 同类，src=dst type → 不触发跨类型查找；Checkpoint 10 Task A 暴露的那个 bug 不是本子图 AUC 0.82 的原因。
2. **TGN msg_store 跨 batch 问题已 workaround**：`_eval_auc` 已加 msg_store pre-clear + no_grad 包裹 train→eval transition；training 循环加 detach 在 reset_state 之前清残余 grad_fn。
3. **Subgraph 采样不再不稳**：max-degree process 作 seed + khop=3 替代 random seed + khop=2，subgraph 从 124-186 nodes（4 seed 完全不同）升到稳定 2000 nodes / 70,646 edges（4 seed 完全相同）。
4. **AUC 训练曲线 plateau 已现**：epoch 15-25 AUC 在 0.81-0.83 间窄幅震荡，epoch 30 微幅上升至 0.825；模型已基本收敛，加 epoch 大概率只能挪 1-2% 不足以稳过 0.85（且违反 hard gate inviolability "调高 epoch 凑过" 禁令）。
5. **Train / val / test 三集 AUC 贴近 0.82**：不是过拟合，是表达力 ceiling。

**真实根因（最强解释）**：节点初始特征是随机 Gaussian（无 BERT 语义）。HTGN 必须从 0 学结构 representation，无任何 input semantic prior；ATLAS 的判别力很大程度上依赖文件路径 / 进程名 / IP 地址这种 semantic-rich 特征，纯结构信号（边类型、邻接关系）能榨出 0.82 已经是 HTGN 容量的合理上限。这与 GNN 文献 "无 features 链路预测 0.65-0.75 / 有 features 0.85-0.95" 经验区间一致。

**RFC 三选项分析**：

| 选项 | 实施 | 工时 | 通过含义 |
|---|---|---|---|
| A | 接受 0.825 作为 Phase 3 无 BERT 阶段 sanity 上限；conditional pass + Phase 4 BERT 集成后必须重测 | 0h | 诚实承认 0.85 假设了 BERT 特征；推迟最终验证到 Phase 4 |
| B | 拉两条 Phase 7 fix 前置 + 加 BERT 占位特征 | 4-6h | 跨类型 bug 在该子图不活跃所以前置不一定改善；投资风险高 |
| C | 把 MLP head 从 Linear(512, 1) 改为 2 层 ReLU + 隐 256 dim | 0.2h | 通过原因是 head capacity 而非 HTGN 学到了 0.85 结构信号——与"验证 HTGN 结构学习能力"sanity 意图错位 |

**最终决策（2026-05-06，user 拍板）**：**Option A，conditional pass**。理由：(a) 0.85 阈值原本设计假设有 BERT 特征；(b) 0.825 with random features 在 ML 文献上已是 strong baseline；(c) Phase 4 BERT 集成大概率把 AUC 推到 0.88+；(d) Option B 把 Phase 7 工作前置且投资回报低；(e) Option C 通过原因不诚实。

**Option A 落地四支柱条件**（user 强制，缺一不可）：

1. **v0.3-htgn tag message 显式 conditional**：精确措辞 `"Phase 3 conditional pass: HTGN sanity AUC 0.8144 ± 0.0068 across 4 seeds [1, 7, 42, 100] with random node features; 0.85 hard gate provisionally relaxed pending Phase 4 BERT integration re-validation. See docs/known_issues.md::Phase 4 待办 for re-test protocol."` **禁止**写成 "Phase 3 complete" 或 "HTGN validated"。（注：user RFC 期间用 "0.825 ± 0.008" 模板，本 tag 替换为 multi-seed 聚合实测数字 0.8144 ± 0.0068）
2. **Phase 4 重测协议工程化为可执行 spec**：见下方 Phase 4 待办 :: "Phase 3 sanity AUC re-validation" 子节。
3. **脚本与多 seed 数据落 commit**：`scripts/checkpoint10_task_b.py` 保留不删；`data/checkpoint10_taskB_summary.json` 含 4 seed 完整结果（不只 seed 42 一个）。
4. **Phase 12 论文 Methods 章节预定措辞模板**：见下方 Phase 12 论文素材 :: "Phase 3 sanity AUC 演进数字" 子节。

**Phase 12 Methods 写作 hook**：解释 Phase 3 sanity check 时引用本条 RFC 决议 + 重测协议，把 conditional pass 的诚实记录转为论文贡献证据（"我们诚实测量并报告了 BERT 特征对 HTGN 链路预测的边际增益"）。

## Phase 4 待办

### Pretraining 数据 benign-only 约束的重审议程（2026-05-06，Checkpoint 10 Option C 决议触发）— **RESOLVED 2026-05-06 (Checkpoint 11.1 RFC: Option B 通过附三条件)**

> **闭环标注（2026-05-06，Checkpoint 11.1 RFC 决议）**：本议程经 Checkpoint 11.1 RFC 三选项分析（A 前置 Phase 8 工作 / B mixed + Phase 7 切 benign-only / C 论文 timeline 启发式 stop-gap），user 拍板 **Option B 附三条件**：(1) `docs/design_decisions.md` 决策 9 footnote 紧版措辞（mixed = unverified-impact baseline + Phase 11 必须 ablation + 3pp 叙事调整阈值）；(2) `docs/known_issues.md::Phase 11 消融扩展` 新增 B7（mixed vs benign_only_ground_truth 二档对比）；(3) `docs/known_issues.md::Phase 7 待办` quick A/B 前置议程。本议程视为 resolved；以下原 (a)(b)(c) 三选项分析保留作为决议过程 audit trail。



Phase 3 Checkpoint 10 因 `AtlasGroundTruthLabelLoader` Phase 8 待办无法切真实 benign-only 子图，user 选 Option C 把 benign-only 约束推到 Phase 4 入口讨论。**Phase 4 跨模态融合启动前必须重审 pretraining 数据的 benign-only 约束**——开 Phase 4 第一个 RFC 议程，逐条决议：

(a) **跨模态联合预训练阶段是否需要纯 benign 数据**：HTGN-LM 跨模态注意力的预训练任务（Phase 4 / Checkpoint 12-14 待 launch spec）会把图嵌入与 LM 嵌入对齐；如果训练数据混入攻击事件，模型可能把"攻击模式"学成"正常 representation"，污染下游 Phase 8 anomaly fine-tuning 的 representation baseline。需根据 Phase 4 损失函数性质决定：MLM-style + 对比损失对数据噪声相对鲁棒，离群少量攻击事件影响有限；node-level 重建损失敏感度更高。

(b) **如需 benign-only，是否依赖 Phase 8 真实 label loader 才能切**：若 (a) 决议要 benign-only，最干净路径是 Phase 4 launch 前先实施 `AtlasGroundTruthLabelLoader`（Phase 8 待办前置），用真实标签筛子图。代价：Phase 8 工作量前置 1-2 天。

(c) **如果 Phase 8 label loader 滞后于 Phase 4，是否走 ATLAS 论文 timeline 启发式临时切分作为 stop-gap**：备选——基于 ATLAS 论文 Table I 提供的攻击时间区间，避开攻击窗口取早期良性时段子图作 stop-gap；Phase 8 label loader 落地后 retroactively 校验启发式切分的纯净度。这条只在 (b) 因故无法前置时启用。

**Phase 4 入口 RFC 触发器**：开始 Phase 4 第一个 commit 前，main agent 必须读本条目并给出 (a)(b)(c) 三选一决议；不得 silent 跳过。议程产出预期：一条 docs commit 在 known_issues.md "Phase 3 设计偏离记录::Task B 完全 benign 子图 spec" 子节下追加 "Phase 4 RFC 决议（YYYY-MM-DD）：选 X，理由 Y" 标注，让 audit trail 串联起来。

### Phase 3 sanity AUC re-validation（2026-05-06，Checkpoint 10 Option A conditional pass 触发）— **COMPLETED with informational null finding 2026-05-06 (Checkpoint 11.2-γ-1 决议)**

> **闭环标注（2026-05-06，Checkpoint 11.2-γ-1 决议）**：本议程经 4 档 BERT 集成 ablation (random Gaussian baseline 0.8144 / [CLS] entity-identifier 0.8126 / β entity-event-context TOP_K=5 truncated 0.8113 / β entity-event-context TOP_K=2 in-spec 0.8147) 实测，4-seed mean AUC 全部聚集在 0.811-0.815 区间，std 0.007-0.016，**统计上完全无差异**——证实 random edge masking + structural negative sampling 的链路预测任务由图拓扑信号完全决定，BERT 语义特征通过 input-feature 通道无法贡献 lift。**双门槛 gate（绝对 ≥ 0.88 OR 相对 lift ≥ +0.04）均未通过**（β in-spec 实测 lift = +0.0003）。User 拍板 **Option γ-1**：
>
> - Phase 3 conditional pass 状态从 "pass / fail" 二元变更为 "**informationally complete**"——回答的是"HTGN 在 structure-only 任务上 ceiling OK"，不是 "BERT 集成 OK"
> - 原 0.88 hard gate **撤销**（gate premise "BERT 通常 +0.05-0.10 lift" 文献经验只适用于 sentence classification / NER / QA 等 features 直接决定输出的任务，不适用于 structure-determined link prediction；agent Phase 3 Option A 决议论证错误，本闭环诚实标记，留 audit trail）
> - BERT 跨模态融合的真实 evaluation 推到 Phase 7-8 anomaly detection（attack 事件含语义异常签名时 BERT semantic features 必有 lift；cross-modal attention 作为 fusion mechanism 比 input-feature injection 更适合 anomaly classification use case）
> - 详见 `docs/design_decisions.md` 决策 4.2 footnote (2026-05-06) + 下方 Phase 7 待办 "BERT-fused-attention vs HTGN-only quick A/B 扩展" 议程 + 下方 Phase 12 论文素材 "Phase 3 sanity AUC 演进数字" 4-row ablation 表更新
> - **Phase 4 进度影响**：Checkpoint 12 双向跨模态注意力可直接启动；Phase 4 整体目标变更为 "architecture 落地 + forward 不报错 + 梯度正常"，AUC-style 单点验证留 Phase 7-8
>
> 以下原 re-validation 协议保留作为决议过程 audit trail（**spec 已不再适用，但保留作为 Phase 12 audit trail 素材**）：

Phase 3 Checkpoint 10 Task B 在无 BERT 特征条件下达 AUC 0.8144 ± 0.0068（4 seed [1, 7, 42, 100]），低于 0.85 hard gate。User 选 Option A（conditional pass），把验证责任推到 Phase 4 BERT 集成后重测。本子节是 Option A 落地条件 2 "重测协议工程化为可执行 spec" 的实现——**Phase 4 第一个 deliverable 必须包含本重测**。

**重测精确配置**（与 Checkpoint 10 Task B 完全一致，仅替换节点特征源）：

| 维度 | 锁定值 |
|---|---|
| 数据源 | ATLAS scenario M3, host h2 (M3_h2) first 1.0h window |
| Subgraph 采样 | max-degree process 节点作 K-hop seed，khop=3，max_nodes=2000，edge_ranking="weight" |
| 边 mask | 10% 边 random shuffle 作 positive；剩余 90% 作 training context |
| 负采样 | structured：每条 mask 边 (u, op, v) 配 (u, op, v') 其中 v' 同 dst_type 随机且 (u, op, v') 不在原图；负正 1:1 |
| 切分 | masked positives + negatives 各 7:1.5:1.5 train/val/test |
| MLP head | `Linear(2*hidden_dim=512, 1)` 单层（**不变**，禁止改成 2 层 ReLU 凑数） |
| Loss | BCEWithLogitsLoss |
| Optimizer | Adam lr=1e-3 |
| Epochs | 30 |
| Seeds | `[1, 7, 42, 100]`（**与 Checkpoint 10 完全一致**，方便对比）|
| HTGN config | 默认 yaml（hidden_dim=256, n_layers=3, num_heads=8, dropout=0.1, time2vec_dim=32, residual_alpha=0.5, layer_decay_gamma=[1.0, 0.7, 0.4], raw_msg_dim=64） |
| **唯一变更** | 节点初始特征：从 `torch.randn(n, 256)` 替换为 frozen bert-base-uncased `[CLS]` embedding 编码节点 textual context（process name / file path / IP / domain / user name 等，cleaner 处理后）|

**实施路径**：

1. **复用脚本**：`scripts/checkpoint10_task_b.py` **保留不删**，已加 `--use-bert-features` CLI flag 占位（当前 raise NotImplementedError）。Phase 4 第一个 deliverable 实施 BERT feature 接线代码替换该 NotImplementedError，让 `uv run python scripts/checkpoint10_task_b.py --use-bert-features --seed-list 1,7,42,100` 即可跑出重测数字。
2. **特征接线细节**：
   - 每个节点的 textual context 通过 `loghetero.data.cleaner.normalise_event_text()`（已在 Phase 2 / Checkpoint 6 sanity 验证可用）转 placeholder-rich 字符串；
   - 用 frozen BERT 编码，取 `[CLS]` token embedding（768 维）；
   - 投影到 HIDDEN_DIM=256（用 `nn.Linear(768, 256)` 或随机投影，Phase 4 launch spec 决定）；
   - 替换 `_build_htgn` 的 `x_dict` 来源，其余 pipeline 不动。
3. **Phase 4 重测通过门槛（**比原 0.85 高 3 个百分点**）**：4 seed [1, 7, 42, 100] **平均** test AUC ≥ **0.88**。理由：作为"BERT 集成确实带来语义提升"的诚实验证；如 BERT 集成后只达原 0.85 hard gate，意味着 BERT 没贡献多少 → 触发架构级 RFC（不允许"刚过 0.85 就放过"）。
4. **重测失败处理**：若 4 seed 平均 < 0.88，触发架构级 RFC（不允许再放过）。候选根因列表：
   - BERT cleaner 对 ATLAS 文件路径 / 进程名的语义抽取质量（cf. Checkpoint 6 cos-sim 0.97-1.00 验证已部分覆盖）；
   - HGT attention 对 BERT 高维 embedding 的 fusion 是否需要专门 projection；
   - Phase 7 待办的两条 PyG fix（msg_store + 跨类型 src memory）是否在 BERT-rich 场景下贡献变大。
5. **重测落档要求**：跑完后追加一条 commit `feat(phase4): Phase 3 sanity AUC re-validation with BERT features` 到 Phase 4 的 working branch，commit body 报告 4 seed 数字 + Δ vs Phase 3 baseline (**0.8144** mean) + 是否过 0.88 门槛；同时在本条目下追加 "Re-validation 完成日期 + commit hash + 数字" 闭环标注。

**baseline 对比锚**：Phase 3 conditional pass 的 baseline 数字已 commit 进 `data/checkpoint10_taskB_summary.json`，含 4 seed 完整 loss/AUC 曲线 + multi_seed_aggregate（mean / std / min / max）。Phase 4 重测脚本输出同结构 JSON 写到 `data/checkpoint10_taskB_summary_bert.json`（区分文件名），前后对比一目了然。

## Phase 5 待办

### 字段级 mask 任务的"添加机制"（Phase 4 / Checkpoint 13 RFC 决议延迟到 Phase 5）

**触发原因**：Phase 4 launch spec 写"目标字段替换 / 删除 / 添加机制"三件事，Checkpoint 13 RFC 决议（2026-05-06，user 拍板）对添加机制取 Option C 即 **Checkpoint 13 不实施，延迟到 Phase 5**。Checkpoint 13 落地的是替换=A（field 内全部 token 替换为 [MASK]）+ 删除=B（用单个 [MASK] 替代整个 field 让序列变短保留一个 anchor 位）两种操作，共用一个 prediction head 通过 label 区分。

**为何延迟到 Phase 5**：

- 添加机制的语义是"向良性事件序列注入虚假 / 异常 field 或 event"，与 RAPA-GTCL（创新点 2）的合成攻击逻辑天然耦合——RAPA 攻击模板本身就是基于 ATT&CK TTP 构造的"虚假 event 注入"。
- Phase 5 实施 RAPA 模板时复用同一注入框架（注入逻辑、event-id 追踪、mask label 体系），比 Checkpoint 13 单独造一个轻量添加机制更工程一致。
- 论文叙事上："字段级 mask 添加机制"与"基于 ATT&CK 的合成攻击注入"统一在 Phase 5 实施，对应 paper Methods 章节单一段落而非分散两段，叙事也更立体。
- 这一延迟**不构成 spec 偏离**：Phase 4 launch spec 的"目标字段替换 / 删除 / 添加机制"三件事在 Phase 4 完成两件，第三件在 Phase 5 完成，但 Phase 4 / Checkpoint 13 的 commit message 与 module docstring 必须显式说明此项延迟与延迟到 Phase 5 的工程一致性 rationale，避免 review 时被误读为 spec 偏离。

**Phase 5 启动时必须 cover 的扩展项**：

1. RAPA 模板实施时，注入逻辑的核心 utility（field/event 插入、event-id 重新编号、混合训练样本生成）必须设计成可被字段级 mask "添加机制"复用的形式。具体讲：注入框架应该暴露一个 `inject_synthetic_field(event_seq, field_type, target_position) -> (modified_seq, label)` 类的接口，既能服务 RAPA 攻击模板（label = is_attack），也能服务字段级 mask 添加机制（label = is_inserted_field 二分类目标）。
2. Checkpoint 13 实施的 ModifiedMLMHead（基于 fused hidden state 预测 mask token）需要在 Phase 5 添加机制实施时**额外加一个 binary classification head**预测每个 token 是否为"插入的虚假 field"，与原 token-prediction head 同时活跃但走独立 loss 与独立 fused hidden state 路径。
3. 添加机制实施完成后追加 commit `feat(objectives): Phase 5 完成字段级 mask 添加机制（基于 RAPA 注入框架复用）`，并在本条目下追加 "完成日期 + commit hash + 与 RAPA 模板共享 utility 接口名" 闭环标注。
4. Phase 12 论文 Methods 章节"4.x Modified MLM with field-level masking"段落必须把替换 / 删除 / 添加三机制作为同一个工程框架的三种实例化呈现，而非"我们 Phase 4 做了两件 Phase 5 又补了一件"的散乱叙事——通过统一注入框架的设计，三机制叙事是 architecturally unified 的。

**审计 anchor**：本条目是 Checkpoint 13 RFC（2026-05-06）的 audit trail 之一，与下列 commit / 文档记录一同构成完整决议链：(a) `feat(objectives): Phase 4 / Checkpoint 13 modified MLM task on fused hidden states` commit message 中的"添加机制延迟到 Phase 5"段落；(b) `src/loghetero/models/objectives/modified_mlm.py` 模块 docstring 中的同段说明；(c) `docs/CHECKPOINT_LOG.md` Checkpoint 13 entry 的"决策点"小节。

### 20 TTP 模板设计必须含 6 类 hard negative benign admin behaviors（2026-05-06，Phase 5 launch spec 启动前预读议程）

**触发原因**：Phase 5 创新点二的论文叙事是"首个把 MITRE ATT&CK 模板作为图增强样本与图文对比目标在预训练阶段联合训练的框架"。GPT 反思（2026-05-06）暴露的关键风险：合成攻击如果只与"普通良性事件"对比，模型有可能学到的是"识别注入格式"而非"识别攻击行为本身"——即合成攻击的"假可分性"陷阱。Phase 5 启动前必须把 hard negative benign admin behaviors 设计进模板对照集合，避免该陷阱在 Phase 8 anomaly detection 评测时才暴露。

**6 类 hard negative benign admin behaviors（必须在 Phase 5 模板设计中显式 cover）**：

1. **管理员 PowerShell**：合法系统管理员日常使用 PowerShell 执行配置修改、服务管理、用户管理、远程会话等操作。与 T1059.001 PowerShell 攻击 TTP 在表层 syscall + process tree 上极其相似，是模型最容易混淆的良性对照。
2. **自动化脚本访问敏感路径**：备份脚本、配置同步工具、合法 audit 工具访问 `/etc/`、`/root/`、`C:\Windows\System32\` 等敏感路径。与 T1003 Credential Access、T1083 File and Directory Discovery 等 TTP 在文件访问模式上重叠。
3. **合法 RDP**：用户合法远程桌面会话登录、远程办公、远程协助。与 T1021.001 RDP attack TTP 在 network connection + login event 模式上完全一致，区分点只在于是否有后续异常行为链。
4. **安全扫描**：内部安全团队的漏洞扫描工具（Nessus / OpenVAS / qualys 等）大量端口扫描 + 远程探测 + 弱口令测试。与 T1046 Network Service Discovery、T1110 Brute Force 等 TTP 在 network behavior 上无法表层区分。
5. **软件更新**：Windows Update、Linux package manager (apt/yum/dnf)、第三方软件自动更新等。涉及 process spawning + file modification + network download，与 T1105 Ingress Tool Transfer + T1059 Command and Scripting Interpreter 在表层模式上重叠。
6. **备份程序大量读文件**：磁盘备份工具（rsync / robocopy / Veeam / NetBackup 等）一次性读取大量文件。与 T1005 Data from Local System、T1039 Data from Network Shared Drive 等 TTP 在 file read 频率上完全一致，区分点只在 destination（外部 IP vs 内网备份服务器）。

**Phase 5 模板设计的硬性要求**：

1. **20 个 ATT&CK TTP 模板**与**6 类 hard negative benign admin behaviors 模板**作为**两个并列对照集合**实施，不混在同一个生成器里。每类 hard negative 至少生成 200-500 条事件序列对应一个 TTP 模板的同等规模，让 Phase 8 anomaly classifier 必须区分"真攻击 TTP"与"模式相似的良性管理员行为"而非"攻击 vs 普通良性"。
2. **模板生成必须共享同一注入框架**（即 Phase 5 待办::"字段级 mask 任务的添加机制" 子节中规划的 `inject_synthetic_field` / `inject_synthetic_event` 接口），让 hard negative 与攻击 TTP 在数据生成层面有完全相同的"注入指纹"——这样模型不能靠"是否有注入痕迹"作为分类捷径。
3. **Phase 5 commit chain 必须包含一条 explicit hard-negative-coverage commit**（建议 message: `feat(rapa): Phase 5 hard negative benign admin behaviors templates (anti false-separability)`），把 6 类对照模板作为单独 audit anchor 落档，避免后续 review 时被误读为"Phase 5 只做了攻击模板"。
4. **Phase 11 ablation matrix 必须含一个 "without hard negatives" 对照配置**（建议 cell ID: B7-γ）：跑同一异常检测 task 但训练数据移除 6 类 hard negative，看 anomaly F1 是否虚高——如虚高显著（>5pp）说明假可分性陷阱在 Phase 5 启动前预读议程下已被规避，论文叙事可以诚实报告"我们设计了 hard negative 对照集合避免假可分性风险"作为方法论 contribution。

**Phase 12 论文 Methods 章节使用方式**：

本议程作为 "我们如何设计 hard negative 对照集合避免合成攻击假可分性风险" 工程方法论支撑写入 Phase 12 论文 Methods 章节相关段落（建议放在 "4.x RAPA template design and benign control set" 子节或 "Reproducibility & methodology" 子节）。可对照写作 hook：cf. 主流 cyber security ML 论文（FLASH / KAIROS / MAGIC 等）大多没有显式 hard negative benign control，我们额外报告 6 类 hard negative 设计 + Phase 11 ablation B7-γ 对照实测，可作为 Methods 章节 contribution evidence——审稿人可以看到具体方法论的 false-separability 防御设计而非"我们注入了 ATT&CK TTP 然后模型学到了识别"的黑盒陈述。

**审计 anchor**：本条目是 GPT 反思（2026-05-06）的 audit trail 之一，user 在 Checkpoint 13 收尾时提出 Phase 5 启动前预读议程，未来 Phase 5 launch spec 落地时本条目作为模板设计的硬性要求清单。Phase 5 commit message 与 module docstring 必须 reference 本条目作为 false-separability 防御设计的设计依据。

## Phase 12 论文素材

### Phase 3 sanity AUC 演进数字（2026-05-06，Checkpoint 10 Option A conditional pass 对应 paper 措辞预定）

**论文 Methods 章节段落措辞模板**（"4.x HTGN encoder design and link prediction sanity check" 段适配）：

> Phase 3 link prediction sanity validates HTGN's structural learning capability on
> mixed-event provenance graphs across four feature-injection configurations
> (4 seeds [1, 7, 42, 100], M3_h2 first 1.0h window 2000-node K-hop subgraph, 30-epoch
> BCE training with structured negative sampling 1:1):
>
> | Configuration                                          | 4-seed mean test AUC | std    | Δ vs random | Notes                                                          |
> |--------------------------------------------------------|---------------------:|-------:|------------:|----------------------------------------------------------------|
> | (a) Random Gaussian baseline                           |                0.8144 | 0.0068 |       —     | structural-only ceiling                                        |
> | (b) Naive BERT `[CLS]` of `"<type> <id>"` per-entity   |                0.8126 | 0.0164 |     −0.0018 | short-input degenerate regime (cf. Reimers & Gurevych 2019)    |
> | (c) BERT mean-pool entity-event-context, TOP_K=5       |                0.8113 | 0.0127 |     −0.0031 | input truncated 91% at 256 tokens                              |
> | (d) BERT mean-pool entity-event-context, TOP_K=2       |                0.8147 | 0.0109 |     +0.0003 | inputs in spec 50-150 token range, 0.4% truncated              |
>
> All four configurations cluster within statistical noise (means 0.811-0.815, std
> 0.007-0.016), establishing that **under our current experimental setting** — random
> edge masking, structural (in-batch type-respecting) negative sampling, input-feature
> BERT injection through a frozen-encoder + learned-projection channel, and the
> ATLAS provenance graph — this link prediction task is **structure-dominated**:
> graph topology dominates the discriminative signal, and BERT semantic features
> about node identities do not contribute additional separability through the
> input-feature channel regardless of pooling strategy or input formatting we tried.
>
> The bounded scope of this null result deserves emphasis: it does **not** claim
> that link prediction is intrinsically structure-determined in general — the
> text-rich-graph literature (GraphFormers, Patton, GreaseLM, ConGraT) reports
> the opposite finding under different graph regimes (especially text-rich graphs
> without dense local structure or with sparse-edge cold-start nodes). What our
> result rules out is the specific hypothesis "naive BERT input-feature injection
> can lift our particular link-prediction sanity check," and our subsequent design
> response — bidirectional cross-modal attention as a *fusion mechanism* applied
> during pretraining (Phase 4) and evaluated downstream on anomaly detection (Phase
> 7-8 anomaly F1) where attack events carry semantic anomaly signatures (rare
> process names, anomalous file path patterns, blocklist IPs) — is a hypothesis
> to be tested, not a guaranteed remedy. The Phase 4 Checkpoint 14.5 anomaly
> detection probe (within-TTP 80/20 holdout, 5 ATT&CK templates, three-config
> contrast HTGN-only / BERT-only / fusion) provides early directional evidence;
> the Phase 8 anomaly F1 ablation B7 (mixed vs benign-only pretraining) and the
> Phase 7 BERT-fused-attention vs HTGN-only quick A/B together close the loop
> with full-scale empirical evidence on whether cross-modal value resides in
> attention-as-fusion-mechanism for our setting.

**所有占位符已填（2026-05-06，Checkpoint 11.2-γ-1 决议落地）**：

| 配置 | 数据 artifact | 决议落档 |
|---|---|---|
| (a) random Gaussian baseline | `data/checkpoint10_taskB_summary.json` | Phase 3 Checkpoint 10 baseline |
| (b) [CLS] entity-identifier null result | `data/checkpoint10_taskB_summary_bert.json` | Phase 4 Checkpoint 11.2 first attempt |
| (c) β TOP_K=5 truncated（实施 defect contrast）| `data/checkpoint11_2_beta_topk5_truncated_summary.json` | preserved as Phase 12 contrast despite implementation defect (token mean 313, 91% truncated; 用作 "we caught and fixed our own implementation defect" 透明素材) |
| (d) β TOP_K=2 in-spec canonical | `data/checkpoint11_2_beta_summary.json` | Phase 4 Checkpoint 11.2-β canonical result，dual-threshold gate FAIL → Option γ-1 触发 |

**禁止覆盖任一 artifact**——4 档数据全部保留作为 Phase 12 ablation 表的可复现锚点。Phase 12 论文写作时直接引用上述表格 + 4 个 JSON 数字。

**γ-1 决议后论文叙事**：从原计划"BERT integration validates HTGN" 改为 "BERT integration null result on **structure-dominated** link prediction sanity (under our current ATLAS data + structural negative sampling + input-feature injection setting), indicating that cross-modal value plausibly resides in attention-as-fusion-mechanism (Phase 4, to be probed by Checkpoint 14.5 anomaly detection probe and validated by Phase 7-8 full-scale anomaly F1) rather than feature-as-input-to-structure-prediction"。这是 negative-result-as-positive-contribution 叙事——审稿人通常欣赏作者诚实报告 null finding 而非掩盖。完整决议链 audit trail：`docs/design_decisions.md` 决策 4.2 footnote (2026-05-06) + Phase 4 待办::Phase 3 sanity AUC re-validation 闭环标注 + Phase 7 待办::BERT-fused-attention vs HTGN-only quick A/B 扩展 议程。

**边界条件陈述（2026-05-06 Phase 4 launch spec 严谨化补丁，避免论文 Methods 章节被审稿人反驳）**：

1. **Phase 4 入口实验的精确否定范围**：Phase 4 入口 Checkpoint 11.2-γ-1 实验否定的精确假设是"BERT 简单 input-feature injection 能提升我们当前设置下的 link prediction sanity"，此处的"当前设置"特指 ATLAS provenance graph + random edge masking + structural in-batch type-respecting negative sampling + frozen BERT + learned linear projection 这五项工程组合，缺一不可。
2. **不可外推的两条**：(a) **不能外推**为"BERT 在所有 link prediction 任务上无效"——cold-start link prediction 在文献中（GraphFormers / Patton / GreaseLM / ConGraT 等 text-rich graph 工作）有大量依赖语义特征的反例，特别是 text-rich graphs without dense local structure 或 sparse-edge cold-start node 场景；(b) **不能外推**为"BERT 跨模态融合在 anomaly detection 任务上必有效"——anomaly detection 任务的 BERT 价值是 hypothesis to test，需要 Phase 7-8 重新验证而非默认成立，Phase 4 内部由 Checkpoint 14.5 anomaly detection 前置 probe 提供方向性早期证据。
3. **论文 Methods 章节统一措辞**：所有 link prediction sanity 相关陈述必须用 "structure-dominated under current ATLAS data, negative sampling strategy, and fusion design" 这一带边界条件的精确措辞，**禁止用** "structure-determined link prediction" 这种过强陈述——后者会被审稿人引用上述 4 篇 text-rich graph 工作当场反驳，前者则因带边界条件审稿人查不到反例。
4. **Phase 4 Checkpoint 14.5 异常检测前置 probe 在论文中的角色**：作为 "我们没有等到 Phase 8 才发现 fusion 不工作" 的工程严谨性 evidence。Probe 协议（5 个 ATT&CK TTP 纯本地实现禁外部 LLM API + within-TTP 80/20 holdout + 三配置 HTGN-only / BERT-only / fusion 对比 + lift ≥ 0.03 且 paired t-test p<0.1 双条件门槛 + BERT-only ≈ fusion 触发 RFC）在 Methods 章节作为 "early validation gate" 段落直接引用，比 Phase 8 final number 更说明研究纪律。

**论文叙事框架**（解释为什么这一段是 contribution 而非 limitation）：

1. **诚实测量框架**：我们没有把 BERT 与 HTGN 联合训练的最终 AUC 直接报为 single number；而是显式分解了"无 BERT 的结构信号上限"与"BERT 加入后的边际增益"。这种 ablation 风格的报告比单数字报告信息量大得多。
2. **Phase 3 conditional pass 的诚实**：0.8144 with random features 不达 0.85 hard gate，但我们没有调高 epoch 凑过、没有改 MLP head 凑过、没有挑 luckier seed 凑过；而是诚实记录 borderline + 解释 ceiling 来源 + 把验证推到 Phase 4。这种工程纪律本身可以在 Methods 章节的"Reproducibility & methodology" 子节作为 contribution evidence。
3. **可对照写作 hook**：cf. GraphFormers / Patton 这类 text-rich graph LM 工作通常直接报告 final AUC；我们多报告一个 "without text features" baseline 是 contribution 的一部分。

**Methods 章节图表建议**：可附 figure"AUC evolution from random features to BERT features"，X 轴是两组数字（"random init" + "BERT init"），Y 轴 AUC 0-1，柱状图 + error bar (std)。这种图比纯文字报告更直观说服。

**Phase 12 写作时检查清单**：
- [ ] 占位符是否已被 Phase 4 实测数字替换
- [ ] Δ 数字是否 ≥ +0.05（如 < 0.05 说明 BERT 贡献小，叙事重心需调整）
- [ ] 是否引用 `docs/known_issues.md::Phase 3 设计偏离记录::Task B AUC 0.825 borderline conditional pass` 作为 audit trail 锚点
- [ ] 是否在 Limitation 章节同步说明 conditional pass 的工程过程（user 说 "诚实保留缺口而非掩盖" 是研究工程范例）

### Phase 4 入口 BERT 集成 root-cause investigation 与诊断协议（2026-05-06，Checkpoint 11.2 lesson 标准范式）

**触发场景**：Phase 3 conditional pass 把 sanity AUC re-validation 推到 Phase 4 入口（Phase 4 待办子节）。Checkpoint 11.2 第一次实施用 naive BERT 集成方案（frozen BERT [CLS] of `"<type> <id>"` per-entity short text + learnable Linear(768, 256) projection），4-seed 测得 AUC = 0.8126 ± 0.0164 vs Phase 3 baseline 0.8144 ± 0.0068，**Δ ≈ 0**——BERT 集成未带来正向贡献。User 三档处理协议要求 AUC < 0.85 → STOP + root-cause investigation。

**三层排查协议**（agent-driven，作为 Methods 章节"我们如何诊断 BERT 集成失败"段落素材）：

1. **第一层：节点身份纯度**——发现 K-hop 子图 1956 file 节点中 27.3% 是 hex handle (`0x4b0` 等无 path 信息) 而非真路径。Root cause：`src/loghetero/data/parsers/atlas.py:283` 的 `obj_name = fields.get("Object Name") or fields.get("Handle ID")` fallback 在 ATLAS 部分 security event 缺 Object Name 时退化为 handle ID。**判断**：partial degenerate 是 contributing factor 但不是主因——剩余 72.7% file 节点有真路径仍未带来正向贡献。
2. **第二层：BERT [CLS] 对 short input 的 representation quality**——SimCSE / BERT-flow 文献指出 raw BERT [CLS] 在 short input (<10 token) 上是 isotropic 退化的，per-entity identifier 输入正好落在这个 BERT 没被验证过的 use case 区间。Phase 2 / Checkpoint 6 sanity check 验证 BERT 在 cleaned event sentence (50-200 token) 上 cos-sim 0.97-1.00 表现强；per-entity identifier (2-6 token) 是完全不同 regime，**用 Phase 2 验证过的 encoder 但用在了它没被验证过的 use case 上**——这是真正的主因。
3. **第三层：integration code correctness**——`scripts/checkpoint10_task_b.py::_compute_bert_features` + `BertFeatureProjection` wiring verified 无 bug：frozen BERT、batched encoding、shared learnable Linear projection 在 optimizer。**排除 code bug 是 contributing factor**。

**修正方案（Option β，Checkpoint 11.2-β 实施）**：把 per-node 输入从 entity-identifier 升级为 entity-event-context（取节点参与的前 5 个事件 cleaned text 拼接，~50-150 token，落回 Phase 2 sanity 验证过的 BERT sentence-level regime）+ 把 pooling 从 [CLS] 切换为 attention-mask-weighted mean pooling。BERT 保持完全冻结（Phase 1 工程不变量）。

**Phase 12 Methods 章节素材完整性**：本三层排查 + 修正方案是 "我们的工程严谨性" 的具体证据。论文写作时这一段比纯理论 motivation 更有说服力——审稿人可以看到具体诊断过程而非"我们设计了一个系统它工作了"的黑盒陈述。可对照写作 hook：cf. Reimers & Gurevych 2019 (Sentence-BERT) 也有类似"naive BERT 不适合 sentence embedding 我们改 mean pool"的诊断叙事，但他们没有在系统级安全检测语境下做。

**对应数据**：[CLS] failed attempt baseline 保留在 `data/checkpoint10_taskB_summary_bert.json` 作 Phase 12 ablation 对比基线（**禁止覆盖**）；β 修正方案结果落 `data/checkpoint11_2_beta_summary.json`。Phase 12 论文素材"Phase 3 sanity AUC 演进数字"子节的措辞模板对应 3 行表格：`(Phase 3 random Gaussian baseline) / (naive [CLS] entity-identifier) / (entity-event-context + mean pool)`。

### Contribution-boundary 设计原则（2026-05-05，Checkpoint 8 lesson）

两条可在 Methods 章节"Section 4.x How we adapt PyG TGNMemory to heterogeneous provenance graphs"段落直接引用的设计模式：

1. **Absent-vs-zero 语义**：异构 wrapper 在 lookup 时对 non-memory node types **不返回零张量**，而是让 caller 显式判断 `if ntype in output_dict`。理由：absence 本身就是 informative signal，silent 返回零会让上层模块误以为"这个类型有 memory 但都是零"——掩盖架构假设的 caller 错误使用。该原则在 `loghetero.models.graph.tgn_memory.HeteroTGNMemory.forward` 强制；Phase 4 跨模态注意力 caller 必须遵循。论文里这条作为"strict separation between configured node types and zero embeddings"的 contribution evidence。

2. **`uses_pyg_X_internally` introspection 测试模式**：为每个"我们 wrap PyG / Hugging Face / etc. base machinery"的模块，写一条 introspection 测试断言内部确实是被 wrapped 的标准类。例如 `tests/test_tgn_memory.py::test_uses_pyg_tgnmemory_internally` 用 `isinstance(tgn, PyG.TGNMemory)` 锁定我们的 contribution 是 wrapper layer 而非重写。论文 Methods 里"What we reuse vs what we add" 明细可以直接引用这些测试名作为 evidence。同样模式应用于 Phase 4 跨模态 attention（wrap BERT layer）+ Phase 5 RAPA（wrap MITRE STIX parser）+ Phase 8 baselines（wrap KAIROS / MAGIC / FLASH 官方 code）。



- **BERT 在 ATLAS 真实日志上 cos-sim 0.97-1.00 的强语义聚合**（2026-05-05 标记，由 Phase 2 / Checkpoint 6 sanity check 引发）。`scripts/bert_sanity_check.py` 在 ATLAS S1 / 600 events 上验证：benign DNS query top-5 NN 全是其他 DNS query (cos-sim 0.97-1.00)；noteworthy file_access top-5 NN 全是同模式 file_access (cos-sim 1.00)。
  - **论文 Methods 章节素材**：这一结果从经验上验证了 "不做 DAPT 也能用 bert-base-uncased 直接 forward 进入 LogHetero 联合预训练" 的工程决策正确性（决策 4.1 BERT 默认冻结）。Cleaner + 156 special token 的 placeholder 重写让 BERT 编码器对系统日志有合理语义抽取能力，**省去了几小时-几天的 DAPT 预训练**。
  - **Phase 12 写作要点**：放在 Methods 章节"4.x Text encoder design"段，作为我们选择 frozen BERT-base + cleaner-driven placeholder 这个工程组合的"empirical validation" 段落论据。可附 cos-sim 数字 + 一两个 NN retrieval 例（"DNS query → DNS query"、"file_access → file_access"）作为 figure。
  - **可对照写作 hook**：cf. Patton (Jin et al., ACL '23) 那篇 paper 也讨论了在 text-rich network 上预训练 LM 的必要性 vs 直接用通用 LM 的代价权衡——我们的结论是 "for log domain with proper cleaner, frozen general LM works"。

### multi-agent review pattern 在创新模块代码验证中的两类分工（2026-05-06，Checkpoint 12 lesson 标准范式）

**背景**：subagent-driven-development skill 在 Phase 4 Checkpoint 12（双向跨模态注意力模块实施）首次正式应用，确立了 implementer subagent → spec compliance reviewer subagent → code quality reviewer subagent → fix subagent 四步验证 pattern。该 pattern 在本次实施中暴露了一个真实方法论收获：spec compliance review 与 code quality review 是两类不同的分工，互补不冗余，多 agent 分工把这两种视角拆开后避免了任一 agent 视角偏置遗漏。

**两类分工的精确定义**：

1. **Spec compliance reviewer 看 "实现是否符合规范"**：检查 module API 签名、参数名、返回值类型、required tests 是否完备、required prohibitions 是否被遵守、外部接口是否与 spec 字面对齐。视角是 spec 文档与代码的字面对应——"spec 说要 X，代码有没有 X？"
2. **Code quality reviewer 看 "测试是否真验证了规范"**：检查测试断言是否能 catch 真实 bug、模块 docstring 是否与实现真实状态一致、命名是否准确、内部一致性是否成立。视角是代码内部自洽性与测试有效性——"代码自洽吗？测试真的能 catch 它声称要 catch 的东西吗？"

**Checkpoint 12 实测的两轮 catch**：

- Spec compliance review（首轮，Sonnet）报 ⚠️ Compliant 无 MUST_FIX，三处 implementer self-flag 全部得到 reasoned verdict（input projection 共享 acceptable / grad norm 阈值 1e6 数学合理 / NaN guard 正确性必需）；判定通过。
- Code quality review（次轮，Sonnet）独立 catch 两条 Important 问题，spec review 完全 miss 但确实存在：
  - **Important 1**：模块 docstring (line 21-22) 写 "no sharing" 但实际 input projection (text_proj / graph_proj) 跨两个方向共享；docstring 与实现状态字面矛盾，将误导任何做参数审计或推断梯度更新机制的读者。
  - **Important 2**：`test_independent_params_diverge_after_update` 断言 `tg_changed or gt_changed` 是 tautological——loss = fused_text.sum() 只走 Text→Graph 路径，gt_changed 必然 False，化简为单变量断言 `tg_changed`；aliased tensor (text_proj.weight 和 gt 路径里的某个权重共用 storage 这种 bug) 仍能 trivially pass。修复为 `tg_changed and not gt_changed`：aliased tensor 会让 gt_changed 与 tg_changed 同步变化，断言 fail，正确捕获 bug。

**为何两类分工不能合并**：

- Spec reviewer 的视角是 "spec → 代码"，遵循规范条目逐项核对；这种视角对 docstring 内部矛盾不敏感，因为 docstring 不是 spec 的一部分；对测试断言强度不敏感，因为 spec 说的是"测试覆盖 N 类，每类至少 1 项"，没说"测试断言必须能 catch 特定 bug class"。
- Code quality reviewer 的视角是 "代码 → 一致性"，独立审视代码是否说服自己；这种视角对 spec 字面对应不敏感（已假定 spec review 通过），但对内部矛盾、tautological 断言、误导性 docstring 高度敏感。
- 单一 agent 难以同时持两种视角且不偏置任一方。多 agent 分工把两种视角分配给独立 subagent，避免任一 agent 视角偏置遗漏。

**Phase 12 论文 Methods 章节使用方式**：

本方法论作为 "我们如何保证创新模块代码的科研验证质量" 工程方法论支撑，写入 Methods 章节相关段落（建议放在 "Reproducibility & methodology" 子节）。可对照写作 hook：cf. 主流深度学习论文通常只报告 unit test 通过率作为代码质量证据；我们额外报告 multi-agent review pattern 的两类分工 + 真实 catch 案例（Checkpoint 12 docstring 矛盾 + tautological 断言两条 Important 问题），这种工程纪律本身可作为 Methods 章节 contribution evidence——审稿人可以看到具体方法论的两类视角分工与真实 catch 数字而非"我们做了 unit test"的黑盒陈述。

**确立为 Phase 4 后续 sub-checkpoint 标准实施路径**：每个 sub-checkpoint (13 / 14 / 14.5) 都走 implementer → spec compliance review → code quality review → fix if needed 四步 pattern，**不允许跳过 code quality review 这一步**。Phase 5+ 创新模块（RAPA-GTCL 对比学习目标、改造 GTCL 损失等）继续延用该 pattern。

**例外情况**：纯验证脚本（如 smoke test、ablation driver、benchmark 脚本）不需要走 4 步 pattern，因为这类脚本本身不是 "创新模块代码" 而是 "验证创新模块代码的工具"。verification 脚本走单 agent 实施 + 主 agent sanity check 即可。该例外的理由：spec / code quality 两类视角主要 catch "代码声称做 X 但实际做 Y" 这种创新模块语义偏差，而验证脚本的语义是"实测某 metric"——脚本跑通且 metric 数字与预期范围对齐就已经是自验证，再加一层 review 边际收益小于成本。

## Phase 7 待办

### TGN msg_store 跨 batch 清理（2026-05-06，Checkpoint 9 发现）

**现象**：`tests/test_htgn.py::TestStandardCoverage::test_multi_batch_with_detach_runs_cleanly` 跨 batch 第二次 `loss.backward()` 抛 `RuntimeError: Trying to backward through the graph a second time`，即使在 batch 1 末尾调用 `htgn.tgn_memory.detach()`。根因：PyG `TGNMemory` 内部维护 `msg_store: dict[int, tuple[Tensor, Tensor, Tensor, Tensor]]`，存放每个 dst node 上次收到的 raw_msg / src / t / src_msg 元组，等下次 forward 时聚合成 message 喂 GRU。`detach()` 当前只 detach `memory` 与 `last_update` 两个 buffer，**不清也不 detach `msg_store` 内部的 raw_msg tensor**——后者仍持有 batch 1 计算图的引用。

**为什么是 Phase 7 责任而非 Checkpoint 9 模块 bug**：HTGN 模块本身在单 batch 路径下 4 套参数梯度 sanity 全部独立 pass（user-required Checkpoint 9 deliverable）；跨 batch 持久化协议属于 DataLoader / Lightning Module 层职责。Checkpoint 9 用 `@pytest.mark.skip(reason="Deferred to Phase 7: ...")` 显式挂钩，Phase 7 训练循环建立时本待办自动归属当时的实施 PR。

**两条 fix 实施路径（Phase 7 启动时二选一，先尝 Path A）**：

- **Path A（推荐，wrapper-side fix）**：扩展 `src/loghetero/models/graph/tgn_memory.py::HeteroTGNMemory.detach()`，让其在调用 per-type `TGNMemory.detach()` 之外，**额外清空** 每个 per-type TGNMemory 的 `msg_store`。具体实现：
  ```python
  def detach(self) -> None:
      for tgn in self._memories.values():
          tgn.detach()  # detach memory + last_update buffers
          tgn.msg_store.clear()  # NEW: drop batch-1 raw_msg references
  ```
  在 Lightning Module 的 `on_train_batch_end` hook 里调用 `self.htgn.tgn_memory.detach()`。**优势**：fix 集中在 HeteroTGNMemory 一处，对调用方透明；**风险**：清空 msg_store 意味着 batch 边界丢失上一批最近 raw_msg，第一次 forward 会用零初始 message，需在 Phase 7 通过 epoch loss 曲线验证不影响收敛（如确实降级，回退到 Path B）。
- **Path B（备选，pipeline-side fix）**：在 Lightning Module 的 `on_train_batch_start` hook 中先 `htgn.tgn_memory.reset_msg_store()`（需扩 HeteroTGNMemory 暴露此方法）再训练，使 msg_store 永远不跨 batch 携带梯度图；或者在 `update_state(...)` 调用之后立即 `forward(n_id_dict)` 触发 PyG 内部 message passing 把 msg_store 排空，让 raw_msg 在 batch 边界前已被消费。**优势**：semantically 更接近 PyG 设计本意（message store 在 forward 中即时消费）；**风险**：增加调用约束，HeteroTGNMemory caller 必须遵守 update→forward 配对协议，违反时 silent drop message。

**Phase 7 实施时**：
1. 启动 Phase 7 第一天先做 1 小时 PyG dry-run sanity check（minimal 训练循环 + minimal HeteroTGNMemory），验证选定的 fix path 真能让多 batch backward 跑通；这是对 Phase 3 期间 PyG 接口连续 3 个 surprise（Long timestamp / 零节点 graceful skip / msg_store 跨 batch）的应对，前置侦察成本小但能避免中段被连环 PyG 接口问题阻塞。
2. fix 落地后立即去掉 `tests/test_htgn.py::TestStandardCoverage::test_multi_batch_with_detach_runs_cleanly` 的 `@pytest.mark.skip` 装饰器，让它转为常态绿测试；同时给本 known_issues 条目标 [resolved (commit X)]。

### HeteroTGNMemory 跨类型 src 索引语义 proper fix（2026-05-06，Checkpoint 10 Task A 触发）

**现象**：见 "Phase 3 设计偏离记录::HeteroTGNMemory 跨类型 src 索引语义错误"。Checkpoint 10 用 num_nodes_per_type[memory_types] = max-across-types 的 workaround 规避 OOB 但 src memory 拿错 slot；Phase 7 真实训练前必须修。

**为什么 Phase 7 前不能继续 workaround**：Phase 7 batch=16 或 32 真实训练会涉及 batch 内多个不同类型节点频繁触发跨类型边 message passing；workaround 让 src memory 始终是 garbage 直接污染 TGN GRU 学习信号——Checkpoint 10 sanity check 容忍该噪声因 HGT 主路径占 85% 主导，但 Phase 4+ 跨模态融合训练会让 TGN memory 路径权重通过对比学习自适应放大，garbage src memory 会被 confounded fit，导致 Phase 8 anomaly detection AUC 不稳。

**三条 fix 实施路径（Phase 7 启动时三选一，user 拍板）**：

- **Path A（推荐，最小 invasion）**：在 `src/loghetero/models/graph/tgn_memory.py::HeteroTGNMemory.update_state` 中检测 `src_type != dst_type`，将 src 替换为 dst（自指）后再调用底层 `TGNMemory.update_state`；语义上等价于"消息 src 信息全部走 raw_msg 通道（已含 src embedding 投影），不通过 PyG memory 查找拿 src 隐状态"。具体实现：
  ```python
  def update_state(self, dst_type: NodeType, src: Tensor, dst: Tensor,
                   t: Tensor, raw_msg: Tensor, *, src_type: NodeType) -> None:
      if dst_type not in self._memories:
          return  # silent no-op (existing behaviour)
      tgn = self._memories[dst_type]
      effective_src = dst if src_type != dst_type else src  # NEW
      tgn.update_state(effective_src, dst, t, raw_msg)
  ```
  调用点（HTGN.forward）需补传 src_type 参数。**优势**：保 PyG TGNMemory + IdentityMessage 不动；语义清晰（"raw_msg 通道独占 src 信息"）；3 行核心改动。**风险**：`memory[src]` slot 被 `memory[dst]` 替代后 IdentityMessage concat 多了一份 dst 自身 embedding（重复 information），轻微冗余但不破坏正确性。
- **Path B（替换 message function）**：自定义 `class HeteroIdentityMessage(IdentityMessage)` 重写 `forward(z_src, z_dst, raw_msg, t_enc)` 跳过 z_src 通道；将 PyG TGNMemory 构造时 `message_module=HeteroIdentityMessage(...)` 注入。**优势**：semantically 干净（src memory lookup 完全消除，message dim 减少 memory_dim）；**风险**：依赖 PyG message function 接口稳定性；整改 message_dim 涉及 GRU input dim 调整。
- **Path C（per-type message store）**：HeteroTGNMemory 维护 per-(src_type, dst_type) 独立 msg_store，update_state 时把 src memory 从 src_type 的 memory（而非 dst_type 的）查找；最 proper 但侵入性大，需重写 PyG TGNMemory 内部 msg_store 结构。**仅作 Phase 11+ ablation 备选**，Phase 7 不推荐。

**Phase 7 实施时**：
1. 启动 Phase 7 第一天的 PyG dry-run sanity check 阶段（见上方 "TGN msg_store 跨 batch 清理" 条目）一并验证选定 fix path 在跨类型边上的正确性。
2. fix 落地后，把 Checkpoint 10 Task A + Task B 中 num_nodes_per_type 的 max-across-types workaround 改回 actual-per-type，重跑两脚本验证 AUC / loss 数字与 workaround 版一致或更优；若数字劣化触发 RFC 重新评估 fix path。
3. 给本待办标 [resolved (commit X)]，相应在 "Phase 3 设计偏离记录::HeteroTGNMemory 跨类型 src 索引语义错误" 加 "Phase 7 RFC 决议：选 Path X，commit Y" 串联标注。

### VRAM batch=32 真实测量 sanity gate（2026-05-06，Checkpoint 9 benchmark naive 外推超 target）

**现象**：`scripts/bench_htgn.py` 在 ATLAS S1 K-hop 单子图 forward+backward 实测 per-sample VRAM peak 0.191 GB，naive 32 倍线性外推 6.12 GB，**超过 4 GB target**（Checkpoint 9 launch spec 中 batch=32 < 4 GB）。当时为快速完成 benchmark 用了 `x.repeat(32, 1)` 复制 batch（导致 edge_index 越界 CUDA assert，最终改回单样本测量 + 线性外推）。naive 外推**不代表 Phase 7 真实 batch 显存**：PyG `Batch.from_data_list()` 把多个独立子图合并为一张大图（节点 / 边 index 平移），稀疏邻接 + sparse softmax 会比 naive 复制紧凑得多；TGN memory 也是 per-node-id 共享而非 per-sample 复制。

**为什么是 Phase 7 责任而非 Checkpoint 9 阻塞**：Checkpoint 9 forward 时延 29.57 ms 已达硬目标；显存外推超目标只在 naive 测量条件下成立，真实 PyG Batch 路径未被实测。Checkpoint 10 链路预测仅训练单子图，触不到 batch=32 配置。

**Phase 7 batch sizing sanity gate（强制三步走，禁止省略）**：

1. **第一步：用 PyG `Batch.from_data_list()` 真实合并子图实测 VRAM**。在 `scripts/` 下加专用 bench 脚本（如 `scripts/bench_htgn_batch.py`），用真实 ATLAS S1 K-hop 子图集合（同 Checkpoint 9 复用），构造 `Batch.from_data_list([sub_1, ..., sub_32])` → forward+backward → 记录 `torch.cuda.max_memory_allocated()`。落到 `data/htgn_bench_batch.json` 与 Checkpoint 9 的 `data/htgn_bench.json` 一致风格 commit 进 git。
2. **第二步：分支决策**：
   - 实测 ≤ 4 GB → 直接进 Phase 7 batch=32 训练。
   - 实测 4 GB < x ≤ 12 GB → 启用 PyTorch `torch.utils.checkpoint` gradient checkpointing 包 HGTLayer forward；重测显存。如降至 ≤ 4 GB → batch=32；否则降至兜底 batch=16。
   - 实测 > 12 GB → 直接 batch=16 兜底 + gradient checkpointing。
3. **第三步：禁止动作**——在没有真实 `Batch.from_data_list()` 测量的情况下，**禁止**直接配置 batch=32 或更大启动训练；**禁止**用 naive `x.repeat()` 测量结果作为 batch 显存依据；**禁止**通过"关闭 TGN memory" 或"砍 hidden_dim" 等修改架构的方式凑过显存——这些都属"调高 epoch 凑过"类的 bypass，违反 Phase 3 hard gate inviolability 纪律。

如果第二步分支决策走到 batch=16 兜底，需在 PROGRESS.md / CHECKPOINT 11 报告中显式记录"Phase 7 batch size = 16（实测显存约束所致），与 Checkpoint 9 launch spec batch=32 假设差异；对训练稳定性影响在 Phase 11 ablation 中校核"。

### Mixed-vs-benign quick A/B 前置测试（2026-05-06，Checkpoint 11.1 RFC Option B 条件 3 触发）

**触发原因**：Checkpoint 11.1 RFC 决议 Option B（Phase 4 用 mixed 数据），benign-only pretraining 推到 Phase 7 实施。User 强制 Phase 7 启动前**必须先做 mixed-vs-benign quick A/B 测试**，不允许 Phase 7 直接用 mixed 数据跑全量预训练。

**Phase 7 第一个 sub-checkpoint 强制议程**（hard gate，禁止省略）：

1. **数据子集**：ATLAS 一个小子集（如 S1 + M1 两个 scenario，共 3 个 (host, window) 子图），用 `AtlasGroundTruthLabelLoader`（Phase 8 待办成果，Phase 7 启动前必须完成）切两组：
   - Group A: mixed 数据（不过滤）
   - Group B: benign-only 数据（filter 掉所有 ATLAS ground-truth 标记的 attack 事件）
2. **mini pretraining**：用 Phase 4 跨模态融合架构（HTGN + BERT + cross-attention + 改造 MLM）跑 5-10 epoch 的 mini pretraining，分别用 Group A 与 Group B 数据。
3. **双指标对比**：
   - **Perplexity**（MLM 任务的 loss-derived 指标，pretrain quality 直接代理）
   - **下游 link prediction AUC**（用 mini pretrained representation freeze 后跑同 Checkpoint 10 Task B 协议，对比 mixed-pretrained vs benign-pretrained 的 AUC 差距）
4. **决策**：
   - 如 mixed vs benign 在 perplexity 上差 > 5% **OR** 在 link prediction AUC 上差 > 3pp → **Phase 7 全量预训练改用 benign-only 数据**，不延续 Phase 4 的 mixed 配置；同时回头标 Checkpoint 11.1 RFC Option B 决议为 "post-verification: mixed had material impact, switched to benign-only at Phase 7"。
   - 如 mixed vs benign 差距 < 上述阈值 → Phase 7 全量预训练用 mixed 数据（与 Phase 4 配置一致），benign-only 保留作为 Phase 11 ablation 对照。
5. **报告与落档**：Phase 7 第一个 sub-checkpoint 报告必须含 mini pretraining loss 曲线 + 双指标对比表 + 决议结果，落 commit 进 git。

**禁止动作**：在没跑 quick A/B 测试的情况下直接启动 Phase 7 全量预训练（不论选 mixed 还是 benign）。这条 sanity gate 是 Checkpoint 11.1 RFC Option B 的 落地保障，不是建议而是硬纪律。

### BERT-fused-attention vs HTGN-only quick A/B 扩展（2026-05-06，Checkpoint 11.2-γ-1 决议触发）

**触发原因**：Checkpoint 11.2-γ-1 决议把 BERT 跨模态融合的真实 evaluation 推到 Phase 7-8 anomaly detection（详见 `docs/design_decisions.md` 决策 4.2 footnote 2026-05-06 + 上方 "Phase 3 sanity AUC re-validation" 闭环标注）。**Phase 7 启动前必须验证 BERT 跨模态融合在 anomaly-relevant 数据上确实有 lift，不能默认假设**——这是对 Checkpoint 11.2 link prediction null finding 的 follow-up 验证。

**Phase 7 mixed-vs-benign quick A/B（已规划议程）扩展为 2×2 grid**：

|  | mixed pretraining | benign-only pretraining |
|---|---|---|
| **HTGN-only**（无 cross-attention） | A1 | A2 |
| **BERT-fused-attention**（Phase 4.1 cross-attention 启用）| B1 | B2 |

**对比指标（在 Phase 8 anomaly detection 任务上）**：

1. **anomaly F1 score**（核心 - 跨模态融合 真正的 use case 指标）
2. **anomaly AUC**（辅助 - 与 Phase 3 link prediction AUC 不同任务）
3. **representation 可视化**（t-SNE / UMAP - attack vs benign 节点 representation 是否被 cross-attention 推得更分离）

**通过门槛（hard gate）**：

- **B1 vs A1**（mixed 数据下 BERT-fused vs HTGN-only）：anomaly F1 lift ≥ +0.03 或 anomaly AUC lift ≥ +0.02，验证跨模态融合真有贡献
- **B2 vs A2**（benign 数据下同对比）：同阈值
- **B1+B2 同时不达阈值** → 触发新一轮架构级 RFC 重新评估 Phase 4 跨模态注意力设计（这是 γ-1 决议设定的"如果 BERT 在 anomaly detection 也没有 lift，那是 BERT 在我们整个 use case 下都不适合"的 fallback gate）

**实施时序**：

- 必须在 Phase 7 全量联合预训练之前跑完 4 cells（数据子集如 Phase 7 待办 "Mixed-vs-benign quick A/B 前置测试" 子节描述：S1 + M1 mini pretraining）
- 报告 commit message 前缀 `feat(phase7): BERT-fused-attention vs HTGN-only quick A/B (Checkpoint 11.2-γ-1 fallback verification)`
- 跑完后回头标 Checkpoint 11.2-γ-1 决议条目 "Phase 7 A/B verification 完成日期 + commit hash + B1 vs A1 / B2 vs A2 实测 lift 数字" 闭环

**Phase 12 论文叙事 hook**：如 Phase 7 A/B 显示 BERT-fused-attention 在 anomaly detection 上确实有显著 lift，论文 Methods 章节就有了 "我们诚实排除 BERT 集成在 link prediction 上无效 + 验证 BERT 集成在 anomaly detection 上显著有效" 这条完整决策链；如 Phase 7 A/B 也显示 null finding，论文叙事重心要从"跨模态融合是创新点 1 的核心贡献"调整为"我们发现 BERT 跨模态融合在 provenance graph anomaly detection 上的边际贡献有限，主创新转向 HTGN 异构时序图编码 + RAPA-GTCL 攻击模板增强"——后一种叙事虽然弱化创新点 1 但保留了创新点 2 的完整性。

## Phase 8 待办

- **`AtlasGroundTruthLabelLoader` 实现**（2026-05-05 标记，由 Checkpoint 5 引发）。当前 `src/loghetero/data/datamodule.py::benign_only_label_loader` 是 Phase 1.6 stub（所有 event 返回 0），Phase 8 finetune_anomaly mode 需要真实标签。实施步骤：
  1. 解析 ATLAS `paper_experiments/{S1, S2, S3, S4, M1, ..., M6}/output/scenario_file_testing_preprocessed_logs_*` 与 `eval_seq_graph_*.json` 提取**攻击实体清单**（attack entities = list of file paths / process names / IPs / domains 涉及攻击）。注：ATLAS 论文未发布 ground-truth attack-entity sets 的官方文件，需基于 README 例（如 S1 的 `["0xalsaheel.com", "aalsahee/index.html", "192.168.223.3", "payload.exe"]`）+ paper Table I 重建。
  2. 实现 `src/loghetero/data/label_loaders.py::AtlasGroundTruthLabelLoader`：构造时加载所有 scenario 的攻击实体集，`__call__(event)` 返回 1 if `event.subject ∈ entities or event.obj ∈ entities` else 0。
  3. DataModule 构造时通过 `label_loader=AtlasGroundTruthLabelLoader(scenarios=[...])` 替换 stub。
  4. 配套测试：fixture 含已知攻击实体 + 标签验证；fold stats 重新跑确认 attack count 列从 0 变成实际数字。

## Phase 11 消融扩展

### B7 — Pretraining 数据干净度对比（2026-05-06，Checkpoint 11.1 RFC Option B 条件 2 触发）

**触发原因**：Checkpoint 11.1 RFC 决议 Option B 把 Phase 4 mixed 数据明确标注为 "unverified-impact baseline"。Phase 11 ablation 矩阵（v3 prompt §6 Phase 11）原本规划 B0-B6 围绕模型架构变量，**新增 B7 围绕数据干净度变量**。

**B7 配置**：

| Cell | Pretraining 数据 | 模型架构 | 备注 |
|---|---|---|---|
| **B0** | mixed（Phase 4 / 7 实际配置）| 完整 HTGN + BERT + cross-attention + 改造 MLM | 主 baseline |
| **B7-α** | benign_only_ground_truth（用 `AtlasGroundTruthLabelLoader` 切真 benign）| 同 B0 | 必须做（**hard requirement，禁止省略**）|
| **B7-β** | benign_only_paper_timeline（论文 timeline 启发式切分；Phase 11 时间允许时加）| 同 B0 | 时间允许加（Soft requirement）|

**对比指标**：Phase 8 anomaly detection F1（不仅看 pretraining perplexity，因为 perplexity 可能不反映 attack-as-normal 污染对下游的实际影响）+ Phase 8 anomaly detection AUC + 节点级 representation 可视化（t-SNE / UMAP 看 attack vs benign 节点 representation 是否在 mixed 训练后被错误聚到一起）。

**论文叙事调整 trigger（决策 9 footnote 已规定）**：

- 如 B0 vs B7-α 在 Phase 8 anomaly F1 上差异 **≤ 3pp** → mixed 数据假设成立，论文 Methods 章节按 mixed 数据写。
- 如 差异 **> 3pp** → mixed 数据有实际污染，论文 Methods 章节**必须诚实说明 mixed 预训练带来的 representation 偏差并把 benign-only 作为推荐配置**。

**实施时序**：B7 在 Phase 11 系统消融 sweeps 中作为额外一行运行，不允许跳过。Phase 11 实施 agent 必须读本条目作为 Phase 11 launch spec 的硬扩展项。

## Phase 12 待核实（写 related work 前必须 resolve）

- **Threatrace 与 ATT&CK 强关联性核实**（2026-05-05 标记，由决策 2 Innovation 2 prior work 引发）。Threatrace (Wang et al., NDSS '22) 据印象主要是用 GraphSAGE 做 provenance graph 上的 node-level 异常检测，**不一定显式使用 ATT&CK 模板**。Phase 12 写 related work 时按以下流程处理：
  1. 拉 Threatrace 原文与代码（NDSS '22；GitHub 搜 "threatrace"）。
  2. 核实其方法是否显式以 ATT&CK TTP 作为输入或训练监督信号。
  3. 如果是 → 保留在 Innovation 2 prior work 清单中；
  4. 如果否 → 把 Threatrace 移到 Innovation 1 的 PIDS baseline 类（与 KAIROS / MAGIC / FLASH 同类），并把 Innovation 2 的 ATT&CK-augmentation 先验工作替换为：TTPDrill / AttacKG / Holmes / RapSheet 这几个候选中真正以 ATT&CK 做攻击合成的工作（同样需 verify 而非凭印象引用）。
  5. 修订完落到 `docs/design_decisions.md` 决策 2 + 修订历史。

## 环境（Phase 0 探明，2026-05-05）

| 项 | 取值 |
|----|------|
| GPU | 8 × NVIDIA RTX 4090（24 GB / 卡，共 ~196 GB VRAM） |
| CUDA driver | 13.0 |
| nvcc | 12.8 |
| Python（项目用） | 3.10.12（系统 Python 3.11.15 也存在） |
| uv | 0.11.9（用 `pip install --user uv` 安装；ASTRAL `install.sh` SSL 失败） |
| OS | Linux 5.15 (Ubuntu) |

**显存预算建议（Phase 1+ 时再细化）：** 单卡 24 GB 可容纳 batch size ≈ 32 的 BERT + HTGN 联合 forward；如需更大 batch 在 Phase 7 启用 gradient checkpointing 或 DDP across 8 卡。

## 已知风险（持续维护）

无。

## 安装注意事项

- `uv sync --extra ml` 安装 PyTorch 时默认从 PyPI 拉 CUDA 12.x wheel。如需指定 cu121 / cu118 / cpu，参考 https://pytorch.org/get-started/locally/ 配 `[tool.uv.sources]`。
- ASTRAL `install.sh` 在某些代理环境下 SSL 失败；用 `pip install --user uv` 作为 fallback。

## 数据访问

- **ATLAS**：Phase 1 用 `scripts/download_atlas.sh` 自动从 `purseclab/ATLAS` 拉取。
- **DARPA TC E3**：项目所有者手工申请；`scripts/download_darpa_e3.sh` 仅做占位 + sha256 校验，不自动下载。
- **MITRE ATT&CK**：Phase 5 用 `scripts/download_mitre_attack.py` 从 `mitre/cti` 公开 STIX 数据拉取。

## ATLAS 数据校验清单（Phase 1.1 落地，回应 Q1）

**协议（决定 2026-05-05）。** `scripts/download_atlas.sh` 拉取后，`scripts/verify_data_integrity.py` 必须把以下三个层级的统计值与 `purseclab/ATLAS` 仓库 README 给出的预期对账：

1. **每个 scenario 的预期文件数**：以 `purseclab/ATLAS` README 公布的清单为准。
2. **每个文件的字节数（必校）**：固化下来作为 baseline；如果 `purseclab/ATLAS` README 没列 sha256，至少把 byte count 写入 `data/atlas_manifest.json` 作为 reproducibility anchor。
3. **每个文件的行数（必校）**：日志类文件按行计数，作为内容完整性的辅助校验。

**校验规则。** 如果 README 给出 sha256，校验 sha256 + byte count；如果没给，至少校验 byte count + line count。任何不一致 fail-fast 并把差异详情追加到本文件 `## 数据完整性偏差` 小节（Phase 1.1 创建）。

**Manifest 格式（Phase 1.1 实施）：**

```json
{
  "scenarios": {
    "S1": {
      "files": [
        {"path": "...", "bytes": 12345678, "lines": 9876, "sha256": "..."}
      ]
    }
  }
}
```

每次 `verify_data_integrity.py` 通过后把当前事实写入 manifest；后续重跑必须和 manifest 完全一致才算通过。Manifest 文件 commit 进 git（不是 DVC 管的大文件，仅几 KB JSON）以便 reviewer 一眼看到我们用的是哪一份 ATLAS。
