# Checkpoint 16 Hard Negative Coverage 6 vs 8 Categories Cross-Reference Design

**Stage**：Phase 5 Checkpoint 16 launch / Stage 1（Tightening 1 硬要求 1-4 落档）
**Created**：2026-05-08
**Owner**：implementer（Stage 1）；spec compliance reviewer + code quality reviewer 验证完整性（Stage 2）
**Branch / HEAD**：`feat/04-cross-attention` @ `9a9eedf`（Path B audit gap close），上游 `1094df1`（Cycle F + Checkpoint 15 closure）

---

## §1 Context / motivation

Phase 5 创新点二即"首个把 MITRE ATT&CK 模板作为图增强样本与图文对比目标在预训练阶段联合训练"叙事的核心方法论防御点之一是**避免合成攻击假可分性陷阱**。GPT critique（2026-05-06）锁定 6 类 hard negative benign admin behaviors 必须在 Phase 5 模板设计中显式 cover（见 `docs/known_issues.md::Phase 5 待办` 父 entry "20 TTP 模板设计必须含 6 类 hard negative benign admin behaviors"），让 Phase 8 anomaly classifier 必须区分"真攻击 TTP"与"模式相似的良性管理员行为"而非"攻击 vs 普通良性"。

Cycle F + Checkpoint 15 closure（commit `1094df1`）落地 20 TTP 攻击模板后，Checkpoint 15 RFC 期间 implementer 在 hard negative coverage assessment 中提出了 **8 类 implementer-recommended 自然分组**作为下一步 hard negative 模板设计的工程蓝图。该 8 类来源仅在会话窗口讨论，verify-only dispatch 后 Path B 处理（commit `9a9eedf`）补齐到 `docs/known_issues.md::Phase 5 待办::Tightening 1` 独立 entry。

Tightening 1 entry（`docs/known_issues.md` line 361 起）锁定 4 条 Checkpoint 16 launch 硬要求，其中第 1 条要求 implementer 必须做 explicit 6 vs 8 categories cross-reference table 落到 docs；第 2 条要求显式验证 vulnerability scanner（6-row #4）加 备份程序大量读文件（6-row #6）这两类是否被 8 类完整覆盖；第 3 条要求 cross-reference table 由 implementer 加 spec compliance reviewer 加 code quality reviewer 验证完整性；第 4 条要求 cross-reference 暴露未覆盖时触发 Checkpoint 16 RFC 不擅自决定。本文档即 Stage 1 implementer 落档 deliverable。

---

## §2 8 categories implementer-recommended natural grouping

来源：Checkpoint 15 RFC 期间 implementer hard negative coverage assessment 提出（`docs/known_issues.md::Phase 5 待办::Tightening 1` entry line 366-375）。

