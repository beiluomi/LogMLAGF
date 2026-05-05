"""Log-line cleaner: normalise concrete entities into special-token placeholders.

This module transforms raw log strings into a canonical form suitable for the
extended BERT tokenizer (``loghetero.data.tokenizer``). The output uses
placeholder tokens (e.g. ``[IP]``, ``[HASH_SHA256]``, ``[PATH_WIN_SYS32]``)
that the tokenizer recognises as single tokens with custom-initialised
embeddings.

The cleaning is line-by-line; multi-line context (Windows audit bodies) is the
parser's responsibility, not the cleaner's.

Patterns are ordered most-specific-first so that longer / more-specific
matches win against generic fallbacks (e.g. SHA-256 hex string is checked
before the generic [HEX] catch-all).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Pattern

# ---------------------------------------------------------------------------
# Regex patterns (compiled once at module import).
# ---------------------------------------------------------------------------

# Hashes (most specific first)
_RE_SHA256 = re.compile(r"\b[a-fA-F0-9]{64}\b")
_RE_SHA1 = re.compile(r"\b[a-fA-F0-9]{40}\b")
_RE_MD5 = re.compile(r"\b[a-fA-F0-9]{32}\b")

# UUID
_RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# IPs
_RE_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_RE_IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")

# URLs
_RE_URL_HTTPS = re.compile(r"\bhttps://[^\s'\"]+")
_RE_URL_HTTP = re.compile(r"\bhttp://[^\s'\"]+")

# Identity / numeric IDs
_RE_HEX_PREFIX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_RE_HEX_LONG = re.compile(r"\b[0-9a-fA-F]{16,}\b")  # generic long hex (post-hash check)
_RE_SID = re.compile(r"\bS-1-(?:5|0|1|2|3|4)-(?:\d+-?)+\b")

# Windows path prefixes (most specific first)
_RE_PATH_WIN_SYS32 = re.compile(r"[Cc]:\\Windows\\System32(?:\\\S*)?", re.IGNORECASE)
_RE_PATH_WIN_SYSWOW64 = re.compile(r"[Cc]:\\Windows\\SysWOW64(?:\\\S*)?", re.IGNORECASE)
_RE_PATH_WIN_PROGRAM_FILES_X86 = re.compile(
    r"[Cc]:\\Program Files \(x86\)(?:\\\S*)?", re.IGNORECASE
)
_RE_PATH_WIN_PROGRAM_FILES = re.compile(
    r"[Cc]:\\Program Files(?:\\\S*)?", re.IGNORECASE
)
_RE_PATH_WIN_PROGRAMDATA = re.compile(r"[Cc]:\\ProgramData(?:\\\S*)?", re.IGNORECASE)
_RE_PATH_WIN_USERS = re.compile(r"[Cc]:\\Users(?:\\\S*)?", re.IGNORECASE)
_RE_PATH_WIN_WINDOWS = re.compile(r"[Cc]:\\Windows(?:\\\S*)?", re.IGNORECASE)
_RE_PATH_WIN_TEMP = re.compile(r"[Cc]:\\(?:Temp|tmp)(?:\\\S*)?", re.IGNORECASE)
_RE_PATH_WIN_DRIVE = re.compile(r"\b[A-Za-z]:\\\S+")  # generic Windows drive path
_RE_PATH_WIN_UNC = re.compile(r"\\\\[\w.-]+\\\S+")     # \\server\share\path

# Linux path prefixes. We use (?<!\S) ("not preceded by non-whitespace") instead
# of \b because \b requires a word-character/non-word transition and "/" is not
# a word character -- so \b/etc/ would only match at start-of-string.
_RE_PATH_LINUX_BIN = re.compile(r"(?<!\S)/(?:usr/)?(?:s?bin|local/bin)/\S+")
_RE_PATH_LINUX_ETC = re.compile(r"(?<!\S)/etc/\S+")
_RE_PATH_LINUX_HOME = re.compile(r"(?<!\S)/home/\S+")
_RE_PATH_LINUX_TMP = re.compile(r"(?<!\S)/tmp/\S+")
_RE_PATH_LINUX_VAR = re.compile(r"(?<!\S)/var/\S+")
_RE_PATH_LINUX_PROC = re.compile(r"(?<!\S)/proc/\S+")

# Registry keys
_RE_REG_HKLM_RUN = re.compile(
    r"\bHKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run(?:\\\S*)?",
    re.IGNORECASE,
)
_RE_REG_HKLM = re.compile(r"\bHKLM\\\S+", re.IGNORECASE)
_RE_REG_HKCU = re.compile(r"\bHKCU\\\S+", re.IGNORECASE)

# Timestamps. UTC / Z suffix is optional and may be preceded by whitespace
# (firefox.txt writes "2018-11-03 02:44:43.813000 UTC" with a space before UTC).
_RE_TS_ISO = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*(?:Z|UTC))?"
)
_RE_TS_US_AMPM = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*[AP]M\b")

# Bare numbers / IDs (last fallback for hex)
_RE_PORT = re.compile(r"\bport[\s=:]+(\d+)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Substitution table (pattern, placeholder).
# Order matters: most-specific first.
# ---------------------------------------------------------------------------

_SUBSTITUTIONS: list[tuple[Pattern[str], str]] = [
    # 1. Timestamps (before any digit-bearing rule)
    (_RE_TS_ISO, "[TIMESTAMP]"),
    (_RE_TS_US_AMPM, "[TIMESTAMP]"),
    # 2. URLs (before IP/hex inside URL would match)
    (_RE_URL_HTTPS, "[URL_HTTPS]"),
    (_RE_URL_HTTP, "[URL_HTTP]"),
    # 3. UUID + SID + length-locked hashes (before generic hex)
    (_RE_UUID, "[GUID]"),
    (_RE_SID, "[SID]"),
    (_RE_SHA256, "[HASH_SHA256]"),
    (_RE_SHA1, "[HASH_SHA1]"),
    (_RE_MD5, "[HASH_MD5]"),
    # 4. IPs
    (_RE_IPV4, "[IP_V4]"),
    (_RE_IPV6, "[IP_V6]"),
    # 5. Registry keys (most specific first)
    (_RE_REG_HKLM_RUN, "[PATH_REGISTRY_RUN]"),
    (_RE_REG_HKLM, "[PATH_REGISTRY_HKLM]"),
    (_RE_REG_HKCU, "[PATH_REGISTRY_HKCU]"),
    # 6. Windows paths (most specific first; system32 before windows; pf-x86 before pf)
    (_RE_PATH_WIN_SYS32, "[PATH_WIN_SYS32]"),
    (_RE_PATH_WIN_SYSWOW64, "[PATH_WIN_SYSWOW64]"),
    (_RE_PATH_WIN_PROGRAM_FILES_X86, "[PATH_WIN_PROGRAM_FILES_X86]"),
    (_RE_PATH_WIN_PROGRAM_FILES, "[PATH_WIN_PROGRAM_FILES]"),
    (_RE_PATH_WIN_PROGRAMDATA, "[PATH_WIN_PROGRAMDATA]"),
    (_RE_PATH_WIN_USERS, "[PATH_WIN_USERS]"),
    (_RE_PATH_WIN_TEMP, "[PATH_WIN_TEMP]"),
    (_RE_PATH_WIN_WINDOWS, "[PATH_WIN_WINDOWS]"),
    (_RE_PATH_WIN_UNC, "[PATH_WIN_UNC]"),
    (_RE_PATH_WIN_DRIVE, "[PATH_WIN_DRIVE]"),
    # 7. Linux paths
    (_RE_PATH_LINUX_BIN, "[PATH_LINUX_BIN]"),
    (_RE_PATH_LINUX_ETC, "[PATH_LINUX_ETC]"),
    (_RE_PATH_LINUX_HOME, "[PATH_LINUX_HOME]"),
    (_RE_PATH_LINUX_TMP, "[PATH_LINUX_TMP]"),
    (_RE_PATH_LINUX_VAR, "[PATH_LINUX_VAR]"),
    (_RE_PATH_LINUX_PROC, "[PATH_LINUX_PROC]"),
    # 8. Generic hex / handle IDs (after hashes/UUID/IP have eaten the structured ones)
    (_RE_HEX_PREFIX, "[HEX]"),
    (_RE_HEX_LONG, "[HEX_LONG]"),
]


def clean(text: str) -> str:
    """Apply all substitutions and lowercase the result.

    Args:
        text: One log line (no newlines required).

    Returns:
        The cleaned, lowercased line. Placeholder tokens stay uppercase
        because the BERT tokenizer is told they are special tokens (no
        wordpiece splitting, no case-folding).
    """
    if not text:
        return text
    out = text
    # Apply structured-entity substitutions BEFORE lowercasing so case-sensitive
    # patterns (hex hashes, Windows paths) match cleanly.
    for pattern, placeholder in _SUBSTITUTIONS:
        out = pattern.sub(placeholder, out)
    # Now lowercase non-placeholder content. Placeholders stay uppercase since
    # they're square-bracketed; we only fold non-bracketed regions.
    return _lower_outside_brackets(out)


def clean_many(lines: Iterable[str]) -> list[str]:
    """Vectorised :func:`clean` for convenience."""
    return [clean(line) for line in lines]


_BRACKET_TOKEN_RE = re.compile(r"\[[A-Z0-9_]+\]")


def _lower_outside_brackets(s: str) -> str:
    """Lowercase everything except [SPECIAL_TOKEN] placeholders."""
    parts: list[str] = []
    last_end = 0
    for m in _BRACKET_TOKEN_RE.finditer(s):
        parts.append(s[last_end : m.start()].lower())
        parts.append(m.group(0))  # keep placeholder as-is
        last_end = m.end()
    parts.append(s[last_end:].lower())
    return "".join(parts)
