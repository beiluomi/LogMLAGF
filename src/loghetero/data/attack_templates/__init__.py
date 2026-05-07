"""ATT&CK TTP synthetic attack event template registry (Phase 4 / Checkpoint 14.5
+ Phase 5 / Checkpoint 15).

Phase 4 templates (RFC-14.5-1 accepted sequences, RFC-14.5-10 hand-coded):
    - T1059.001: PowerShell execution + C2 (7 events)
    - T1003.001: LSASS credential dump via Mimikatz (7 events)
    - T1071.001: HTTP C2 beaconing (7 events)
    - T1547.001: Registry Run Key persistence (7 events)
    - T1041:     Exfiltration over C2 channel (7 events)

Phase 5 templates (Checkpoint 15 Cycle A-F, RFC adjudication):
    - T1055:     Process Injection via svchost (8 events)
    - T1068:     Exploitation for Privilege Escalation via kernel driver (8 events)
    - T1021.001: RDP lateral movement / single-host approximation (8 events)
    - T1566.001: Spearphishing Attachment (7 events)
    - T1078:     Valid Accounts credential abuse (7 events)
    - T1057:     Process Discovery via tasklist + findstr (7 events)
    - T1083:     File and Directory Discovery via dir_enum (8 events)
    - T1027:     Obfuscated Files via certutil decode (7 events)
    - T1070.004: Indicator Removal: File Deletion via cleanup_tool (7 events)
    - T1053.005: Scheduled Task persistence + execution (8 events)
    - T1543.003: Windows Service persistence + execution (7 events)

Usage::

    from loghetero.data.attack_templates import ALL_TEMPLATES
    for tmpl in ALL_TEMPLATES:
        events = tmpl.generate(seed_subject, seed_type, t_start, t_end, rng, iid)
"""

from __future__ import annotations

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.attack_templates.t1003_001_lsass_memory import T1003001LsassMemory
from loghetero.data.attack_templates.t1021_001_rdp import T1021001RDP
from loghetero.data.attack_templates.t1027_obfuscated_files import T1027ObfuscatedFiles
from loghetero.data.attack_templates.t1041_exfiltration import T1041Exfiltration
from loghetero.data.attack_templates.t1053_005_scheduled_task import T1053005ScheduledTask
from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection
from loghetero.data.attack_templates.t1057_process_discovery import T1057ProcessDiscovery
from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell
from loghetero.data.attack_templates.t1068_exploitation_for_privesc import (
    T1068ExploitationForPrivEsc,
)
from loghetero.data.attack_templates.t1070_004_file_deletion import T1070004FileDeletion
from loghetero.data.attack_templates.t1071_001_web_protocols import T1071001WebProtocols
from loghetero.data.attack_templates.t1078_valid_accounts import T1078ValidAccounts
from loghetero.data.attack_templates.t1083_file_discovery import T1083FileDiscovery
from loghetero.data.attack_templates.t1543_003_windows_service import T1543003WindowsService
from loghetero.data.attack_templates.t1547_001_registry_run_keys import T1547001RegistryRunKeys
from loghetero.data.attack_templates.t1566_001_spearphishing_attachment import (
    T1566001SpearphishingAttachment,
)

ALL_TEMPLATES: list[AttackTemplate] = [
    T1059001PowerShell(),
    T1003001LsassMemory(),
    T1071001WebProtocols(),
    T1547001RegistryRunKeys(),
    T1041Exfiltration(),
    T1055ProcessInjection(),
    T1068ExploitationForPrivEsc(),
    T1021001RDP(),
    T1566001SpearphishingAttachment(),
    T1078ValidAccounts(),
    T1057ProcessDiscovery(),
    T1083FileDiscovery(),
    T1027ObfuscatedFiles(),
    T1070004FileDeletion(),
    T1053005ScheduledTask(),
    T1543003WindowsService(),
]

__all__ = [
    "AttackTemplate",
    "T1059001PowerShell",
    "T1003001LsassMemory",
    "T1071001WebProtocols",
    "T1547001RegistryRunKeys",
    "T1041Exfiltration",
    "T1055ProcessInjection",
    "T1068ExploitationForPrivEsc",
    "T1021001RDP",
    "T1566001SpearphishingAttachment",
    "T1078ValidAccounts",
    "T1057ProcessDiscovery",
    "T1083FileDiscovery",
    "T1027ObfuscatedFiles",
    "T1070004FileDeletion",
    "T1053005ScheduledTask",
    "T1543003WindowsService",
    "ALL_TEMPLATES",
]
