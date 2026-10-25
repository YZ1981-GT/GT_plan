# -*- coding: utf-8 -*-
"""H1 处置检查表的 store 合并门面 —— `pilot_h1_grouped_dynamic` 的伴生模块。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 13 的缺陷修复 · Requirements 3.1 / 3.4

═══ 为什么抽成伴生模块 ═══

`pilot_h1_grouped_dynamic` 已 1868 行（whitelist 基线），仓库的文件行数门禁措辞是
「**打磨应让文件变小不变大**」⇒ 把 merge 门面追加进去会顶穿 +5% 阈值。
边界：主模块持有身份常量 / 契约装配 / 投影；本模块只持有**回方向合并**。

═══ 修的是什么缺陷 ═══

`oo_to_html` 的回写分派对 `h1.disposal_check` 一直写着
`bridge.merge_projection_into_store_rows`，而主模块**从未定义过它**
（`git show HEAD:` 逐个确认，非改造引入）⇒ H1 走到 store 镜像那步就是 `AttributeError` →
opaque 500，即「OO 编辑保存后 §9.6 的 store_mirrored / marker_visible 永远不成立」。
缺陷能长期活着是因为 H1 的 adapter 也未注册（那条路径没人真走到过）。

主模块以 `from .pilot_h1_store_merge import merge_projection_into_store_rows` 重导出，
调用方（注册表 → `getattr(bridge, plan.merge_rows_fn)`）看到的仍是主模块属性，零改动。
"""
from __future__ import annotations

from typing import Any, Mapping

__all__ = ["merge_projection_into_store_rows"]


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把已 extract 的 projection 合进 `H1-8-rows` HTML store 行（不读盘）。

    🔴 复用框架层 `phase5_row_table_sheet` 的两个纯函数（`set_json_path` /
    `resolve_json_path`）而**不复制**一份：主模块的 `MANAGED_FIELD_SPECS` 第 5 位就是
    json_path（与 D1/D3 同位），映射关系由它单一给出，两侧不可能各写一份而脱钩。

    🔴 幽灵行防护（D4-2 同源缺陷）：Excel Table 边界被扩展时，若新行只有一个杂散的
    editable 格非空，这一个字段就会让 identity 通过 shell 创建关卡，而业务名称列
    （本表 `asset_name`，契约第 4 列）因从未在 Excel 里写入内容、根本不产出 FieldValue，
    永久停在空值 —— 用户在结构化视图里看到「有 rowId、没数据」的行。只对**本次新增**的
    identity 加这道门：已存在的行永不受影响（清空是合法编辑）。

    ⚠️ 本表首列 `seq` 是 `auto_source`（序号，前端自动生成）⇒ 幽灵行判据**不能**用首列，
    必须用真正的业务名称列 `asset_name`（用 `seq` 会把「只填了序号的空行」当成真行留下）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        resolve_json_path,
        set_json_path,
    )
    from app.services.workpaper_sync.pilot_h1_grouped_dynamic import (
        MANAGED_FIELD_SPECS,
        ROW_IDENTITY_STORE_KEY,
    )

    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS}
    #: 🔴 幽灵行判据列：业务名称而非首列（首列 seq 是 auto_source，见 docstring）。
    name_json_path = field_to_path["asset_name"]

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    pre_existing_ids = set(by_id)
    applied = 0
    visited = 0
    touched_rows: set[str] = set()
    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {ROW_IDENTITY_STORE_KEY: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        field_id = str(key).rsplit("/", 1)[-1]
        json_path = field_to_path.get(field_id)
        if not json_path:
            continue
        visited += 1
        if set_json_path(target, json_path, getattr(fv, "value", None)):
            applied += 1
            touched_rows.add(str(rid))

    ghost_ids = {
        rid
        for rid in order
        if rid not in pre_existing_ids
        and not str(resolve_json_path(by_id[rid], name_json_path) or "").strip()
    }
    if ghost_ids:
        order = [rid for rid in order if rid not in ghost_ids]
        touched_rows -= ghost_ids

    return [by_id[rid] for rid in order], applied, visited, touched_rows
