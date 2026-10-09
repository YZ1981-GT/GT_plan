# -*- coding: utf-8 -*-
"""B60-1 工时预算表的 store 合并门面 —— `pilot_simple_checklist` 的伴生模块。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure（B60 OO→HTML 打通）

═══ 修的是什么 ═══

B60 此前是 `store_item_registry.NON_STORE_BACKED_ADAPTERS` 的**唯一**成员，理由是
「契约 `review` 段无 `html_store`、15 个字段 `store_item_id` 全为 None ⇒ 纯 Excel entry，
HTML 宿主不读 checklist store」。

那条归类在当时是对的 —— 但它描述的是**当时前端还没有 HTML 面**这个事实。
`b60/GtB60HourBudgetPanel.vue` 落地后，B60-1 工时表在 HTML 侧有了真载体：
它读写 `checklist_responses` 的 `B60-1-hour-budget-rows`（remark 存 JSON 行数组，
行身份 `rowUuid`）。于是「不需要镜像」不再成立 —— 用户在 OnlyOffice 里改的行
**回不到**那张表，面板空态甚至写着一句不成立的承诺
「打开在线编辑并 forcesave 后将镜像至此」。

⇒ 本模块补上回方向：`oo_to_html._mirror_store_backed_if_needed` 按注册表拿到
`plan.merge_rows_fn`，`getattr(bridge, …)` 取到这里。

═══ 为什么抽成伴生模块 ═══

`pilot_simple_checklist` 已 1007 行，仓库行数门的措辞是「**打磨应让文件变小不变大**」。
边界与 G7/H1 两个伴生模块一致：主模块持有身份常量 / 契约装配 / 投影，本模块只持有
**回方向合并**；主模块 re-export，调用方（`getattr(bridge, plan.merge_rows_fn)`）零改动。

═══ 与 H1/G7 门面的三处形态差异（不是照抄）═══

1. **字段路径就是 `column_key` 本身**：`MANAGED_FIELD_SPECS` 是 6 元组
   `(column_key, 列, mode, value_type, header_source_cell, 标签)` —— 第 5 位是表头单元格
   **不是** json_path（H1 那份第 5 位才是 json_path）。B60 的 store 行是扁平 snake_case
   对象（`{rowUuid, grade, member_name, …}`），契约 `json_pointer` 逐字就是
   `/rows/{row_uuid}/<column_key>`，前端面板读的也是 `row.grade` / `row.member_name`
   ⇒ 三方同名，无需映射表。照抄 H1 的 `spec[4]` 会把表头单元格当路径写出 `{"A5": …}`。
2. **行身份键是 `rowUuid`**（H1 是 `rowId`、G4/G6 是 `id`）—— 取自契约
   `row_identity.json_pointer = /rows/*/rowUuid`，与前端面板 `ROW_ID_KEY` 逐字一致。
3. **`budget_cost`（F 列）是 `formula`**：模板里 `F = (C+D)*E`。它不进 store ——
   写它等于把 Excel 算出来的值固化成 HTML 侧的"事实"，下次 C/D/E 变了就产生两份不一致的
   数。按 `MANAGED_FIELD_SPECS` 的 mode 过滤掉，不依赖 `fv.is_protected` 单条防线。
"""
from __future__ import annotations

from typing import Any, Final, Mapping

__all__ = [
    "ROW_IDENTITY_STORE_KEY",
    "STORE_ITEM_ID",
    "html_store_payload",
    "merge_projection_into_store_rows",
]

#: HTML 侧 store item —— `checklist_responses.item_id`，remark 存 JSON 行数组。
#: 逐字对齐前端 `b60/GtB60HourBudgetPanel.vue` 的 `STORE_ITEM_ID`。
#: 🔴 `oo_to_html._mirror_store_backed_if_needed` 读的是 `bridge.STORE_ITEM_ID`，
#:    bridge = `plan.provider_module` = `pilot_simple_checklist` ⇒ 主模块必须 re-export。
STORE_ITEM_ID: Final[str] = "B60-1-hour-budget-rows"

#: 行身份在 store 行对象里的键名。与契约 `row_identity.json_pointer = /rows/*/rowUuid`
#: 及前端面板 `ROW_ID_KEY` 逐字一致。
#: 🔴 三家 pilot 各不相同：H1 用 `rowId`、G4/G6 用 `id`、B60 用 `rowUuid` —— 照抄会让
#:    回写按错的键匹配行，结果是「每次 forcesave 都新增一批重复行」。
ROW_IDENTITY_STORE_KEY: Final[str] = "rowUuid"


