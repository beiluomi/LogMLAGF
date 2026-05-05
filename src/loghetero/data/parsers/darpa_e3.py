"""DARPA TC E3 CDM parser skeleton (Phase 1.2 fixture-validated).

The E3 dataset itself is gated by manual application; this module ships the
parser SHELL so the rest of Phase 1 can compile and unit-test against
hand-crafted CDM JSON fixtures. Once the project owner finishes the data
request, ``parse_file`` will already work against the real ``ta1-*.json``
files.

The CDM type -> LogHetero NodeType mapping is the canonical source of truth
required by ``docs/design_decisions.md`` decision 5. It lives at module top as
``_CDM_NODE_TYPE_MAP`` and MUST NOT be duplicated in downstream code.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from .base import (
    EdgeType,
    Event,
    NodeType,
    ParseStats,
    Parser,
)

# ---------------------------------------------------------------------------
# CDM type -> LogHetero NodeType mapping (decision 5).
# DO NOT duplicate this dict in downstream code; import it from this module.
# ---------------------------------------------------------------------------

_CDM_NODE_TYPE_MAP: dict[str, NodeType] = {
    "Subject": NodeType.process,
    "Principal": NodeType.user,
    "FileObject": NodeType.file,
    "UnnamedPipeObject": NodeType.file,  # decision 5: align with KAIROS / MAGIC / FLASH
    "MemoryObject": NodeType.file,        # decision 5: shared memory as file
    "SrcSinkObject": NodeType.socket,    # decision 5: SrcSinkObject footnote
    "NetFlowObject": NodeType.network,
}


# CDM EventType -> EdgeType mapping. Send / recv depend on whether the
# predicateObject resolves to a socket (SrcSinkObject) or network (NetFlow);
# that disambiguation happens at edge-emit time in :func:`_resolve_edge_type`
# below. Unknown CDM event types fall to ``EdgeType.UNKNOWN``.
_CDM_SIMPLE_EVENT_MAP: dict[str, EdgeType] = {
    "EVENT_OPEN": EdgeType.FILE_OPEN,
    "EVENT_CLOSE": EdgeType.FILE_CLOSE,
    "EVENT_READ": EdgeType.FILE_READ,
    "EVENT_WRITE": EdgeType.FILE_WRITE,
    "EVENT_EXECUTE": EdgeType.PROCESS_EXEC,
    "EVENT_FORK": EdgeType.PROCESS_FORK,
    "EVENT_EXIT": EdgeType.PROCESS_EXIT,
    "EVENT_CONNECT": EdgeType.NET_CONNECT,
    "EVENT_ACCEPT": EdgeType.NET_ACCEPT,
    "EVENT_UNLINK": EdgeType.FILE_DELETE,
    "EVENT_RENAME": EdgeType.FILE_RENAME,
}


def _resolve_edge_type(event_type: str, obj_node_type: NodeType) -> EdgeType:
    """Map a CDM (event_type, obj_node_type) pair to a unique :class:`EdgeType`.

    Send/recv events fan out by destination type to keep
    ``ALLOWED_EDGE_TRIPLES`` unambiguous (Checkpoint 3 invariant).
    """
    if event_type == "EVENT_SENDTO":
        return EdgeType.NET_SEND_SOCKET if obj_node_type is NodeType.socket else EdgeType.NET_SEND_NETWORK
    if event_type == "EVENT_RECVFROM":
        return EdgeType.NET_RECV_SOCKET if obj_node_type is NodeType.socket else EdgeType.NET_RECV_NETWORK
    return _CDM_SIMPLE_EVENT_MAP.get(event_type, EdgeType.UNKNOWN)


def cdm_node_type(cdm_type: str) -> NodeType:
    """Map a CDM type name (e.g. ``"FileObject"``) to a :class:`NodeType`.

    Unknown types fall back to ``NodeType.file`` per decision 5's "未列出的
    边缘类型 → file (兜底)" rule. Callers should record the raw CDM type in
    ``Event.attributes["raw_cdm_type"]`` to support Phase 8 baseline-consistency
    audits.
    """
    return _CDM_NODE_TYPE_MAP.get(cdm_type, NodeType.file)


class CDMParser(Parser):
    """Parse CDM JSON-Lines records into :class:`Event`.

    DARPA TC E3 ships CDM data as Avro originally; community converters dump it
    as one JSON object per line. This parser accepts that JSONL form. Each
    line is one CDM record dict with shape::

        {
          "datum": {
            "com.bbn.tc.schema.avro.cdm18.Event": {
              "uuid": "...",
              "type": "EVENT_OPEN",
              "subject": {"com.bbn.tc.schema.avro.cdm18.UUID": "..."},
              "predicateObject": {"com.bbn.tc.schema.avro.cdm18.UUID": "..."},
              "timestampNanos": 1523344567890123456,
              ...
            }
          }
        }

    or for an object record::

        {
          "datum": {
            "com.bbn.tc.schema.avro.cdm18.FileObject": {
              "baseObject": {"hostId": "...", ...},
              "uuid": "...",
              ...
            }
          }
        }

    Phase 1.2 emits an :class:`Event` only for CDM ``Event`` records. Object
    records are kept as a UUID -> (cdm_type, attributes) side-table so that
    Event records can resolve subject/object via UUID lookup. For simplicity
    in this skeleton, the object table is built on the fly from the same
    file; production may want a multi-pass pipeline.
    """

    LOG_TYPE: ClassVar[str] = "darpa.cdm"

    # CDM datum keys are fully-qualified class names; we pattern-match on the
    # short form (last path component) for portability across cdm17/18/19/20.
    _EVENT_KEY_SUFFIX = ".Event"

    def parse_file(
        self,
        path: Path,
        *,
        scenario_id: str,
        host_id: str,
        stats: ParseStats | None = None,
    ) -> Iterator[Event]:
        if stats is None:
            stats = ParseStats()

        # First pass: build UUID -> (cdm_type, host_id) side-table so Event
        # records can resolve their subject / object UUIDs to a node type.
        # For real E3 data this table is large but bounded; for the fixture it
        # is trivial.
        uuid_index: dict[str, tuple[str, str]] = {}
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                obj = self._safe_json_loads(line)
                if obj is None:
                    continue
                short_type, payload = self._extract_short_type(obj)
                if short_type is None or payload is None:
                    continue
                if short_type == "Event":
                    continue
                uuid = payload.get("uuid")
                base_obj = payload.get("baseObject") or {}
                # Per CDM schema, hostId may live on baseObject; if absent we
                # fall back to the parser's caller-provided host_id.
                if uuid:
                    uuid_index[uuid] = (short_type, base_obj.get("hostId") or host_id)

        # Second pass: emit Events with subject/object types resolved.
        with path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                stripped = line.rstrip("\r\n")
                if not stripped.strip():
                    stats.record_skipped()
                    continue
                obj = self._safe_json_loads(stripped)
                if obj is None:
                    stats.record_failure(line_num, stripped, "invalid JSON")
                    continue
                short_type, payload = self._extract_short_type(obj)
                if short_type is None or payload is None:
                    stats.record_failure(line_num, stripped, "no recognised CDM datum")
                    continue
                if short_type != "Event":
                    stats.record_skipped()
                    continue

                ts_ns = payload.get("timestampNanos")
                if not isinstance(ts_ns, int):
                    stats.record_failure(line_num, stripped, "missing timestampNanos")
                    continue

                event_type = payload.get("type") or "EVENT_UNKNOWN"

                subj_uuid = self._unwrap_uuid(payload.get("subject"))
                obj_uuid = self._unwrap_uuid(payload.get("predicateObject"))
                if subj_uuid is None or obj_uuid is None:
                    stats.record_skipped()
                    continue

                subj_cdm_type, _ = uuid_index.get(subj_uuid, ("Subject", host_id))
                obj_cdm_type, _ = uuid_index.get(obj_uuid, ("FileObject", host_id))
                operation = _resolve_edge_type(event_type, cdm_node_type(obj_cdm_type))

                stats.record_success()
                yield Event(
                    timestamp_ns=ts_ns,
                    subject=subj_uuid,
                    subject_type=cdm_node_type(subj_cdm_type),
                    obj=obj_uuid,
                    obj_type=cdm_node_type(obj_cdm_type),
                    operation=operation,
                    log_type=self.LOG_TYPE,
                    scenario_id=scenario_id,
                    host_id=host_id,
                    attributes={
                        "event_type": event_type,
                        "subj_cdm_type": subj_cdm_type,
                        "obj_cdm_type": obj_cdm_type,
                        "subj_uuid": subj_uuid,
                        "obj_uuid": obj_uuid,
                    },
                )

    @staticmethod
    def _safe_json_loads(line: str) -> dict | None:
        try:
            return json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None

    @classmethod
    def _extract_short_type(cls, record: dict) -> tuple[str | None, dict | None]:
        """Return (short cdm type name, payload dict) or (None, None)."""
        datum = record.get("datum")
        if not isinstance(datum, dict) or not datum:
            return None, None
        # datum is a single-key dict whose key is the fully-qualified type
        full_key = next(iter(datum))
        payload = datum[full_key]
        if not isinstance(payload, dict):
            return None, None
        short = full_key.split(".")[-1]
        return short, payload

    @staticmethod
    def _unwrap_uuid(field: object) -> str | None:
        """CDM wraps UUIDs as ``{"com.bbn.tc.schema.avro.cdm*.UUID": "..."}``."""
        if isinstance(field, str):
            return field
        if isinstance(field, dict) and field:
            inner = next(iter(field.values()))
            return inner if isinstance(inner, str) else None
        return None
