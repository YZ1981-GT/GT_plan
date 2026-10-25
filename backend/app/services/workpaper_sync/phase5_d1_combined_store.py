# -*- coding: utf-8 -*-
"""D1 的**多 store item 组合投影与回写分派**（`phase5_d1_notes_receivable` 的伴生模块）。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 25~29

═══ 为什么单独一个模块 ═══

「把 12 张受管 sheet / 18 张行表的 store 载荷合成**一个** Projection，再把反读回来的
Projection 分派回各自 store item」是一个独立概念，与 entry 模块剩下的职责
（常量声明 / 契约装配 / instrumentation 声明 / 发布编排）正交。

抽出来同时让宿主模块回落到行数门基线之下 —— 门的首选处置就是抽伴生模块，
而不是抬 whitelist 基线（那只是记账，欠账还在）。

真源在本模块；`phase5_d1_notes_receivable` 保留同名薄转发，
所以 registry、判据与外部调用方的引用路径**一个都不用改**。

🔴 本模块**按 spec 泛化**，不是逐 item 手写清单：遍历伴生模块
`phase5_d1_expansion.managed_row_table_specs()`，`rows` 形态走框架层行表引擎、
`dict` 形态走 D1-7 专用门面、静态受管区走各自模块的专用函数。
新接一张 sheet 不需要改本模块 —— 这正是行表引擎要的收敛。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.workpaper_sync.contracts import SyncContract


def _store_payload_error() -> type[Exception]:
    """entry 模块定义的 `StorePayloadError`（带 `error_code`，是真源）。

    🔴 **必须复用同一个类，不得在本模块另定义一份**：判据与调用方都按
    `ENTRY.StorePayloadError` 捕获它，两边各一份会让
    `pytest.raises(ENTRY.StorePayloadError)` 捕不到本模块抛出的那个 ——
    抽模块首版就是这么红了 2 条。
    函数内 import 是为了避开 entry ↔ 本模块的循环导入。
    """
    from app.services.workpaper_sync.phase5_d1_notes_receivable import (
        StorePayloadError,
    )

    return StorePayloadError

__all__ = [
    "build_combined_store_projection",
    "merge_projection_into_all_d1_stores",
]


def build_combined_store_projection(
    payloads: Mapping[str, str | bytes | Sequence[Any]],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """把**全部**受管 store item 的载荷合成一个 Projection（materialize overlay 用）。

    🔴 与 D4 的同名函数不同型：D4 是逐 item 手写清单（历史演化），本家**按 spec 泛化** ——
    遍历伴生模块的 `managed_row_table_specs()`，`rows` 形态走框架层引擎、`dict` 形态走
    D1-7 专用门面。新接一张 sheet 不需要改本函数（这正是行表引擎要的收敛）。

    🔴 **三条通路**（对应契约里三类 table）：
    * `rows` 动态区 → 框架层行表引擎 `build_store_projection`；
    * `dict` 动态区（D1-7 备查簿 `{bankRows, commercialRows}`）→ 专用门面；
    * **静态受管区** → 各自模块的专用投影函数（行表引擎会拒静态 spec，
      `store_row_identity()` 对 `row_identity_key == ""` 直接抛）。
    """
    from app.services.workpaper_sync import phase5_d1_07_memo as _d107
    from app.services.workpaper_sync import phase5_d1_expansion as _exp
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        StoreKind,
        build_store_projection as _engine_build,
    )

    values: dict[str, Any] = {}
    row_keys: dict[str, tuple[str, ...]] = {}
    dict_item_ids: set[str] = set()

    for spec in _exp.managed_row_table_specs():
        if spec.store_kind is StoreKind.dict:
            # dict 形态（D1-7 备查簿 `{bankRows, commercialRows}`）由专用门面整体投影，
            # 两个区共用同一 store item ⇒ 只跑一次。
            dict_item_ids.add(spec.store_item_id)
            continue
        raw = payloads.get(spec.store_item_id, spec.empty_payload)
        try:
            proj = _engine_build(spec, raw, contract=contract, limits=limits)
        except RowTableStorePayloadError as exc:
            # 保持 4xx（同 build_store_projection 的转译约定），并点明是哪个 item。
            raise _store_payload_error()(f"{spec.store_item_id}: {exc}") from exc
        values.update(proj.values)
        row_keys.update(dict(proj.row_keys))

    for item_id in sorted(dict_item_ids):
        try:
            proj = _d107.build_d17_store_projection(
                payloads.get(item_id, "{}"), contract=contract, limits=limits
            )
        except _d107.D17StorePayloadError as exc:
            raise _store_payload_error()(f"{item_id}: {exc}") from exc
        values.update(proj.values)
        row_keys.update(dict(proj.row_keys))

    # ── 静态受管区（第三条通路）────────────────────────────────────────
    # 🔴 静态受管区的 `(store_item_id, build_fn)` 清单留在 entry 模块（它与那边的
    #    灰度开关同源同生灭）。函数内 import 是为了避开 entry ↔ 本模块的循环导入。
    from app.services.workpaper_sync.phase5_d1_notes_receivable import (
        _static_region_projection_builders,
    )

    for item_id, build_fn in _static_region_projection_builders():
        try:
            proj = build_fn(payloads.get(item_id, "[]"), contract=contract)
        except ValueError as exc:
            raise _store_payload_error()(f"{item_id}: {exc}") from exc
        values.update(proj.values)
        row_keys.update(dict(proj.row_keys))

    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


def merge_projection_into_all_d1_stores(
    *,
    projection: Any,
    base_by_item: Mapping[str, Any],
) -> dict[str, tuple[list[dict[str, Any]], int, int, set[str]]]:
    """回方向整体镜像：把 merged projection 按 store item 分别合回各自的行数组。

    由 `store_mirror._mirror_dual_stores` 经 `plan.merge_all_fn` 按名调用
    （注册表 `dual_store_fn` 非空才会走那条多 item 路径 —— 本 entry 2026-09-28 起注册）。

    🔴 与 D4 的 `merge_projection_into_all_d4_stores` 不同型：D4 是逐 item 手写清单，
    本家**按 spec 泛化** —— 遍历伴生模块 `managed_row_table_specs()` 的 `rows` 形态 spec，
    逐个调框架层 `merge_projection_into_store_rows(spec, ...)`。接一张新 sheet 不改本函数。

    🔴 **不返回** `StoreKind.dict`（D1-7 备查簿）—— 它走注册表 `dedicated_items` 的
    `merge_d17_from_projection`（`_mirror_dedicated_dict_stores` 负责），
    在这里返回会与它重复写库。

    🔴 **静态受管区**（D1-4 第三区）走自己的 merge 函数（行表引擎会拒静态 spec），
    但**照常返回** —— 它有契约 table、投影里有它的 stable key，与动态区同样需要回写。

    `base_by_item` 的值可能是 list（rows-store）或 dict（调用方对 dict-store 的透传），
    本函数只接受 list；非 list 一律当空基线（与 D4 同款容差，不抛 —— 抛会让整个回写失败）。
    """
    from app.services.workpaper_sync import phase5_d1_expansion as _exp
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        StoreKind,
        merge_projection_into_store_rows as _engine_merge,
    )

    out: dict[str, tuple[list[dict[str, Any]], int, int, set[str]]] = {}
    for spec in _exp.managed_row_table_specs():
        item_id = spec.store_item_id
        if not item_id or spec.store_kind is StoreKind.dict:
            continue
        base = base_by_item.get(item_id)
        base_rows = list(base) if isinstance(base, list) else []
        out[item_id] = _engine_merge(
            spec,
            projection=_projection_slice_for(projection, spec.table_key),
            base_rows=base_rows,
        )

    # ── 静态受管区（专用 merge，签名与框架层一致）────────────────────────
    from app.services.workpaper_sync import phase5_d1_04_bad_debt as _d104

    # 与出方向同源：静态受管区的 merge handler 清单也留在 entry 模块。
    from app.services.workpaper_sync.phase5_d1_notes_receivable import (
        _static_region_merge_handlers,
    )

    for item_id, merge_fn in _static_region_merge_handlers():
        base = base_by_item.get(item_id)
        base_rows = list(base) if isinstance(base, list) else []
        out[item_id] = merge_fn(
            projection=_projection_slice_for(
                projection, _d104.SPEC_D104_NOTETYPE.table_key
            ),
            base_rows=base_rows,
        )
    return out


def _projection_slice_for(projection: Any, table_key: str) -> Any:
    """取 merged projection 里**只属于该受管区**的切片。

    🔴 **必须切**，不能把整份 combined projection 直接喂给框架层
    `merge_projection_into_store_rows` —— 它遍历 `projection.stable_keys()` 并按
    `row_key` 建行，只用 `field_to_path.get(field_id)` 做过滤。而**不同区的列名会重名**
    （D1-2 与 D1-8 都有 `note_type`/`bill_amount` 等）⇒ 过滤挡不住，别区的行会被合进本区数组。

    实测（2026-09-28，本文件配套判据 `test_merge_all_covers_every_rows_form_item` 抓到）：
    不切片时 `D1-cat-rows` 合出 **16 行**（把 endorse/writeoff/pledge… 各区的合成行全吞了），
    而它只该有 2 行。框架层那个函数的隐含前提是「projection 只含本区数据」——单区 provider
    成立，多区 combined 不成立。D4 的同名 merge_all 也是「按 table 前缀分别 merge」。

    切片只按 `stable_key` 的首段（`{table_key}/…`）过滤，不改框架层（那会牵动全部 adapter）。
    """
    from app.services.workpaper_sync.adapters.base import Projection

    prefix = f"{table_key}/"
    return Projection(
        contract_id=projection.contract_id,
        semantic_version=projection.semantic_version,
        document_type=projection.document_type,
        values={
            k: v for k, v in dict(projection.values).items() if str(k).startswith(prefix)
        },
        row_keys={table_key: tuple(dict(projection.row_keys).get(table_key, ()))},
    )
