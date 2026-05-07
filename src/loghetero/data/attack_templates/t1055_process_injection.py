"""T1055 - Process Injection (Phase 5 / Checkpoint 15 Cycle A).

ATT&CK reference: https://attack.mitre.org/techniques/T1055/

Behavioural chain (8 events, shared-seed APT design):

    1. user --> USER_LOGON --> process (injector.exe)  [seed = victim user]
    2. injector.exe --> PROCESS_CREATE --> injector_elevated.exe
    3. injector.exe --> HANDLE_REQUEST --> svchost_handle  [file node, see workaround]
    4. injector.exe --> FILE_WRITE --> shellcode.bin
    5. injector.exe --> FILE_READ --> shellcode.bin
    6. injector.exe --> HANDLE_DUPLICATE --> svchost_handle  [file node, see workaround]
    7. svchost_injected --> NET_CONNECT --> c2_net  [process node, see workaround]
    8. svchost_injected --> NET_SEND_NETWORK --> c2_net

Shared-seed design (RFC-14.5-4):
    Seed is the compromised ``user`` node (e.g. ``"victim_user"``). Step 1
    anchors USER_LOGON from that existing benign user node to a new
    ``atk_<iid>_injector.exe`` process node. All remaining nodes are
    ``atk_``-prefixed.

Schema workaround: svchost dual-node design (Checkpoint 17 schema workaround
inventory entry #1 -- docs/known_issues.md "Checkpoint 17 schema workaround
inventory tracking"):

    T1055 Process Injection semantically involves svchost.exe in two distinct
    roles: (a) target of HANDLE_REQUEST / HANDLE_DUPLICATE (steps 3 and 6),
    and (b) subject of NET_CONNECT / NET_SEND_NETWORK after injection (steps 7
    and 8). ALLOWED_EDGE_TRIPLES does NOT contain
    ``(process, HANDLE_REQUEST, process)`` nor
    ``(process, HANDLE_DUPLICATE, process)``.

    Workaround per RFC adjudication (inventory entry #1):
    - ``atk_{iid}_svchost_handle``    -- NodeType.file, used in steps 3 and 6
    - ``atk_{iid}_svchost_injected``  -- NodeType.process, used in steps 7 and 8

    Graph proximity (timestamp adjacency + same ``iid`` prefix) implicitly
    represents the injection relationship without an explicit type-change edge.
    Checkpoint 17 upgrade plan: add explicit
    ``(process, HANDLE_REQUEST, process)``,
    ``(process, HANDLE_DUPLICATE, process)``, and
    ``(process, HANDLE_CLOSE, process)`` triples to ALLOWED_EDGE_TRIPLES.

    ALLOWED_EDGE_TRIPLES 当前不含 ``(process, HANDLE_REQUEST, process)`` 与
    ``(process, HANDLE_DUPLICATE, process)`` 三元组. T1055 借用两个 distinct
    node ID ``svchost_handle`` (file node) + ``svchost_injected`` (process
    node) 隐式表示注入关系, 是符合 EDR 工具建模习惯的工程妥协 (EventID 4656 /
    4690 以文件句柄方式记录目标进程). Checkpoint 17 RFC 统一扩展 ALLOWED_EDGE_TRIPLES
    时处理.

    dangling injector_elevated 设计说明:
    injector_elevated 创建反映 PROCESS_CREATE 后 elevation 步骤但不作
    subsequent ops 的 subject 因为 svchost_injected 才是 post-injection active
    process. 这是 T1055 与 T1003.001 mimi_el-as-active-elevated-child 模式的真实
    语义差异不是建模疏漏, dangling 节点对 Phase 6-8 graph proximity learning 信号
    贡献 near-zero 但不破坏 attack 子图整体可学性.

Module-level constants pattern (Phase 5 new convention):

    T1055 uses module-level constants (e.g. ``_INJECTOR = "injector.exe"``) rather
    than class-level constants (e.g. ``self._INJECTOR``) to keep the inner
    ``_ev()`` closure inside ``generate()`` clean -- accessing module-level names
    avoids ``self.`` prefix inside the closure. This differs from the Phase 4
    exemplar T1003.001 which uses class-level constants. Phase 5 templates adopt
    module-level as the new convention; T1003.001 codebase consistency refactor is
    deferred to Phase 11+ codebase consistency agenda (not blocking Phase 5).
"""

