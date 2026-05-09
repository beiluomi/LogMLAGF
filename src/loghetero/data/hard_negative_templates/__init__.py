"""Phase 5 / Checkpoint 16 Stage 2 hard-negative benign template registry.

These templates simulate **legitimate admin / benign behavior** that lexically
resembles attack TTPs but is structurally / semantically distinct. They are
NOT attack templates. They emit ``Event`` objects with ``label=0`` (benign)
so that the fusion classifier can be evaluated against confounding admin
behaviors that share lexical surface with confound TTPs.

Cycle G Batch A (7 templates spanning 4 of the 10 designed classes) +
Cycle H Batch A second batch (9 templates spanning 3 additional classes —
total 16 templates spanning 7 of the 10 designed classes; remaining
classes deferred to subsequent Stage 2 cycles):

    - Class #1 Office/Email Normal (Cycle H — 3 templates):
        - NEG-1.1: benign_office_outlook_attachment_view
        - NEG-1.2: benign_office_excel_pivot_edit
        - NEG-1.3: benign_office_browser_pdf_download_open
    - Class #2 Web Server CGI (Cycle G — 2 templates):
        - NEG-2.1: benign_webserver_apache_cgi_perl
        - NEG-2.2: benign_webserver_nginx_php_fpm
    - Class #3 合法 Auth (Cycle G — 2 templates):
        - NEG-3.1: benign_auth_user_interactive_logon
        - NEG-3.2: benign_auth_kerberos_service_ticket
    - Class #4 Admin Tool 执行 (Cycle H — 3 templates):
        - NEG-4.1: benign_admin_powershell_user_mgmt
        - NEG-4.2: benign_admin_sc_service_restart
        - NEG-4.3: benign_admin_schtasks_create
    - Class #5 Certutil LOLBin (Cycle G — 1 template):
        - NEG-5.1: benign_certutil_hash_verify_patch
    - Class #6 FS 操作 (Cycle H — 3 templates):
        - NEG-6.1: benign_fs_audit_log_scan
        - NEG-6.2: benign_fs_config_sync_task
        - NEG-6.3: benign_fs_sysadmin_directory_listing
    - Class #7 软件驱动安装 (Cycle G — 2 templates):
        - NEG-7.1: benign_driver_install_printer
        - NEG-7.2: benign_driver_install_av_engine

Schema-workaround reuse summary (per design propose §5.X + known_issues.md
inventory entries 1-4 — Cycle G + Cycle H both trigger ZERO new inventory
entries):

    - USER_PRIV_GRANT user-anchor (T1068 workaround #2 reuse):
        NEG-3.2, NEG-4.2, NEG-4.3, NEG-7.1, NEG-7.2.
    - svcctl pipe-as-file (T1543.003 sc.exe pattern reuse):
        NEG-4.2, NEG-7.1, NEG-7.2.
    - Registry-as-file (T1547.001 pattern reuse):
        NEG-7.1.
    - Vanilla schema (no workaround):
        NEG-1.1, NEG-1.2, NEG-1.3, NEG-2.1, NEG-2.2, NEG-3.1, NEG-4.1,
        NEG-5.1, NEG-6.1, NEG-6.2, NEG-6.3.

Usage::

    from loghetero.data.hard_negative_templates import ALL_HARD_NEGATIVE_TEMPLATES
    for tmpl in ALL_HARD_NEGATIVE_TEMPLATES:
        events = tmpl.generate(seed_subject, seed_type, t_start, t_end, rng, iid)

    # Lookup by NEG-ID (stage 3 sanity check + Phase 11 ablation anchor):
    from loghetero.data.hard_negative_templates import NEG_TEMPLATE_REGISTRY
    tmpl_cls = NEG_TEMPLATE_REGISTRY["NEG-5.1"]
    events = tmpl_cls().generate(...)

These templates are NOT registered in
:data:`loghetero.data.attack_templates.ALL_TEMPLATES` — they have a separate
registry list to keep the attack-injector iteration disjoint.

Design source-of-truth: ``docs/checkpoint_16_hard_negative_templates_design.md``
(commit ``daeefa5``).
"""