def html_store_payload() -> dict[str, Any]:
    """契约 `review.html_store` 段 —— 与身份常量、回方向合并同处一地（三者必须同改）。"""
    return {
        "table": "checklist_responses",
        "payload_column": "remark",
        "payload_column_mode": "remark_only",
        "shape": "json_array_of_row_objects",
        "item_ids": [STORE_ITEM_ID],
        "payload_column_source": (
            "audit-platform/frontend/src/components/workpaper/b60/"
            "GtB60HourBudgetPanel.vue —— flushPendingSave() 经 "
            "PUT /api/workpapers/{wpId}/checklist-responses 写 "
            f"{{ item_id: '{STORE_ITEM_ID}', remark: JSON.stringify(rows) }}，"
            "防抖 600ms；宿主 GtB60Bundle 切「在线编辑」前 await 它"
        ),
        "note": (
            "B60-1 工时表的受管行存成 checklist_responses 的 remark JSON 数组。"
            f"🔴 行身份键是 {ROW_IDENTITY_STORE_KEY}（与契约 row_identity "
            f"/rows/*/{ROW_IDENTITY_STORE_KEY} 及前端 ROW_ID_KEY 逐字一致；"
            "H1 用 rowId、G4/G6 用 id，三家不同不可照抄）。"
            "🔴 字段在 store 行对象里是扁平 snake_case，逐字等于 column_key"
            "（grade / member_name / budget_execution_hours …）—— 契约 json_pointer、"
            "前端读取键、MANAGED_FIELD_SPECS 的 column_key 三方同名，无需映射表。"
            "🔴 F 列 budget_cost 是 formula（=(C+D)*E）：它声明了 store_item_id 以保持"
            "列覆盖完整，但回方向按 mode 过滤掉 —— 把 Excel 算出的值固化进 HTML store "
            "会造第二份事实。"
            "🔴 meta 表 hour_budget_meta（单位名称 / 会计期间 / 编制人…）不在 item_ids 里："
            "前端面板只渲染行表、不读 meta，声明它有 store 就是造载体。"
        ),
    }


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把已 extract 的 projection 合进 `B60-1-hour-budget-rows` HTML store 行（不读盘）。

    :returns: `(merged_rows, applied, visited, touched_row_ids)` —— 与
        `oo_to_html` 的 rows 分支签名一致（它按 `applied <= 0 and base_rows` 决定是否跳过写库）。
    """
    from app.services.workpaper_sync.pilot_simple_checklist import MANAGED_FIELD_SPECS

    #: 只回写 `editable` 列。`formula` 列（F `budget_cost`）由 Excel 与前端各自重算，
    #: 把它固化进 store 会造第二份事实（见模块 docstring 第 3 条）。
    writable_fields = {
        spec[0] for spec in MANAGED_FIELD_SPECS if spec[2] == "editable"
    }
    #: 幽灵行判据列 —— 业务姓名。Excel Table 边界被扩展时，若新行只有一个杂散 editable
    #: 格非空，那一个字段就能让 identity 通过关卡，而姓名列从未写入 ⇒ 用户在结构化视图里
    #: 看到「有 rowUuid、没数据」的行（D4-2 / H1 同源缺陷）。只对**本次新增**的行设这道门，
    #: 已存在的行永不受影响（清空是合法编辑）。
    name_field = "member_name"

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
            # meta 表（`hour_budget_meta`，A3 区的单位名称 / 会计期间 / 编制人…）没有行身份。
            # 🔴 它在 HTML 侧**没有载体** —— `GtB60HourBudgetPanel` 只渲染行表，不读 meta。
            #    跳过它而不是凭空写进行数组，否则会造出契约外的结构。
            continue
        field_id = str(key).rsplit("/", 1)[-1]
        if field_id not in writable_fields:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {ROW_IDENTITY_STORE_KEY: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        visited += 1
        new_value = getattr(fv, "value", None)
        if target.get(field_id) != new_value:
            target[field_id] = new_value
            applied += 1
            touched_rows.add(str(rid))

    ghost_ids = {
        rid
        for rid in order
        if rid not in pre_existing_ids
        and not str(by_id[rid].get(name_field) or "").strip()
    }
    if ghost_ids:
        order = [rid for rid in order if rid not in ghost_ids]
        touched_rows -= ghost_ids

    return [by_id[rid] for rid in order], applied, visited, touched_rows