from __future__ import annotations

import random

from loghetero.data.attack_templates.base import AttackTemplate
from loghetero.data.parsers.base import EdgeType, Event, NodeType

_INJECTOR = "injector.exe"
_INJECTOR_EL = "injector_elevated.exe"
_SVCHOST_HANDLE = "svchost_handle"   # file node -- schema workaround, see docstring
_SVCHOST_INJECTED = "svchost_injected"  # process node -- schema workaround, see docstring
_SHELLCODE = "shellcode.bin"
_C2_IP = "185.220.101.45"
_C2_PORT = "443"
_LOG_TYPE = "synthetic_atlas"
_SCENARIO = "synthetic_apt"
_HOST = "h2"


class T1055ProcessInjection(AttackTemplate):
    """Process injection chain (T1055) synthetic event generator."""

    def __init__(self) -> None:
        super().__init__("T1055", "Process Injection")

    def generate(
        self,
        seed_subject: str,
        seed_subject_type: str,
        t_start_ns: int,
        t_end_ns: int,
        rng: object,
        instance_id: int,
    ) -> list[Event]:
        """Generate an 8-event process injection chain."""
        assert isinstance(rng, random.Random)
        iid = instance_id

        # Seed: existing benign user node (shared-seed design, RFC-14.5-4).
        injector = f"atk_{iid}_{_INJECTOR}"
        injector_el = f"atk_{iid}_{_INJECTOR_EL}"
        # Dual-node svchost workaround (inventory entry #1):
        # svchost_handle is a FILE node for HANDLE_REQUEST / HANDLE_DUPLICATE.
        # svchost_injected is a PROCESS node for NET_CONNECT / NET_SEND_NETWORK.
        svchost_handle = f"atk_{iid}_{_SVCHOST_HANDLE}"
        svchost_injected = f"atk_{iid}_{_SVCHOST_INJECTED}"
        shellcode = f"atk_{iid}_{_SHELLCODE}"
        c2_net = f"atk_{iid}_{_C2_IP}:{_C2_PORT}"

        n_events = 8
        span = t_end_ns - t_start_ns
        base_step = span // n_events
        timestamps = [
            t_start_ns + k * base_step + rng.randint(0, max(1, base_step // 4))
            for k in range(n_events)
        ]
        timestamps.sort()

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
                attributes={"ttp": self.ttp_id, "instance_id": iid, "label": 1},
            )

        return [
            # 1. Attacker-controlled process logon; seed_subject is the victim user.
            _ev(timestamps[0], seed_subject, NodeType.user, EdgeType.USER_LOGON, injector, NodeType.process),
            # 2. injector.exe spawns an elevated child.
            _ev(timestamps[1], injector, NodeType.process, EdgeType.PROCESS_CREATE, injector_el, NodeType.process),
            # 3. injector.exe requests a handle to svchost (file node, schema workaround).
            _ev(timestamps[2], injector, NodeType.process, EdgeType.HANDLE_REQUEST, svchost_handle, NodeType.file),
            # 4. injector.exe writes shellcode to disk.
            _ev(timestamps[3], injector, NodeType.process, EdgeType.FILE_WRITE, shellcode, NodeType.file),
            # 5. injector.exe reads shellcode back into memory.
            _ev(timestamps[4], injector, NodeType.process, EdgeType.FILE_READ, shellcode, NodeType.file),
            # 6. injector.exe duplicates the svchost handle (file node, schema workaround).
            _ev(timestamps[5], injector, NodeType.process, EdgeType.HANDLE_DUPLICATE, svchost_handle, NodeType.file),
            # 7. Injected svchost (process node, distinct from svchost_handle) connects to C2.
            _ev(timestamps[6], svchost_injected, NodeType.process, EdgeType.NET_CONNECT, c2_net, NodeType.network),
            # 8. Injected svchost sends data to C2.
            _ev(timestamps[7], svchost_injected, NodeType.process, EdgeType.NET_SEND_NETWORK, c2_net, NodeType.network),
        ]
