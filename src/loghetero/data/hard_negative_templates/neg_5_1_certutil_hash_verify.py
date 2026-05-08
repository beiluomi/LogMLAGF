"""T#5.1 benign_certutil_hash_verify_patch — Hard Negative Template.

Class: #5 Certutil LOLBin (per design propose §3.5 + §5.5)
NEG-ID: NEG-5.1
Cross-reference:
    docs/checkpoint_16_hard_negative_templates_design.md §3.5 minimal sketch
    + §5.5 schema readiness (vanilla, no workaround) + §4.1 boundary clarification

ATT&CK-like NEG-ID:
    NEG-5.1 — established as audit-trail anchor for stage 3 sanity check,
    Phase 11 ablation, and Phase 12 paper write-up. NEG-5.1 is the singular
    Certutil-LOLBin class hard-negative template (Class #5 has only 1
    template per Checkpoint 16 distribution propose §2 because sub-pattern
    is concentrated on hash-verify workflow).

Distinct lexical signature + boundary (verbatim from design propose §3.5
plus the explicit user caveat for §5 single-template lexical-anchor risk):

    Confound TTPs: T1140 deobfuscate-decode-files / T1105 ingress-tool-transfer.

    Boundary (design propose §3.5 verbatim):
        合法 IT certutil hash-verify **不**包含 (certutil.exe, NET_CONNECT, *)
        (无 -urlcache -split -f 远程下载语义) 加 **写出文件是 .sha256 hash 而非
        decoded payload** (无 .exe / .dll / .ps1 写出). BERT-only 看 certutil
        词频与 T1140 / T1105 share, 区分必须靠 network connection 加
        write-file-extension semantics.

    EXPLICIT caveat (controller mandate for NEG-5.1, Class #5 single-template
    lexical-anchor risk mitigation):

        lexical pattern 设计确保 hash verify scenario 与 T1105 ingress tool
        transfer 的 lexical signature 真正 distinct 不仅依赖 certutil binary
        name 即 T#5.1 设计需要包含 verifying-against-trusted-hash-list
        workflow + admin context (Group Policy / WSUS scheduled) anchor 而非
        仅 certutil.exe -hashfile 命令模式.

    Caveat operationalization in this module (admin-context anchors that
    ride on file-node-ID semantics + sequence-shape semantics, NOT on
    certutil-binary-name lexical):

      (a) Source MSU file under ``C:\\Patches\\`` path prefix indicating
          admin-managed patch staging area (WSUS / SCCM / Group Policy
          Software Installation deposit dir per Microsoft documented
          conventions, e.g. WSUSContent share or local patch cache).
      (b) Output ``.sha256`` hash file written to the SAME ``C:\\Patches\\``
          dir (adjacent to source MSU) — this is the "verifying-against-
          trusted-hash-list" workflow anchor: the hash is co-located with
          the trusted-list staging area NOT written to a temp / appdata
          location. T1105 ingress-tool-transfer would NOT co-locate hash
          adjacent to a managed patch dir.
      (c) Read of the trusted hash list ``C:\\Patches\\trusted_hashes.txt``
          BEFORE the hashfile compute — encodes the "verify-against-list"
          workflow pattern (admin reads the trusted-list to know what hash
          to expect). This trusted-list FILE_READ is the structural anchor
          that T1105 lacks (ingress-tool-transfer never reads a trusted
          hash list, it just downloads + writes payload).
      (d) NO NET_CONNECT in the sequence — anonymization-robust structural
          anchor (T1105 must connect outbound to fetch payload).
      (e) NO FILE_WRITE to .exe / .dll / .ps1 / decoded-payload extensions
          — anonymization-robust structural anchor (T1140 deobfuscate-
          decode-files must produce a decoded-payload file).

    These structural anchors mean: even if anonymization masks the strings
    "certutil.exe" and ".sha256" and "C:\\Patches\\", the **edge-type
    sequence** (USER_LOGON, FILE_READ trusted-list, FILE_READ source-msu,
    FILE_WRITE hash-output, PROCESS_EXIT — no NET_CONNECT, no PROCESS_CREATE
    child) remains structurally disjoint from T1105 (which contains
    NET_CONNECT + outbound NET_SEND_NETWORK + payload-file FILE_WRITE) and
    T1140 (which contains decoded-payload FILE_WRITE).

ALLOWED_EDGE_TRIPLES workaround reuse:
    NONE — vanilla schema. Per design §5.5, all triples used by T#5.1 are
    natively in ALLOWED_EDGE_TRIPLES (parsers/base.py lines 106-141):
      - (user, USER_LOGON, process)            line 135
      - (process, FILE_READ, file)             line 110
      - (process, FILE_WRITE, file)            line 111
      - (process, PROCESS_EXIT, process)       line 123 (self-loop)
    No workaround inventory entry triggered (Checkpoint 17 inventory
    remains at 4 entries, known_issues.md lines 437-440).

Sequence shape anchor + length range + distinguishing structural pattern:
    Sequence shape (ordered edge types):
        USER_LOGON
          → FILE_READ  (trusted hash list, anchor (c))
          → FILE_READ  (source MSU, anchor (a))
          → FILE_WRITE (output .sha256 hash, anchor (b))
          → PROCESS_EXIT
    Length range: events_min=5, events_max=5 (deterministic shape — single
        certutil hashfile invocation against single trusted-list entry
        produces fixed 5-event chain).
    Distinguishing structural pattern: hash-verify workflow comprises a
        FILE_READ trusted-list + FILE_READ source-MSU + FILE_WRITE hash-
        output triple anchored under the SAME C:\\Patches\\ admin-managed
        path prefix, with NO NET_CONNECT and NO downstream PROCESS_CREATE
        — structurally disjoint from T1105 (NET_CONNECT + payload write)
        and T1140 (decoded-payload write to non-hash extension).
"""

