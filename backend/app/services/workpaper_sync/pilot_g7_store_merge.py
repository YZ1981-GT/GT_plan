# -*- coding: utf-8 -*-
"""G7 国企披露 Tab 的 store 合并门面 —— `pilot_g7_two_level_dynamic` 的伴生模块。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 13 的缺陷修复 · Requirements 3.1 / 3.4

═══ 为什么抽成伴生模块 ═══

`pilot_g7_two_level_dynamic` 已 2450 行（whitelist 基线），仓库的文件行数门禁措辞是
「**打磨应让文件变小不变大**」⇒ 把 merge 门面追加进去会顶穿 +5% 阈值。
边界：主模块持有身份常量 / 契约装配 / 投影；本模块只持有**回方向合并**。

═══ 修的是什么缺陷 ═══

`oo_to_html` 的回写分派对 `g7.soe_subsidiary_disclosure` 一直写着
`bridge.merge_projection_into_store_state`，而主模块**从未定义过它**
（`git show HEAD:` 逐个确认，非改造引入）⇒ G7 走到 store 镜像那步就是 `AttributeError` →
opaque 500。缺陷能长期活着是因为那条路径没人真走到过。

═══ 为什么是 `state` 而不是 `rows`（三家 store 形态的第三种）═══

G7 的 store 是**一个对象**而非行数组：
``{version: 2, tables: {tableId: [{id: metric, values: {renderKey: v}}]}, entitySlots: {...}}``
⇒ 合并的单位是「矩阵格」而不是「行」。
"""
from __future__ import annotations

from typing import Any, Mapping

__all__ = ["merge_projection_into_store_state"]


def merge_projection_into_store_state(
    *,
    projection: Any,
    base_state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], int, int]:
    """把已 extract 的 projection 合进国企披露 Tab 的 state 对象（不读盘）。

    必须保证三件事：
      * **保留** `version` / `entitySlots` / 其他 table（本函数只动受管矩阵表）
      * **不新建** metric 行（metric 集合由前端渲染层与契约共同冻结；OO 侧不得凭空造指标行）
      * **不新建** 实体列（`entitySlots` 是实体真源，OO 侧改不了公司清单）

    🔴 后两条是 fail-closed 而非宽容：OO 里多出来的格若被当成新 metric/新实体写回，
    会让前端 `applySavedState` 读到契约外的键 —— 那正是
    `UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED` 登记的历史键搁浅形态（改造前的
    `c{n}Current` 至今读不到）。命中即跳过并原样保留 store，不静默造结构。

    :returns: `(merged_state, applied, visited)` —— 与 `oo_to_html` 的 state 分支签名一致
        （它按 `applied <= 0 and base_state` 决定是否跳过写库）。
    """
    from app.services.workpaper_sync.pilot_g7_two_level_dynamic import (
        MATRIX_TABLE_KEY,
        RENDER_MATRIX_TABLE_ID,
        RENDER_SLOT,
        STORE_STATE_VERSION,
        dynamic_column_keys_for_entities,
        render_column_key_for_seq,
    )

    state: dict[str, Any] = dict(base_state or {})
    state.setdefault("version", STORE_STATE_VERSION)
    tables_raw = state.get("tables")
    tables: dict[str, Any] = dict(tables_raw) if isinstance(tables_raw, Mapping) else {}

    rows_raw = tables.get(RENDER_MATRIX_TABLE_ID)
    rows: list[dict[str, Any]] = [
        dict(r) for r in rows_raw if isinstance(r, Mapping)
    ] if isinstance(rows_raw, (list, tuple)) else []

    #: metric_key → 该行在 rows 里的下标（**不新建**：不在此表的 metric 一律跳过）
    row_index_by_metric = {
        str(r.get("id")): i for i, r in enumerate(rows) if r.get("id")
    }

    # 实体名 → 动态列键 → 渲染层列键。实体清单取 store 的 entitySlots（实体真源）。
    slots = state.get("entitySlots")
    entity_names: tuple[str, ...] = ()
    if isinstance(slots, Mapping):
        raw_names = slots.get(RENDER_SLOT)
        if isinstance(raw_names, (list, tuple)):
            entity_names = tuple(
                str(n) for n in raw_names if isinstance(n, str) and n.strip()
            )
    column_keys = dynamic_column_keys_for_entities(entity_names) if entity_names else ()
    render_key_by_column_key = {
        column_key: render_column_key_for_seq(seq)
        for seq, column_key in enumerate(column_keys, start=1)
    }

    applied = 0
    visited = 0
    prefix = f"{MATRIX_TABLE_KEY}/"
    for stable_key in projection.stable_keys():
        key = str(stable_key)
        if not key.startswith(prefix):
            continue
        fv = projection.get(stable_key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        metric_key, _, column_key = key[len(prefix):].partition("/")
        if not metric_key or not column_key:
            continue
        idx = row_index_by_metric.get(metric_key)
        render_key = render_key_by_column_key.get(column_key)
        if idx is None or render_key is None:
            # 契约外的 metric / 实体清单外的列 ⇒ fail-closed 跳过（见 docstring）
            continue
        visited += 1
        row = rows[idx]
        cells_raw = row.get("values")
        cells: dict[str, Any] = dict(cells_raw) if isinstance(cells_raw, Mapping) else {}
        new_val = getattr(fv, "value", None)
        if cells.get(render_key) != new_val:
            cells[render_key] = new_val
            row["values"] = cells
            rows[idx] = row
            applied += 1

    if rows or RENDER_MATRIX_TABLE_ID in tables:
        tables[RENDER_MATRIX_TABLE_ID] = rows
    state["tables"] = tables
    return state, applied, visited
