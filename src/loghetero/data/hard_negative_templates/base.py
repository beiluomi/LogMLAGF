"""Base class for Phase 5 / Checkpoint 16 hard negative benign templates.

These templates simulate **legitimate admin behavior** that lexically resembles
attack TTPs but is structurally / semantically distinct. They are NOT attack
templates. They emit ``Event`` objects with ``label=0`` (benign) so that the
fusion classifier can be evaluated against confounding admin behaviors that
share lexical surface with confound TTPs (e.g. Apache CGI perl child-process
chain vs T1190 webshell-write).

Key contrasts vs :class:`loghetero.data.attack_templates.base.AttackTemplate`:

- ``label=0`` (benign) NOT ``label=1`` (attack).
- No ``atk_`` node-ID prefix — these are benign admin behaviors not attack
  chains. Nodes use a ``neg_<iid>_<name>`` prefix to keep them disjoint from
  attack-template node IDs while clearly marking them as hard-negative
  generated.
- ``neg_id`` (NEG-ID) is the audit-trail anchor (e.g. ``"NEG-5.1"``)
  consistent with the Checkpoint 16 design doc per-class numbering.
- These templates are NOT registered in
  :data:`loghetero.data.attack_templates.ALL_TEMPLATES` to avoid being
  iterated during attack injection. They have their own
  :data:`loghetero.data.hard_negative_templates.ALL_HARD_NEGATIVE_TEMPLATES`.

Design source-of-truth: ``docs/checkpoint_16_hard_negative_templates_design.md``
(commit ``daeefa5``).

Cycle G (Stage 2 Step 2 Batch A) implements 7 templates spanning 4 classes:
    - Class #5 Certutil LOLBin: T#5.1 (NEG-5.1) hash_verify_patch
    - Class #2 Web Server CGI: T#2.1 (NEG-2.1) apache_cgi_perl,
      T#2.2 (NEG-2.2) nginx_php_fpm
    - Class #3 合法 Auth: T#3.1 (NEG-3.1) user_interactive_logon,
      T#3.2 (NEG-3.2) kerberos_service_ticket
    - Class #7 软件驱动安装: T#7.1 (NEG-7.1) driver_install_printer,
      T#7.2 (NEG-7.2) driver_install_av_engine
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from loghetero.data.parsers.base import Event


class HardNegativeTemplate(ABC):
    """Abstract base for synthetic hard-negative benign-behavior event generators.

    Concrete subclasses implement ``generate()`` returning a list of
    :class:`Event` objects whose attributes carry ``label=0`` and
    ``neg_id=<NEG-ID>``. Caller (Phase 5 hard-negative injector — to be wired
    in a later cycle) seeds via ``seed_subject`` (typically a benign user node
    name) and a timestamp window analogous to
    :class:`loghetero.data.attack_templates.base.AttackTemplate`.

    Args:
        neg_id: Hard-negative audit identifier, e.g. ``"NEG-5.1"``. Matches
            the per-class numbering in the Checkpoint 16 design doc §3.X.
        neg_name: Human-readable benign behavior name, e.g.
            ``"benign_certutil_hash_verify_patch"``.
    """

    def __init__(self, neg_id: str, neg_name: str) -> None:
        self.neg_id = neg_id
        self.neg_name = neg_name

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
        """Generate synthetic benign hard-negative events for one chain instance.

        Args:
            seed_subject: human-readable node ID of the seed benign-user node
                (e.g. ``"benign_admin_user"``).
            seed_subject_type: NodeType string of the seed (typically
                ``"user"``).
            t_start_ns: lower bound of injection timestamp window (ns).
            t_end_ns: upper bound of injection timestamp window (ns).
            rng: a ``random.Random`` instance for reproducible generation.
            instance_id: unique integer distinguishing multiple chain
                instances, used to prefix node IDs (``neg_<iid>_<name>``).

        Returns:
            List of :class:`Event` objects carrying ``label=0``,
            ``neg_id=<NEG-ID>``, ``instance_id=<iid>`` in ``attributes``.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(neg_id={self.neg_id!r})"
