# MITRE ATT&CK Template Registry

*Phase 5 will populate this document with the full ≥20-template registry, each entry linked to its concrete generator in `src/loghetero/data/attack_templates/`.*

## Coverage target

≥ 20 TTP templates spanning ≥ 8 of the 12 ATT&CK Enterprise tactics:

| Tactic              | Planned TTPs (subject to Phase-5 refinement)              |
|---------------------|-----------------------------------------------------------|
| Execution           | T1059.001 PowerShell · T1059.003 cmd · T1059.004 Unix shell · T1106 Native API |
| Persistence         | T1547.001 Registry Run · T1543.003 Windows Service · T1053.005 Scheduled Task |
| Defense Evasion     | T1027 Obfuscated Files · T1070.004 File Deletion · T1112 Modify Registry |
| Credential Access   | T1003.001 LSASS · T1003.008 /etc/passwd · T1555 Credential Stores |
| Discovery           | T1057 Process Discovery · T1083 File and Directory Discovery |
| Lateral Movement    | T1021.001 RDP · T1021.002 SMB                              |
| Command and Control | T1071.001 Web Protocols · T1095 Non-Application Protocol  |
| Exfiltration        | T1041 Exfil Over C2 · T1567.002 Cloud Storage Exfil       |

Each template is implemented as a Python class deriving from `BaseAttackTemplate`, exposing `generate_subgraph(benign_context) -> tuple[ProvenanceGraph, list[InjectedNodeId]]`.
