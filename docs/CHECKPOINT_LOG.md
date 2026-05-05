# LogHetero — Checkpoint Log（追加式 audit trail）

> **严格只追加，不修改**。每次 checkpoint 完成后追加一条记录。作为项目演进的可审计日志，未来 Phase 12 写论文 Limitation / Methodology 章节时按时间线还原研究决策路径的素材。

每条记录的固定字段：

- **编号与名称**
- **完成日期**
- **对应 commit hash**
- **核心交付物清单**
- **关键 metric 数字**
- **本 checkpoint 解决的核心决策点**（含 user override / agent push back 事件）
- **触发的 known_issues 新增条目**

---

## Phase 0 — Scaffold

- **完成日期**：2026-05-05
- **Commit**：`d9ff51e` (init) + `d66450c` (decisions 5-7 + CI split) + `008cbff` (citation verification) + `aa184f4` (merge to main)
- **核心交付物**：完整目录骨架；uv-based 依赖（dev / ml extras）；Makefile（hello / lint / format / test / integration-test / refresh-manifest / phase-gated targets）；pre-commit + CI（ci.yml fast lane + integration.yml weekly）；CLI 入口 `loghetero hello`；deterministic `set_seed` + 统一 logger；6 smoke 测试；`docs/design_decisions.md` 宪法初版（决策 1–7）；README 含实施进度跟踪。
- **关键 metric**：6 / 6 smoke 测试通过；ruff + mypy 全绿；scaffold init 完成耗时半天。
- **决策点**：
  - 决策 1：不复现任何已有论文作为方法主线（独立研究）。
  - 决策 2：两条创新点精确措辞——**user 抓出 PLATO 是 AI 引用幻觉**，agent 用 web search 核实，删 PLATO，加 verified GraphFormers / GreaseLM / Patton / THLM / ConGraT / HGT。
  - 决策 3：双盲匿名化策略。
  - 决策 4：工程不变量（BERT 冻结、HTGN day 1、双向跨模态 day 1、对比学习端到端、Hydra 模块化）。
  - 决策 5：DARPA TC E3 CDM → 5 类节点映射；user 修正 agent 默认 `UnnamedPipeObject → socket`，改为 `→ file` 与 KAIROS / MAGIC / FLASH 对齐；SrcSinkObject footnote 标 Phase 8 待审。
  - 决策 6：Leave-one-attack-out + (host_id, time_window) 联合切分初版（initial = 1.0h，待 Phase 1.5 数据后回看）。
  - 决策 7：AI 协作披露策略（保留 Co-Authored-By: Claude）。
- **新增 known_issues**：环境快照（8× RTX 4090 / CUDA 12.8 / Python 3.10.20 / uv 0.11.9）；Phase 12 待核实 Threatrace 与 ATT&CK 关联；ATLAS 数据校验清单；CI 拆分策略。

---

## Checkpoint 1 — Phase 1.1 ATLAS 下载 + Manifest 校验

