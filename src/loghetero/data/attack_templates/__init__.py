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

Usage::

    from loghetero.data.attack_templates import ALL_TEMPLATES
    for tmpl in ALL_TEMPLATES:
        events = tmpl.generate(seed_subject, seed_type, t_start, t_end, rng, iid)
"""

from __future__ import annotations

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.attack_templates.t1003_001_lsass_memory import T1003001LsassMemory
from loghetero.data.attack_templates.t1041_exfiltration import T1041Exfiltration
from loghetero.data.attack_templates.t1055_process_injection import T1055ProcessInjection
from loghetero.data.attack_templates.t1059_001_powershell import T1059001PowerShell
from loghetero.data.attack_templates.t1071_001_web_protocols import T1071001WebProtocols
from loghetero.data.attack_templates.t1547_001_registry_run_keys import T1547001RegistryRunKeys

ALL_TEMPLATES: list[AttackTemplate] = [
    T1059001PowerShell(),
    T1003001LsassMemory(),
    T1071001WebProtocols(),
    T1547001RegistryRunKeys(),
    T1041Exfiltration(),
    T1055ProcessInjection(),
]

__all__ = [
    "AttackTemplate",
    "T1059001PowerShell",
    "T1003001LsassMemory",
    "T1071001WebProtocols",
    "T1547001RegistryRunKeys",
    "T1041Exfiltration",
    "T1055ProcessInjection",
    "ALL_TEMPLATES",
]
