"""统一 entry namespace 与 legacy 分裂探测（Task 10）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 7.4, 7.6, 7.7

## 新实例口径（本模块拥有）

child ``entry_id`` = ``pwi-{workbookInstanceId}:{sheetUid}``
—— 一份整册内唯一，跨 lane 不依赖 ``opaque-{wp_code}`` / ``opaque-{wp_id}``。

## Legacy 分裂（平台事实，不擅自合并）

``ENTRY_ID_NAMESPACE_SPLIT_NOTE``（``opaque_entry_gate``）记录：
* ``custom_cells`` → ``opaque-{wp_code}``
* ``offline_upload`` / ``wopi_put_file`` → ``opaque-{wp_id}``

``assert_sync_entry_namespace_unified()`` **fail-closed**：分裂仍在则抛
``NamespaceSplitError``，禁止宣称 SYNC-ENTRY-NAMESPACE 已关闭。

``assert_sync_multi_resolver_cleared()`` 读
``workpaper_sync_task72_pre_delete_eligibility.json`` 的 ``multi_resolver_count``，
非 0 则抛 ``MultiResolverDeferredError``。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.workpaper_sync.opaque_entry_gate import ENTRY_ID_NAMESPACE_SPLIT_NOTE
from app.services.workpaper_sync.writer_migration import opaque_entry_id

__all__ = [
    "unified_child_entry_id",
    "legacy_opaque_ids_for_wp",
    "NamespaceSplitError",
    "MultiResolverDeferredError",
    "NamespaceGateReport",
    "probe_namespace_gates",
    "assert_sync_entry_namespace_unified",
    "assert_sync_multi_resolver_cleared",
    "migration_plan_for_instance",
]

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MULTI_RESOLVER_ELIGIBILITY = (
    _REPO_ROOT / "backend" / "data" / "workpaper_sync_task72_pre_delete_eligibility.json"
)


class NamespaceSplitError(RuntimeError):
    """SYNC-ENTRY-NAMESPACE 尚未归零：wp_code / wp_id opaque 分裂仍在。"""


class MultiResolverDeferredError(RuntimeError):
    """SYNC-MULTI-RESOLVER 尚未归零：仍有 deferred OO router 行。"""


def unified_child_entry_id(*, workbook_instance_id: str, sheet_uid: str) -> str:
    wid = workbook_instance_id.strip()
    uid = sheet_uid.strip()
    if not wid or not uid:
        raise ValueError("workbook_instance_id / sheet_uid 不得为空")
    if ":" in uid:
        raise ValueError("sheet_uid 不得含冒号（保留作 entry 分隔符）")
    return f"pwi-{wid}:{uid}"[:256]


def legacy_opaque_ids_for_wp(*, wp_code: str, wp_id: Any) -> dict[str, str]:
    """展示同一 wp 在分裂口径下会生成的两个 opaque entry_id（只读探测）。"""
    import uuid as _uuid

    wid = wp_id if isinstance(wp_id, _uuid.UUID) else _uuid.UUID(str(wp_id))
    return {
        "custom_cells_lane": opaque_entry_id(wp_code=wp_code, wp_id=wid),
        "wopi_or_offline_lane": opaque_entry_id(wp_code=None, wp_id=wid),
    }


@dataclass(frozen=True, slots=True)
class NamespaceGateReport:
    entry_namespace_unified: bool
    multi_resolver_cleared: bool
    multi_resolver_count: int
    split_note: Mapping[str, Any]
    blockers: tuple[str, ...]


def probe_namespace_gates() -> NamespaceGateReport:
    """只读探测两道 SYNC gate；不修改任何生产状态。"""
    blockers: list[str] = []

    lanes_code = set(ENTRY_ID_NAMESPACE_SPLIT_NOTE.get("lanes_using_wp_code") or ())
    lanes_id = set(ENTRY_ID_NAMESPACE_SPLIT_NOTE.get("lanes_using_wp_id") or ())
    unified = not lanes_code or not lanes_id or lanes_code == lanes_id
    # 真实判据：登记表仍把 custom_cells 与 wopi/offline 分到不同 source
    if lanes_code and lanes_id and lanes_code.isdisjoint(lanes_id):
        unified = False
        blockers.append("SYNC-ENTRY-NAMESPACE: opaque wp_code/wp_id split still registered")

    count = -1
    cleared = False
    if _MULTI_RESOLVER_ELIGIBILITY.exists():
        data = json.loads(_MULTI_RESOLVER_ELIGIBILITY.read_text(encoding="utf-8"))
        live = data.get("multi_resolver_live") or {}
        count = int(
            live.get("multi_resolver_count", data.get("multi_resolver_count", -1))
        )
        cleared = bool(live.get("multi_resolver_is_zero")) if live else count == 0
        if not cleared:
            blockers.append(f"SYNC-MULTI-RESOLVER: multi_resolver_count={count}")
    else:
        blockers.append("SYNC-MULTI-RESOLVER: eligibility artifact missing")

    return NamespaceGateReport(
        entry_namespace_unified=unified,
        multi_resolver_cleared=cleared,
        multi_resolver_count=count,
        split_note=dict(ENTRY_ID_NAMESPACE_SPLIT_NOTE),
        blockers=tuple(blockers),
    )


def assert_sync_entry_namespace_unified() -> None:
    report = probe_namespace_gates()
    if not report.entry_namespace_unified:
        raise NamespaceSplitError(
            "SYNC-ENTRY-NAMESPACE 未关闭："
            + "; ".join(b for b in report.blockers if "ENTRY-NAMESPACE" in b)
        )


def assert_sync_multi_resolver_cleared() -> None:
    report = probe_namespace_gates()
    if not report.multi_resolver_cleared:
        raise MultiResolverDeferredError(
            "SYNC-MULTI-RESOLVER 未关闭："
            + "; ".join(b for b in report.blockers if "MULTI-RESOLVER" in b)
        )


def migration_plan_for_instance(
    *,
    workbook_instance_id: str,
    sheet_uid: str,
    wp_code: str,
    wp_id: Any,
) -> dict[str, Any]:
    """为新整册 child 生成「legacy opaque → 统一 pwi entry」映射计划（不执行写入）。"""
    unified = unified_child_entry_id(
        workbook_instance_id=workbook_instance_id,
        sheet_uid=sheet_uid,
    )
    legacy = legacy_opaque_ids_for_wp(wp_code=wp_code, wp_id=wp_id)
    return {
        "workbook_instance_id": workbook_instance_id,
        "sheet_uid": sheet_uid,
        "unified_entry_id": unified,
        "legacy_opaque_ids": legacy,
        "legacy_ids_diverge": legacy["custom_cells_lane"] != legacy["wopi_or_offline_lane"],
        "action": "map_both_legacy_ids_to_unified_on_cutover",
        "gate": probe_namespace_gates().blockers,
    }
