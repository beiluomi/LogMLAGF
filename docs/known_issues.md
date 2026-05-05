# Known Issues

## 经验启发式校准记录（避免被早期 GNN 数字误导）

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

## Phase 4 待办

### Pretraining 数据 benign-only 约束的重审议程（2026-05-06，Checkpoint 10 Option C 决议触发）

Phase 3 Checkpoint 10 因 `AtlasGroundTruthLabelLoader` Phase 8 待办无法切真实 benign-only 子图，user 选 Option C 把 benign-only 约束推到 Phase 4 入口讨论。**Phase 4 跨模态融合启动前必须重审 pretraining 数据的 benign-only 约束**——开 Phase 4 第一个 RFC 议程，逐条决议：

(a) **跨模态联合预训练阶段是否需要纯 benign 数据**：HTGN-LM 跨模态注意力的预训练任务（Phase 4 / Checkpoint 12-14 待 launch spec）会把图嵌入与 LM 嵌入对齐；如果训练数据混入攻击事件，模型可能把"攻击模式"学成"正常 representation"，污染下游 Phase 8 anomaly fine-tuning 的 representation baseline。需根据 Phase 4 损失函数性质决定：MLM-style + 对比损失对数据噪声相对鲁棒，离群少量攻击事件影响有限；node-level 重建损失敏感度更高。

(b) **如需 benign-only，是否依赖 Phase 8 真实 label loader 才能切**：若 (a) 决议要 benign-only，最干净路径是 Phase 4 launch 前先实施 `AtlasGroundTruthLabelLoader`（Phase 8 待办前置），用真实标签筛子图。代价：Phase 8 工作量前置 1-2 天。

(c) **如果 Phase 8 label loader 滞后于 Phase 4，是否走 ATLAS 论文 timeline 启发式临时切分作为 stop-gap**：备选——基于 ATLAS 论文 Table I 提供的攻击时间区间，避开攻击窗口取早期良性时段子图作 stop-gap；Phase 8 label loader 落地后 retroactively 校验启发式切分的纯净度。这条只在 (b) 因故无法前置时启用。

**Phase 4 入口 RFC 触发器**：开始 Phase 4 第一个 commit 前，main agent 必须读本条目并给出 (a)(b)(c) 三选一决议；不得 silent 跳过。议程产出预期：一条 docs commit 在 known_issues.md "Phase 3 设计偏离记录::Task B 完全 benign 子图 spec" 子节下追加 "Phase 4 RFC 决议（YYYY-MM-DD）：选 X，理由 Y" 标注，让 audit trail 串联起来。

## Phase 12 论文素材

### Contribution-boundary 设计原则（2026-05-05，Checkpoint 8 lesson）

两条可在 Methods 章节"Section 4.x How we adapt PyG TGNMemory to heterogeneous provenance graphs"段落直接引用的设计模式：

1. **Absent-vs-zero 语义**：异构 wrapper 在 lookup 时对 non-memory node types **不返回零张量**，而是让 caller 显式判断 `if ntype in output_dict`。理由：absence 本身就是 informative signal，silent 返回零会让上层模块误以为"这个类型有 memory 但都是零"——掩盖架构假设的 caller 错误使用。该原则在 `loghetero.models.graph.tgn_memory.HeteroTGNMemory.forward` 强制；Phase 4 跨模态注意力 caller 必须遵循。论文里这条作为"strict separation between configured node types and zero embeddings"的 contribution evidence。

2. **`uses_pyg_X_internally` introspection 测试模式**：为每个"我们 wrap PyG / Hugging Face / etc. base machinery"的模块，写一条 introspection 测试断言内部确实是被 wrapped 的标准类。例如 `tests/test_tgn_memory.py::test_uses_pyg_tgnmemory_internally` 用 `isinstance(tgn, PyG.TGNMemory)` 锁定我们的 contribution 是 wrapper layer 而非重写。论文 Methods 里"What we reuse vs what we add" 明细可以直接引用这些测试名作为 evidence。同样模式应用于 Phase 4 跨模态 attention（wrap BERT layer）+ Phase 5 RAPA（wrap MITRE STIX parser）+ Phase 8 baselines（wrap KAIROS / MAGIC / FLASH 官方 code）。



- **BERT 在 ATLAS 真实日志上 cos-sim 0.97-1.00 的强语义聚合**（2026-05-05 标记，由 Phase 2 / Checkpoint 6 sanity check 引发）。`scripts/bert_sanity_check.py` 在 ATLAS S1 / 600 events 上验证：benign DNS query top-5 NN 全是其他 DNS query (cos-sim 0.97-1.00)；noteworthy file_access top-5 NN 全是同模式 file_access (cos-sim 1.00)。
  - **论文 Methods 章节素材**：这一结果从经验上验证了 "不做 DAPT 也能用 bert-base-uncased 直接 forward 进入 LogHetero 联合预训练" 的工程决策正确性（决策 4.1 BERT 默认冻结）。Cleaner + 156 special token 的 placeholder 重写让 BERT 编码器对系统日志有合理语义抽取能力，**省去了几小时-几天的 DAPT 预训练**。
  - **Phase 12 写作要点**：放在 Methods 章节"4.x Text encoder design"段，作为我们选择 frozen BERT-base + cleaner-driven placeholder 这个工程组合的"empirical validation" 段落论据。可附 cos-sim 数字 + 一两个 NN retrieval 例（"DNS query → DNS query"、"file_access → file_access"）作为 figure。
  - **可对照写作 hook**：cf. Patton (Jin et al., ACL '23) 那篇 paper 也讨论了在 text-rich network 上预训练 LM 的必要性 vs 直接用通用 LM 的代价权衡——我们的结论是 "for log domain with proper cleaner, frozen general LM works"。

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

## Phase 8 待办

- **`AtlasGroundTruthLabelLoader` 实现**（2026-05-05 标记，由 Checkpoint 5 引发）。当前 `src/loghetero/data/datamodule.py::benign_only_label_loader` 是 Phase 1.6 stub（所有 event 返回 0），Phase 8 finetune_anomaly mode 需要真实标签。实施步骤：
  1. 解析 ATLAS `paper_experiments/{S1, S2, S3, S4, M1, ..., M6}/output/scenario_file_testing_preprocessed_logs_*` 与 `eval_seq_graph_*.json` 提取**攻击实体清单**（attack entities = list of file paths / process names / IPs / domains 涉及攻击）。注：ATLAS 论文未发布 ground-truth attack-entity sets 的官方文件，需基于 README 例（如 S1 的 `["0xalsaheel.com", "aalsahee/index.html", "192.168.223.3", "payload.exe"]`）+ paper Table I 重建。
  2. 实现 `src/loghetero/data/label_loaders.py::AtlasGroundTruthLabelLoader`：构造时加载所有 scenario 的攻击实体集，`__call__(event)` 返回 1 if `event.subject ∈ entities or event.obj ∈ entities` else 0。
  3. DataModule 构造时通过 `label_loader=AtlasGroundTruthLabelLoader(scenarios=[...])` 替换 stub。
  4. 配套测试：fixture 含已知攻击实体 + 标签验证；fold stats 重新跑确认 attack count 列从 0 变成实际数字。

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
