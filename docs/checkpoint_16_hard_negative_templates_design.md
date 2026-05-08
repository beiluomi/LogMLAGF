# Checkpoint 16 Hard Negative Templates Design (Stage 2 Step 1)

**Stage**：Phase 5 Checkpoint 16 / Stage 2 Step 1（design propose 半步协议；design-then-implement）
**Created**：2026-05-08
**Owner**：implementer（Stage 2 Step 1 design）；spec compliance reviewer + code quality reviewer 验证完整性（Stage 2 Step 1 review 阶段）；implementer Stage 2 Step 2（执行 design propose）
**Branch / HEAD**：`feat/04-cross-attention` @ `be41d82`（Stage 1 closure）
**Upstream chain**：`be41d82 ← 9a9eedf ← 1094df1`（up to date with `origin/feat/04-cross-attention`）

---

## §1 Context

### §1.1 背景

Phase 5 创新点二（"首个把 MITRE ATT&CK 模板作为图增强样本与图文对比目标在预训练阶段联合训练"）的核心方法论防御是**避免合成攻击假可分性陷阱**。GPT critique（2026-05-06）锁定 6 类 hard negative benign admin behaviors 必须在 Phase 5 模板设计中显式 cover（见父 entry "20 TTP 模板设计必须含 6 类 hard negative benign admin behaviors"，`docs/known_issues.md` line 335 起），让 Phase 8 anomaly classifier 必须区分"真攻击 TTP"与"模式相似的良性管理员行为"而非"攻击 vs 普通良性"。

Cycle F + Checkpoint 15 closure（commit `1094df1`）落地 20 TTP 攻击模板后，Checkpoint 15 RFC 期间 implementer 在 hard negative coverage assessment 中提出了 **8 类 implementer-recommended 自然分组**作为 hard negative 模板设计的工程蓝图。Tightening 1 entry（`docs/known_issues.md` line 361 起）把 8 类落档并锁定 Checkpoint 16 launch 4 条硬要求；Stage 1（commit `be41d82`，`docs/checkpoint_16_hard_negative_design.md`）落地 6 × 8 cross-reference table、§7 RFC trigger Yes 决议加 propose 第 9 + 第 10 类 candidate（**Network Probing & Scanning Normal** + **Backup Agent Bulk Read Normal**）。

### §1.2 Stage 2 Step 1 任务

User + 指导 Claude 联合裁定接受 Stage 1 propose：8 类扩展为 **10 类**。Stage 2 Step 1（本文档）即 design propose 半步协议——在 implementer 写代码前先把 distribution propose / per-template sketch / pairwise boundary clarification / ALLOWED_EDGE_TRIPLES 适配性 pre-assessment / Tightening 2 lexical-pattern caveat 主动检查这 5 项 deliverable 落档，spec compliance reviewer + code quality reviewer 两轮 findings 处理后 controller commit + push，再进入 Stage 2 Step 2 实施。

### §1.3 Cross-references

- Stage 1 closure commit `be41d82`（docs(phase5): Checkpoint 16 Stage 1 Tightening 1 cross-reference table + RFC trigger (rows 4+6)）
- Path B audit gap close commit `9a9eedf`（docs(phase5): close Tightening 1+2 audit gap in known_issues (post-1094df1 verify-only dispatch finding)）
- Cycle F + Checkpoint 15 closure commit `1094df1`（feat(phase5): Cycle F + Checkpoint 15 close）
- `docs/checkpoint_16_hard_negative_design.md`（Stage 1 design doc 248 lines @ commit `be41d82`）
- `docs/known_issues.md::Phase 5 待办` 父 entry "20 TTP 模板设计必须含 6 类 hard negative benign admin behaviors"（line 335 起）
- `docs/known_issues.md::Phase 5 待办` Tightening 1 entry（line 361 起）
- `docs/known_issues.md::Phase 5 待办` Tightening 2 entry "T1486 ransomware-mimicry hard negative pair 单独 lexical-blind sanity check 协议"（line 388 起）
- `docs/known_issues.md::Phase 5 待办` ALLOWED_EDGE_TRIPLES schema 扩展议程 entry（line 411 起）
- `docs/known_issues.md::Phase 5 待办` Checkpoint 17 schema workaround inventory tracking entry（line 429 起，4 entries pre-Checkpoint-17）

---

## §2 Distribution propose（Deliverable 1）

10 类 hard negative 模板分布提议表。设计原则：常见 surface 类（#1 Office/Email、#4 Admin Tool、#6 FS 操作）多 (3 模板) 覆盖 sub-pattern 多样性；尖锐 pattern 类（#5 Certutil LOLBin、#7 软件驱动安装）少 (1-2 模板) 因 sub-pattern 集中且 lexical signature 已较 distinct；新加 #9 + #10 各 3 模板覆盖各自 sub-pattern diversity（#9 涵盖 port scanning / banner grab / weak pwd test 三 sub-pattern；#10 涵盖 rsync vs robocopy vs Veeam-NetBackup-Bacula 三 backup-agent 模式）。

| #N | 类别名（verbatim） | 计划模板数 | 主要 ATT&CK confound TTPs | 分配 reasoning |
|---|---|---:|---|---|
| 1 | **Office/Email Normal** | 3 | T1566.001 spearphishing-attachment / T1204.002 user-execution-malicious-file | 三 sub-pattern：(a) Outlook 收 attachment 不执行 macro / (b) Word/Excel 编辑文档保存 / (c) browser 下载文档+本地打开。常见 surface 配合 T1566.001 已落地 attack TTP 必须重叠 |
| 2 | **Web Server CGI** | 2 | T1190 exploit-public-facing-application / T1505.003 web-shell | 两 sub-pattern：(a) Apache+CGI perl/python 子进程 / (b) Nginx+PHP-FPM 子进程。Sub-pattern 较集中 |
| 3 | **合法 Auth** | 2 | T1078 valid-accounts / T1110 brute-force / T1558 Kerberoasting | 两 sub-pattern：(a) 单次 interactive logon / (b) Kerberos ticket 请求 + service ticket 取用。frequency-burst 留给 #9 |
| 4 | **Admin Tool 执行** | 3 | T1059.001 PowerShell / T1059.003 Cmd / T1047 WMI / T1053.005 Scheduled Task / T1543.003 Service | 三 sub-pattern：(a) admin PowerShell user-mgmt / (b) admin sc.exe service-mgmt / (c) admin schtasks.exe scheduled-task-mgmt。覆盖 4 个 attack TTP confound |
| 5 | **Certutil LOLBin** | 1 | T1140 deobfuscate-decode-files / T1105 ingress-tool-transfer | 单 sub-pattern：内部 IT 用 certutil hash-verify 合法 patch 文件。Sub-pattern 集中 + lexical signature 已较 distinct，1 模板足够 |
| 6 | **FS 操作** | 3 | T1003 credential-access / T1083 file-and-directory-discovery / T1005 data-from-local-system | 三 sub-pattern：(a) cron 触发的 audit log scan / (b) Task Scheduler 触发的 config-sync read+write / (c) sysadmin 直接 ls/cat /etc/。多 sub-pattern + 与 T1486 ransomware-mimicry 单独 sanity check pair 必须仔细设计 lexical-blind 抵抗 |
| 7 | **软件驱动安装** | 2 | T1547.006 kernel-modules-and-extensions / T1543.003 service-creation | 两 sub-pattern：(a) 设备驱动安装（打印机 / 显卡）+ service registration / (b) 安全软件 / 虚拟化驱动安装。Sub-pattern 集中 |
| 8 | **合法 RDP** | 2 | T1021.001 RDP attack | 两 sub-pattern：(a) 用户日常远程办公 RDP login + interactive session / (b) IT helpdesk 远程协助 RDP + clipboard/drive-redirect。与 T1021.001 attack 在表层无法区分 |
| 9 | **Network Probing & Scanning Normal**（新加） | 3 | T1046 network-service-discovery / T1110 brute-force / T1018 remote-system-discovery | 三 sub-pattern：(a) Nessus 端口 scan + service banner grab / (b) nmap 内网扫描 + version detection / (c) hydra-internal 受控 weak-pwd test 字典攻击。Sub-pattern diversity 必须 ≥ 3 |
| 10 | **Backup Agent Bulk Read Normal**（新加） | 3 | T1005 data-from-local-system / T1039 data-from-network-shared-drive / T1486 ransomware-mimicry pair | 三 sub-pattern：(a) rsync 内网备份服务器同步 / (b) robocopy Windows 全量复制到内网 SMB / (c) Veeam/NetBackup-style 专业 agent + VSS-snapshot + 中央 backup server 协调。与 T1486 ransomware-mimicry hard negative pair 单独 sanity check 强相关 |
| **Total** | — | **24** | — | 落在 target 20-30 区间内，Stage 2 Step 2 实施时如某模板设计触发 NEEDS_CONTEXT 可降到 22-23 但不应低于 20 |

**Sum check**：3 + 2 + 2 + 3 + 1 + 3 + 2 + 2 + 3 + 3 = **24 模板**（target 20-30 ✓）。

---

## §3 Per-template minimal sketches（Deliverable 2）

每模板 sketch 含 4 字段：(a) **TTP-like name** - `benign_<class>_<descriptor>` 命名 / (b) **主 syscall/operation/edge sequence** - 5-15 行简化序列 / (c) **最 confound attack TTP** - ATT&CK technique ID / (d) **lexical-pattern boundary** - 1-2 句 distinct signature 加为何不让 BERT-only saturate。

### §3.1 Class #1 Office/Email Normal（3 模板）

**T#1.1 `benign_office_outlook_attachment_view`**
- Sequence：(user, USER_LOGON, outlook.exe) → (outlook.exe, FILE_WRITE, attachment.docx) → (outlook.exe, PROCESS_CREATE, winword.exe) → (winword.exe, FILE_READ, attachment.docx) → (winword.exe, FILE_WRITE, attachment.docx) [user 编辑保存]
- Confound：T1566.001 spearphishing-attachment
- Boundary：合法 Outlook → Word 链 **不**含 macro spawning child shell（无 (winword.exe, PROCESS_CREATE, cmd.exe/powershell.exe)）+ **不**含 outbound C2 connection。BERT-only 看 lexical 仅 outlook.exe + winword.exe + .docx 词频；与 T1566.001 共享前 4 步 shape，区分点必须靠 process-tree depth + child-process-class signal 而非 token 词频，避免 BERT-only saturate。

