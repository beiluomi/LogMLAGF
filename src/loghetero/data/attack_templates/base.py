"""Base class for ATT&CK TTP synthetic attack event generators (Phase 4 / Checkpoint 14.5).

Every concrete TTP module inherits :class:`AttackTemplate` and implements
``generate()`` to produce a list of synthetic :class:`~loghetero.data.parsers.base.Event`
objects matching the TTP's behavioural chain.

Design decisions (locked per RFC-14.5 adjudications):
- RFC-14.5-9: 5 TTPs x 100 events = 500 attack events total.
- RFC-14.5-4 (shared-seed): the caller (SyntheticInjector) passes a seed node
  name and timestamp window so the TTP chain can anchor to a real benign node.
- RFC-14.5-10: hand-coded from public MITRE ATT&CK knowledge; no network fetch.

ALLOWED_EDGE_TRIPLES schema workaround (RFC-14.5-1):

    ALLOWED_EDGE_TRIPLES currently lacks registry edge types and
    process-as-file-like-handle edge types. T1547.001 borrows FILE_WRITE
    to \\Registry\\Machine... path and T1003.001 borrows HANDLE_REQUEST
    to lsass.exe file node as engineering compromises consistent with how
    EDR tools actually model these events. If Phase 5 RAPA full 20-template
    implementation discovers a need to extend ALLOWED_EDGE_TRIPLES with
    registry and process-handle edge types, handle that uniformly then.

    ALLOWED_EDGE_TRIPLES 当前不含 registry 边类型与 process-as-file-like-handle
    边类型, T1547.001 借用 FILE_WRITE 到 \\Registry\\Machine... 路径与 T1003.001
    借用 HANDLE_REQUEST 到 lsass.exe file node 是符合 EDR 工具实际建模习惯的工程妥
    协. Phase 5 RAPA 完整 20 个模板实施时如发现需要扩 ALLOWED_EDGE_TRIPLES 添加
    registry 与 process-handle 边类型再统一处理.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from loghetero.data.parsers.base import Event


class AttackTemplate(ABC):
    """Abstract base for synthetic ATT&CK TTP event generators.

    Subclasses implement ``generate()`` to return a list of :class:`Event`
    objects that model the TTP's behavioural chain.  The caller (SyntheticInjector)
    calls ``generate()`` repeatedly (with different seeds) to produce the
    configured number of attack events per TTP.

    Args:
        ttp_id: MITRE ATT&CK technique identifier, e.g. ``"T1059.001"``.
        ttp_name: human-readable technique name, e.g. ``"PowerShell"``.
    """

    def __init__(self, ttp_id: str, ttp_name: str) -> None:
        self.ttp_id = ttp_id
        self.ttp_name = ttp_name

    @abstractmethod
    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate synthetic attack events for one TTP chain instance.

        Args:
            seed_subject: human-readable node ID of the shared seed node
                (e.g. ``"victim_user"`` for a compromised user account).
            seed_subject_type: NodeType string of the seed
                (e.g. ``"user"`` or ``"process"``).
            t_start_ns: lower bound of the injection timestamp window (ns).
            t_end_ns: upper bound of the injection timestamp window (ns).
            rng: a ``random.Random`` instance for reproducible generation.
            instance_id: unique integer distinguishing multiple chain instances
                of the same TTP (used to make ``atk_``-prefixed node IDs unique).

        Returns:
            List of :class:`Event` objects.  Each event's ``subject``/``obj``
            follow the shared-seed design: the first event anchors on the seed
            node; subsequent events involve ``atk_``-prefixed new nodes.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(ttp_id={self.ttp_id!r})"
