# -*- coding: utf-8 -*-
"""模板骨架槽位复用 —— store 新行先落进「模板原样」的空闲骨架行，剩余的才插行。

spec: d2-skeleton-slot-reuse-and-writeback-speed · R1 / R2 · design §2~§4

═══ 为什么需要 ═══

instrumentation 给模板受管区的每一行预生成骨架身份 ``GTROW-{template}-{row:04d}``，而
``excel_materialize.plan_managed_writes`` 只按身份落位：store 行在 substrate 上找不到身份 ⇒
一律交给 ``_plan_row_shift`` 插在**最后一个有身份的行之后**。骨架行既不收敛也不被占用 ⇒
新企业首次切「在线编辑」时，模板的 12 行骨架原样留在第 13~24 行，业务数据从第 25 行开始
（重药安徽 D2-2 实测；``_archive/42`` design §7.5 第 3 条登记的未修项）。

═══ 判据（全部是合取，任一不满足就不复用）═══

1. provider 显式声明该表启用（:data:`REUSE_TABLES_ATTR`）—— 默认不启用，未声明的表逐字节不变；
2. 身份是模板骨架（``contracts.is_template_skeleton_identity``，与收敛 / roundtrip 豁免同一真源），
   且只在一行出现（重复身份属 anomaly，不碰）；
3. 该行可编辑格仍是模板原值（``SkeletonBaseline.carries_user_content`` 为假，比不了按用户内容算）；
4. 本次 projection 没有声明这个骨架身份（声明了就是 store 行，按身份照常更新）；
5. 行号在「最后一个已有物理行的 projection 声明行」**之后** —— 新行永不排到已有业务数据上方，
   store 行序不被打乱。存量底稿（数据在骨架之后）因此不会被就地改形。

被复用行的身份退役：本模块只算「哪些行、哪些身份」，写入与豁免由 ``excel_materialize`` /
``excel_extract`` 完成（见 design §3）。本模块是纯函数，不 import 引擎模块（避免成环）。
"""
from __future__ import annotations

import functools
import importlib
from dataclasses import dataclass, field
from typing import Any, Callable, Final, Mapping, Sequence

from app.services.workpaper_sync.contracts import (
    PROTECTED_MODES,
    is_template_skeleton_identity,
)
from app.services.workpaper_sync.models import SyncDomainError

__all__ = [
    "BASELINE_FN_ATTR",
    "NO_ADOPTION",
    "REUSE_TABLES_ATTR",
    "SkeletonSlotReuseDeclarationError",
    "SlotAdoption",
    "clear_reuse_declaration_cache",
    "plan_slot_adoption",
    "reuse_declaration",
    "skeleton_slot_candidates",
]

#: provider 模块上「启用槽位复用的受管表」声明（``tuple[str, ...]`` 的 table_key）。
REUSE_TABLES_ATTR: Final[str] = "SKELETON_SLOT_REUSE_TABLE_KEYS"

#: provider 模块上「模板骨架基线」零参函数名（R12 已有，返回 ``SkeletonBaseline``）。
BASELINE_FN_ATTR: Final[str] = "template_skeleton_baseline"


class SkeletonSlotReuseDeclarationError(SyncDomainError):
    """provider 声明了启用表，却给不出可调用的模板骨架基线（部署期缺陷，不静默退回）。"""

    error_code = "skeleton_slot_reuse_declaration_invalid"


@dataclass(frozen=True)
class SlotAdoption:
    """一次物化里被复用的骨架槽位。行号均为**位移前**口径。"""

    #: store 行身份 → 被它占用的行号
    adopted: Mapping[str, int] = field(default_factory=dict)
    #: 行号 → 该行退役的骨架身份
    retired: Mapping[int, str] = field(default_factory=dict)

    @property
    def retired_identities(self) -> tuple[str, ...]:
        """退役骨架身份，按行号升序（确定序，进计划与审计记录）。"""
        return tuple(self.retired[row] for row in sorted(self.retired))


NO_ADOPTION: Final[SlotAdoption] = SlotAdoption()


def _provider_module_path(contract_id: str) -> str | None:
    """契约 → provider 模块（交付台账是唯一映射；不在台账里的契约一律不启用）。"""
    from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    for row in DELIVERED_PER_ENTRY_CONTRACTS:
        if str(row.get("contract_id")) == contract_id:
            return str(row.get("provider_module") or "") or None
    return None


