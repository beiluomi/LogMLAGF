"""LogHetero tokenizer: bert-base-uncased + 156 domain-special placeholders.

Phase 1.3 deliverable per the Checkpoint 3 launch spec. Special tokens are
**added but not retrained** -- their embeddings are initialised from the mean
of related natural-language BERT tokens (the *synonym init* strategy). This
avoids a full DAPT (per design_decisions.md decision 4.1) while still giving
the cross-modal attention layer a sensible starting point for Phase 4.

The Checkpoint 3 nearest-neighbour sanity script (``scripts/tokenizer_nn_sanity.py``)
asserts that the initialised embedding for each special token is closer to its
synonym set than to a uniformly random BERT token, which is the smell-test we
care about before training begins.

Categories (16 + 30 + 24 + 24 + 20 + 12 + 4 + 14 + 12 = 156):

* generic identity (16)
* path (30)
* file extension (24)
* process name (24)
* network / port (20)
* identity / account (12)
* time (4)
* event-id (14)
* op / verb (12)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizerBase

# ---------------------------------------------------------------------------
# Special token list (~156 tokens). The cleaner emits these placeholders;
# anything missing here would tokenize as wordpieces of the bracket-wrapped
# string, defeating the purpose. Add carefully and update SYNONYM_INIT in lock
# step.
# ---------------------------------------------------------------------------

SPECIAL_TOKENS: list[str] = [
    # generic identity (16)
    "[IP]", "[IP_V4]", "[IP_V6]", "[IP_PRIV]", "[IP_PUB]", "[IP_LOOPBACK]",
    "[HASH_MD5]", "[HASH_SHA1]", "[HASH_SHA256]", "[HASH]", "[HEX]", "[HEX_LONG]",
    "[URL]", "[URL_HTTP]", "[URL_HTTPS]", "[DOMAIN]",
    # path (30)
    "[PATH_SEP]", "[PATH_DRIVE]", "[PATH_ABSOLUTE]", "[PATH_RELATIVE]", "[PATH_WIN_UNC]",
    "[PATH_WIN_SYS32]", "[PATH_WIN_SYSWOW64]", "[PATH_WIN_PROGRAM_FILES]",
    "[PATH_WIN_PROGRAM_FILES_X86]", "[PATH_WIN_PROGRAMDATA]", "[PATH_WIN_USERS]",
    "[PATH_WIN_USER]", "[PATH_WIN_TEMP]", "[PATH_WIN_APPDATA]", "[PATH_WIN_LOCALAPPDATA]",
    "[PATH_WIN_WINDOWS]", "[PATH_WIN_DESKTOP]", "[PATH_WIN_DOCUMENTS]",
    "[PATH_WIN_DOWNLOADS]", "[PATH_WIN_DRIVE]", "[PATH_WIN_STARTUP]",
    "[PATH_LINUX_BIN]", "[PATH_LINUX_ETC]", "[PATH_LINUX_HOME]", "[PATH_LINUX_TMP]",
    "[PATH_LINUX_VAR]", "[PATH_LINUX_PROC]",
    "[PATH_REGISTRY_HKLM]", "[PATH_REGISTRY_HKCU]", "[PATH_REGISTRY_RUN]",
    # file extension (24)
    "[EXT_EXE]", "[EXT_DLL]", "[EXT_BAT]", "[EXT_CMD]", "[EXT_PS1]", "[EXT_PSM1]",
    "[EXT_VBS]", "[EXT_JS]", "[EXT_HTA]", "[EXT_TXT]", "[EXT_LOG]", "[EXT_TMP]",
    "[EXT_HTML]", "[EXT_PDF]", "[EXT_DOC]", "[EXT_DOCX]", "[EXT_XLS]", "[EXT_XLSX]",
    "[EXT_ZIP]", "[EXT_RAR]", "[EXT_7Z]", "[EXT_JSON]", "[EXT_XML]", "[EXT_INI]",
    # process name (24)
    "[PROC]", "[PROC_SYSTEM]", "[PROC_FIREFOX]", "[PROC_CHROME]", "[PROC_IEXPLORE]",
    "[PROC_CMD]", "[PROC_POWERSHELL]", "[PROC_PWSH]", "[PROC_BASH]",
    "[PROC_EXPLORER]", "[PROC_MMC]", "[PROC_TASKMGR]",
    "[PROC_LSASS]", "[PROC_SVCHOST]", "[PROC_SERVICES]", "[PROC_WINLOGON]",
    "[PROC_CSRSS]", "[PROC_SMSS]",
    "[PROC_NOTEPAD]", "[PROC_OUTLOOK]", "[PROC_WORD]", "[PROC_EXCEL]",
    "[PROC_VSCODE]", "[PROC_PAYLOAD]",
    # network / port (20)
    "[PORT]", "[PORT_HTTP]", "[PORT_HTTPS]", "[PORT_DNS]", "[PORT_FTP]",
    "[PORT_SSH]", "[PORT_RDP]", "[PORT_SMB]", "[PORT_HIGH]", "[PORT_LOW]",
    "[NET_HTTP]", "[NET_HTTPS]", "[NET_DNS]", "[NET_TCP]", "[NET_UDP]",
    "[NET_ICMP]", "[NET_C2]", "[NET_LOCAL]", "[NET_REMOTE]", "[NET_LAN]",
    # identity / account (12)
    "[USER]", "[USER_DOMAIN]", "[SID]", "[LOGON_ID]", "[HANDLE_ID]", "[PROC_ID]",
    "[PARENT_PROC_ID]", "[ACCESS_MASK]", "[ACCESS_REASON]", "[GUID]",
    "[REGISTRY_KEY]", "[SERVICE_NAME]",
    # time (4)
    "[TIMESTAMP]", "[TIME_DAY]", "[TIME_HOUR]", "[TIME_RECENT]",
    # event-id semantic (14)
    "[EVENT_FILE_OPEN]", "[EVENT_FILE_READ]", "[EVENT_FILE_WRITE]",
    "[EVENT_FILE_DELETE]", "[EVENT_FILE_CLOSE]",
    "[EVENT_PROC_CREATE]", "[EVENT_PROC_EXIT]", "[EVENT_PROC_FORK]",
    "[EVENT_NET_CONNECT]", "[EVENT_NET_REQUEST]", "[EVENT_NET_SEND]",
    "[EVENT_NET_RECV]",
    "[EVENT_HANDLE_OPEN]", "[EVENT_HANDLE_CLOSE]",
    # op / verb (12)
    "[OP_AUDIT_SUCCESS]", "[OP_AUDIT_FAIL]", "[OP_LOGON]", "[OP_LOGOFF]",
    "[OP_PRIVILEGE]", "[OP_OBJECT_ACCESS]", "[OP_POLICY_CHANGE]",
    "[OP_QUERY]", "[OP_RESPONSE]", "[OP_DOWNLOAD]", "[OP_UPLOAD]", "[OP_EXEC]",
]

# Synonym phrases for embedding initialisation. Each special token's embedding
# is initialised as the mean of the BERT token embeddings of the words listed.
# Words that don't exist in BERT vocabulary are silently skipped; if NO synonym
# survives, the token gets the BERT random init (which we then flag as a
# WARNING in the nearest-neighbour sanity script).
SYNONYM_INIT: dict[str, list[str]] = {
    # generic identity
    "[IP]": ["ip", "address", "host", "network"],
    "[IP_V4]": ["ip", "address", "version", "four"],
    "[IP_V6]": ["ip", "address", "version", "six"],
    "[IP_PRIV]": ["ip", "private", "internal", "local"],
    "[IP_PUB]": ["ip", "public", "external", "internet"],
    "[IP_LOOPBACK]": ["loopback", "local", "host"],
    "[HASH_MD5]": ["hash", "checksum", "fingerprint", "md"],
    "[HASH_SHA1]": ["hash", "checksum", "fingerprint", "sha"],
    "[HASH_SHA256]": ["hash", "checksum", "fingerprint", "sha"],
    "[HASH]": ["hash", "checksum", "fingerprint", "digest"],
    "[HEX]": ["hex", "hexadecimal", "code", "value"],
    "[HEX_LONG]": ["hex", "hexadecimal", "long", "code"],
    "[URL]": ["url", "link", "address", "web"],
    "[URL_HTTP]": ["url", "http", "web", "request"],
    "[URL_HTTPS]": ["url", "https", "web", "secure"],
    "[DOMAIN]": ["domain", "name", "host", "website"],
    # path
    "[PATH_SEP]": ["path", "separator", "slash", "directory"],
    "[PATH_DRIVE]": ["drive", "disk", "volume", "letter"],
    "[PATH_ABSOLUTE]": ["absolute", "path", "full", "directory"],
    "[PATH_RELATIVE]": ["relative", "path", "directory", "current"],
    "[PATH_WIN_UNC]": ["network", "share", "server", "path"],
    "[PATH_WIN_SYS32]": ["windows", "system", "library", "directory"],
    "[PATH_WIN_SYSWOW64]": ["windows", "system", "library", "directory"],
    "[PATH_WIN_PROGRAM_FILES]": ["program", "files", "applications", "installed"],
    "[PATH_WIN_PROGRAM_FILES_X86]": ["program", "files", "applications", "installed"],
    "[PATH_WIN_PROGRAMDATA]": ["program", "data", "directory", "applications"],
    "[PATH_WIN_USERS]": ["users", "home", "directory", "profile"],
    "[PATH_WIN_USER]": ["user", "home", "directory", "profile"],
    "[PATH_WIN_TEMP]": ["temporary", "files", "directory", "cache"],
    "[PATH_WIN_APPDATA]": ["application", "data", "directory", "user"],
    "[PATH_WIN_LOCALAPPDATA]": ["local", "application", "data", "directory"],
    "[PATH_WIN_WINDOWS]": ["windows", "system", "directory", "operating"],
    "[PATH_WIN_DESKTOP]": ["desktop", "user", "directory", "files"],
    "[PATH_WIN_DOCUMENTS]": ["documents", "user", "directory", "files"],
    "[PATH_WIN_DOWNLOADS]": ["downloads", "user", "directory", "files"],
    "[PATH_WIN_DRIVE]": ["drive", "windows", "path", "letter"],
    "[PATH_WIN_STARTUP]": ["startup", "auto", "launch", "program"],
    "[PATH_LINUX_BIN]": ["binary", "executable", "system", "command"],
    "[PATH_LINUX_ETC]": ["configuration", "system", "settings", "directory"],
    "[PATH_LINUX_HOME]": ["home", "user", "directory", "profile"],
    "[PATH_LINUX_TMP]": ["temporary", "files", "directory", "cache"],
    "[PATH_LINUX_VAR]": ["variable", "data", "logs", "directory"],
    "[PATH_LINUX_PROC]": ["process", "system", "kernel", "interface"],
    "[PATH_REGISTRY_HKLM]": ["registry", "machine", "system", "key"],
    "[PATH_REGISTRY_HKCU]": ["registry", "user", "current", "key"],
    "[PATH_REGISTRY_RUN]": ["registry", "run", "startup", "auto"],
    # file extension
    "[EXT_EXE]": ["executable", "binary", "program", "windows"],
    "[EXT_DLL]": ["library", "dynamic", "linked", "windows"],
    "[EXT_BAT]": ["batch", "script", "windows", "command"],
    "[EXT_CMD]": ["command", "batch", "windows", "script"],
    "[EXT_PS1]": ["powershell", "script", "windows", "automation"],
    "[EXT_PSM1]": ["powershell", "module", "windows", "automation"],
    "[EXT_VBS]": ["script", "visual", "basic", "windows"],
    "[EXT_JS]": ["javascript", "script", "web", "code"],
    "[EXT_HTA]": ["html", "application", "windows", "script"],
    "[EXT_TXT]": ["text", "file", "plain", "document"],
    "[EXT_LOG]": ["log", "file", "events", "text"],
    "[EXT_TMP]": ["temporary", "file", "cache", "data"],
    "[EXT_HTML]": ["html", "web", "document", "page"],
    "[EXT_PDF]": ["pdf", "document", "portable", "format"],
    "[EXT_DOC]": ["document", "word", "office", "file"],
    "[EXT_DOCX]": ["document", "word", "office", "file"],
    "[EXT_XLS]": ["spreadsheet", "excel", "office", "file"],
    "[EXT_XLSX]": ["spreadsheet", "excel", "office", "file"],
    "[EXT_ZIP]": ["zip", "archive", "compressed", "file"],
    "[EXT_RAR]": ["rar", "archive", "compressed", "file"],
    "[EXT_7Z]": ["archive", "compressed", "file", "seven"],
    "[EXT_JSON]": ["json", "data", "format", "structured"],
    "[EXT_XML]": ["xml", "markup", "data", "structured"],
    "[EXT_INI]": ["configuration", "file", "settings", "ini"],
    # process name
    "[PROC]": ["process", "program", "executable", "running"],
    "[PROC_SYSTEM]": ["system", "process", "kernel", "windows"],
    "[PROC_FIREFOX]": ["firefox", "browser", "web", "mozilla"],
    "[PROC_CHROME]": ["chrome", "browser", "web", "google"],
    "[PROC_IEXPLORE]": ["explorer", "internet", "browser", "microsoft"],
    "[PROC_CMD]": ["command", "shell", "windows", "prompt"],
    "[PROC_POWERSHELL]": ["powershell", "shell", "windows", "scripting"],
    "[PROC_PWSH]": ["powershell", "shell", "core", "modern"],
    "[PROC_BASH]": ["bash", "shell", "linux", "unix"],
    "[PROC_EXPLORER]": ["explorer", "windows", "shell", "desktop"],
    "[PROC_MMC]": ["management", "console", "windows", "administrative"],
    "[PROC_TASKMGR]": ["task", "manager", "windows", "process"],
    "[PROC_LSASS]": ["security", "authority", "windows", "authentication"],
    "[PROC_SVCHOST]": ["service", "host", "windows", "process"],
    "[PROC_SERVICES]": ["services", "windows", "manager", "system"],
    "[PROC_WINLOGON]": ["logon", "windows", "session", "authentication"],
    "[PROC_CSRSS]": ["client", "server", "windows", "subsystem"],
    "[PROC_SMSS]": ["session", "manager", "windows", "subsystem"],
    "[PROC_NOTEPAD]": ["notepad", "text", "editor", "windows"],
    "[PROC_OUTLOOK]": ["outlook", "email", "office", "microsoft"],
    "[PROC_WORD]": ["word", "office", "document", "microsoft"],
    "[PROC_EXCEL]": ["excel", "spreadsheet", "office", "microsoft"],
    "[PROC_VSCODE]": ["code", "editor", "visual", "studio"],
    "[PROC_PAYLOAD]": ["payload", "malicious", "executable", "attack"],
    # network / port
    "[PORT]": ["port", "number", "network", "service"],
    "[PORT_HTTP]": ["port", "http", "web", "service"],
    "[PORT_HTTPS]": ["port", "https", "secure", "web"],
    "[PORT_DNS]": ["port", "dns", "name", "resolution"],
    "[PORT_FTP]": ["port", "ftp", "file", "transfer"],
    "[PORT_SSH]": ["port", "ssh", "secure", "shell"],
    "[PORT_RDP]": ["port", "remote", "desktop", "protocol"],
    "[PORT_SMB]": ["port", "smb", "share", "network"],
    "[PORT_HIGH]": ["port", "high", "ephemeral", "number"],
    "[PORT_LOW]": ["port", "low", "well", "known"],
    "[NET_HTTP]": ["http", "web", "protocol", "request"],
    "[NET_HTTPS]": ["https", "secure", "web", "protocol"],
    "[NET_DNS]": ["dns", "name", "resolution", "lookup"],
    "[NET_TCP]": ["tcp", "transport", "control", "protocol"],
    "[NET_UDP]": ["udp", "user", "datagram", "protocol"],
    "[NET_ICMP]": ["icmp", "ping", "internet", "control"],
    "[NET_C2]": ["command", "control", "server", "communication"],
    "[NET_LOCAL]": ["local", "internal", "network", "host"],
    "[NET_REMOTE]": ["remote", "external", "network", "host"],
    "[NET_LAN]": ["lan", "local", "area", "network"],
    # identity / account
    "[USER]": ["user", "account", "person", "name"],
    "[USER_DOMAIN]": ["domain", "user", "account", "windows"],
    "[SID]": ["security", "identifier", "windows", "user"],
    "[LOGON_ID]": ["logon", "session", "identifier", "windows"],
    "[HANDLE_ID]": ["handle", "identifier", "object", "system"],
    "[PROC_ID]": ["process", "identifier", "id", "system"],
    "[PARENT_PROC_ID]": ["parent", "process", "identifier", "id"],
    "[ACCESS_MASK]": ["access", "mask", "permissions", "rights"],
    "[ACCESS_REASON]": ["access", "reason", "granted", "permissions"],
    "[GUID]": ["unique", "identifier", "global", "guid"],
    "[REGISTRY_KEY]": ["registry", "key", "windows", "configuration"],
    "[SERVICE_NAME]": ["service", "name", "windows", "system"],
    # time
    "[TIMESTAMP]": ["timestamp", "time", "date", "moment"],
    "[TIME_DAY]": ["day", "date", "time", "calendar"],
    "[TIME_HOUR]": ["hour", "time", "clock", "moment"],
    "[TIME_RECENT]": ["recent", "time", "now", "current"],
    # event-id semantic
    "[EVENT_FILE_OPEN]": ["file", "open", "access", "read"],
    "[EVENT_FILE_READ]": ["file", "read", "access", "data"],
    "[EVENT_FILE_WRITE]": ["file", "write", "modify", "data"],
    "[EVENT_FILE_DELETE]": ["file", "delete", "remove", "destroy"],
    "[EVENT_FILE_CLOSE]": ["file", "close", "release", "handle"],
    "[EVENT_PROC_CREATE]": ["process", "create", "spawn", "start"],
    "[EVENT_PROC_EXIT]": ["process", "exit", "terminate", "end"],
    "[EVENT_PROC_FORK]": ["process", "fork", "child", "spawn"],
    "[EVENT_NET_CONNECT]": ["network", "connect", "establish", "session"],
    "[EVENT_NET_REQUEST]": ["network", "request", "send", "query"],
    "[EVENT_NET_SEND]": ["network", "send", "transmit", "data"],
    "[EVENT_NET_RECV]": ["network", "receive", "incoming", "data"],
    "[EVENT_HANDLE_OPEN]": ["handle", "open", "request", "object"],
    "[EVENT_HANDLE_CLOSE]": ["handle", "close", "release", "object"],
    # op / verb
    "[OP_AUDIT_SUCCESS]": ["audit", "success", "permitted", "allowed"],
    "[OP_AUDIT_FAIL]": ["audit", "failure", "denied", "blocked"],
    "[OP_LOGON]": ["logon", "login", "authenticate", "user"],
    "[OP_LOGOFF]": ["logoff", "logout", "session", "end"],
    "[OP_PRIVILEGE]": ["privilege", "rights", "elevated", "admin"],
    "[OP_OBJECT_ACCESS]": ["object", "access", "permissions", "audit"],
    "[OP_POLICY_CHANGE]": ["policy", "change", "configuration", "audit"],
    "[OP_QUERY]": ["query", "request", "lookup", "search"],
    "[OP_RESPONSE]": ["response", "answer", "reply", "result"],
    "[OP_DOWNLOAD]": ["download", "fetch", "retrieve", "receive"],
    "[OP_UPLOAD]": ["upload", "send", "transmit", "post"],
    "[OP_EXEC]": ["execute", "run", "launch", "start"],
}


def build_tokenizer(model_name: str = "bert-base-uncased") -> Any:
    """Load BERT tokenizer and add :data:`SPECIAL_TOKENS` as special tokens.

    Returns the augmented :class:`PreTrainedTokenizerBase`. The number of new
    tokens added equals ``len(SPECIAL_TOKENS)`` (the additions are recorded so
    you can immediately call :func:`init_special_token_embeddings` on the
    matching model).
    """
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    n_added = tokenizer.add_tokens(SPECIAL_TOKENS, special_tokens=True)
    if n_added != len(SPECIAL_TOKENS):
        # Some token already existed in vocab (rare for our bracketed names).
        # We don't fail; the caller can read .vocab_size to verify the final shape.
        pass
    return tokenizer


def init_special_token_embeddings(model: Any, tokenizer: Any) -> dict[str, str]:
    """Initialise newly added special token embeddings via :data:`SYNONYM_INIT`.

    For each ``[TOKEN]`` in :data:`SPECIAL_TOKENS` whose synonym list yields
    at least one in-vocab BERT token, we set the new token's embedding to the
    mean of those synonym embeddings.

    Args:
        model: A Transformers model whose ``get_input_embeddings()`` returns a
            ``nn.Embedding`` matrix that has already been ``resize_token_embeddings``-ed
            to the augmented tokenizer's vocab size.
        tokenizer: The tokenizer returned from :func:`build_tokenizer`.

    Returns:
        Mapping ``{token: status}`` where status is one of
        ``"initialised"`` / ``"random_unk_synonyms"`` (synonyms all ``[UNK]``,
        token kept as random init) / ``"missing_in_vocab"`` (token not added).
    """
    import torch

    embeddings = model.get_input_embeddings().weight.data
    unk_id = tokenizer.unk_token_id
    statuses: dict[str, str] = {}

    for tok in SPECIAL_TOKENS:
        tok_id = tokenizer.convert_tokens_to_ids(tok)
        if tok_id is None or tok_id == unk_id:
            statuses[tok] = "missing_in_vocab"
            continue
        synonyms = SYNONYM_INIT.get(tok, [])
        syn_ids = [tokenizer.convert_tokens_to_ids(s) for s in synonyms]
        syn_ids = [i for i in syn_ids if i is not None and i != unk_id]
        if not syn_ids:
            statuses[tok] = "random_unk_synonyms"
            continue
        with torch.no_grad():
            mean_embed = embeddings[torch.tensor(syn_ids)].mean(dim=0)
            embeddings[tok_id] = mean_embed
        statuses[tok] = "initialised"

    return statuses
