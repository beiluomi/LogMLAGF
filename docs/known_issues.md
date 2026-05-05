# Known Issues

## 经验启发式校准记录（避免被早期 GNN 数字误导）

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