@functools.lru_cache(maxsize=None)
def reuse_declaration(contract_id: str) -> tuple[frozenset[str], Callable[[], Any] | None]:
    """``(启用的 table_key 集, 基线函数)``；未声明 ⇒ ``(frozenset(), None)``。

    :raises SkeletonSlotReuseDeclarationError: 声明了启用表却没有可调用的基线函数。
    """
    module_path = _provider_module_path(str(contract_id))
    if module_path is None:
        return frozenset(), None
    from app.services.workpaper_sync.adapters.registry import _ALLOWED_PROVIDER_MODULES

    if module_path not in _ALLOWED_PROVIDER_MODULES:
        # 与注册链同一纪律：台账是可编辑常量，不在白名单里的模块不得被动态 import。
        return frozenset(), None
    module = importlib.import_module(module_path)
    tables = frozenset(str(key) for key in (getattr(module, REUSE_TABLES_ATTR, ()) or ()))
    if not tables:
        return frozenset(), None
    baseline_fn = getattr(module, BASELINE_FN_ATTR, None)
    if not callable(baseline_fn):
        raise SkeletonSlotReuseDeclarationError(
            f"契约 {contract_id!r} 的 provider {module_path.rsplit('.', 1)[-1]!r} 声明了 "
            f"{REUSE_TABLES_ATTR}={sorted(tables)}，却没有可调用的 {BASELINE_FN_ATTR}() —— "
            "判不了「模板原样」就不能复用骨架行（会把用户在 OO 里填进模板空行的内容覆盖掉）"
        )
    return tables, baseline_fn


def clear_reuse_declaration_cache() -> None:
    """测试隔离 / 运维：清掉声明解析缓存。"""
    reuse_declaration.cache_clear()


def skeleton_slot_candidates(
    *,
    contract_id: str,
    table_key: str,
    scan: Any,
    substrate_projection: Any,
) -> dict[int, str]:
    """substrate 上「骨架身份 ∧ 只出现一次 ∧ 可编辑格仍是模板原值」的行（行号 → 身份）。

    未声明启用 / 没有骨架行 ⇒ 空 dict，且不读模板。
    """
    tables, baseline_fn = reuse_declaration(str(contract_id))
    if scan is None or baseline_fn is None or table_key not in tables:
        return {}
    rows_by_identity = getattr(scan, "rows_by_identity", {}) or {}
    skeleton_rows = {
        int(row): str(identity)
        for row, identity in scan.row_identity_by_row.items()
        if is_template_skeleton_identity(str(identity))
        and len(rows_by_identity.get(identity, (row,))) == 1
    }
    if not skeleton_rows:
        return {}
    identities = set(skeleton_rows.values())
    prefix = f"{table_key}/"
    fields: dict[str, list[tuple[str, Any]]] = {}
    for key, value in substrate_projection.values.items():
        stable_key = str(key)
        if not stable_key.startswith(prefix):
            continue
        rid = str(getattr(value, "row_key", None) or "")
        if rid not in identities or getattr(value, "mode", None) in PROTECTED_MODES:
            continue
        fields.setdefault(rid, []).append(
            (stable_key.rsplit("/", 1)[-1], getattr(value, "value", None))
        )
    baseline = baseline_fn()
    return {
        row: identity
        for row, identity in sorted(skeleton_rows.items())
        if not baseline.carries_user_content(
            table_key=table_key, row_identity=identity, fields=fields.get(identity, ())
        )
    }


def plan_slot_adoption(
    *,
    candidates: Mapping[int, str],
    physical: Mapping[int, str],
    wanted: Sequence[str],
    orphan: Sequence[str],
) -> SlotAdoption:
    """把 orphan（声明序）依次放进空闲槽位（行号升序）。放不下的留给插行。"""
    if not candidates or not orphan:
        return NO_ADOPTION
    wanted_set = {str(identity) for identity in wanted}
    last_declared = max(
        (row for row, identity in physical.items() if identity in wanted_set), default=0
    )
    free = [
        row
        for row in sorted(candidates)
        if row > last_declared
        and physical.get(row) == candidates[row]
        and candidates[row] not in wanted_set
    ]
    pairs = list(zip(orphan, free))
    if not pairs:
        return NO_ADOPTION
    return SlotAdoption(
        adopted={str(identity): row for identity, row in pairs},
        retired={row: candidates[row] for _identity, row in pairs},
    )