| # | 类名（verbatim） | Sub-pattern 描述 + 表层易混淆 ATT&CK TTP |
|---|---|---|
| 1 | **Office/Email Normal** | 普通办公员工日常 Outlook / Word / Excel / 浏览器开 attachment / 内部 email 收发 / 文档编辑等 office productivity 行为。在 process spawn + file write + network connection 模式上易与 T1566.001 spearphishing-attachment 攻击 TTP 在表层混淆（区分点是 attachment 是否实际执行 macro / payload）。|
| 2 | **Web Server CGI** | 内部 web server（Apache / Nginx / IIS）正常 CGI 处理 HTTP request 触发 child process（perl / python / php-cgi 等）。在 process tree + network connection 模式上易与 T1190 exploit-public-facing-application 攻击 TTP 表层混淆（区分点是 child process 是否进入 reverse shell / 写入 webshell）。|
| 3 | **合法 Auth** | 普通用户日常合法 interactive login / SSH / network logon / Kerberos ticket 请求。涉及 logon event + session start + token issuance，与 T1078 valid accounts / T1110 brute force / T1558 Kerberoasting 在表层 logon event 模式上易混淆（区分点是登录后行为链 + ticket 用法）。|
| 4 | **Admin Tool 执行** | 系统管理员合法使用 PowerShell / cmd / WMI / scheduled tasks / sc.exe / net.exe 等 admin 工具执行配置修改 / 服务管理 / 用户管理 / 远程会话等运维操作。与 T1059.001 PowerShell / T1059.003 Cmd / T1047 WMI / T1053.005 Scheduled Task / T1543.003 Service 等 TTP 在表层 syscall + process tree + command-line 上极其相似（区分点是命令意图 + 后续行为链）。|
| 5 | **Certutil LOLBin** | 内部 IT 合法使用 certutil 处理证书 / hash 校验 / file decode 等系统功能。与 T1140 deobfuscate-decode-files / T1105 ingress tool transfer 在 certutil 调用模式上完全一致（区分点是 decode 后 payload 内容 + download URL 信誉）。|
| 6 | **FS 操作** | 系统管理员或自动化运维工具合法访问敏感路径（`/etc/`、`/root/`、`C:\Windows\System32\` 等）做配置查看 / 备份 / audit。涉及大量 file read + 偶发 file write，与 T1003 credential access / T1083 file and directory discovery / T1005 data from local system 在 file access pattern 上重叠（区分点是访问路径语义 + 后续 exfil destination）。|
| 7 | **软件驱动安装** | 合法系统驱动安装（设备驱动 / 安全软件驱动 / 虚拟化驱动等），涉及 driver file write 到 `\Driver\` + service registration + reboot trigger。与 T1547.006 kernel-modules-and-extensions / T1543.003 service-creation 在 driver-related event 模式上重叠（区分点是 driver 签名 + 来源信誉）。|
| 8 | **合法 RDP** | 用户合法远程桌面会话登录 / 远程办公 / 远程协助。涉及 RDP network connection + login event + interactive session，与 T1021.001 RDP attack TTP 在 network + login pattern 上完全一致（区分点是后续异常行为链如 credential dump / lateral movement）。|

---

## §3 6 categories GPT-critique hard negative benign admin behaviors

来源：父 entry "20 TTP 模板设计必须含 6 类 hard negative benign admin behaviors"（`docs/known_issues.md` line 335 起）+ GPT critique（2026-05-06）。

| # | 类名（verbatim） | Sub-pattern 描述 + 表层易混淆 ATT&CK TTP（紧凑版） |
|---|---|---|
| 1 | **管理员 PowerShell** | 系统管理员日常 PowerShell 配置修改 / 服务管理 / 用户管理 / 远程会话。Sub-patterns：`Invoke-Command` 远程执行 / `Set-Service` 服务管理 / `New-LocalUser` 用户创建 / `Get-WmiObject` WMI 查询。表层与 T1059.001 PowerShell 攻击 TTP 在 syscall + process tree 上极其相似。|
| 2 | **自动化脚本访问敏感路径** | 备份脚本 / 配置同步工具 / 合法 audit 工具访问 `/etc/`、`/root/`、`C:\Windows\System32\`。Sub-patterns：cron / Task Scheduler 触发的脚本批量 read sensitive paths / config file write back / log audit scan。与 T1003 credential access / T1083 file and directory discovery 在 file access pattern 上重叠。|
| 3 | **合法 RDP** | 用户合法远程桌面会话 / 远程办公 / 远程协助。Sub-patterns：RDP login event / interactive session start / clipboard-redirect / drive-redirect。与 T1021.001 RDP attack TTP 在 network connection + login event 模式上完全一致区分点只在后续异常行为链。|
| 4 | **安全扫描** | 内部安全团队 Nessus / OpenVAS / Qualys 等漏洞扫描工具。Sub-patterns：(a) network port scanning（大量 SYN / connect 到多端口）/ (b) remote probing（service banner grab / version detection）/ (c) weak password testing（受控字典攻击对内部账户）。与 T1046 network service discovery / T1110 brute force 在 network behavior 上无法表层区分。|
| 5 | **软件更新** | Windows Update / Linux package manager (apt/yum/dnf) / 第三方软件自动更新。Sub-patterns：update agent process spawning / package file download from update repo / file modification 到 `\Program Files\` / 偶发 service restart。与 T1105 ingress tool transfer + T1059 command and scripting interpreter 在表层模式上重叠。|
| 6 | **备份程序大量读文件** | 磁盘备份工具一次性读取大量文件。Sub-patterns：(a) bulk file read（短时间内大量 NTFS / ext4 read syscall）/ (b) rsync 类工具行为（远程同步 + delta 传输）/ (c) robocopy 类工具行为（Windows 全量复制）/ (d) Veeam 类专业备份（VSS snapshot + 备份 agent 写到备份服务器）/ (e) NetBackup 类企业备份（agent + 中央备份服务器协调）。与 T1005 data from local system / T1039 data from network shared drive 在 file read 频率上完全一致区分点只在 destination（外部 IP vs 内网备份服务器）。|

---

## §4 6 × 8 cross-reference table（48 cells）

**Cell 取值语义**：
- `Full`：8-col 完整涵盖 6-row sub-pattern 无显著 gap
- `Partial: <gap>`：覆盖部分 sub-pattern，显式列出未覆盖 aspect
- `None: <reason>`：完全不覆盖

由于 48 cells inline rationale 在单一表格中过宽，本节用紧版 cell 取值（`Full` / `Partial: <gap>` / `None: <reason>`），详细 per-row 分析见 §5。

### §4.1 Sub-table A：6-row × 8-col cells 1-4

| 6-row \ 8-col | 1. Office/Email Normal | 2. Web Server CGI | 3. 合法 Auth | 4. Admin Tool 执行 |
|---|---|---|---|---|
| **1. 管理员 PowerShell** | None: 办公 productivity 不涉及 admin shell 操作 | None: web server CGI 与 admin shell 工具链不重叠 | Partial: 仅覆盖 admin 远程登录会话起点不覆盖 PowerShell 命令执行本体 | Full: PowerShell / cmd / WMI 是 admin tool 执行的核心 sub-pattern |
| **2. 自动化脚本访问敏感路径** | None: 办公场景不涉及系统敏感路径自动化访问 | Partial: CGI 子进程偶有读 web 服务器配置但不覆盖 OS 级敏感路径 | None: 合法 Auth 不直接产生敏感路径访问行为 | Partial: admin 工具可触发脚本但不专门覆盖 cron/Task-Scheduler 触发自动化 + 敏感路径 read 频率模式 |
| **3. 合法 RDP** | None: 办公场景不直接涉及 RDP session | None: web CGI 与 RDP 协议无关 | Partial: 仅覆盖 logon event 起点不覆盖 RDP-specific session 加 clipboard/drive redirect | None: admin tool 执行不专门覆盖 RDP session 本身（即使 RDP 内部用 admin tool） |
| **4. 安全扫描** | None: 办公行为与扫描器流量无关 | None: web CGI 与扫描器流量无关 | Partial: 仅与 weak password testing sub-pattern 在 logon event 起点上交集不覆盖 port scanning / remote probing | Partial: scanner 作为内部 IT tool 在执行语义上有交集但不覆盖 network probing flow 本身 |
| **5. 软件更新** | None: 办公行为不直接产生系统级 update 流 | None: web CGI 与系统 update 流无关 | None: 合法 Auth 与 update agent 流无关 | Partial: apt/yum/dnf / Windows Update CLI 调用属 admin tool 执行但不覆盖 update agent process + repo download 完整链 |
| **6. 备份程序大量读文件** | None: 办公行为不产生 bulk file read 模式 | None: web CGI 与 backup 流无关 | None: 合法 Auth 与 backup agent 流无关 | Partial: rsync/robocopy CLI 调用属 admin tool 执行但不覆盖 backup-specific frequency-pattern + Veeam/NetBackup agent 模式 |

### §4.2 Sub-table B：6-row × 8-col cells 5-8

| 6-row \ 8-col | 5. Certutil LOLBin | 6. FS 操作 | 7. 软件驱动安装 | 8. 合法 RDP |
|---|---|---|---|---|
| **1. 管理员 PowerShell** | None: certutil 与 PowerShell 工具链不直接交集 | Partial: PowerShell 触发 FS 操作有交集但不覆盖 PowerShell 远程执行本体 | None: 驱动安装与 PowerShell 命令本体不直接交集 | Partial: RDP session 内可执行 PowerShell 但 8-col #8 RDP 不专门覆盖 PowerShell 命令本体 |
| **2. 自动化脚本访问敏感路径** | None: certutil 与脚本敏感路径访问不直接交集 | Full: FS 操作类直接覆盖敏感路径 read/write + audit / config 同步 sub-patterns | None: 驱动安装与脚本敏感路径访问不直接交集 | None: RDP 与本地脚本敏感路径访问不直接交集 |
| **3. 合法 RDP** | None: certutil 与 RDP 协议无关 | None: FS 操作与 RDP session 不直接交集 | None: 驱动安装与 RDP 协议无关 | Full: 8-col #8 与 6-row #3 是直接对应类，完全覆盖 RDP login + interactive session + redirect |
| **4. 安全扫描** | None: certutil 与扫描器无关 | None: FS 操作与 network 扫描不直接交集 | None: 驱动安装与扫描器无关 | None: RDP 与扫描器流不直接交集 |
| **5. 软件更新** | Partial: certutil 偶被 update agent 用于 hash 校验但不覆盖 update agent process / repo download 主链 | Partial: update 写入 `\Program Files\` 属 FS 操作但不覆盖 update agent process + 网络 download 链 | Partial: 驱动作为 software 子集且 update 含 driver update 时有交集但 8-col #7 仅覆盖 driver install 不覆盖通用 software update（如 Windows Update 安装非驱动 patch / 第三方 app 自动更新） | None: RDP 与 software update 流不直接交集 |
| **6. 备份程序大量读文件** | None: certutil 与 bulk file read 无关 | Partial: FS 操作覆盖 file read syscall 本身但不专门覆盖 bulk read frequency-pattern + backup destination 语义 + Veeam/NetBackup agent 模式 | None: 驱动安装与备份流无关 | None: RDP 与备份流不直接交集 |

---

## §5 Per-row coverage assessment（6 rows）

**Aggregate 判定规则**：
- `Fully covered` = 至少有一个 8-col 给出 Full
- `Partially covered` = 没有 Full 但至少有一个 Partial
- `Not covered` = 全部 8-col 给 None

### §5.1 Row 1：管理员 PowerShell

Sub-patterns：`Invoke-Command` 远程执行 / `Set-Service` 服务管理 / `New-LocalUser` 用户创建 / `Get-WmiObject` WMI 查询。8 列中 **primary cover = #4 Admin Tool 执行（Full）**——PowerShell / cmd / WMI 是 admin tool 执行的核心 sub-pattern；**secondary cover** = #3 合法 Auth（Partial，覆盖 admin 远程登录起点）+ #6 FS 操作（Partial，PowerShell 触发的 FS 操作有交集）+ #8 合法 RDP（Partial，RDP session 内 PowerShell 操作）。

**Aggregate coverage status：Fully covered**（#4 给 Full）。

### §5.2 Row 2：自动化脚本访问敏感路径

Sub-patterns：cron / Task Scheduler 触发 / 备份脚本 / 配置同步 / log audit scan / sensitive path read+write back。8 列中 **primary cover = #6 FS 操作（Full）**——FS 操作直接覆盖敏感路径 read/write + audit / config 同步；**secondary cover** = #4 Admin Tool 执行（Partial，admin 工具触发脚本但不专门覆盖 cron/Task-Scheduler 触发模式）+ #2 Web Server CGI（Partial，CGI 子进程偶有读配置但限于 web 配置非 OS 敏感路径）。

**Aggregate coverage status：Fully covered**（#6 给 Full）。

### §5.3 Row 3：合法 RDP

Sub-patterns：RDP login event / interactive session start / clipboard-redirect / drive-redirect。8 列中 **primary cover = #8 合法 RDP（Full）**——8-col #8 与 6-row #3 是直接对应类完全覆盖；**secondary cover** = #3 合法 Auth（Partial，仅覆盖 logon event 起点不覆盖 RDP-specific redirect 行为）。

**Aggregate coverage status：Fully covered**（#8 给 Full）。

### §5.4 Row 4：安全扫描

Sub-patterns：(a) network port scanning / (b) remote probing / (c) weak password testing。8 列中 **没有任何一列给 Full**：
- #3 合法 Auth：Partial（仅与 weak password testing sub-pattern 在 logon event 起点上交集，且语义不同——合法 Auth 不含字典批量尝试 frequency 模式）
- #4 Admin Tool 执行：Partial（scanner 作为内部 IT tool 在执行语义上有交集，但不覆盖 network probing flow 本身）
- 其余 6 列均 None：Office/Email Normal、Web Server CGI、Certutil LOLBin、FS 操作、软件驱动安装、合法 RDP 与 network scanning + remote probing + weak pwd test 三 sub-patterns 完全不交集

**Uncovered aspects**：
- (a) network port scanning：8 类完全不覆盖。Criticality = **HIGH**。该 aspect 是攻击 TTP T1046 network service discovery 与 vulnerability scanner 良性使用的 distinct discriminative signal——BERT-only 在 Phase 8 strict fusion ablation 时若仅靠 lexical pattern（如 "scan" / port number 词频）形成 shortcut，则 fusion 实际有效但 BERT-only 已 saturate 让 fusion lift 假阴性。
- (b) remote probing：8 类完全不覆盖。Criticality = **HIGH**。同上理由——T1046 + T1018 remote system discovery 与扫描器良性 service banner grab 在 network event 模式上一致。
- (c) weak password testing：仅 #3 合法 Auth 给 Partial。Criticality = **MEDIUM-HIGH**。weak pwd test frequency 模式与 T1110 brute force 一致，#3 不覆盖该 frequency-pattern。

**Aggregate coverage status：Partially covered**（无 Full 但有 #3 + #4 给 Partial）。**Uncovered aspect 是 critical discriminative signal**。

### §5.5 Row 5：软件更新

Sub-patterns：update agent process spawning / package download from repo / file modification 到 `\Program Files\` / 偶发 service restart。8 列中 **没有任何一列给 Full**：
- #4 Admin Tool 执行：Partial（apt/yum/dnf / Windows Update CLI 属 admin tool 执行但不覆盖 update agent process + repo download 完整链）
- #5 Certutil LOLBin：Partial（certutil 偶被 update agent 用于 hash 校验但不覆盖主链）
- #6 FS 操作：Partial（update 写入 `\Program Files\` 属 FS 操作但不覆盖 update agent process + 网络 download 链）
- #7 软件驱动安装：Partial（驱动作为 software 子集且 update 含 driver update 时有交集但 8-col #7 仅覆盖 driver install 不覆盖通用 software update 即 Windows Update 非驱动 patch / 第三方 app 自动更新）
- 其余 4 列均 None

**Uncovered aspects**：update agent process（独立 long-running update agent 如 wuauserv / packagekitd 的 process spawn + state machine 行为）+ repo download network flow 的 update-agent-specific 模式（与 update repo 域名 + checksum verification）。Criticality = **MEDIUM**。该 aspect 与 T1105 ingress tool transfer 的 download 行为在 network 事件上重叠但 destination 域名信誉是 distinct discriminative signal——8 类的 #4 / #5 / #6 / #7 各 Partial 组合后已部分覆盖语义但缺 update-agent-as-distinct-process-class 概念。Phase 8 strict fusion ablation 时 BERT-only 可能利用 update repo 域名 lexical pattern（如 `*.windowsupdate.com` / `archive.ubuntu.com`）已 saturate，但 fusion 通过 process state machine 提供 incremental signal 应仍可 lift——uncovered aspect **不构成 critical discriminative signal**（domain lexical 已足够 saturate BERT-only baseline）。

**Aggregate coverage status：Partially covered**（无 Full 但 #4 + #5 + #6 + #7 多列 Partial）。**Uncovered aspect 非 critical discriminative signal**。

### §5.6 Row 6：备份程序大量读文件

Sub-patterns：(a) bulk file read frequency / (b) rsync 类 / (c) robocopy 类 / (d) Veeam 类专业备份（VSS snapshot + 备份 agent）/ (e) NetBackup 类企业备份（agent + 中央备份服务器协调）。8 列中 **没有任何一列给 Full**：
- #4 Admin Tool 执行：Partial（rsync/robocopy CLI 调用属 admin tool 执行但不覆盖 backup-specific frequency + Veeam/NetBackup agent 模式）
- #6 FS 操作：Partial（FS 操作覆盖 file read syscall 本身但不专门覆盖 bulk read frequency + backup destination 语义 + Veeam/NetBackup agent 模式）
- 其余 6 列均 None

**Uncovered aspects**：
- bulk read frequency-pattern aspect：#6 FS 操作仅覆盖 file read syscall 本身不覆盖"短时间大量 read"的 frequency feature。Criticality = **HIGH**。该 frequency 是 T1005 data from local system 与 backup 良性使用的 distinct discriminative signal——backup destination（内网备份服务器 vs 外部 IP）才是真正区分点，8 类全部不覆盖 backup destination 语义。
- Veeam / NetBackup 专业 backup agent process + 中央协调模式：8 类完全不覆盖。Criticality = **HIGH**。Phase 8 strict fusion ablation 时 BERT-only 若仅靠 file path lexical pattern + read syscall 词频形成 shortcut（已可能 saturate），则 fusion 实际通过 process state machine + destination 信誉提供 incremental signal 但 BERT-only saturate 让 fusion lift 假阴性的风险显著。

**Aggregate coverage status：Partially covered**（无 Full 但 #4 + #6 给 Partial）。**Uncovered aspect 是 critical discriminative signal**。

---

## §6 Special focus analysis（hard requirement #2）

Tightening 1 硬要求 #2 显式要求关键检查点验证 vulnerability scanner 加备份程序大量读文件这两类是否被 8 类完整覆盖加是否需要扩展第 9 / 第 10 类。

### §6.1 Vulnerability scanner（6-category #4 安全扫描）

**Sub-patterns 显式列出**：
- (a) network port scanning（大量 SYN / connect 探测多端口）
- (b) remote probing（service banner grab / version detection）
- (c) weak password testing（受控字典攻击对内部账户）

**逐 sub-pattern coverage 评估**：

| Sub-pattern | 候选 8-col | 评估 |
|---|---|---|
| (a) port scanning | #4 Admin Tool 执行（scanner 作为 IT 工具）/ #6 FS 操作（None）/ #3 合法 Auth（None） | **None / Partial only via #4 Admin Tool 间接**——8 类无任何 network probing 专门类，#4 Admin Tool 仅覆盖 scanner 工具本身的 process 启动语义不覆盖 network probing flow |
| (b) remote probing | 候选同上 | **None / Partial only via #4 间接**——同 (a)，8 类无 network probing 类 |
| (c) weak password testing | #3 合法 Auth（最近候选）/ #4 Admin Tool 执行 | **Partial via #3**——#3 仅覆盖单次 logon event 起点不覆盖字典批量尝试 frequency 模式 |

**结论**：vulnerability scanner 整体**未被 8 类完整覆盖**。port scanning 与 remote probing 两个 sub-pattern 8 类完全无对应类，weak password testing 仅 #3 部分覆盖。

**Propose 第 9 类 candidate**（implementer propose 不擅自决定实施留 RFC 裁定）：
- **Candidate name**：**Network Probing & Scanning Normal**
- **Scope description**：内部安全团队 / IT audit 合法网络探测 + 端口扫描 + service banner grab + 受控弱口令测试。Sub-patterns 含 Nessus / OpenVAS / Qualys / nmap / hydra-internal-controlled-test 等工具的 network event burst + multi-host probing flow。
- **与现有 8 类 boundary 划分**：与 #4 Admin Tool 执行的边界为"scanner 工具的 process 启动属 #4，network probing flow 本体（连接到多 host * 多 port 的 burst）属第 9 类"；与 #3 合法 Auth 的边界为"weak pwd 测试单次 logon event 属 #3，frequency 模式（短时间多次 logon failure）属第 9 类"。

### §6.2 备份程序大量读文件（6-category #6）

**Sub-patterns 显式列出**：
- (a) bulk file read（短时间大量 read syscall）
- (b) rsync 类工具行为
- (c) robocopy 类工具行为
- (d) Veeam 类专业备份（VSS snapshot + 备份 agent）
- (e) NetBackup 类企业备份（agent + 中央备份服务器协调）

**逐 sub-pattern coverage 评估**：

| Sub-pattern | 候选 8-col | 评估 |
|---|---|---|
| (a) bulk file read | #6 FS 操作（最近候选） | **Partial**——#6 覆盖 read syscall 本身不覆盖 frequency-pattern aspect |
| (b) rsync / (c) robocopy | #4 Admin Tool 执行（CLI 工具调用） / #6 FS 操作 | **Partial via #4 + #6 组合**——CLI 调用属 #4，文件读取属 #6，但 backup-specific destination 语义（内网备份服务器 vs 外部 IP）8 类全部不覆盖 |
| (d) Veeam / (e) NetBackup | 无直接候选 | **None**——专业 backup agent process + 中央协调模式 8 类完全无对应 |

**备份目的语义评估**（destination = 内网备份服务器 vs 外部 IP）：8 类全部不覆盖该 destination 区分点，而该 destination 是 T1005 data from local system / T1041 exfiltration over C2 channel 与备份良性使用的核心 distinct discriminative signal。

**结论**：备份程序大量读文件整体**未被 8 类完整覆盖**。bulk read frequency-pattern 仅 #6 部分覆盖 + Veeam/NetBackup 专业 agent 模式 8 类完全无对应 + backup destination 语义 8 类全部不覆盖。

**Propose 第 10 类 candidate**（implementer propose 不擅自决定实施留 RFC 裁定）：
- **Candidate name**：**Backup Agent Bulk Read Normal**
- **Scope description**：磁盘备份工具 / 企业备份系统一次性大量读取文件 + 写到内网备份服务器。Sub-patterns 含 rsync / robocopy / Veeam / NetBackup / Bacula 等工具的 bulk read frequency-burst + agent process state machine + 内网 backup server destination flow。
- **与现有 8 类 boundary 划分**：与 #6 FS 操作的边界为"单次 file read 属 #6，short-window high-frequency bulk read 属第 10 类"；与 #4 Admin Tool 执行的边界为"rsync/robocopy CLI 调用属 #4，backup agent 长驻 process（Veeam Backup Service / NetBackup bpcd 等）属第 10 类"。

---

## §7 RFC trigger determination

### §7.1 Per-row 6 类 aggregate coverage status 总结（来自 §5）

| Row | Aggregate status | Primary cover | Secondary cover | Critical uncovered aspect？ |
|---|---|---|---|---|
| 1. 管理员 PowerShell | Fully covered | #4 Admin Tool 执行 | #3 + #6 + #8 | N/A |
| 2. 自动化脚本访问敏感路径 | Fully covered | #6 FS 操作 | #4 + #2 | N/A |
| 3. 合法 RDP | Fully covered | #8 合法 RDP | #3 | N/A |
| 4. 安全扫描 | **Partially covered** | （无 Full）#3 + #4 各 Partial | — | **Yes (HIGH)**：port scanning + remote probing + weak pwd test frequency |
| 5. 软件更新 | Partially covered | （无 Full）#4 + #5 + #6 + #7 各 Partial | — | No（update repo 域名 lexical 已足以让 BERT-only saturate 不形成 fusion lift 假阴性） |
| 6. 备份程序大量读文件 | **Partially covered** | （无 Full）#4 + #6 各 Partial | — | **Yes (HIGH)**：bulk read frequency + Veeam/NetBackup agent + backup destination 语义 |

### §7.2 RFC trigger 判定规则适用

- 任一 row Not covered → 强 trigger：**无 Not covered row**
- 任一 row Partially covered 且 §5 显式 uncovered aspect 是 critical discriminative signal → 弱 trigger：**Row 4（安全扫描）+ Row 6（备份程序大量读文件）两 row 触发弱 trigger**
- 全部 row Fully covered 或 Partially covered with non-critical uncovered aspect → 不 trigger

### §7.3 结论

**RFC triggered：Yes**

**触发 row**：
- Row 4 安全扫描：critical uncovered aspects = network port scanning + remote probing + weak password testing frequency mode
- Row 6 备份程序大量读文件：critical uncovered aspects = bulk read frequency-pattern + Veeam/NetBackup professional agent + backup destination semantic

**Extension proposal**（implementer propose 不擅自决定实施留 user 在 Checkpoint 16 RFC 中裁定）：

- **第 9 类 candidate**：**Network Probing & Scanning Normal**——内部安全团队 / IT audit 合法网络探测 + 端口扫描 + service banner grab + 受控弱口令测试。Sub-patterns 含 Nessus / OpenVAS / Qualys / nmap / hydra-internal-controlled-test 等工具。Boundary 与 #4 Admin Tool（process 启动属 #4，network probing flow 属 #9）+ #3 合法 Auth（单次 logon 属 #3，frequency burst 属 #9）。
- **第 10 类 candidate**：**Backup Agent Bulk Read Normal**——磁盘备份工具 / 企业备份系统一次性大量读取文件 + 写到内网备份服务器。Sub-patterns 含 rsync / robocopy / Veeam / NetBackup / Bacula 等。Boundary 与 #6 FS 操作（单次 file read 属 #6，short-window high-frequency bulk burst 属 #10）+ #4 Admin Tool（CLI 调用属 #4，backup agent 长驻 process 属 #10）。

**Note for RFC**：上述两 candidate 名 + scope + boundary 仅 implementer propose。最终是否扩 9 类 / 10 类 / 仅 9 类 / 仅 10 类 / 用 hybrid 方案（如把 weak pwd test 并入 #3 合法 Auth 的 frequency-aware sub-pattern + 把 bulk read 并入 #6 FS 操作的 frequency-aware sub-pattern）由 user 在 Checkpoint 16 RFC 中裁定。

---

## §8 Cross-references

1. `docs/known_issues.md::Phase 5 待办` Tightening 1 entry "Checkpoint 16 hard negative coverage 6 vs 8 categories cross-reference table 议程（Tightening 1）"（line 361 起，2026-05-08，post Cycle F + Checkpoint 15 closure verify-only dispatch finding）——本设计文档 4 条硬要求来源 + 8 类 verbatim 清单来源
2. `docs/known_issues.md::Phase 5 待办` 父 entry "20 TTP 模板设计必须含 6 类 hard negative benign admin behaviors（2026-05-06，Phase 5 launch spec 启动前预读议程）"（line 335 起）——6 类 verbatim 清单 + GPT critique 来源 + 假可分性陷阱叙事来源
3. Cycle F + Checkpoint 15 closure commit `1094df1`（feat(phase5): Cycle F + Checkpoint 15 close (T1190+T1560.001+T1486+T1490, 20 templates total, schema workaround inventory 4 entries pre-Checkpoint-17)）——20 TTP 模板落地 anchor + 8 类来源会话窗口讨论时点
4. Path B audit gap close commit `9a9eedf`（docs(phase5): close Tightening 1+2 audit gap in known_issues (post-1094df1 verify-only dispatch finding)）——Tightening 1 entry 落 known_issues.md anchor，本设计文档 source-of-truth 落档
5. `docs/PROGRESS.md` Phase 5 / Checkpoint 15 Section（仅 reference 不修改）——Checkpoint 15 关闭状态 + Checkpoint 16 launch readiness anchor