**T#1.2 `benign_office_excel_pivot_edit`**
- Sequence：(user, USER_LOGON, explorer.exe) → (explorer.exe, PROCESS_CREATE, excel.exe) → (excel.exe, FILE_READ, quarterly_report.xlsx) → (excel.exe, FILE_WRITE, quarterly_report.xlsx) → (excel.exe, FILE_WRITE, ~$quarterly_report.xlsx) [Office lock file]
- Confound：T1204.002 user-execution-malicious-file
- Boundary：合法 Excel 编辑写 ~$ lock file 是 Office 标志特征；T1204.002 reverse-shell-via-excel-macro 会有 (excel.exe, PROCESS_CREATE, powershell.exe) + outbound NET_CONNECT。BERT-only 仅看 excel.exe + .xlsx 词频不足以区分编辑 vs macro-execute；区分点必须靠 child-process + network 链。

**T#1.3 `benign_office_browser_pdf_download_open`**
- Sequence：(user, USER_LOGON, chrome.exe) → (chrome.exe, NET_HTTP_REQUEST, vendor_pdf_url) → (chrome.exe, FILE_WRITE, vendor_quote.pdf) → (chrome.exe, PROCESS_CREATE, AcroRd32.exe) → (AcroRd32.exe, FILE_READ, vendor_quote.pdf)
- Confound：T1566.002 spearphishing-link / T1204.001 user-execution-malicious-link
- Boundary：合法 PDF 下载-打开链 **不**含 (AcroRd32.exe, NET_CONNECT, c2_net) 加 **不**含 (AcroRd32.exe, PROCESS_CREATE, *)。BERT-only 看 chrome + AcroRd32 + .pdf 词频与 spearphishing-link 共享，区分必须靠下游 process-tree + outbound-network signal。

### §3.2 Class #2 Web Server CGI（2 模板）

**T#2.1 `benign_webserver_apache_cgi_perl`**
- Sequence：(apache.exe, NET_ACCEPT, network_inbound) → (apache.exe, PROCESS_CREATE, perl.exe) → (perl.exe, FILE_READ, /var/www/cgi-bin/report.pl) → (perl.exe, FILE_READ, /var/www/data/report.csv) → (perl.exe, FILE_WRITE, /tmp/perl_render_<pid>.html) → (perl.exe, PROCESS_EXIT, perl.exe)
- Confound：T1190 exploit-public-facing-application
- Boundary：合法 CGI perl 子进程 **不**写 webshell（无 (perl.exe, FILE_WRITE, *.php / *.jsp / *.aspx in /var/www/) 加 **不**进入 reverse shell（无 (perl.exe, NET_CONNECT, external_ip)）。BERT-only 看 apache + perl + cgi-bin 词频与 T1190 已落地 webshell-write workaround event 重叠（apache.exe, FILE_WRITE, webshell.php），区分必须靠 file-extension + write-target-path semantics。

**T#2.2 `benign_webserver_nginx_php_fpm`**
- Sequence：(nginx.exe, NET_ACCEPT, network_inbound) → (nginx.exe, NET_SEND_SOCKET, socket_to_phpfpm) → (php-fpm.exe, FILE_READ, /var/www/html/checkout.php) → (php-fpm.exe, NET_CONNECT, network_db_backend) → (php-fpm.exe, NET_SEND_NETWORK, network_db_backend) [SQL query] → (php-fpm.exe, NET_RECV_NETWORK, network_db_backend)
- Confound：T1505.003 web-shell
- Boundary：合法 PHP-FPM 子进程 **不**写新 .php 文件加 **不**调用 shell utilities（无 (php-fpm.exe, PROCESS_CREATE, sh / bash / cmd)）。BERT-only 看 nginx + php-fpm + .php 词频与 T1505.003 web-shell-as-php 共享，区分必须靠下游 process spawn 加 file-write 信号。

### §3.3 Class #3 合法 Auth（2 模板）

**T#3.1 `benign_auth_user_interactive_logon`**
- Sequence：(user, USER_LOGON, winlogon.exe) → (winlogon.exe, PROCESS_CREATE, userinit.exe) → (userinit.exe, PROCESS_CREATE, explorer.exe) → (explorer.exe, FILE_READ, %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup) → (explorer.exe, PROCESS_CREATE, slack.exe) [启动项]
- Confound：T1078 valid-accounts
- Boundary：合法用户 logon → explorer → 启动项链 **不**包含 credential-access 子链（无 LSASS access，无 SAM hive read），加进入正常应用而非 shell。BERT-only 看 winlogon + userinit + explorer 词频几乎与 T1078 共享前 3 步，区分必须靠后续 process-tree branch（normal app vs shell + credential dump）。

**T#3.2 `benign_auth_kerberos_service_ticket`**
- Sequence：(user, USER_LOGON, lsass.exe) → (user, USER_PRIV_GRANT, lsass.exe) → (lsass.exe, NET_CONNECT, kdc_network) → (lsass.exe, NET_SEND_NETWORK, kdc_network) [TGS-REQ] → (lsass.exe, NET_RECV_NETWORK, kdc_network) [TGS-REP] → (lsass.exe, FILE_WRITE, krb5cc_<uid>) [ticket cache]
- Confound：T1558 Kerberoasting
- Boundary：合法 Kerberos service ticket 请求 **是单次** + ticket service principal 是 normal user-facing service（如 cifs/HTTP），加 **不**包含 ticket cache export 到外部 process（无 (powershell.exe, FILE_READ, krb5cc_*)）。BERT-only 看 lsass + kerberos + krb5cc 词频与 T1558 共享，区分必须靠 service-principal 集合 + downstream ticket 用法。

### §3.4 Class #4 Admin Tool 执行（3 模板）

**T#4.1 `benign_admin_powershell_user_mgmt`**
- Sequence：(user, USER_LOGON, powershell.exe) → (powershell.exe, FILE_READ, C:\Scripts\add_user.ps1) → (powershell.exe, NET_CONNECT, dc_network) [LDAP] → (powershell.exe, NET_SEND_NETWORK, dc_network) [New-ADUser RPC] → (powershell.exe, NET_RECV_NETWORK, dc_network) → (powershell.exe, PROCESS_EXIT, powershell.exe)
- Confound：T1059.001 PowerShell + T1136.002 create-domain-account
- Boundary：合法 admin PowerShell user-mgmt 只用 New-ADUser → DC RPC，**不**包含 (powershell.exe, PROCESS_CREATE, child) 加 **不**写 payload 到 disk（无 (powershell.exe, FILE_WRITE, *.ps1) 二次落地）。BERT-only 看 powershell + .ps1 + LDAP 词频与 T1059.001 PowerShell 攻击共享前 3 步几乎完全，区分必须靠 child-process + payload-write 缺失。

**T#4.2 `benign_admin_sc_service_restart`**
- Sequence：(user, USER_LOGON, sc.exe) → (user, USER_PRIV_GRANT, sc.exe) → (sc.exe, FILE_WRITE, \\.\pipe\svcctl) [SCM RPC] → (sc.exe, PROCESS_EXIT, sc.exe) [admin restarts existing service]
- Confound：T1543.003 windows-service
- Boundary：合法 sc.exe restart **不**包含 (sc.exe, FILE_WRITE, C:\Windows\System32\<new_svc>.exe)（不创建新 service 二进制）加 **不**包含 IMAGEPATH 修改写 registry 模拟边。BERT-only 看 sc.exe + svcctl 词频与 T1543.003 share，区分必须靠 service-binary write 加 service IMAGEPATH 修改缺失。

**T#4.3 `benign_admin_schtasks_create`**
- Sequence：(user, USER_LOGON, schtasks.exe) → (user, USER_PRIV_GRANT, schtasks.exe) → (schtasks.exe, FILE_READ, C:\Windows\System32\Tasks\<existing>) → (schtasks.exe, FILE_WRITE, C:\Windows\System32\Tasks\backup_daily) [task XML] → (schtasks.exe, PROCESS_EXIT, schtasks.exe)
- Confound：T1053.005 scheduled-task
- Boundary：合法 schtasks 创建 **task 命令是 well-known admin tool**（指向 backup utility / patch script）+ trigger 是 daily 而非 onlogon-immediate；T1053.005 attack 创建 **task 命令指向 attacker payload** 加 trigger 是 immediate-onlogon。BERT-only 看 schtasks + Tasks 词频共享，区分必须靠 task-payload + trigger semantics。

### §3.5 Class #5 Certutil LOLBin（1 模板）

**T#5.1 `benign_certutil_hash_verify_patch`**
- Sequence：(user, USER_LOGON, certutil.exe) → (certutil.exe, FILE_READ, C:\Patches\KB5028166.msu) → (certutil.exe, FILE_WRITE, C:\Patches\KB5028166.sha256) [hash output] → (certutil.exe, PROCESS_EXIT, certutil.exe)
- Confound：T1140 deobfuscate-decode-files / T1105 ingress-tool-transfer
- Boundary：合法 IT certutil hash-verify **不**包含 (certutil.exe, NET_CONNECT, *)（无 -urlcache -split -f 远程下载语义）加 **写出文件是 .sha256 hash 而非 decoded payload**（无 .exe / .dll / .ps1 写出）。BERT-only 看 certutil 词频与 T1140 / T1105 share，区分必须靠 network connection 加 write-file-extension semantics。

### §3.6 Class #6 FS 操作（3 模板）