from __future__ import annotations

import random

from loghetero.data.hard_negative_templates.base import HardNegativeTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_CERTUTIL = "certutil.exe"
_PATCH_DIR = r"C:\Patches"
_TRUSTED_HASH_LIST = r"C:\Patches\trusted_hashes.txt"
_SOURCE_MSU = r"C:\Patches\KB5028166.msu"
_OUTPUT_HASH = r"C:\Patches\KB5028166.sha256"
_LOG_TYPE = "synthetic_hard_negative"
_SCENARIO = "synthetic_benign_admin"
_HOST = "h_neg_5_1"
_NEG_ID = "NEG-5.1"


class Neg51CertutilHashVerify(HardNegativeTemplate):
    """T#5.1 benign certutil hash-verify-against-trusted-list patch workflow."""

    def __init__(self) -> None:
        super().__init__(_NEG_ID, "benign_certutil_hash_verify_patch")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate a 5-event certutil hash-verify-against-trusted-list chain.

        Admin context anchors (caveat operationalization):
          - Source MSU under C:\\Patches\\ admin-managed staging path.
          - Trusted hash list FILE_READ BEFORE hashfile compute (verify-
            against-list workflow).
          - Output .sha256 file co-located in C:\\Patches\\ adjacent to MSU.
          - No NET_CONNECT (anonymization-robust vs T1105).
          - No decoded-payload FILE_WRITE (anonymization-robust vs T1140).
        """
        assert isinstance(rng, random.Random)
        iid = instance_id

        certutil = f"neg_{iid}_{_CERTUTIL}"
        trusted_list = f"neg_{iid}_{_TRUSTED_HASH_LIST}"
        source_msu = f"neg_{iid}_{_SOURCE_MSU}"
        output_hash = f"neg_{iid}_{_OUTPUT_HASH}"

        n_events = 5
        span = t_end_ns - t_start_ns
        base_step = span // n_events
        timestamps = [
            t_start_ns + k * base_step + rng.randint(0, max(1, base_step // 4))
            for k in range(n_events)
        ]
        timestamps.sort()

        attrs_base = {
            "neg_id": self.neg_id,
            "instance_id": iid,
            "label": 0,
        }

        def _ev(
            ts: int,
            subj: str,
            s_type: NodeType,
            op: EdgeType,
            obj: str,
            o_type: NodeType,
        ) -> Event:
            return Event(
                timestamp_ns=ts,
                subject=subj,
                subject_type=s_type,
                obj=obj,
                obj_type=o_type,
                operation=op.value,
                log_type=_LOG_TYPE,
                scenario_id=_SCENARIO,
                host_id=_HOST,
                attributes=dict(attrs_base),
            )

        return [
            # 1. Admin user logs on, launches certutil.exe (interactive admin
            #    session — per Group Policy / WSUS scheduled task context).
            _ev(
                timestamps[0],
                seed_subject,
                NodeType.user,
                EdgeType.USER_LOGON,
                certutil,
                NodeType.process,
            ),
            # 2. certutil.exe reads the trusted hash list (verify-against-list
            #    workflow anchor — admin loads expected hash before compute).
            _ev(
                timestamps[1],
                certutil,
                NodeType.process,
                EdgeType.FILE_READ,
                trusted_list,
                NodeType.file,
            ),
            # 3. certutil.exe reads the source MSU patch file (admin-managed
            #    C:\Patches\ staging dir anchor).
            _ev(
                timestamps[2],
                certutil,
                NodeType.process,
                EdgeType.FILE_READ,
                source_msu,
                NodeType.file,
            ),
            # 4. certutil.exe writes the .sha256 hash output (co-located with
            #    source under C:\Patches\, distinct from decoded-payload write).
            _ev(
                timestamps[3],
                certutil,
                NodeType.process,
                EdgeType.FILE_WRITE,
                output_hash,
                NodeType.file,
            ),
            # 5. certutil.exe exits cleanly (PROCESS_EXIT self-loop, no child
            #    process spawned — distinct from T1140 deobfuscation chains
            #    that often spawn decoded-payload).
            _ev(
                timestamps[4],
                certutil,
                NodeType.process,
                EdgeType.PROCESS_EXIT,
                certutil,
                NodeType.process,
            ),
        ]