from __future__ import annotations

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.hard_negative_templates.neg_1_1_outlook_attachment import (
    Neg11OutlookAttachment,
)
from loghetero.data.hard_negative_templates.neg_1_2_excel_pivot import Neg12ExcelPivot
from loghetero.data.hard_negative_templates.neg_1_3_browser_pdf import Neg13BrowserPdf
from loghetero.data.hard_negative_templates.neg_2_1_apache_cgi_perl import (
    Neg21ApacheCgiPerl,
)
from loghetero.data.hard_negative_templates.neg_2_2_nginx_php_fpm import (
    Neg22NginxPhpFpm,
)
from loghetero.data.hard_negative_templates.neg_3_1_user_interactive_logon import (
    Neg31UserInteractiveLogon,
)
from loghetero.data.hard_negative_templates.neg_3_2_kerberos_service_ticket import (
    Neg32KerberosServiceTicket,
)
from loghetero.data.hard_negative_templates.neg_4_1_powershell_user_mgmt import (
    Neg41PowershellUserMgmt,
)
from loghetero.data.hard_negative_templates.neg_4_2_sc_service_restart import (
    Neg42ScServiceRestart,
)
from loghetero.data.hard_negative_templates.neg_4_3_schtasks_create import (
    Neg43SchtasksCreate,
)
from loghetero.data.hard_negative_templates.neg_5_1_certutil_hash_verify import (
    Neg51CertutilHashVerify,
)
from loghetero.data.hard_negative_templates.neg_6_1_audit_log_scan import (
    Neg61AuditLogScan,
)
from loghetero.data.hard_negative_templates.neg_6_2_config_sync_task import (
    Neg62ConfigSyncTask,
)
from loghetero.data.hard_negative_templates.neg_6_3_sysadmin_directory_listing import (
    Neg63SysadminDirectoryListing,
)
from loghetero.data.hard_negative_templates.neg_7_1_driver_install_printer import (
    Neg71DriverInstallPrinter,
)
from loghetero.data.hard_negative_templates.neg_7_2_driver_install_av_engine import (
    Neg72DriverInstallAvEngine,
)

ALL_HARD_NEGATIVE_TEMPLATES: list[HardNegativeTemplate] = [
    Neg51CertutilHashVerify(),
    Neg21ApacheCgiPerl(),
    Neg22NginxPhpFpm(),
    Neg31UserInteractiveLogon(),
    Neg32KerberosServiceTicket(),
    Neg71DriverInstallPrinter(),
    Neg72DriverInstallAvEngine(),
    Neg11OutlookAttachment(),
    Neg12ExcelPivot(),
    Neg13BrowserPdf(),
    Neg41PowershellUserMgmt(),
    Neg42ScServiceRestart(),
    Neg43SchtasksCreate(),
    Neg61AuditLogScan(),
    Neg62ConfigSyncTask(),
    Neg63SysadminDirectoryListing(),
]

# NEG-ID -> template class registry. Used by stage 3 sanity check + Phase 11
# ablation runners to look up a template by audit identifier.
NEG_TEMPLATE_REGISTRY: dict[str, type[HardNegativeTemplate]] = {
    "NEG-5.1": Neg51CertutilHashVerify,
    "NEG-2.1": Neg21ApacheCgiPerl,
    "NEG-2.2": Neg22NginxPhpFpm,
    "NEG-3.1": Neg31UserInteractiveLogon,
    "NEG-3.2": Neg32KerberosServiceTicket,
    "NEG-7.1": Neg71DriverInstallPrinter,
    "NEG-7.2": Neg72DriverInstallAvEngine,
    "NEG-1.1": Neg11OutlookAttachment,
    "NEG-1.2": Neg12ExcelPivot,
    "NEG-1.3": Neg13BrowserPdf,
    "NEG-4.1": Neg41PowershellUserMgmt,
    "NEG-4.2": Neg42ScServiceRestart,
    "NEG-4.3": Neg43SchtasksCreate,
    "NEG-6.1": Neg61AuditLogScan,
    "NEG-6.2": Neg62ConfigSyncTask,
    "NEG-6.3": Neg63SysadminDirectoryListing,
}

__all__ = [
    "HardNegativeTemplate",
    "Neg51CertutilHashVerify",
    "Neg21ApacheCgiPerl",
    "Neg22NginxPhpFpm",
    "Neg31UserInteractiveLogon",
    "Neg32KerberosServiceTicket",
    "Neg71DriverInstallPrinter",
    "Neg72DriverInstallAvEngine",
    "Neg11OutlookAttachment",
    "Neg12ExcelPivot",
    "Neg13BrowserPdf",
    "Neg41PowershellUserMgmt",
    "Neg42ScServiceRestart",
    "Neg43SchtasksCreate",
    "Neg61AuditLogScan",
    "Neg62ConfigSyncTask",
    "Neg63SysadminDirectoryListing",
    "ALL_HARD_NEGATIVE_TEMPLATES",
    "NEG_TEMPLATE_REGISTRY",
]