- **完成日期**：2026-05-05
- **Commit**：`79f78be`
- **核心交付物**：`scripts/download_atlas.sh`（幂等 shallow-clone + unzip 全部 10 个 raw_logs/*.zip）；`scripts/verify_data_integrity.py`（bytes / lines / sha256 三层校验，二次跑 fail-fast 写 known_issues 偏差小节）；`data/atlas_manifest.json` 作为 reproducibility anchor commit 进 git（12 KB JSON）。
- **关键 metric**：10 scenarios（S1-S4 + M1-M6）/ 48 文件 / **6.91 GB / 114,245,126 lines**；100% 完整（0 missing）；二次 verify 输出 OK。Sha256 自计算（README 无），fallback 到 bytes + lines 主校验。
- **决策点**：confirm Q-A: 远程仓库存在但空，clone fallback 到 git init OK；Q-B: 单卡推进、暂按 200 GB 数据预算；Q-D: 开发期真名 zbyangyangyang@gmail.com，Phase 12 filter-repo 匿名；Q-E: uv + DVC + 英文 docstring + 中文设计文档；Q-F: W&B offline + project=loghetero。
- **新增 known_issues**：M5 h1 security_events 量级偏大（396 MB / 14M 行，3-4× 其他 M h1）标 Checkpoint 2 待验证；ATLAS README 不发布 sha256 → fallback 到 bytes + lines。

---

## Checkpoint 2 — Phase 1.2 解析器实现

- **完成日期**：2026-05-05
- **Commit**：`c224eb8`
- **核心交付物**：`parsers/base.py`（Event dataclass / NodeType 5 类 / ParseStats / Parser ABC / Eastern-Time 时区辅助）+ 20 测试；`parsers/atlas.py`（Dns / Firefox / SecurityEvents 三 parser；`_AUDIT_EVENTID_DISPATCH` 7-EventID 表）；`parsers/darpa_e3.py`（CDMParser 骨架 + `_CDM_NODE_TYPE_MAP` 决策 5 写死） + 17 测试；`scripts/parse_atlas_all.py` 多进程驱动；`data/atlas_parse_summary.json` 提交进 git。
- **关键 metric**：**57 / 57 测试通过**；全量解析 6.91 GB / **39.5s 壁钟 / 8 worker**；overall 解析 success 2,828,821 / failed 2,349 / skipped 43,283,066 → **failure rate 0.083%**。29 / 30 (scenario, log_type) cells = 0% 失败；唯一非零 M3/h1/security_events = 1.63%（root cause: ATLAS 上游 CSV 工具 bug）。
- **决策点**：
  - 时间戳协议：firefox 显式 UTC（authoritative），dns + security_events naive Eastern Time（zoneinfo），转 UTC ns 用 `to_utc_ns()` 直接 timedelta（避免 datetime.timestamp() 浮点损失）。**TZ 假设交叉验证**：dns 22:43:52 EDT → 02:43:52 UTC vs firefox 02:44:43 UTC，差 51 秒，确认 EDT 假设正确。
  - **M5 deep-dive 验证**：M5_h1 EventID 4656/4658/4663（file-handle 三连）放大 4.6×，但 4660/4688/4689（删除/进程创建/进程退出）完全在其他 scenario 范围内 → **真实攻击密集**（典型 T1083 / T1005），非 corruption。
  - **M3/h1 1.6% 失败 root cause**：ATLAS 上游导出工具 bug 把含未 quote 逗号的 policy descriptor 切成多伪行；**user 接受不修**决策。
- **新增 known_issues**：Phase 4 firefox 解析覆盖度回顾（attention 可视化发现链路断裂时再扩展）；M3/h1 解析失败已知项不修；M5 h1 攻击密集已 resolve 标记。

---

## Checkpoint 3 — Phase 1.3 + 1.4 清洗 / Tokenizer / 异构图

- **完成日期**：2026-05-05
- **Commit**：`40dbbca`
- **核心交付物**：`log_cleaner.py`（27 substitution patterns most-specific-first，27 测试）；`tokenizer.py`（156 个 special token，SYNONYM_INIT 字典每 token 配 3-4 个同义词均值 init，11 测试 + 3 integration with BERT）；`provenance_graph.py`（PyG HeteroData multigraph builder + GraphBuildStats，5 测试含 2 反例：empty raises + multigraph 不去重）；EdgeType enum + ALLOWED_EDGE_TRIPLES schema（25 enum + 24 triples）锁定在 `parsers/base.py`；`scripts/build_atlas_graphs.py`；`scripts/tokenizer_nn_sanity.py`；`data/atlas_graph_summary.json` + `data/tokenizer_nn_sanity.json` 提交进 git。
- **关键 metric**：**100 / 100 测试通过**（含 BERT integration）；16 (scenario, host) graph 构建 53.5s / 8 worker；**156 / 156 SYNONYM_INIT 100% 初始化成功率**；NN sanity sample top-1：`[IP]→ip(0.735)`、`[HASH_SHA256]→hash(0.864)`、`[PROC_LSASS]→authentication(0.817)`、`[NET_DNS]→resolution(0.798)`、`[PROC_POWERSHELL]→shell(0.828)`。
- **决策点**：
  - 决策 8 写入：孤立节点保留 + isolated=True 标记，不静默过滤（APT C2 / staging endpoints 常呈孤立）。
  - EdgeType enum 锁定：每个 EdgeType 在 (src, dst) 组合中只出现一次；CDM EVENT_SENDTO / RECVFROM 拆 NET_SEND_SOCKET / NET_SEND_NETWORK 等避免歧义。
  - ML stack bump：torch 2.1 → 2.4+（transformers 需要 `torch.utils._pytree.register_pytree_node` 公共 API）。
  - **socket = 0 / user = 0 across all 16 hosts** 显式标注（Q-1 后续 override 的起点）。
- **新增 known_issues**：无（已知项均在 design_decisions / pyproject 内）。

---

## Q-1 mini-checkpoint — User-Logon Dispatch（4 EventIDs）

- **完成日期**：2026-05-05
- **Commit**：`246ee95`（独立 commit，未混入其他改动，按 Q-1 spec 要求）
- **核心交付物**：`base.py` 加 3 EdgeType（USER_LOGON_FAIL / USER_PRIV_GRANT / USER_EXPLICIT_LOGON）+ 3 ALLOWED_EDGE_TRIPLES；`atlas.py` SecurityEventsParser 重构为 per-EventID extractor pattern（11-EventID dispatch），加 4 个新 extractor + LogonType ∈ {3, 9, 10} 过滤器；底层修两个 bug：`_BODY_KV_RE` 接受顶格行（4624 "Logon Type:" 在 column 0）+ `_parse_event_body` first-wins → last-wins（4624 "Account Name" 在 New Logon section 才是真用户）；9 个新测试覆盖 ≥3 LogonType 反例。
- **关键 metric**：**106 / 106 测试通过**；user 节点 **0 → 70 across all 16 hosts**（每 host 1-5 个，M5_h1 是单 1 个 admin account）；user 边 226 = USER_LOGON 12 + USER_LOGON_FAIL 0 (ATLAS 全无 4625 by grep) + USER_PRIV_GRANT 202 + USER_EXPLICIT_LOGON 12。**5 类节点首次全部在主数据集 ATLAS 上兑现**（仅 socket = 0，等 DARPA TC E3）。
- **决策点**：
  - **User override**：agent 建议把 user-node 缺失推迟到 DARPA TC E3 / Phase 9，user override 要求 ATLAS 主数据集必须兑现 5 类异构 claim。理由：架构一致性 > 边际信号密度；T1021 / T1078 lateral movement 战术需要 user 节点；4624 LogonType {3, 9, 10} 过滤后噪声可控；现在做最便宜，Phase 7 后改成本巨大。
  - **Bug fix 副产物**：refactor 时发现旧 code 在 4663 / 4656 等 file-handle 事件 Process Name 缺失时 fallback 用 account_name 当 process（语义错），新 extractor skip。**-8,143 success / +8,143 skipped vs Checkpoint 3 baseline，是 graph 质量改进**（Phase 1.2 修订记录条目说明）。
- **新增 known_issues**：Phase 1.2 修订记录（避免被 reviewer 误读为退步）；ATLAS user 类节点偏低（Phase 12 Limitation 素材，DARPA TC E3 Principal 节点 Phase 9 会丰富该类）。

---

## Checkpoint 4 — Phase 1.5 时间窗事件密度 + 子图采样

- **完成日期**：2026-05-05
- **Commit**：`ba456a0`（实现）+ `f67d845`（宪法 commit：决策 6 final + 决策 9 new）
- **核心交付物**：`window_splitter.py`（pure stateless helpers，8 测试）；`subgraph_sampler.py`（K-hop 异构 BFS + 3 档 edge_ranking + 决策 8 isolated mask 子图度数重算，12 测试含 4 输入校验反例）；`scripts/build_window_density_histograms.py`（Hydra-driven 4×4 grid + 17th global CDF overlay PNG + decision table + summary JSON）；`configs/data/atlas.yaml` Hydra config（time_window_hours / max_nodes / khop / edge_ranking / max_events_per_window / granularity_sweep_hours，全部参数化），matplotlib>=3.7 加入 ml extras。
- **关键 metric**：**128 / 128 测试通过**；直方图 driver 42.7s 壁钟 / 8 worker；**16 (scenario, host) 在所有 swept 粒度（0.5h / 1h / 2h / 4h）下 mean events/window 16k-200k**，远超 launch-spec [10, 10000] 启发区间；S3 / S4 在 1.0h+ 仅 1 nonempty window；M5_h1 dominant 5 windows × 124k each。
- **决策点**：
  - **决策 6 final**：时间窗粒度 = 1.0h 全局统一，不分档。Checkpoint 4 第 17 张 CDF overlay 显示无 h1 / h2 bimodal、无 attacker / victim 单一分轴可分。
  - **Launch spec [10, 10000] heuristic 校准**：user 接受是早期 GNN 经验失效，HGTConv 在 RTX 4090 上 forward 100k-edge 子图亚秒级，事件密度高于经验区间不影响训练。已记入 known_issues "经验启发式校准记录" 子节。
  - **决策 9 new**：训练样本单位 = (target_event, subgraph_at_target, label) 三元组，**不是** (window, subgraph, label) 二元组。per-window down-sampling 防 M5_h1 主导；attack 全保留 / benign cap 1000；leave-one-out 在 (host, window) 二元组上切但样本来自 target_events；预计 ~64k train / ~4k-8k test per fold。
  - **Q-2**：156 token SYNONYM_INIT 扫描显示仅 [OP_LOGON] 单 1 个 single-survivor，user 接受不修（cos-sim 1.0 可被 Phase 7 联合预训练自然推开）。
  - subgraph.max_nodes 50 → 128（PIDS 文献 KAIROS / MAGIC 在 100-500 节点区间，128 是 2 的幂便于 batched matmul，sweep space [96, 128, 256]）。
- **新增 known_issues**：经验启发式校准记录（避免被 16k-200k events/window 数字误导）。

---

## Checkpoint 5 — Phase 1.6 Lightning DataModule

- **完成日期**：2026-05-05
- **Commit**：`4b8dd6a`
- **核心交付物**：`datamodule.py` 实现决策 6 + 8 + 9（3 modes: pretrain / finetune_anomaly / finetune_compression；DataLoader trio；2 setup asserts: `_assert_no_window_leakage` + `_assert_tz_alignment`，错误信息直接指向修复点；LabelLoader callable 接口 + benign_only_label_loader stub）；`tests/test_datamodule.py`（12 测试含 2 必要反例）；`scripts/build_fold_stats_report.py` 跨 10 leave-one-attack-out folds 报告；`data/atlas_fold_stats.json` 提交。
- **关键 metric**：**140 / 140 测试通过**；10 leave-one-attack-out folds 全部 0 leakage；训练样本规模 **40k-46k / fold**；测试样本规模 **1k-7.7k / fold**（与决策 9 预测 ~64k / ~4-8k 对齐）；54 (host, window) buckets 总数。
- **决策点**：
  - 反例 1：leakage assert on constructed (X, 3) overlap 触发，错误含 "DECISION 6 VIOLATION" + 指向 `_partition_by_scenario`。
  - 反例 2：TZ assert on 12-hour offset 触发，错误含 "TZ SANITY FAIL" + 指向 `localize_eastern`。
  - LabelLoader 接口设计：callable 注入，stub `benign_only_label_loader` 在 Phase 1 阶段（label=0 全 benign），Phase 8 替换为 `AtlasGroundTruthLabelLoader`。fold stats 报告 attack 列全 0 已显式标注。
- **新增 known_issues**：Phase 8 待办 — `AtlasGroundTruthLabelLoader` 实现（解析 ATLAS `paper_experiments/{S*,M*}/output/` 攻击实体清单）。

---

## Q-2 mini-checkpoint — SYNONYM_INIT Regression Script Persisted

- **完成日期**：2026-05-05
- **Commit**：`b606a5c`
- **核心交付物**：`scripts/check_synonym_init.py` standalone CLI（完整 docstring、输入 `--model` / `--threshold`，输出 3-line summary + single-survivor list，exit code 语义清晰）。原 ad-hoc shell snippet 升级为 first-class regression gate。
- **关键 metric**：bert-base-uncased 上 156 / 156 tokens have ≥1 in-vocab synonym；single-survival = 1（[OP_LOGON]→user）；low-survival = 1；threshold = 20；**exit 0 = OK**。
- **决策点**：Q-2 mini-checkpoint 持久化到 v0.1-data tag 内（不推迟到 Phase 2），保证任何人 checkout v0.1-data 都能复现 Checkpoint 4 报告里的 Q-2 结果。
- **新增 known_issues**：无。

---

## Phase 1 Closeout — Handoff Infrastructure（PROGRESS.md / CHECKPOINT_LOG.md）

- **完成日期**：2026-05-05
- **Commit**：（本次 commit，hash 在 git log post-merge 可见；**该条目自身的 hash 在 v0.1-data tag commit chain 末位**）
- **核心交付物**：`docs/PROGRESS.md`（单一真相源，每 checkpoint 整体覆写）；`docs/CHECKPOINT_LOG.md`（追加式 audit trail，本文件初始化含 Phase 0 + 5 checkpoints + 2 mini-checkpoints + 此 closeout 自身）；`README.md` 顶部新增"新会话起步指引"段；`docs/known_issues.md` 加 "Phase 8 待办" 子节（label loader 实现）。
- **关键 metric**：N/A（纯文档基础设施）。
- **决策点**：从 Phase 2 起每 checkpoint commit 必须同步更新这两份文档，否则视同 checkpoint 未完成。AI 代理之间会话交接的 token-cost 优化（贴 PROGRESS.md → 几秒带入 context vs 重新介绍项目）。
- **新增 known_issues**：Phase 8 待办（AtlasGroundTruthLabelLoader 实现 spec）。

---

*下一条记录：Phase 2 / Checkpoint 6 (BERT 文本编码器集成)。*
