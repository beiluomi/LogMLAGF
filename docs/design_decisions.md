# LogHetero 关键设计决策记录

> **本文件是后续所有阶段的"宪法"。** 任何与下列决策冲突的实现都必须先在 PR 中提出 RFC 修改本文档，再写代码。修改本文档的 PR 必须由项目所有者审核合并。

---

## 决策 1：不复现任何已有论文作为方法主线

**决定（2026-05-05，项目启动）。** LogHetero 是一个独立研究项目；MLAGF 不作为基线、不引用、不实现。所有方法实现都是 LogHetero 自身。基线只跑已发表的 SOTA：

- **异常检测（主线）**：AirTag (USENIX Sec'23) / KAIROS (S&P'24) / MAGIC (USENIX Sec'24) / FLASH (NDSS'24) / PROGRAPHER (USENIX Sec'23) / Unicorn (NDSS'20) / ProvDetector (NDSS'20)
- **日志压缩（次要任务，推迟到 rebuttal 阶段）**：CPR (CCS'16) / NodeMerge (CCS'18) / LogShrink (ICSE'24)

**论证。** 复现已有方法只会让我们陷入"在 X 基础上 +Y"的增量框架，审稿人会问"为什么不直接和 X 比？"——我们要的是清晰的"我们做了什么、谁先做的"。同时仓库历史不带 MLAGF 代码痕迹，投稿时双盲处理简单。

**风险与对策。** 审稿人可能问"既然你们以前做过 MLAGF，凭什么这次不延续？"。Related-work 章节将 MLAGF 列入"prior work in this space"并明确说明本工作的范式差异：同构图 → 异构时序图、后融合 → 预训练联合融合、单模态目标 → 图–文对比目标。

---

## 决策 2：两条核心新颖性声明的精确措辞

**决定（2026-05-05，项目启动）。** 论文 introduction 与 related-work 章节一律使用以下精确措辞，不得擅自扩展。任何阶段的代码注释、commit message、README 中提到 novelty 时都要用这套措辞。

### 创新点 1（HTGN-LM Co-Pretraining）

> **首个面向溯源图 APT 检测的、把异构时序 GNN 与 LM 在预训练阶段做双向跨模态融合的框架。**

**关键限定词（缺一不可）：**

- "面向溯源图 APT 检测"——domain-scoped，不是通用图–文学习。
- "异构时序 GNN"——heterogeneous + temporal 同时具备。
- "LM"——预训练语言模型（如 BERT），不是 word embedding，不是 NLM。
- "预训练阶段"——pretraining-time fusion，不是 finetune-time fusion，不是推理时拼接。
- "双向跨模态融合"——文本 token 与图节点互相 query，不是单向 cross-attn，不是 [SEP] 拼接，不是 late-fusion。

**最近的先验工作（必须在 related work 正面对比）。**

- **GraphFormers** (Yang et al., NeurIPS '21; arXiv:2105.02605) — GNN-nested Transformer 做文档图 + LM 表示学习。**非异构、非时序、非溯源图领域、非每层双向跨模态融合。**
- **GreaseLM** (Zhang et al., ICLR '22 Spotlight; arXiv:2201.08860) — 多层 modality interaction 融合 LM 与 KG，**架构上最接近我们的双向跨模态融合**。但目标领域是 commonsense QA + 知识图，**非异构异质类型、非时序节点记忆、非溯源图、非预训练阶段（其训练目标是 finetune for QA）**。
- **Patton** (Jin et al., ACL '23 Long Oral; aclanthology.org/2023.acl-long.387) — text-rich network 上的 LM 预训练（network-contextualized MLM + masked node prediction），**预训练范式最接近**。但**网络同构、无时序、无双向跨模态注意力机制**。
- **THLM** (Zou et al., EMNLP Findings '23; arXiv:2310.12580) — text-attributed heterogeneous graph 上的 LM 预训练，**"异构 + LM 预训练"维度最直接的先验**。但**LM 与异构 GNN 是 joint optimization 而非每层双向跨模态融合；无时序节点记忆；非溯源图 / 非 APT 检测。**

**禁止使用 "to the best of our knowledge" 单独作为新颖性论证**。必须用上述差异化对比补足。

### 创新点 2（RAPA-GTCL）

> **首个把 MITRE ATT&CK 模板作为图增强样本、与图–文对比目标在预训练阶段联合训练的框架。**

**关键限定词（缺一不可）：**

- "MITRE ATT&CK 模板"——结构化的 TTP 模板，不是任意攻击知识或规则告警。
- "图增强样本"——graph augmentation samples 注入良性图，不是规则匹配、不是 IOC 黑名单。
- "图–文对比目标"——GTCL，InfoNCE 形式，正负样本同时来自图侧与文本侧。
- "预训练阶段联合训练"——pretraining-time joint objective，不是 inference-time augmentation，不是 finetune 阶段引入。

**最近的先验工作（必须在 related work 正面对比）。**

- **Threatrace** — provenance graph 上的 node-level 异常检测。**非 graph augmentation、非对比学习目标。** 注：Threatrace 与 ATT&CK 的强关联性需在 Phase 12 写 related work 前重新核实（见 `docs/known_issues.md` "Phase 12 待核实"），如果其实并不显式使用 ATT&CK 模板，则把它移到 Innovation 1 的 PIDS baseline 类（与 KAIROS / MAGIC / FLASH 同类），改用真正用 ATT&CK 做攻击合成的工作（TTPDrill / AttacKG / Holmes / RapSheet 候选）。
- **ConGraT** (Brannon et al., TextGraphs-17 @ ACL '24 workshop; arXiv:2305.14321, 首发 2023-05) — text-attributed graph 上的 graph–text contrastive 预训练，CLIP-风格 InfoNCE，**"图–文对比目标"维度最直接的先验**。但**无攻击模式增强（无 RAPA）、非异构异质类型、非溯源图领域、非预训练阶段联合多目标**。注：workshop paper，submitter 可能被审稿人就 venue 权重质疑——以 arXiv 首发时间锚定 priority。
- 其他基于 ATT&CK 驱动合成的 PIDS 工作 — **非预训练阶段、非图–文对比框架**。

同样禁止 "to the best of our knowledge" 单独充数。

---

## 决策 3：双盲匿名化策略

**决定（2026-05-05，项目启动）。** 投稿目标是 USENIX Security / NDSS / CCS / ICSE，全部要求双盲。匿名化策略：

1. **开发期身份。** 仓库 local config 设为 `user.email = zbyangyangyang@gmail.com`、`user.name = beiluomi`（与 GitHub 用户名一致）。**不动全局 git config**，避免污染其他项目。本仓库 commit 历史保留真实身份，确保贡献者可信、可追溯。
2. **匿名仓库（Phase 12 实现）。** 用 `git filter-repo` 镜像出独立的匿名仓库（如 `anonymous-loghetero/loghetero-anon`），通过 `--mailmap mailmap.anon` 重写所有 commit 的 author / committer 邮箱、姓名，以及 commit message 中可能出现的真实标识。
3. **主仓库历史不做任何破坏性操作。** 投稿不影响主仓库；rebuttal 阶段维护两个仓库（公开主仓库 + 匿名投稿仓库）。
4. **代码内匿名化。** 所有 docstring、注释、license header、`docs/architecture.md` 等英文产物中不得包含真实姓名、邮箱、机构、内部代号。Phase 12 用 `scripts/anonymize_check.sh` 扫描敏感词清单。
5. **W&B 与日志。** 投稿用 `WANDB_ENTITY=anonymous-loghetero`，本地默认 offline 模式（避免 entity 信息泄露）。TensorBoard 日志同样不得包含可识别字段。
6. **数据。** DARPA TC E3、ATLAS 不在仓库内，DVC remote 与匿名仓库分离；attack template 数据来自公开 `mitre/cti` 仓库，本身不含可识别信息。

**Phase 0 已落地的部分。**

- Makefile 加 `make anonymize` 占位 target（指向 Phase 12 实现）。
- 本节内容写入决策记录。
- `.gitignore` 排除 `.env*` 与 `*.secret` 文件，避免意外提交敏感信息。

**Phase 12 待执行。**

- `scripts/anonymize_check.sh` — 敏感词扫描（ripgrep + 正则）。
- `scripts/anonymize_repo.sh` — `git filter-repo` 流水线 + mailmap 模板生成。
- 投稿前 dry-run，由项目所有者复核后才推到匿名仓库。

---

## 决策 4：其他工程不变量

以下选择已经定下，任何阶段不允许擅自改变。如果实现中遇到问题，**先停下来在 PR 中提出 RFC**，由项目所有者裁定。

### 4.1 文本编码器策略

- 默认使用 `bert-base-uncased`，**冻结**（CLIP-style）。
- LoRA on last 4 layers 仅作为 Phase 7 消融对照（B6）。
- 全微调作为第三档消融。
- **不做从零 BERT 预训练。**
- DAPT 仅在 Phase 7 联合训练发现文本表示明显欠拟合时作为 1-epoch 热身追加。

### 4.2 图编码器策略

- HTGN（HGT + Time2Vec + TGN memory）从 day 1 实现。
  - **HGT** (Hu, Dong, Wang, Sun — WWW '20; arXiv:2003.01332; DOI 10.1145/3366423.3380027) 是 HTGN 的 building block；论文 related work 中引用为异构图 transformer 的基础工作，**不作为 novelty 对比对象**——我们的贡献在于把 HGT 与 Time2Vec、TGN-memory、双向跨模态融合组合成新的预训练框架，而非重新发明异构 attention。
- **不实现同构 GraphSAGE 中间产物**——这是工程上的浪费。
- 同构 GAT、HGT-without-temporal 仅作为 Phase 11 消融对照（B4、B5）。

> **† Phase 11 消融 B5 实施细节（2026-05-05 决议，回应 Checkpoint 7 RFC）**：B5（HGT-without-temporal）通过两个开关组合实现——`residual_alpha=0` 关闭 Time2Vec 边残差通道（详见 `docs/known_issues.md` "HGTConv edge_attr 接口限制 + Option C 残差通道决议"），`tgn_memory.enabled=false` 关闭 TGN 节点记忆模块（Checkpoint 8 实现时同样加 switch）。剩余配置即为 stock HGTConv on heterogeneous graph 的纯空间异构基线。这个组合开关让 B5 与完整 LogHetero 的代码路径**只差两个 yaml 配置项，不需要维护独立模型类**。`configs/model/graph/htgn.yaml` 是这两个 switch 的 single source of truth。

> **‡ Footnote (2026-05-06, Checkpoint 11.2-γ-1 决议；2026-05-06 Phase 4 launch spec 严谨化补丁)：HTGN link prediction sanity 在当前设置下是 structure-dominated 任务（边界条件：current ATLAS data + structural negative sampling strategy + input-feature BERT injection 融合方式），BERT 跨模态融合的真实 evaluation 推到 Phase 7-8**
>
> Phase 4 入口对 Phase 3 conditional pass 做 sanity AUC re-validation，4 档 BERT 集成方案（random Gaussian baseline / [CLS] entity-identifier / mean-pool entity-event-context TOP_K=5 truncated / mean-pool entity-event-context TOP_K=2 in-spec 50-150 token）测得 4-seed mean test AUC 全部聚集在 **0.811-0.815 区间，std 0.007-0.016，统计上完全无差异**（详见 `docs/known_issues.md::Phase 12 论文素材::Phase 3 sanity AUC 演进数字` 4-row ablation 表）。这意味着在 current ATLAS 数据 + random edge masking + structural negative sampling + input-feature BERT injection 这一组合条件下，链路预测信号由图拓扑主导，BERT 语义特征通过 input-feature 通道无法贡献额外可分辨信息。
>
> **边界条件须保留**：cold-start link prediction 文献中存在大量依赖 semantic features 的反例（GraphFormers / Patton / GreaseLM / ConGraT 等 text-rich graph 工作；特别是 text-rich graphs without dense local structure 场景），措辞写成 "structure-determined" 会被审稿人引文献当场反驳，因此此处统一取 "structure-dominated under current setting" 的诚实陈述。Phase 4 入口实验否定的精确假设是"BERT 简单 input-feature injection 能提升我们当前设置下的 link prediction sanity"，**不能外推为**"BERT 在所有 link prediction 任务上无效"也**不能外推为**"BERT 在 anomaly detection 上必有效"。
>
> **决议**：Phase 3 conditional pass 状态从 "pass / fail" 二元变更为 "**informationally complete**"——回答的是"HTGN 在 structure-only 任务上 ceiling 0.81-0.82 OK"而非 "BERT 集成 OK"。原 Phase 4 BERT 重测 0.88 hard gate **撤销**（gate 设计基于"BERT 加 features 通常 +0.05-0.10 lift"的文献经验，但那个经验适用于 sentence classification / NER / QA 等 features 直接决定输出的任务，不适用于本设置下 structure-dominated 的 link prediction——agent Phase 3 Option A 决议时援引的论证是错的，本 footnote 诚实标记）。
>
> **BERT 跨模态融合的真实 evaluation 场景**：Phase 7 联合预训练 + Phase 8 anomaly detection。attack 事件含语义异常签名（罕见 process name + 异常文件路径模式 + IP 黑名单等），BERT semantic features 在 anomaly classification 上**可能**带来 lift（待 Phase 7-8 实证验证；该假设属于 hypothesis to test 而非 default-true），且 cross-modal attention（Phase 4.1 Checkpoint 12 实施）作为 fusion mechanism 在文献先验中比 input-feature injection 更适合 attack-anomaly use case，但这一适配性也需要 Phase 4 Checkpoint 14.5 异常检测前置 probe 给出方向性证据后再继续推进 Phase 7-8 大规模训练。
>
> **Phase 4 进度影响**：Checkpoint 11 informationally complete → 直接进 Checkpoint 12 双向跨模态注意力实施。Phase 4 整体目标改为 "verify cross-attention architecture 落地 + forward 不报错 + 梯度正常 + 七项 gate 全过 + Checkpoint 14.5 anomaly probe 双条件通过"，AUC-style 单点验证关卡留到 Phase 7-8。详见 `docs/known_issues.md::Phase 4 待办::Phase 3 sanity AUC re-validation` 的 "completed with informational null finding" 标注 + `Phase 7 待办` 新增的 "BERT-fused-attention vs HTGN-only quick A/B 扩展" 议程。
>
> **Phase 12 论文价值**：4-row ablation 数字保留作为 negative-result-as-positive-contribution 素材——"我们诚实尝试 4 种 BERT 集成 + 验证在当前设置下 link prediction structure-dominated + 把跨模态融合真实 evaluation 推到 Phase 7-8 anomaly detection" 是 Methods 章节 ablation 段末尾的一段 design rationale，比掩盖 null finding 强；同时配合 known_issues.md Phase 12 论文素材子节的边界陈述（避免审稿人 cold-start link prediction 反例反驳）一同写入论文，确保严谨性而非过度断言。

### 4.3 融合策略

- 双向跨模态注意力（BERT 第 3 / 6 / 9 / 12 层）从 day 1 实现。
- **不实现 [SEP] 拼接中间产物**——这是工程上的浪费。
- 简单 concat、late-fusion 仅作为 Phase 11 消融对照（B3）。

### 4.4 对比学习目标

- GTCL 是端到端联合预训练目标，从设计初期就和 RAPA 二分类、aux-MLM 一起反向传播。
- 三类负样本混合：50% in-batch random + 30% in-window hard + 20% RAPA-synthetic。比例通过 Hydra 配置调整。

### 4.5 模块化

- HTGN 与 RAPA-GTCL 都是 Hydra 可独立开关的子模块。
- 消融矩阵 B0–B6 直接映射这两个模块的开关组合。

### 4.6 工具链

- 依赖管理：`uv`（不是 poetry，不是 pip-tools）。
- 大文件管理：`DVC`（不是 Git LFS）。
- 实验跟踪：W&B（默认 offline 模式）+ TensorBoard mirror。
- 代码注释 / docstring：英文。
- 内部决策文档（本文件、`known_issues.md`）：中文。
- 投稿用文档（`architecture.md` / `reproduce.md` / `attack_templates.md`）：英文。

---

## 决策 5：DARPA TC E3 CDM → 5 类节点映射规则

**决定（2026-05-05，回应 Q2）。** 把 DARPA TC E3 CDM schema 的全部节点类型映射到 LogHetero 的 5 类异构节点（process / file / socket / network / user）。映射表如下，**写死在 `src/loghetero/data/parsers/darpa_e3.py` 的 `_CDM_NODE_TYPE_MAP` 常量**，不允许在 Phase 1+ 的代码中分散硬编码。

| CDM 类型              | LogHetero 节点类型 | 备注                                              |
|-----------------------|-------------------|---------------------------------------------------|
| Subject (Process)     | process           |                                                   |
| Principal             | user              |                                                   |
| FileObject            | file              |                                                   |
| UnnamedPipeObject     | **file**          | 与 KAIROS / MAGIC / FLASH 对齐（关键，见下方论证） |
| MemoryObject          | file              | 共享内存按文件语义处理                              |
| SrcSinkObject         | socket            | generic source/sink，多数为 IPC †                  |
| NetFlowObject         | network           |                                                   |
| Event                 | （边，不是节点）   | Event 承载操作类型与时间戳，不参与节点类型           |
| 未列出的边缘类型      | file（兜底）       | 同时计入 `docs/known_issues.md` 待审               |

> **† SrcSinkObject 映射注解**：本映射为 LogHetero 默认，属于灰色地带（KAIROS / MAGIC 在它们的 ATLAS 处理脚本中可能采用不同映射）。Phase 8 跑 KAIROS / MAGIC 基线时如发现其官方代码采用其他映射，按本节末"Phase 8 基线一致性原则"统一更新本表，不在基线代码里 patch。

### UnnamedPipeObject → file 的论证（Q2 修正了 Phase 0 报告里的默认）

1. **PIDS 文献一致性**：KAIROS (S&P'24) / MAGIC (USENIX Sec'24) / FLASH (NDSS'24) 三篇主要基线都把 pipe 当 file 处理。我们要和它们公平对比就必须保持一致。
2. **语义同构**：pipe 的访问语义是 `read` / `write`，与 file 同构；与 socket 的 `connect` / `send` / `recv` 异构。
3. **Audit 日志 fd 行为**：pipe 的 file descriptor 在内核审计日志中表现为文件式 IO（与普通 file 走同一套系统调用）。

### ATLAS user-node 数量脚注（2026-05-05，Q-1 mini-checkpoint）

11-EventID dispatch 在 ATLAS 16 (scenario, host) 上产生 70 个 user 节点（详见 `docs/known_issues.md` 同标题条目）。这是 ATLAS 数据集本身的客观特征——4624 几乎全是 LogonType=5 (Service) 噪声、4625 全为零、4648 罕见——**不是 dispatch 漏报**。架构一致性目标已达成（5 类节点中 4 类在主数据集非零，仅 socket 等 DARPA TC E3）。Phase 12 论文 Limitation 章节将明确说明 user-node 故事在 DARPA TC E3 cross-dataset evaluation (Phase 9) 上更完整地呈现。

### Phase 8 基线一致性原则

如果 Phase 8 跑某个基线时发现该基线把 pipe 处理成别的类型（例如 ProvDetector 或 Unicorn），**立即停下来在 PR 中提出，由项目所有者裁定**。原则：所有对比方法在数据预处理层共享同一映射表，不许各自为政——任何映射调整必须在本表统一更新，不能在基线代码里 patch。

---

## 决策 6：Leave-One-Attack-Out 切分协议（host + time-window 联合）

**决定（2026-05-05，回应 Q3）。** ATLAS 10 个攻击场景的评测严格走 leave-one-attack-out 协议，**良性背景流量按 (host_id, time_window) 二元组联合切分**——同一主机 + 同一时间窗的良性事件不允许同时出现在 train 与 test。

### 论证（reviewer 可审计的标准）

KAIROS (S&P'24) 与 MAGIC (USENIX Sec'24) 都明确批评过 ATLAS 原作切分协议存在**良性数据泄漏**：原协议只按攻击场景切，但同一主机的良性流量在 train / test 间共享，模型可以学到"主机指纹"而非异常模式。LogHetero 的协议把 `(host, time-window)` 当成最小切分单元，杜绝这种泄漏。

### 具体协议

- **目标场景**：被 leave-out 的那 1 个 attack scenario 作为 test 集，包含其攻击事件与该场景内所有良性背景流量。
- **训练良性池**：从其他 9 个 scenario 中按 `(host_id, time_window)` 二元组联合采样良性事件。
- **不变量**：对于任意一对 `(host_id, time_window)`，其全部良性事件要么完全进 train，要么完全进 test，不允许跨集泄漏。
- **不变量校验**：`src/loghetero/data/datamodule.py` 在 `setup` 时必须 `assert` 这一条件，违反则 fail-fast。
- **时间窗粒度**：**1.0 小时**（最终决定，详见下方 "Phase 1 数据流水线跑起来后再回看的事项" 子节）。

### Phase 1 数据流水线跑起来后再回看的事项

**时间窗粒度（最终决定，2026-05-05，回应 Checkpoint 4 数据）：1 小时。** 这是基于 ATLAS 实际事件密度（每 window 25k–134k events）拍定的全局统一粒度。事件密度高于早期 GNN 经验区间但完全在现代 HGT 容量内（HGTConv 在 RTX 4090 上 forward 100k-edge 子图为亚秒级）。所有 (scenario, host) 共享同一粒度，**不分档**，依据是 Checkpoint 4 第 17 张全局 CDF 图无 h1/h2 bimodal、无 attacker/victim 单一分轴可分。

**历史背景（保留以供 audit）。** 决策 6 初版写"时间窗粒度 1 小时是初值，Phase 1 跑通后须输出每个 scenario 的事件密度直方图，由项目所有者审视后决定是否调整（事件稀疏的 scenario 可能拉到 4 小时；事件密集的 scenario 可能压到 30 分钟）"。Checkpoint 4 数据（`data/atlas_window_density_summary.json`）显示：所有 16 (scenario, host) 在所有 swept 粒度（0.5h / 1h / 2h / 4h）下平均事件密度 16k–200k，**没有任何粒度落入初版 launch spec 的 [10, 10000] 启发区间**——该启发区间是早期 GNN 时代经验，对现代 HGT 不适用，已在 `docs/known_issues.md` "经验启发式校准记录" 子节标注。最终统一选 1.0h（保持初值），不分档。

调整时**所有 scenario 必须用同一粒度**这条规则保留——不能逐 scenario 调，否则评测协议本身变成不可比的混合体。

---

## 决策 9：训练与评测样本单位（per-event subgraph，不是 per-window）

**决定（2026-05-05，回应 Checkpoint 4 数据）。** 训练样本的逻辑单位是 `(target_event, subgraph_at_target, label)` **三元组**，**不是** `(window, subgraph_of_window, label)` 二元组。

### 论证

Checkpoint 4 数据揭示 ATLAS 每 window 含 16k–200k events，远超早期 GNN [10, 10000] heuristic。如果以 window 为样本单位：

- M5_h1 这样的高密度 host 会单独占据数据集主导（5 windows × 124k events），稀释其他 hosts 的信号；
- 良性 / 恶意 window 数量比极不平衡（多数 window 只含良性事件）；
- BERT 文本 input 没有自然对应物——一个 window 含数万事件文本无法 batch；
- HTGN 子图采样也以单个 target event 为中心更自然（K-hop 邻域 = 该事件附近的因果链）。

以 event 为样本单位（subgraph 仍以 event 为中心做 K-hop）解决以上四问题：BERT 处理单 event 的清洗后文本（几十–几百 token），HTGN 处理以 event 为中心、最多 `subgraph.max_nodes`（默认 128）节点的子图，标签按事件粒度而非 window 粒度。

### 协议

1. **训练样本三元组** `(target_event, subgraph_at_target, label)`：
   - `target_event`：来自某个 (host, window) 内的某一具体事件，按下方 §2 采样；
   - `subgraph_at_target`：以 `target_event` 涉及的 subject + obj 节点为中心、K-hop 异构邻域采样得到的子图（max_nodes / khop / edge_ranking 走 Hydra 配置 `configs/data/atlas.yaml::subgraph`）；
   - `label`：良性 / 恶意（pretrain 模式 `None`；finetune_anomaly 模式来自 ATLAS ground truth 的二分类标签）。

2. **每 window 内 target_event 采样策略**（防止 M5_h1 等高密度 host 主导数据集）：
   - **良性 window**：均匀下采样到上限 `sample.max_events_per_window`（默认 1000）；
   - **恶意 window**：**全部攻击事件保留**（不下采样，攻击事件稀缺），良性事件下采样到 `sample.max_events_per_window`；
   - 上限作为 Hydra 参数透出（`configs/data/atlas.yaml::sample.max_events_per_window`）；
   - 下采样使用全局 numpy 种子（已在 `utils/seed.py` 固定）保证可复现，跑两次同 config 得到同一 train / test 切分与同一 target_event 集合。

3. **leave-one-attack-out 与决策 6 的关系**：
   - 切分协议依然作用在 `(host_id, time_window)` 二元组上（决策 6 保持）；
   - 但训练 / 评测样本来自该二元组下属的所有 `target_events`；
   - **不变量**：任意 `(host, window)` 内的所有 `target_events` 完全进 train 或完全进 test，不允许跨集泄漏（决策 6 的 fail-fast assert 在 event 层面照样成立）。

4. **预计样本规模**（基于 Checkpoint 4 数据 + `max_events_per_window=1000`）：
   - 训练样本：16 hosts × ~4 windows/host × ~1000 events/window ≈ **~64k 训练样本**
   - 测试样本（leave-one-attack-out 一个 fold）：1–2 hosts × 1–7 windows × 1000 events/window ≈ **~4k–8k 测试样本**
   - 64k 训练样本足以训练 BERT-base + HTGN 联合模型（GLUE benchmarks 多在 数 K–数十 K 量级）。
   - 4k–8k 测试样本足以测出稳定 F1（标准 anomaly detection benchmark 测试集多在 1k–10k 量级）。

### Phase 1.6 DataModule 实现 spec

- **三种模式**：`pretrain` / `finetune_anomaly` / `finetune_compression`
  - pretrain 模式：label 字段返回 `None`（无监督）
  - finetune_anomaly 模式：label 字段返回 0 (benign) / 1 (attack)
  - finetune_compression 模式：label 字段返回压缩 ground truth（Phase 10 详化，Checkpoint 5 占位即可）
- **DataLoader 三接口**：`train_dataloader / val_dataloader / test_dataloader`，每模式都正确实现
- **决策 6 不变量 assert**（`(host_id, time_window)` 联合切分）必须在 `setup` 时验证，违反 `AssertionError` fail-fast
- **Cross-log-type TZ sanity check** 必须在 `setup` 顶部跑：取每个 (scenario, host) 的 dns / firefox / security_events 第一条事件，验证 dns 的 EDT→UTC 转换后与 firefox 的 UTC 时间差 ≤ 5 min，失败抛 `AssertionError` 错误信息直接指向 `parsers/atlas.py::localize_eastern`
- **≥2 反例测试** 覆盖上述两个 assert 的真正触发：
  - (a) 故意构造跨集泄漏的 (host, window) 数据，期望 leakage assert 触发
  - (b) 故意把某个 log type 的时间戳偏移 12 小时（模拟 TZ 错误），期望 TZ sanity assert 触发

### Footnote (2026-05-06, Checkpoint 11.1 RFC)：Phase 4 跨模态联合预训练数据 benign-only 约束决议

Phase 4 跨模态联合预训练阶段采用 mixed 数据（含未过滤 attack 事件）作为 **unverified-impact baseline 而非默认无害选择**。Benign-only pretraining 推到 Phase 7 实施，届时按 `AtlasGroundTruthLabelLoader`（Phase 8 待办成果）切真 benign 子集。Phase 11 ablation **必须**包含 `pretrain_data: {mixed, benign_only_ground_truth}` 二档对比（如时间允许加 `benign_only_paper_timeline` 第三档）量化 attack-noise 对预训练表征的实际污染程度。**如 ablation 显示 mixed vs benign_only 在 Phase 8 anomaly F1 上差异 > 3 个百分点，论文 Methods 章节必须诚实说明 mixed 预训练带来的 representation 偏差并把 benign-only 作为推荐配置**。

**决议背景**：Phase 3 / Checkpoint 10 Option C 决议（放宽 benign-only 约束）把 Phase 4 入口的 benign-only 重审作为待办挂出（详见 `docs/known_issues.md::Phase 4 待办::Pretraining 数据 benign-only 约束的重审议程`）。Checkpoint 11.1 RFC 三选项 A（前置 Phase 8 工作）/ B（mixed + Phase 7 切 benign）/ C（论文 timeline 启发式 stop-gap），user 拍板 **Option B 附三条件**：(1) 本 footnote 措辞紧版 + 必须 ablation + 3pp 阈值；(2) Phase 11 ablation 矩阵预先扩展（详见 `known_issues.md::Phase 11 消融扩展`）；(3) Phase 7 启动前 mixed-vs-benign quick A/B 测试预设议程（详见 `known_issues.md::Phase 7 待办`）。

**关键纪律**：本 footnote 把 mixed 数据明确标注为 "unverified-impact baseline" 而非"默认无害"——避免"mixed 影响小"这个未验证假设悄悄变成既定事实写进论文。Phase 12 写论文时必须先看 Phase 11 ablation 实测数字才决定 Methods 章节叙事方向。

---

## 决策 7：AI 协作披露策略（commit `Co-Authored-By`）

**决定（2026-05-05，回应 Q5）。** 开发期所有 commit 保留 `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` 末尾行；投稿前由匿名化流水线统一处理。

### 论证

1. **学术诚信透明性**：AI 协作披露是正确做法；commit history 本身就是一份天然的 audit trail，比事后撰写披露段落更可信。
2. **匿名化兼容**：Phase 12 `git filter-repo + .mailmap` 流水线会把所有作者邮箱（包括 Claude 的 noreply 地址）统一重写为 `anonymous-loghetero <anonymous@anonymous.invalid>`，不构成双盲投稿障碍。
3. **顶会要求对齐**：NeurIPS / ICML / USENIX 等近期都明确要求披露 AI 使用。保留 `Co-Authored-By` 是最低成本的合规方式。

### 实施

- **开发期**：所有由 Claude Code 创建的 commit 自动追加 `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`。
- **项目所有者手工 commit**：自由选择是否追加（手工劳动不强制，但建议保持一致）。
- **Phase 12 匿名化镜像**：`scripts/anonymize_repo.sh` 调用 `git filter-repo --mailmap mailmap.anon`，把所有人——包括 Claude——重写为同一匿名身份。投稿仓库的 commit history 不包含任何可识别信息（人或 AI）。
- **Mailmap 模板（Phase 12 会生成）**：

  ```text
  anonymous-loghetero <anonymous@anonymous.invalid> <zbyangyangyang@gmail.com>
  anonymous-loghetero <anonymous@anonymous.invalid> <noreply@anthropic.com>
  ```

---

## 决策 8：孤立节点（isolated node）保留策略

**决定（2026-05-05，Checkpoint 3 启动）。** 异构图构建时**保留**所有孤立节点（degree=0），在节点上加 `isolated=True` bool 属性，由下游模块决定怎么处理；**禁止在数据流水线层悄悄丢节点**。

### 论证

APT 检测里"出现一次就消失"的孤立节点经常是**攻击者的 staging server / C2 通道 / one-shot exfiltration endpoint**。例如：

- ATLAS S1 的 `0xalsaheel.com` 域名作为 phishing landing page，可能在整个良性背景流量里只被解析一次。
- C2 信标 `192.168.X.X` 出现一次后立即关闭。
- exfiltration 目标 `attacker.evil/upload` 只在攻击的最后阶段被访问。

**"出现一次"这个特征本身就是异常信号**——简单过滤孤立节点等于在数据流水线层就把异常信号删掉，让下游 HTGN + GTCL 看不到。

### 实施

- `src/loghetero/data/provenance_graph.py::build_graph()` 输出的 PyG `HeteroData` 在每个 node store 上加 `isolated: torch.BoolTensor`，标记 `degree == 0` 的节点。
- 下游模块（HTGN、anomaly head）可读 `node.isolated` 决定是否对孤立节点做特殊处理（例如给一个可学习的 isolated-node embedding bias）。
- **fallback 例外（仅一处）**：如果某 (scenario, host_id) 二元组的孤立节点占比 > 80%，说明数据切分太碎（窗口太小 / scenario 事件太稀），在 Checkpoint 4 报告里显式标注，由项目所有者决定是否调整 Phase 1.5 时间窗粒度。

### 与决策 6 的关联

决策 6 的 leave-one-attack-out 切分协议在 (host_id, time_window) 二元组层面切分良性数据；本决策在节点层面保留所有节点。两者正交：切分发生在窗口边界，孤立节点判定发生在窗口内部图构建。

---

## 修订历史

- **2026-05-05** — 初版（v0.0-scaffold）：决策 1–4 写入。
- **2026-05-05** — 第一次扩展：决策 5（CDM 节点映射）、6（Leave-One-Attack-Out 协议）、7（AI 协作披露策略）写入；回应 Q1–Q5。
- **2026-05-05** — 引用核实修订：决策 2 删除 PLATO（确认为 AI 引用幻觉），扩充 Innovation 1 prior work 至 4 条 verified 引用（GraphFormers / GreaseLM / Patton / THLM），Innovation 2 加入 ConGraT 作为 GTCL 直接先验且 Threatrace 标注 Phase 12 待核实；决策 4.2 加入 HGT building-block 引用；决策 5 给 SrcSinkObject 加显式 footnote。
- **2026-05-05** — 决策 8（孤立节点保留策略）写入；回应 Checkpoint 3 启动指令第 4 条。
- **2026-05-05** — Checkpoint 4 数据落定后修订：决策 6 时间窗粒度 1.0h 标 final（基于 16+1 直方图 + 决策表，全局统一不分档）；新增决策 9（训练与评测样本单位 = per-event subgraph）；`configs/data/atlas.yaml::subgraph.max_nodes` 50 → 128（PIDS 文献 KAIROS / MAGIC 在 100–500 节点区间，128 是 2 的幂便于批处理）。
- **2026-05-06** — Checkpoint 11.1 RFC 决议：决策 9 加 footnote "Phase 4 跨模态联合预训练数据 benign-only 约束决议" — Option B（mixed 数据 + Phase 7 切 benign-only）通过附三条件（unverified-impact baseline 措辞 / Phase 11 必须 ablation / 3pp 阈值 / Phase 7 quick A/B 前置议程）。详见决策 9 footnote + `docs/known_issues.md::Phase 4 待办` resolved 标注 + `Phase 11 消融扩展` + `Phase 7 待办`。
- **2026-05-06** — Checkpoint 11.2-γ-1 决议：决策 4.2 加 footnote "HTGN link prediction sanity 是 structure-determined 任务，BERT 跨模态融合的真实 evaluation 推到 Phase 7-8" — 4 档 BERT 集成 ablation (random / [CLS] / β truncated / β in-spec) AUC 全部 0.811-0.815 区间无统计差异；Phase 3 conditional pass 状态变更为 "informationally complete"，原 0.88 hard gate 撤销（gate premise "BERT 通常 +0.05-0.10 lift" 文献经验对 structure-determined link prediction 不适用，agent Phase 3 Option A 决议论证错误，本次诚实标记）；BERT 跨模态融合真实 evaluation 推到 Phase 7-8 anomaly detection；Checkpoint 12 双向跨模态注意力可直接启动，Phase 4 整体目标改为 "architecture 落地 + forward 不报错 + 梯度正常"。