**T#6.1 `benign_fs_audit_log_scan`**
- Sequence：(user, USER_LOGON, audit_scanner.exe) [cron triggered] → (audit_scanner.exe, FILE_READ, /var/log/auth.log) → (audit_scanner.exe, FILE_READ, /var/log/secure) → (audit_scanner.exe, FILE_READ, /var/log/syslog) → (audit_scanner.exe, FILE_WRITE, /var/log/audit_report_<date>.txt) → (audit_scanner.exe, PROCESS_EXIT, audit_scanner.exe)
- Confound：T1083 file-and-directory-discovery / T1005 data-from-local-system
- Boundary：合法 audit log scan **是 cron-triggered + 写出 audit report 到 local audit dir** 加 **不**包含 outbound network exfiltration（无 NET_CONNECT 到 external IP）。BERT-only 看 /var/log/* 词频与 T1083 file-discovery share，区分必须靠 write-destination semantics + 缺失 exfil 链。**T1486 ransomware-mimicry 单独 sanity check 关键 anchor**：本模板无 mass-rename to .lock/.crypt + 无 high-entropy write，§6.1 详细评估。

**T#6.2 `benign_fs_config_sync_task`**
- Sequence：(user, USER_LOGON, config_sync.exe) [Task Scheduler triggered] → (config_sync.exe, FILE_READ, /etc/nginx/nginx.conf) → (config_sync.exe, NET_CONNECT, internal_config_repo_network) → (config_sync.exe, NET_SEND_NETWORK, internal_config_repo_network) → (config_sync.exe, NET_RECV_NETWORK, internal_config_repo_network) → (config_sync.exe, FILE_WRITE, /etc/nginx/nginx.conf.new) → (config_sync.exe, FILE_RENAME, /etc/nginx/nginx.conf)
- Confound：T1083 / T1003 / T1005
- Boundary：合法 config sync **包含 internal repo network 而非 external IP** 加 **写回原 path** 加 FILE_RENAME 是单 file 而非 batch mass-rename。BERT-only 看 /etc/nginx/* 词频与 T1083 share，区分必须靠 network destination 加 rename pattern semantics。

**T#6.3 `benign_fs_sysadmin_directory_listing`**
- Sequence：(user, USER_LOGON, ls.exe) → (ls.exe, FILE_READ, /etc) [directory metadata read] → (ls.exe, PROCESS_EXIT, ls.exe) → (user, USER_LOGON, cat.exe) → (cat.exe, FILE_READ, /etc/passwd) → (cat.exe, PROCESS_EXIT, cat.exe)
- Confound：T1083 file-and-directory-discovery / T1003.008 /etc/passwd-and-/etc/shadow
- Boundary：合法 sysadmin ls + cat /etc/passwd **不**包含 (cat.exe, FILE_READ, /etc/shadow)（不读 hash 文件）加 **不**包含输出重定向到 attacker-controlled file（无 (*, FILE_WRITE, attacker_path)）加 process tree 是 interactive shell 而非 scripted。BERT-only 看 /etc/passwd 词频与 T1003.008 share 完全，区分必须靠 /etc/shadow 缺失加 downstream exfil 缺失。

### §3.7 Class #7 软件驱动安装（2 模板）

**T#7.1 `benign_driver_install_printer`**
- Sequence：(user, USER_LOGON, setup.exe) → (user, USER_PRIV_GRANT, setup.exe) → (setup.exe, FILE_WRITE, C:\Windows\System32\DriverStore\FileRepository\hp_printer.inf_amd64\hp_printer.sys) → (setup.exe, FILE_WRITE, C:\Windows\System32\drivers\hp_printer.sys) → (setup.exe, FILE_WRITE, \\.\pipe\svcctl) [register service via SCM RPC] → (setup.exe, FILE_WRITE, \Registry\Machine\SYSTEM\CurrentControlSet\Services\hp_printer\ImagePath) [IMAGEPATH registry write — registry-as-file workaround reuse from T1547.001 prior pattern, **Cycle G retro-write 2026-05-08 per Option B'**] → (setup.exe, PROCESS_EXIT, setup.exe)
- Confound：T1547.006 kernel-modules-and-extensions / T1543.003 service-creation
- Boundary：合法打印机驱动安装 **驱动来自 vendor signed binary**（path 含 DriverStore + .inf_amd64 anchor）+ service 不是 auto-start-network-listener。T1547.006 攻击驱动安装会把 .sys 直接写 drivers/ 不经 DriverStore + service binary 是 attacker payload。BERT-only 看 .sys + drivers + DriverStore 词频共享，区分必须靠 path semantics + binary-signing context。**IMAGEPATH 区分 anchor**（Cycle G Option B' 落档）：T#7.1 IMAGEPATH 指向 DriverStore-staged 的 vendor-signed binary（internal consistency）；T1543.003 attack template IMAGEPATH 指向 attacker-controlled payload binary（often outside System32 standard paths）。

**T#7.2 `benign_driver_install_av_engine`**
- Sequence：(user, USER_LOGON, av_installer.exe) → (user, USER_PRIV_GRANT, av_installer.exe) → (av_installer.exe, FILE_WRITE, C:\ProgramData\Vendor\Engine\engine.sys) → (av_installer.exe, FILE_WRITE, C:\Windows\System32\drivers\vendor_av.sys) → (av_installer.exe, FILE_WRITE, \\.\pipe\svcctl) → (av_installer.exe, NET_CONNECT, vendor_update_network) → (av_installer.exe, NET_RECV_NETWORK, vendor_update_network) [signature update]
- Confound：T1543.003 windows-service / T1547.006 kernel-modules
- Boundary：合法 AV driver 安装 **包含 vendor update domain network 而非 attacker C2**（vendor_update_network 是 well-known signature endpoint）加 service 是 known-AV-vendor name。BERT-only 看 .sys + drivers + service 词频共享，区分必须靠 network-destination domain reputation + service-name semantics。

**Cycle G retro-write 2026-05-08 — IMAGEPATH 是 conditional anchor not universal driver install requirement**（per Option B' 裁定 + NEG-7.2 push verify Result B 即 verbatim §3.7 sketch 无 IMAGEPATH addition）：driver install 实际 sequence 取决于 service type。Printer driver（T#7.1）必须 IMAGEPATH for SCM registration 即 SCM 用 IMAGEPATH registry value 知道 driver service .sys binary 路径 pure svcctl pipe write 不足以 register service 这是 Windows real-world deployment fidelity。AV engine driver（T#7.2）不必须 IMAGEPATH 因 av engine 通常通过 different mechanism 比如 Filter Manager API 注册 minifilter driver 而非传统 service 模式 加 vendor update NET_CONNECT 已是 distinguishing anchor 不需要 IMAGEPATH。Cycle G implementation 期 NEG-7.1 implementer 发现此 design defect 并 silent 添加 IMAGEPATH 步触发 protocol violation；Option B' 裁定 accept additive 7-event sequence + retro-write design propose（本段）+ lessons explicit 落档（commit 07251b2 Block 6）+ tier 重新标 "Tier 2 协议违反 + design defect detected + retro-write 修复 + lessons 落档"。Future Cycle implementer 必须 NEEDS_CONTEXT 报 user + 指导 Claude 不允许 silent sequence addition。

### §3.8 Class #8 合法 RDP（2 模板）

**T#8.1 `benign_rdp_remote_office_session`**
- Sequence：(user, USER_LOGON, mstsc.exe) [client] → (mstsc.exe, NET_CONNECT, target_host_network) → (user, USER_EXPLICIT_LOGON, target_winlogon.exe) [target host logon] → (target_winlogon.exe, PROCESS_CREATE, target_explorer.exe) → (target_explorer.exe, FILE_READ, target_user_profile_path)
- Confound：T1021.001 RDP（同已落地 attack TTP）
- Boundary：合法 RDP session **不**包含后续 lateral movement / credential dump（无 (target_*, NET_CONNECT, c2_*) 加无 (target_*, FILE_READ, lsass / SAM hive)）。BERT-only 看 mstsc + winlogon + RDP 词频与 T1021.001 share 完全（已落地 attack 模板用同 USER_EXPLICIT_LOGON 边），区分必须靠 downstream behavior chain。**单主机 schema 限制**继承 T1021.001 workaround #3（known_issues.md line 439）：本模板亦只建模 source view 加 docstring 说明限制。

**T#8.2 `benign_rdp_helpdesk_remote_assist`**
- Sequence：(user, USER_LOGON, mstsc.exe) → (mstsc.exe, NET_CONNECT, internal_helpdesk_network) → (mstsc.exe, FILE_WRITE, C:\Users\<helpdesk>\Documents\sessionlog.txt) [session log] → (mstsc.exe, FILE_WRITE, redirected_clipboard_buffer) [clipboard redirect] → (user, USER_EXPLICIT_LOGON, target_winlogon.exe)
- Confound：T1021.001 RDP（重 sub-pattern）
- Boundary：合法 helpdesk RDP **包含 clipboard redirect + drive redirect** 是 helpdesk session 标志特征，但 **不**包含 credential / token theft chain。BERT-only 仅靠 mstsc + clipboard 词频与 T1021.001 lateral-movement attack share，区分必须靠 downstream chain（clipboard write 是 helpdesk session log vs attacker exfil）。

### §3.9 Class #9 Network Probing & Scanning Normal（新加，3 模板）

**T#9.1 `benign_scanning_nessus_port_scan`**
- Sequence：(user, USER_LOGON, nessusd.exe) → (nessusd.exe, NET_CONNECT, internal_target_1_network:22) → (nessusd.exe, NET_CONNECT, internal_target_1_network:80) → (nessusd.exe, NET_CONNECT, internal_target_1_network:443) → (nessusd.exe, NET_CONNECT, internal_target_1_network:3389) → (nessusd.exe, NET_CONNECT, internal_target_2_network:22) → (nessusd.exe, NET_CONNECT, internal_target_2_network:80) → (nessusd.exe, FILE_WRITE, /var/lib/nessus/scans/<scan_id>.nessus) [scan report]
- Confound：T1046 network-service-discovery / T1018 remote-system-discovery
- Boundary：合法 Nessus 扫描 **target 全是 internal_*_network（RFC1918 私网）** 加 写 scan report 到 /var/lib/nessus/。T1046 attack 通常 target 是 internal-target 但 scan report write 缺失加 downstream 是 reconnaissance-then-exploit chain。BERT-only 看 NET_CONNECT burst 加多 port 词频共享，区分必须靠 (a) destination 私网语义 (b) scan report write 落地 (c) downstream 行为链。
- **NEEDS_CONTEXT 候选**：Sequence 含 7+ 个 NET_CONNECT 到不同 (network, port) 节点。每个 NET_CONNECT 边 (process, NET_CONNECT, network) 在 ALLOWED_EDGE_TRIPLES 中（line 125）覆盖。但 `network` node ID encoding 包含 port（如 `internal_target_1_network:22`）这是已落地 attack 模板的惯例（如 T1059.001 用 `c2_net = "185.234.219.11:4444"`），无新 schema 风险。**评估：覆盖**。

**T#9.2 `benign_scanning_nmap_internal_audit`**
- Sequence：(user, USER_LOGON, nmap.exe) → (nmap.exe, NET_CONNECT, internal_target_1_network:80) → (nmap.exe, NET_SEND_NETWORK, internal_target_1_network:80) [version probe] → (nmap.exe, NET_RECV_NETWORK, internal_target_1_network:80) [banner] → (nmap.exe, NET_CONNECT, internal_target_2_network:443) → (nmap.exe, NET_SEND_NETWORK, internal_target_2_network:443) → (nmap.exe, NET_RECV_NETWORK, internal_target_2_network:443) → (nmap.exe, FILE_WRITE, /tmp/nmap_audit_<timestamp>.xml)
- Confound：T1046 + T1018
- Boundary：合法 nmap 内网 audit **target 是私网 + nmap 输出 .xml 而非 attacker 落地 payload**。BERT-only 看 nmap + NET_CONNECT 词频与 T1046 attack share，区分必须靠 destination 网段 + 写出文件 extension semantics。
- **覆盖评估**：所有 (process, NET_CONNECT/NET_SEND_NETWORK/NET_RECV_NETWORK, network) 边在 ALLOWED_EDGE_TRIPLES（line 125, 128, 130）覆盖。**评估：覆盖**。

**T#9.3 `benign_scanning_hydra_weak_pwd_audit`**
- Sequence：(user, USER_LOGON, hydra.exe) → (hydra.exe, NET_CONNECT, internal_target_network:22) → (hydra.exe, NET_SEND_NETWORK, internal_target_network:22) [SSH login attempt 1] → (user, USER_LOGON_FAIL, target_sshd.exe) → (hydra.exe, NET_SEND_NETWORK, internal_target_network:22) [attempt 2] → (user, USER_LOGON_FAIL, target_sshd.exe) → (hydra.exe, NET_SEND_NETWORK, internal_target_network:22) [attempt 3] → (user, USER_LOGON, target_sshd.exe) [合法弱口令测试成功] → (hydra.exe, FILE_WRITE, /tmp/hydra_audit_report.txt)
- Confound：T1110 brute-force / T1110.001 password-guessing
- Boundary：合法 weak-pwd test **target 是 internal_target_network 加 user 是 IT-controlled audit account 加 写出 audit report 落地**。T1110 attack target 是 production account + 无 audit report 写出。BERT-only 看 hydra + USER_LOGON_FAIL burst 词频与 T1110 share 完全，区分必须靠 (a) target account semantics (b) audit report write (c) downstream 行为缺失。
- **覆盖评估**：(user, USER_LOGON, process) + (user, USER_LOGON_FAIL, process) 在 ALLOWED_EDGE_TRIPLES（line 135-137）覆盖。**评估：覆盖**。

### §3.10 Class #10 Backup Agent Bulk Read Normal（新加，3 模板）

**T#10.1 `benign_backup_rsync_internal_sync`**
- Sequence：(user, USER_LOGON, rsync.exe) → (rsync.exe, FILE_READ, /home/user1/doc1.txt) → (rsync.exe, FILE_READ, /home/user1/doc2.txt) → (rsync.exe, FILE_READ, /home/user1/doc3.txt) → (rsync.exe, NET_CONNECT, internal_backup_server_network) → (rsync.exe, NET_SEND_NETWORK, internal_backup_server_network) [bulk transfer] → (rsync.exe, FILE_WRITE, /var/log/rsync_<timestamp>.log)
- Confound：T1005 data-from-local-system / T1041 exfiltration-over-c2-channel
- Boundary：合法 rsync 内网备份 **destination = internal_backup_server_network（RFC1918 私网 anchor）+ 写 rsync log 到本地**。T1005/T1041 attack destination 是 external IP 加 无 backup log 落地。BERT-only 看 rsync + FILE_READ burst 词频与 T1005 share 完全，区分必须靠 destination 私网 anchor。**T1486 ransomware-mimicry pair 单独 sanity check 关键 anchor**：本模板无 FILE_WRITE 到 .lock/.crypt extension + FILE_WRITE 是 log 而非 encrypted bytes，§6.2 详细评估。
- **覆盖评估**：(process, FILE_READ, file) line 110 + (process, NET_CONNECT, network) line 125 + (process, NET_SEND_NETWORK, network) line 128 + (process, FILE_WRITE, file) line 111 全覆盖。**评估：覆盖**。

**T#10.2 `benign_backup_robocopy_smb_full`**
- Sequence：(user, USER_LOGON, robocopy.exe) → (robocopy.exe, FILE_READ, C:\Users\user1\Documents\file1.docx) → (robocopy.exe, FILE_READ, C:\Users\user1\Documents\file2.xlsx) → (robocopy.exe, FILE_READ, C:\Users\user1\Documents\file3.pdf) → (robocopy.exe, NET_CONNECT, internal_smb_share_network) → (robocopy.exe, FILE_WRITE, \\internal-backup\share\user1\file1.docx) → (robocopy.exe, FILE_WRITE, \\internal-backup\share\user1\file2.xlsx) → (robocopy.exe, FILE_WRITE, C:\Logs\robocopy_<date>.log)
- Confound：T1039 data-from-network-shared-drive / T1005
- Boundary：合法 robocopy SMB 备份 **destination = \\internal-backup\share\* (UNC 内网 anchor) + 写 robocopy log 到本地 + FILE_WRITE 文件名与 source 完全相同**（无 .lock/.crypt extension change）。T1039 attack destination 是 attacker SMB share 加 write target 是 attacker-controlled。BERT-only 看 robocopy + FILE_READ + FILE_WRITE burst 词频与 T1039 share，区分必须靠 destination UNC anchor 加 file-extension preservation。
- **覆盖评估**：所有 (process, FILE_READ/WRITE, file) + (process, NET_CONNECT, network) 在 ALLOWED_EDGE_TRIPLES 中。**评估：覆盖**。
- **注意**：FILE_WRITE 到 UNC path \\internal-backup\share\* 是 file node ID 表示 SMB share。这与已落地 T1041 exfiltration / T1071 web protocols 中的 file node 表示惯例一致（用 path 字符串作 file node ID 不区分 local vs remote）。

**T#10.3 `benign_backup_veeam_agent_vss`**
- Sequence：(user, USER_LOGON, veeam_agent.exe) → (user, USER_PRIV_GRANT, veeam_agent.exe) → (veeam_agent.exe, FILE_WRITE, \\.\pipe\svcctl) [VSS service trigger] → (veeam_agent.exe, FILE_READ, C:\VSS_snapshot\Users\user1\file1.docx) [via VSS snapshot] → (veeam_agent.exe, FILE_READ, C:\VSS_snapshot\Users\user1\file2.xlsx) → (veeam_agent.exe, NET_CONNECT, internal_veeam_repo_network) → (veeam_agent.exe, NET_SEND_NETWORK, internal_veeam_repo_network) → (veeam_agent.exe, FILE_WRITE, C:\ProgramData\Veeam\Backup\<job_id>.vbk) [local backup chain entry]
- Confound：T1486 ransomware-mimicry pair / T1005
- Boundary：合法 Veeam agent **VSS-snapshot path 读取（区分于直接 read user file）+ destination 是 Veeam repo network anchor + 写本地 .vbk backup chain entry**。T1486 ransomware 直接 read user file + 写 .locked / .crypt 同名文件 + 不写 backup chain entry。BERT-only 看 veeam + .vbk + FILE_READ burst 词频对 T1486 ransomware-mimicry hard negative pair 单独 sanity check 是关键 distinct anchor，区分必须靠 (a) VSS_snapshot path prefix anchor (b) destination Veeam repo network (c) write target extension (.vbk vs .locked)。
- **覆盖评估**：所有边（FILE_WRITE 到 \\.\pipe\svcctl + FILE_READ + NET_CONNECT + FILE_WRITE）在 ALLOWED_EDGE_TRIPLES 中（VSS-snapshot path 是 file node ID 字符串语义不影响 schema）。**评估：覆盖**。

---

## §4 Mutual boundary clarification（Deliverable 3）

### §4.1 10 类 pairwise mutual boundary（实质 overlap pairs only）

仅列实质 non-trivial overlap pairs（45 cells 全列 overkill，本节聚焦 design 阶段识别的有歧义的 pair）：

#### Pair §4.1.A：#4 Admin Tool 执行 vs #9 Network Probing & Scanning（nmap-as-admin-tool 边界）
- **重叠点**：sysadmin 偶尔用 nmap 做 troubleshooting（"哪些 host alive？"）即 admin tool 用 network probing 工具的 grey area。
- **边界规则**：**process 启动 + 工具 invocation 单次属 #4 Admin Tool 执行**（若 sequence 仅含 1-2 个 NET_CONNECT 单 host 单 port 单次 ping-style）；**多 host 或多 port burst-scan + scan report write 落地属 #9 Network Probing & Scanning**（≥ 5 个 NET_CONNECT 到不同 (host, port) tuple + 写 scan report 到 scanner-specific path）。
- **本 design 实施**：T#4.1/T#4.2/T#4.3 都不含 nmap；T#9.1/T#9.2/T#9.3 必含 ≥ 5 NET_CONNECT burst + scan report write，按规则属 #9 不属 #4。

#### Pair §4.1.B：#6 FS 操作 vs #10 Backup Agent Bulk Read（generic FS ops vs bulk-read frequency-pattern + backup destination）
- **重叠点**：generic file read 序列与 bulk read sequence 在 syscall 层面无差。
- **边界规则**：**单 file 或少量 file（<5）read + write 本地落地属 #6 FS 操作**（如 audit log scan、config sync）；**≥ 5 file FILE_READ 序列 + NET_CONNECT 到 backup destination network + FILE_WRITE 到 backup repo path 属 #10 Backup**。Backup destination 必须是 RFC1918 私网或 UNC 内网 share；写 file 必须是 backup-format-specific（.vbk / .log）或与 source 完全同名（rsync/robocopy preservation）而非 transformation。
- **本 design 实施**：T#6.1（audit log scan）read 3 个 log + write 1 audit report → 属 #6；T#6.2（config sync）read 1 config + write 1 config rename → 属 #6；T#6.3（sysadmin ls + cat）属 #6；T#10.1/T#10.2/T#10.3 全部 ≥ 3 FILE_READ + NET_CONNECT 到 internal_backup_*_network + 写 backup-specific file → 属 #10。

#### Pair §4.1.C：#4 Admin Tool 执行 vs #1 Office/Email Normal（admin 也用 office 工具的边界）
- **重叠点**：sysadmin 也会用 Outlook 收 IT alert email、用 Excel 做 inventory spreadsheet。
- **边界规则**：**process tree 起点是 admin tool（powershell.exe / sc.exe / schtasks.exe）属 #4**；**process tree 起点是 office app（outlook.exe / excel.exe / winword.exe / chrome.exe）+ subject 是 normal user role 属 #1**。
- **本 design 实施**：T#1.1-T#1.3 起点都是 office app（outlook / excel / chrome）；T#4.1-T#4.3 起点都是 admin tool。

#### Pair §4.1.D：#3 合法 Auth vs #8 合法 RDP（RDP 触发 auth event 的边界）
- **重叠点**：RDP session 必然产生 USER_LOGON / USER_EXPLICIT_LOGON event，与 #3 单次 logon event 重叠。
- **边界规则**：**单次 logon 属 #3**（无 mstsc.exe / mstscax.dll involvement，无 NET_CONNECT 到 RDP target_host_network）；**RDP session 起点 mstsc.exe + NET_CONNECT 到 target_host_network + 后续 USER_EXPLICIT_LOGON 属 #8**（即使包含 logon event 整体属 RDP-flavored）。
- **本 design 实施**：T#3.1（interactive logon）+ T#3.2（kerberos service ticket）都不含 mstsc.exe + 不含 NET_CONNECT 到 target_host；T#8.1/T#8.2 必含 mstsc.exe + RDP NET_CONNECT。

#### Pair §4.1.E：#1 子集 admin PowerShell（如有）vs #4 Admin Tool 执行（PowerShell-as-admin-tool）
- **重叠点**：父 entry 6 类的 #1 是"管理员 PowerShell"，与 8 类的 #4 Admin Tool 执行（PowerShell 是 #4 核心 sub-pattern）完全重叠。
- **边界规则**：本 design 10 类中 #1 是 **Office/Email Normal**（不是 6 类的"管理员 PowerShell"）。父 entry 的"管理员 PowerShell"完全归 8/10 类的 **#4 Admin Tool 执行**——T#4.1 即直接 cover。本 pair 在本 design 中**不构成歧义**。

#### Pair §4.1.F：#6 FS 操作 vs #10 Backup Agent（再细分，per spec compliance reviewer pre-flight check）
- **额外说明**：T#10.3（Veeam VSS）写 \\.\pipe\svcctl 触发 VSS service 的 sequence event 与 T#4.2 admin sc.exe 写 \\.\pipe\svcctl 触发 service restart 在 svcctl pipe 写入 event 上重叠。
- **边界规则**：**process 是 admin tool（sc.exe / schtasks.exe）属 #4**；**process 是 backup agent（veeam_agent.exe / netbackup-bpcd）属 #10**。subject 主体 process 命名是 distinct anchor。

#### Pair §4.1.G：#9 Network Probing vs #3 合法 Auth（weak pwd test 边界）
- **重叠点**：T#9.3（hydra weak pwd）必然产生 USER_LOGON_FAIL burst 与 #3 合法 Auth 重叠。
- **边界规则**：**单次 USER_LOGON_FAIL 属 #3 子集（auth fail 是 #3 sub-pattern）**；**≥ 3 USER_LOGON_FAIL burst frequency-mode + 由 hydra-style scanner process 触发属 #9**。
- **本 design 实施**：T#3.1（interactive logon 成功）不含 USER_LOGON_FAIL；T#9.3 含 3 个 USER_LOGON_FAIL by hydra.exe → 属 #9。

### §4.2 Retro-write Stage 1 self-flagged 5 boundary candidates

5 candidates 来自 Stage 1 implementer dispatch report 加 spec compliance reviewer F4。本节是 Stage 1 ephemeral dispatch report 信息的 persistent audit trail。

#### C1：(R1 管理员 PowerShell × #6 FS 操作) Partial — PowerShell 命令本体 vs cmdlet 触发 FS ops 的交集边界

**Stage 1 implementer 判定**：6 × 8 cross-reference table 中给 Partial 不给 Full，理由 #6 FS 操作覆盖 PowerShell 触发的 FS 操作但不覆盖 PowerShell 远程执行本体。

**Stage 2 design 期 implementer 判定**：**Agree with Stage 1 implementer**。

**Reasoning**：本 design Class #4 Admin Tool 执行 T#4.1（admin powershell user-mgmt）已显式 cover PowerShell 命令本体（不写 payload + 不 spawn child process），与 Class #6 FS 操作 T#6.1-T#6.3（cron/Task-Scheduler 触发的 audit / config sync / sysadmin ls+cat）**互不重叠**——T#4.1 process tree 起点是 powershell.exe，T#6.x 起点是 audit_scanner / config_sync / ls.exe。Stage 1 Partial 判定在本 design 中**自然解决为 #4 vs #6 distinct templates**。

#### C2：(R1 管理员 PowerShell × #8 合法 RDP) Partial — RDP session 内 PowerShell co-occurrence vs #8 protocol mechanics 边界

**Stage 1 implementer 判定**：6 × 8 cross-reference table 中给 Partial 不给 Full，理由 RDP session 内可执行 PowerShell 但 8-col #8 不专门覆盖 PowerShell 命令本体。

**Stage 2 design 期 implementer 判定**：**Agree with Stage 1 implementer**。

**Reasoning**：本 design 把 PowerShell 命令本体放 Class #4（T#4.1）+ RDP 会话本体放 Class #8（T#8.1/T#8.2）作为 **distinct templates**。Stage 1 Partial 判定指向 "RDP session 内 PowerShell" 是 hybrid sub-pattern——本 design **明确不构造此 hybrid**：T#8.1（remote office）+ T#8.2（helpdesk remote assist）的 process tree 都到 target_explorer.exe / 文件读取为止不再深入 PowerShell。Stage 1 Partial 判定**在本 design 实施中自然解决为不需要 hybrid template**。

#### C3：(R5 软件更新 × #5 Certutil LOLBin) Partial — certutil 偶被 update agent 用作 hash 校验的极少数 edge case

**Stage 1 implementer 判定**：6 × 8 cross-reference table 中给 Partial 不给 Full（§5.5），理由 certutil 偶被 update agent 用于 hash 校验但不覆盖 update agent 主链。

**Stage 2 design 期 implementer 判定**：**Agree with Stage 1 implementer**。

**Reasoning**：本 design Class #5 Certutil LOLBin T#5.1（`benign_certutil_hash_verify_patch`）显式 scope 是 IT certutil hash-verify。Stage 1 Partial 判定指向 update agent 主链与 certutil 的极少数 edge case overlap——本 design **不**为 update agent 单独建 class（Stage 1 §5.5 已判定 row 5 软件更新非 critical uncovered aspect 不 trigger RFC），仅保留 T#5.1 cover certutil hash-verify sub-pattern。Stage 1 Partial 判定**在本 design 实施中自然解决为 Class #5 单 sub-pattern + 不扩 update-agent 类**。

#### C4：§7 Row 5 non-critical 标记 vs propose 第 11 类 "Software Update Agent Normal" 边界判定

**Stage 1 implementer 判定**：保留 Row 5 软件更新 non-critical 不 propose 第 11 类（§7.1 + §7.3），理由 update repo 域名 lexical 已足以让 BERT-only saturate + fusion 通过 process state machine 提供 incremental signal 应仍可 lift。

**Spec compliance reviewer F2 caveat**：T1059 disambiguation caveat（apt/yum/dnf 与 T1059 共享 package-manager command-line surface 的 lexical shortcut 较弱）。

**Stage 2 design 期 implementer 判定**：**Agree with Stage 1 implementer**（不 propose 第 11 类）+ **附加 design-level 缓解**。

**Reasoning**：Stage 1 论证（update repo 域名 lexical 已 saturate BERT-only + fusion 仍可 lift）合理。Spec reviewer F2 caveat 关注 apt/yum/dnf 共享 T1059 lexical 的弱化是 second-order concern。本 design 在 Class #4 T#4.1 加 Class #6 T#6.x 不直接覆盖 update agent process / repo download 链——这与 Stage 1 §7 决议一致。**Design-level 缓解**：Stage 2 Step 2 实施时，如某 attack TTP 模板（如 Phase 5 已落地 T1105 ingress tool transfer，本仓库实际无 T1105 模块对应代码即跳过——参考 known_issues.md）与 update agent 重叠造成 假可分性 risk，按 spec reviewer F2 caveat 走 NEEDS_CONTEXT 协议不擅自加第 11 类。**第 11 类不 propose**保留 design-level 简化。

#### C5：(R4 安全扫描 × #4 Admin Tool 执行) Partial — spec reviewer F4 加 vulnerability scanner runtime 主要由 network probing 主导而非 admin command-line semantics 即边缘 overcredit

**Stage 1 implementer 判定**：6 × 8 cross-reference table 中给 Partial 不给 Full（§4.1 + §5.4），理由 scanner 作为内部 IT tool 在执行语义上有交集但不覆盖 network probing flow 本身。

**Spec compliance reviewer F4 caveat**：vulnerability scanner runtime 主要由 network probing 主导而非 admin command-line semantics，即 Partial 是边缘 overcredit。

**Stage 2 design 期 implementer 判定**：**Improved/refined judgment** — overlap 应改判更窄（Stage 1 Partial 偏宽）但**不影响最终决议**因 Stage 1 已 propose 第 9 类 + user RFC 裁定接受。

**Reasoning**：Spec reviewer F4 caveat 准确——scanner（Nessus / OpenVAS / Qualys）的核心 signal 是 NET_CONNECT burst + service banner grab + USER_LOGON_FAIL frequency 而非 admin command-line semantics。本 design Class #9 T#9.1-T#9.3 完全把 network probing flow 作 first-class signal 而非借 #4 Admin Tool 间接覆盖——这正是 #9 必扩的工程理由。Stage 1 cell 给 Partial 在严格 audit 下是 weak overcredit 但 **不构成 Stage 1 决议错误**——RFC trigger Yes 已经基于 §5.4 critical uncovered aspects（port scanning + remote probing + weak pwd test frequency）。**design-level 落实**：Class #4 T#4.1-T#4.3 sequence 都不含 NET_CONNECT burst → 与 #9 互斥不重叠，C5 caveat 自然解决。

### §4.3 Stage 2 design 期 implementer 新识别 boundary candidates

设计本 doc 期间识别但 Stage 1 未涵盖的 boundary candidates，flag 给 reviewer 决定 Tier 分类（Tier 2 deferred 或 Tier 3 must-fix）：

**C6（Stage 2 新）：(#6 FS 操作 T#6.2 config sync) vs (T1486 ransomware FILE_WRITE 同 path 模式) — config sync 写回原 path 的 FILE_RENAME single-file pattern**

**Implementer 描述**：T#6.2 sequence 含 (config_sync.exe, FILE_WRITE, /etc/nginx/nginx.conf.new) → (config_sync.exe, FILE_RENAME, /etc/nginx/nginx.conf)。FILE_RENAME 是单 file 而非 batch mass-rename，**与 T1486 ransomware FILE_WRITE.locked + FILE_DELETE 模式有可识别 distinct lexical signature**（无 .new → .conf transformation 在 ransomware 中不存在）。但 spec reviewer 可能 flag 为 lexical-blind sanity check 时是否足够 distinct。

**Implementer 当前判定**：**Tier 2 deferred**——distinct signature 足够（.new suffix vs .locked extension 是 disjoint），但请 reviewer 验证。

**C7（Stage 2 新）：(#9 T#9.3 hydra weak pwd) vs (#3 合法 Auth USER_LOGON_FAIL count threshold)**

**Implementer 描述**：边界规则要求 #9 weak pwd 含 ≥ 3 USER_LOGON_FAIL burst。3 是经验阈值，可能在 anonymized 数据中模糊。

**Implementer 当前判定**：**Tier 2 deferred**——3 阈值是 design-level 启发，Stage 2 Step 2 实施时如发现某 attack TTP 模板的 USER_LOGON_FAIL 也 ≥ 3 触发 NEEDS_CONTEXT 由 reviewer 调整阈值（如改 ≥ 5）。

**C8（Stage 2 新）：(#10 T#10.3 Veeam VSS) vs (#4 admin sc.exe svcctl pipe write)**

**Implementer 描述**：T#10.3 sequence 含 (veeam_agent.exe, FILE_WRITE, \\.\pipe\svcctl)，与 T#4.2 admin sc.exe write svcctl pipe 完全相同 edge type + path。

**Controller 裁定（Path A，user + 指导 Claude 联合裁定 2026-05-08）**：**Tier 1 mitigated by design-期 §6.2 anchor cross-reference + sequence shape anchor**。Implementer 原 "Tier 2 deferred for reviewer validation" 措辞修订为以下三项 design-期落档 mitigation：

- **(a) 整体 sequence shape anchor**：T#10.3 svcctl write 后跟 FILE_READ × ≥3（VSS_snapshot path）+ NET_CONNECT(internal_veeam_repo_network) + NET_SEND_NETWORK + FILE_WRITE(.vbk backup chain) 序列尾，**vs** T#4.2 svcctl write 后立即 PROCESS_EXIT 结束。这是结构性 anchor 而非 lexical anchor 即 anonymization 后仍 robust（边类型序列形状不被 string mask 影响）。
- **(b) Cross-reference §6.2 T#10.3 已落档 3 structural anchors**：VSS_snapshot path prefix（file node ID 字符串前缀 `C:\VSS_snapshot\`）+ internal_veeam_repo_network destination（与外部 IP / public cloud upload 相对的内网备份服务器）+ FILE_DELETE 完全不出现（与 T1486 ransomware mass FILE_DELETE 结构性 disjoint）。详见 §6.2 T#10.3 lexical-blind 抵抗力评估段。
- **(c) 不依赖 subject process name lexical anchor**：明确 design 不靠 `veeam_agent.exe` vs `sc.exe` 字符串区分（anonymization pipeline 必然 token-mask process name 后 anchor 失效）。Boundary collapse 风险通过 (a) + (b) 结构性 anchor 化解。

**Tier 1 narrow footnote**：此 Tier 1 escalation 因 Tightening 2 caveat-同性质 anonymization-after lexical-blind robustness 要求而非 schema violation。后续 boundary cells 默认仍按 Tier 3 docstring note 处理仅当 boundary cell 涉及 anonymization-blind robustness 与 Tightening 2 caveat 同性质时升 Tier 1 design-期 mitigation 落档要求。Cycle B-F precedent 三级分类协议范围保持。

**Step 2 Batch B 实施 T#10.3 module 时 module docstring 重述要求**：必须 verbatim 重述上述 (a) sequence shape anchor + (b) §6.2 已落档 3 anchors + (c) 不依赖 lexical anchor 三项 mitigation 形成 design-期 + implementation-期双落档。这不是新 requirement——Step 1 launch spec §2 第五项 boundary cells transparency 回写纪律已 cover，本处仅 explicit re-affirm。

---

## §5 ALLOWED_EDGE_TRIPLES adaptability pre-assessment（Deliverable 4）

### §5.0 Schema 现状

来源：`src/loghetero/data/parsers/base.py` lines 106-141。

**ALLOWED_EDGE_TRIPLES 当前 28 triples**（footnote：EdgeType enum 含 29 值即 28 操作 + UNKNOWN，UNKNOWN 不在 ALLOWED_EDGE_TRIPLES 中因为 UNKNOWN 不构成合法 triple；`tests/test_hgt_layer.py::test_edge_type_one_hot_uses_29_dim` 锁定的 29 是 enum cardinality 非 ALLOWED_EDGE_TRIPLES cardinality）：
- File / handle (process → file)：FILE_OPEN / FILE_READ / FILE_WRITE / FILE_CLOSE / FILE_ACCESS / FILE_DELETE / FILE_RENAME / HANDLE_REQUEST / HANDLE_CLOSE / HANDLE_DUPLICATE
- Process (process → process)：PROCESS_CREATE / PROCESS_FORK / PROCESS_EXEC / PROCESS_EXIT
- Network：(process → network) NET_CONNECT / NET_ACCEPT / NET_SEND_NETWORK / NET_RECV_NETWORK / NET_HTTP_REQUEST；(process → socket) NET_SEND_SOCKET / NET_RECV_SOCKET；(network → network) NET_DNS_QUERY / NET_DNS_RESPONSE
- User auth (user → process)：USER_LOGON / USER_LOGOFF / USER_LOGON_FAIL / USER_PRIV_GRANT / USER_EXPLICIT_LOGON

**Phase 5 Checkpoint 15 已落地 4 entries schema workaround inventory（known_issues.md line 437-440）**：
1. T1055 svchost.exe 同时作 file node + process node（隐式 process injection）
2. T1068 USER_PRIV_GRANT 归 user 而非 process（priv-grant workaround #2）
3. T1021.001 RDP 单主机 schema（multi-host approximation workaround #3）
4. T1190 webshell-write 替代入站 NET_CONNECT（reverse-direction approximation workaround #4）

### §5.1-§5.10 逐 class 适配性评估

#### §5.1 Class #1 Office/Email Normal

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#1.1 outlook attachment view | (user, USER_LOGON, process), (process, FILE_WRITE, file), (process, PROCESS_CREATE, process), (process, FILE_READ, file) | **Yes** all | 无 schema gap |
| T#1.2 excel pivot edit | (user, USER_LOGON, process), (process, PROCESS_CREATE, process), (process, FILE_READ, file), (process, FILE_WRITE, file) | **Yes** all | 无 schema gap |
| T#1.3 browser pdf download open | (user, USER_LOGON, process), (process, NET_HTTP_REQUEST, network), (process, FILE_WRITE, file), (process, PROCESS_CREATE, process), (process, FILE_READ, file) | **Yes** all | 无 schema gap |

#### §5.2 Class #2 Web Server CGI

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#2.1 apache cgi perl | (process, NET_ACCEPT, network), (process, PROCESS_CREATE, process), (process, FILE_READ, file), (process, FILE_WRITE, file), (process, PROCESS_EXIT, process) | **Yes** all | NET_ACCEPT (process→network) 已在 schema line 126。无 gap |
| T#2.2 nginx php-fpm | (process, NET_ACCEPT, network), (process, NET_SEND_SOCKET, socket), (process, FILE_READ, file), (process, NET_CONNECT, network), (process, NET_SEND_NETWORK, network), (process, NET_RECV_NETWORK, network) | **Yes** all | NET_SEND_SOCKET (process→socket) line 127。无 gap |

#### §5.3 Class #3 合法 Auth

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#3.1 user interactive logon | (user, USER_LOGON, process), (process, PROCESS_CREATE, process), (process, FILE_READ, file) | **Yes** all | 无 gap |
| T#3.2 kerberos service ticket | (user, USER_LOGON, process), (user, USER_PRIV_GRANT, process), (process, NET_CONNECT, network), (process, NET_SEND_NETWORK, network), (process, NET_RECV_NETWORK, network), (process, FILE_WRITE, file) | **Yes** all | USER_PRIV_GRANT 归 user 而非 process 与 T1068 workaround #2 一致 |

#### §5.4 Class #4 Admin Tool 执行

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#4.1 admin powershell user-mgmt | (user, USER_LOGON, process), (process, FILE_READ, file), (process, NET_CONNECT, network), (process, NET_SEND_NETWORK, network), (process, NET_RECV_NETWORK, network), (process, PROCESS_EXIT, process) | **Yes** all | 无 gap |
| T#4.2 admin sc service restart | (user, USER_LOGON, process), (user, USER_PRIV_GRANT, process), (process, FILE_WRITE, file), (process, PROCESS_EXIT, process) | **Yes** all | svcctl pipe 写入用 file node 表示是已落地 workaround 模式（T1543.003 sc.exe 写 svcctl）继承不新增 |
| T#4.3 admin schtasks create | (user, USER_LOGON, process), (user, USER_PRIV_GRANT, process), (process, FILE_READ, file), (process, FILE_WRITE, file), (process, PROCESS_EXIT, process) | **Yes** all | 写 Tasks XML 是 normal file write 无 gap |

#### §5.5 Class #5 Certutil LOLBin

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#5.1 certutil hash verify patch | (user, USER_LOGON, process), (process, FILE_READ, file), (process, FILE_WRITE, file), (process, PROCESS_EXIT, process) | **Yes** all | 无 gap |

#### §5.6 Class #6 FS 操作

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#6.1 audit log scan | (user, USER_LOGON, process), (process, FILE_READ, file), (process, FILE_WRITE, file), (process, PROCESS_EXIT, process) | **Yes** all | 无 gap |
| T#6.2 config sync task | (user, USER_LOGON, process), (process, FILE_READ, file), (process, NET_CONNECT, network), (process, NET_SEND_NETWORK, network), (process, NET_RECV_NETWORK, network), (process, FILE_WRITE, file), (process, FILE_RENAME, file) | **Yes** all | FILE_RENAME (process→file) line 115 |
| T#6.3 sysadmin directory listing | (user, USER_LOGON, process), (process, FILE_READ, file), (process, PROCESS_EXIT, process) | **Yes** all | 无 gap |

#### §5.7 Class #7 软件驱动安装

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#7.1 driver install printer | (user, USER_LOGON, process), (user, USER_PRIV_GRANT, process), (process, FILE_WRITE, file), (process, PROCESS_EXIT, process) | **Yes** all | 写驱动 .sys 是 FILE_WRITE 到 file node；svcctl pipe 写继承 #4 T1543.003 模式无 gap；**IMAGEPATH registry write 继承 T1547.001 registry-as-file pattern**（**Cycle G retro-write 2026-05-08 per Option B' 裁定**：T1547.001 是 prior workaround per known_issues.md line 411-427 Checkpoint 14.5 RFC-14.5-1 audit anchor；**注意此 pattern 不在 line 437-440 4-entry Cycle F inventory** 内 而是 Checkpoint 14.5 落地的 prior pattern reuse；NO new inventory entry triggered）|
| T#7.2 driver install av engine | 同 T#7.1 + (process, NET_CONNECT, network), (process, NET_RECV_NETWORK, network) | **Yes** all | 无 gap |

#### §5.8 Class #8 合法 RDP

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#8.1 rdp remote office session | (user, USER_LOGON, process), (process, NET_CONNECT, network), (user, USER_EXPLICIT_LOGON, process), (process, PROCESS_CREATE, process), (process, FILE_READ, file) | **Yes** all | 单主机 schema 限制继承 T1021.001 workaround #3，docstring 说明 |
| T#8.2 rdp helpdesk remote assist | (user, USER_LOGON, process), (process, NET_CONNECT, network), (process, FILE_WRITE, file), (user, USER_EXPLICIT_LOGON, process) | **Yes** all | 同 T#8.1 单主机限制 |

#### §5.9 Class #9 Network Probing & Scanning Normal

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#9.1 nessus port scan | (user, USER_LOGON, process), (process, NET_CONNECT, network) × N, (process, FILE_WRITE, file) | **Yes** all | NET_CONNECT 可重复无 gap；network node ID 含 port 与已落地 attack 模板惯例一致 |
| T#9.2 nmap internal audit | 同 T#9.1 + (process, NET_SEND_NETWORK, network), (process, NET_RECV_NETWORK, network) | **Yes** all | 无 gap |
| T#9.3 hydra weak pwd audit | (user, USER_LOGON, process), (process, NET_CONNECT, network), (process, NET_SEND_NETWORK, network), (user, USER_LOGON_FAIL, process) × N, (process, FILE_WRITE, file) | **Yes** all | USER_LOGON_FAIL line 137 + 可重复 by 同 user 不同 process subject |

#### §5.10 Class #10 Backup Agent Bulk Read Normal

| 模板 | 需要的 edge triples | ALLOWED_EDGE_TRIPLES 覆盖 | 备注 |
|---|---|---|---|
| T#10.1 rsync internal sync | (user, USER_LOGON, process), (process, FILE_READ, file) × N, (process, NET_CONNECT, network), (process, NET_SEND_NETWORK, network), (process, FILE_WRITE, file) | **Yes** all | 无 gap |
| T#10.2 robocopy smb full | (user, USER_LOGON, process), (process, FILE_READ, file) × N, (process, NET_CONNECT, network), (process, FILE_WRITE, file) × N | **Yes** all | UNC path \\internal-backup\share\* 是 file node ID 字符串语义；与 T1041 已落地 file node 命名惯例一致 |
| T#10.3 veeam agent vss | (user, USER_LOGON, process), (user, USER_PRIV_GRANT, process), (process, FILE_WRITE, file) [svcctl pipe], (process, FILE_READ, file) × N [VSS_snapshot path], (process, NET_CONNECT, network), (process, NET_SEND_NETWORK, network), (process, FILE_WRITE, file) | **Yes** all | VSS_snapshot path 是 file node ID 字符串语义无 gap；svcctl pipe write 继承已落地模式 |

### §5.11 总结

#### High-risk schema #5 candidates 列表

**预期触发 NEEDS_CONTEXT 的模板：0**

所有 24 模板的 design sequence 仅使用现有 ALLOWED_EDGE_TRIPLES 28 triples 加 4 个已落地 schema workaround 模式（svcctl pipe write、file node ID 字符串语义、USER_PRIV_GRANT 归 user 而非 process、单主机 RDP schema 限制）。

**复用已落地 workaround 但非新增 inventory entry**：
- 4 个 #4 + #7 + #10 模板写 \\.\pipe\svcctl（T#4.2 + T#7.1 + T#7.2 + T#10.3）继承 T1543.003 sc.exe 写 svcctl pattern（file-node-as-X higher-level workaround spirit；T1190 workaround #4 是 webshell-write reverse-direction approximation 不同 workaround entry 不应混淆）
- T#8.1 / T#8.2 单主机 RDP schema 继承 T1021.001 workaround #3
- T#3.2 USER_PRIV_GRANT 归 user 继承 T1068 workaround #2

这些是 **复用** 不是新增——按 known_issues.md line 444-447 协议，新增条件是"发现 ALLOWED_EDGE_TRIPLES 当前不支持的边类型（即使有现有 workaround 借用如 file-node-as-X 也算）"。复用既有 workaround **不**触发 inventory 增补。

#### 整体 schema readiness 判定

**Low risk**——24 模板全部覆盖。

#### Step 2 实施序 propose

由于无 high-risk 模板，**实施序无 schema-driven 依赖**，按以下次序简化（与 attack TTP 模板 5 cycle batch 风格一致）：

1. **Cycle G（design 简单 + sub-pattern 集中类）**：Class #5（1 模板）+ Class #2（2 模板）+ Class #3（2 模板）+ Class #7（2 模板）= 7 模板
2. **Cycle H（重 sub-pattern diversity 类，含 lexical-blind sensitive 类）**：Class #1（3 模板）+ Class #4（3 模板）+ Class #6（3 模板，含 T1486 sanity check 关键 anchor）= 9 模板
3. **Cycle I（新加 + 单主机 RDP）**：Class #8（2 模板）+ Class #9（3 模板）+ Class #10（3 模板，含 T1486 sanity check 关键 anchor）= 8 模板

**实施序 rationale**：Cycle G 先 ramp 简单类锁定 design pattern；Cycle H 重 diversity 类巩固；Cycle I 把新加 #9 + #10 加 单主机 #8 放最后，给 reviewer 充分检查 boundary 加 lexical-blind anchor 的时间。**实施序 not strict required**——controller 可调整。

#### Schema 扩展协议

Step 2 实施时如真触发 schema gap（即与 §5 pre-assessment 不一致的实际 edge triple 缺失）implementer 必须走 NEEDS_CONTEXT 协议**不擅自 docstring-bypass**。具体：
- 立即 STOP 加 dispatch 报告 NEEDS_CONTEXT
- 不擅自加新 ALLOWED_EDGE_TRIPLES entry
- 不擅自 docstring 说明 workaround 然后跳过 schema 修改
- 由 controller 决定是 (a) 调整模板设计避开 schema gap 或 (b) 走 RFC 扩展 ALLOWED_EDGE_TRIPLES（参照 known_issues.md line 423-426 方案）

---

## §6 Tightening 2 lexical-pattern caveat 主动检查（Deliverable 5）

### §6.0 协议三要素引用

来源：`docs/known_issues.md::Phase 5 待办` Tightening 2 entry（line 388 起，2026-05-08 Path B 落档）。

1. **anonymize-then-classify 处理在单独 T1486 加对应 ransomware-mimicry pair 上做不混合其他 hard negative**
2. **期望 BERT-only F1 显著降级到 < 0.6** 即 anonymize 移除 lexical shortcut 后 BERT-only 不能仅靠 file 加密 lexical pattern 区分攻击与合法磁盘加密软件批量加密用户文件
3. **这条 sanity check 不能在整体 hard negative library 层面做必须做单独 pair** 因为整体 library 包含其他类的 hard negative 会稀释 lexical-blindness 测试压力

本 design 期 implementer **逐模板** 显式检查 #6 + #10 类即 #6 FS 操作 类与 #10 Backup Agent Bulk Read 类的所有模板对 T1486 ransomware mimicry 的 lexical-blind 抵抗力。

### §6.1 #6 FS 操作 类逐模板检查

**通用 lexical-blind 抵抗力评估规则**：
- 检查 1：是否使用 mass-rename to `.lock` / `.crypt` / `.encrypted` / 类似 ransomware extensions（→ 必须 NO）
- 检查 2：是否使用 high-entropy file content write 即 ransomware-style encrypted bytes（→ 必须 NO）
- 检查 3：distinct lexical signature 是什么（区分 vs T1486 ransomware mimicry pair）

#### T#6.1 `benign_fs_audit_log_scan`

- **检查 1（mass-rename）**：**NO**——sequence 仅含 (audit_scanner.exe, FILE_WRITE, /var/log/audit_report_<date>.txt) 写一份 audit report 到 audit dir + 不重命名 source files。
- **检查 2（high-entropy write）**：**NO**——audit report 是文本格式（plain ASCII / structured log）非 encrypted bytes。
- **检查 3（distinct signature）**：source files = /var/log/auth.log + /var/log/secure + /var/log/syslog（well-known log paths）；write target = /var/log/audit_report_<date>.txt（distinct extension `.txt` + distinct path "audit_report" + 单 file 而非 batch）。T1486 ransomware 写到 .locked / .crypt extension + batch 1:1 same-stem 模式。
- **抵抗力**：**Strong**——lexical signature distinct（audit_report .txt 与 .locked 在 anonymization 后仍 disjoint）。

#### T#6.2 `benign_fs_config_sync_task`

- **检查 1（mass-rename）**：**NO**——sequence 含 (config_sync.exe, FILE_WRITE, /etc/nginx/nginx.conf.new) → (config_sync.exe, FILE_RENAME, /etc/nginx/nginx.conf) 是 single-file `.new` → original-name rename 模式（atomic write）非 batch mass-rename。
- **检查 2（high-entropy write）**：**NO**——nginx.conf 是 plain text 配置非 encrypted bytes。
- **检查 3（distinct signature）**：write target extension `.new` → .conf rename 是 atomic-write idiom；T1486 ransomware 用 .locked extension append 不 rename 回原 extension。FILE_RENAME single-file vs T1486 batch FILE_DELETE source 是结构性 disjoint。
- **抵抗力**：**Strong**——`.new` → `.conf` atomic write 与 `.locked` append-extension 是不同 idiom，anonymization 后仍 distinguishable by **edge type 序列**（FILE_RENAME single-file vs FILE_DELETE batch）。

#### T#6.3 `benign_fs_sysadmin_directory_listing`

- **检查 1（mass-rename）**：**NO**——sequence 完全无 FILE_WRITE 仅含 FILE_READ。
- **检查 2（high-entropy write）**：**NO**——无 FILE_WRITE。
- **检查 3（distinct signature）**：sequence 仅 read /etc + read /etc/passwd 加 PROCESS_EXIT 无 write。T1486 ransomware 必 FILE_WRITE.locked + FILE_DELETE，本模板**结构上无 FILE_WRITE / FILE_DELETE 完全 disjoint**。
- **抵抗力**：**Strong**——结构 disjoint，无须依赖 lexical 即区分。

**#6 类总结**：3/3 模板抵抗力 Strong，无 borderline / weak。

### §6.2 #10 Backup Agent Bulk Read Normal 类逐模板检查

**附加要求**（除 §6.0 三检查外）：**backup-destination 语义 anchor**——写到内网备份服务器 IP / 内部 SMB share / 备份 server hostname pattern 加 NOT 写到外部 IP / public cloud upload。

#### T#10.1 `benign_backup_rsync_internal_sync`

- **检查 1（mass-rename）**：**NO**——sequence 仅含 FILE_READ × 3 + NET_SEND_NETWORK + FILE_WRITE rsync log。无 FILE_RENAME / FILE_DELETE。
- **检查 2（high-entropy write）**：**NO**——FILE_WRITE 是 /var/log/rsync_<timestamp>.log（plain text rsync log 非 encrypted bytes）。
- **检查 3（distinct signature）**：destination = `internal_backup_server_network`（network node ID 含 RFC1918 私网 anchor 即 prefix 含 "internal_backup_server"）；T1486 ransomware C2 destination 是 external IP（如 `185.220.101.58:8080`）。**Backup-destination anchor**：write 仅落地 rsync log 到 /var/log/，**source files 完全无修改**（FILE_READ only）。
- **抵抗力**：**Strong**——结构性 disjoint（source 无 FILE_WRITE/.locked + destination 是 internal anchor）。

#### T#10.2 `benign_backup_robocopy_smb_full`

- **检查 1（mass-rename）**：**NO**——sequence 含 FILE_WRITE 到 \\internal-backup\share\* but **写入 file 名与 source 完全相同**（file1.docx → file1.docx 而非 file1.docx → file1.docx.locked）。无 FILE_RENAME / FILE_DELETE。
- **检查 2（high-entropy write）**：**NO**——robocopy 是 byte-level copy 写入文件 = source 文件 + 与 source 完全相同 mime type。**关键 distinct anchor**：T1486 ransomware FILE_WRITE 后必 FILE_DELETE source；T#10.2 sequence **不含 FILE_DELETE**（robocopy 仅 copy 不 delete）。
- **检查 3（distinct signature）**：destination = `\\internal-backup\share\` UNC path prefix（RFC1918 内网 SMB anchor）；写入 file 与 source 完全同名（无 .locked extension append）；FILE_DELETE 完全缺失。T1486 ransomware FILE_WRITE.locked + FILE_DELETE 模式**结构性 disjoint**。
- **抵抗力**：**Strong**——结构性 disjoint（FILE_DELETE 缺失 + extension preservation）。

#### T#10.3 `benign_backup_veeam_agent_vss`

- **检查 1（mass-rename）**：**NO**——sequence 含 FILE_WRITE 到 C:\ProgramData\Veeam\Backup\<job_id>.vbk（Veeam-specific backup chain entry 非 ransomware extension）+ FILE_WRITE 到 \\.\pipe\svcctl（VSS service trigger 非 file content write）。无 FILE_RENAME / FILE_DELETE。
- **检查 2（high-entropy write）**：**Borderline**——`.vbk` 是 Veeam 专有 backup format 内含 compressed + 可能 encrypted 数据（Veeam supports per-job encryption）。**潜在 lexical 重叠**：anonymization 后 `.vbk` extension 替换为 anonymous token，high-entropy bytes 写入 file 与 ransomware encrypted-write 看起来相似。
- **检查 3（distinct signature）**：(a) source FILE_READ path prefix `C:\VSS_snapshot\*`（VSS-snapshot anchor 非 user file path direct read）vs T1486 ransomware 直接 read `important_doc.docx` 等 user file。(b) destination network = `internal_veeam_repo_network`（内网 anchor）vs T1486 C2 external IP。(c) **不含 FILE_DELETE source**（Veeam preserves source）vs T1486 必 FILE_DELETE。(d) write 仅一份 .vbk backup chain entry vs T1486 1:1 per-source FILE_WRITE.locked。
- **抵抗力**：**Borderline → Strong**（after design adjustment）——

**Design adjustment（implementer 在本 design 阶段主动调整）**：T#10.3 sequence 必须显式 anchor "VSS_snapshot path prefix" 在 source FILE_READ + "internal_veeam_repo_network" anchor 在 destination + "FILE_DELETE 完全不出现" 这三 structural anchors 形成 lexical-blind 抵抗。**不依赖** `.vbk` extension lexical（anonymization 后此 anchor 消失）。Stage 2 Step 2 实施时 implementer 必须显式在模块 docstring 落档这三 anchor 作为 design rationale。

**最终评估**：**Strong**（after structural anchor adjustment）。

**#10 类总结**：3/3 模板抵抗力 Strong（T#10.3 经 design-期主动调整后达到 Strong）。

### §6.3 总评

| Class | 模板数 | Strong | Borderline | Weak | 行动 |
|---|---:|---:|---:|---:|---|
| #6 FS 操作 | 3 | 3 | 0 | 0 | 无须调整 |
| #10 Backup | 3 | 3（含 1 经调整） | 0 | 0 | T#10.3 design-期 structural anchor 调整已 in-place（§6.2） |

**lexical-blind 抵抗力总结**：所有 6 个 #6 + #10 模板预期能让 BERT-only F1 在与 T1486 pair 单独 sanity check 中显著降级 < 0.6——前提是 Stage 2 Step 2 实施时按 §6.2 T#10.3 structural anchor 落档。**design 期预测不是测量**——Checkpoint 16 完成后必须按 Tightening 2 协议（known_issues.md line 408-409）实测加结果落 docs/PROGRESS.md + docs/CHECKPOINT_LOG.md。

**重要提示**：本节是 **design-期主动检查**，实测在 Stage 2 Step 2 实施完成 + Checkpoint 16 closure 后 controller 触发的单独 sanity check dispatch 中执行。如实测 BERT-only F1 ≥ 0.6 触发 RFC（known_issues.md line 408-409 协议）。

---

## §7 Cross-references

1. `docs/checkpoint_16_hard_negative_design.md`（Stage 1 design doc 248 lines @ commit `be41d82`）——Stage 1 closure 6 × 8 cross-reference table + RFC trigger Yes 决议 + propose 第 9 + 第 10 类 candidate
2. `docs/known_issues.md::Phase 5 待办` Tightening 1 entry "Checkpoint 16 hard negative coverage 6 vs 8 categories cross-reference table 议程（Tightening 1）"（line 361 起）——8 类 verbatim 清单 + 4 条 Checkpoint 16 launch 硬要求
3. `docs/known_issues.md::Phase 5 待办` 父 entry "20 TTP 模板设计必须含 6 类 hard negative benign admin behaviors（2026-05-06，Phase 5 launch spec 启动前预读议程）"（line 335 起）——6 类 GPT-critique source-of-truth + Phase 5 4 条硬性要求
4. `docs/known_issues.md::Phase 5 待办` Tightening 2 entry "T1486 ransomware-mimicry hard negative pair 单独 lexical-blind sanity check 协议"（line 388 起）——T1486 pair 单独 sanity check 协议三要素
5. `docs/known_issues.md::Phase 5 待办` Checkpoint 17 schema workaround inventory tracking entry（line 429 起，4 entries pre-Checkpoint-17）——Phase 5 Checkpoint 15 已落地 workaround 列表 + 增补协议
6. `docs/known_issues.md::Phase 5 待办` ALLOWED_EDGE_TRIPLES schema 扩展议程 entry（line 411 起）——schema 扩展决策 RFC framework
7. Cycle F + Checkpoint 15 closure commit `1094df1`（feat(phase5): Cycle F + Checkpoint 15 close (T1190+T1560.001+T1486+T1490, 20 templates total, schema workaround inventory 4 entries pre-Checkpoint-17)）——20 TTP attack 模板落地 anchor + Checkpoint 16 launch readiness anchor
8. Path B audit gap close commit `9a9eedf`（docs(phase5): close Tightening 1+2 audit gap in known_issues (post-1094df1 verify-only dispatch finding)）——Tightening 1 + Tightening 2 entry 落 known_issues.md anchor
9. Stage 1 closure commit `be41d82`（docs(phase5): Checkpoint 16 Stage 1 Tightening 1 cross-reference table + RFC trigger (rows 4+6)）——Stage 1 6×8 table + RFC trigger Yes propose 落档
10. `src/loghetero/data/parsers/base.py` lines 27-141——NodeType + EdgeType + ALLOWED_EDGE_TRIPLES schema 现状 source-of-truth
11. `src/loghetero/data/attack_templates/`——Phase 4-5 已实施 20 TTP 模板代码 reference（design pattern 加 ALLOWED_EDGE_TRIPLES 当前覆盖参考）
