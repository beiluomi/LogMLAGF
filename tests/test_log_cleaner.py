"""Unit tests for the log-line cleaner (Phase 1.3)."""

from __future__ import annotations

from loghetero.data.log_cleaner import clean


class TestIPSubstitution:
    def test_ipv4_substituted(self) -> None:
        assert clean("connect to 192.168.1.1") == "connect to [IP_V4]"

    def test_multiple_ipv4(self) -> None:
        assert "[IP_V4]" in clean("from 10.0.0.1 to 10.0.0.2")
        assert clean("from 10.0.0.1 to 10.0.0.2").count("[IP_V4]") == 2

    def test_ipv6(self) -> None:
        out = clean("addr 2001:db8:85a3::8a2e:370:7334")
        assert "[IP_V6]" in out


class TestHashSubstitution:
    def test_sha256(self) -> None:
        h = "a" * 64
        assert clean(f"hash={h}") == "hash=[HASH_SHA256]"

    def test_sha1(self) -> None:
        h = "b" * 40
        assert clean(f"sha1 {h}") == "sha1 [HASH_SHA1]"

    def test_md5(self) -> None:
        h = "c" * 32
        assert clean(f"md5 {h}") == "md5 [HASH_MD5]"

    def test_sha256_wins_over_sha1_and_md5(self) -> None:
        # 64-char hex must match SHA256 first, not be split into smaller hashes.
        h = "f" * 64
        assert clean(h) == "[HASH_SHA256]"
        assert "[HASH_SHA1]" not in clean(h)
        assert "[HASH_MD5]" not in clean(h)


class TestPathSubstitution:
    def test_windows_system32(self) -> None:
        assert clean("C:\\Windows\\System32\\cmd.exe") == "[PATH_WIN_SYS32]"

    def test_windows_users(self) -> None:
        assert "[PATH_WIN_USERS]" in clean("C:\\Users\\bob\\file.txt")

    def test_windows_program_files_x86_more_specific_than_program_files(self) -> None:
        out = clean("C:\\Program Files (x86)\\Mozilla\\firefox.exe")
        assert "[PATH_WIN_PROGRAM_FILES_X86]" in out
        # Must not double-match as the generic program_files pattern
        assert "[PATH_WIN_PROGRAM_FILES]" not in out.replace("[PATH_WIN_PROGRAM_FILES_X86]", "")

    def test_linux_etc(self) -> None:
        assert "[PATH_LINUX_ETC]" in clean("read /etc/passwd")

    def test_registry_run_key(self) -> None:
        out = clean("HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\evil")
        assert "[PATH_REGISTRY_RUN]" in out


class TestUrlAndUuid:
    def test_https(self) -> None:
        assert clean("fetch https://example.com/path?q=1") == "fetch [URL_HTTPS]"

    def test_http(self) -> None:
        assert clean("fetch http://example.com/x") == "fetch [URL_HTTP]"

    def test_uuid(self) -> None:
        assert clean("id 550e8400-e29b-41d4-a716-446655440000") == "id [GUID]"


class TestTimestampSubstitution:
    def test_iso(self) -> None:
        assert clean("at 2018-11-03 02:44:43.813000 UTC") == "at [TIMESTAMP]"

    def test_us_ampm(self) -> None:
        assert clean("at 11/5/2018 8:31:56 PM") == "at [TIMESTAMP]"


class TestHexAndId:
    def test_hex_prefix(self) -> None:
        assert "[HEX]" in clean("handle 0x20e88")

    def test_long_hex_after_short_hashes(self) -> None:
        # Longer-than-32 hex but not 40/64 chars -> [HEX_LONG] (after hash patterns).
        # Actually with 33 chars it would NOT match SHA1 (40) or SHA256 (64) or MD5
        # (32), so it falls into HEX_LONG (≥16).
        h = "a" * 33
        assert "[HEX_LONG]" in clean(f"x {h}")


class TestPlaceholderPreservation:
    def test_lower_outside_brackets_only(self) -> None:
        # [PATH_WIN_SYS32] must keep upper case after lowercase pass.
        out = clean("Windows System32 contains C:\\Windows\\System32\\foo.exe")
        assert "[PATH_WIN_SYS32]" in out
        # Other text is lowercased
        assert "windows system32 contains" in out


class TestEmptyAndIdempotent:
    def test_empty_string(self) -> None:
        assert clean("") == ""

    def test_already_clean(self) -> None:
        # No structured entities -> just lowercased
        assert clean("Hello World") == "hello world"

    def test_clean_is_idempotent_on_placeholders(self) -> None:
        once = clean("ip 192.168.1.1 hash " + "f" * 64)
        twice = clean(once)
        assert once == twice
