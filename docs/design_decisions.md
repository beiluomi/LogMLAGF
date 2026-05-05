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

- GraphFormers (NeurIPS '21) — 通用文档图 + LM 融合，**非异构、非时序、非溯源图领域**。
- PLATO (KDD '24) — 文本图协同表征学习，**非时序节点记忆、非 APT 检测**。
- THLM — 异构 + LM，**非时序、非预训练阶段双向融合**。

**禁止使用 "to the best of our knowledge" 单独作为新颖性论证**。必须用上述差异化对比补足。

### 创新点 2（RAPA-GTCL）

> **首个把 MITRE ATT&CK 模板作为图增强样本、与图–文对比目标在预训练阶段联合训练的框架。**

**关键限定词（缺一不可）：**

- "MITRE ATT&CK 模板"——结构化的 TTP 模板，不是任意攻击知识或规则告警。
- "图增强样本"——graph augmentation samples 注入良性图，不是规则匹配、不是 IOC 黑名单。
- "图–文对比目标"——GTCL，InfoNCE 形式，正负样本同时来自图侧与文本侧。
- "预训练阶段联合训练"——pretraining-time joint objective，不是 inference-time augmentation，不是 finetune 阶段引入。

**最近的先验工作（必须在 related work 正面对比）。**

- Threatrace — 基于 ATT&CK 的异常检测，**非 graph augmentation、非对比学习目标**。
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
- **不实现同构 GraphSAGE 中间产物**——这是工程上的浪费。
- 同构 GAT、HGT-without-temporal 仅作为 Phase 11 消融对照（B4、B5）。

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

## 修订历史

- **2026-05-05** — 初版（v0.0-scaffold）：决策 1–4 写入。
