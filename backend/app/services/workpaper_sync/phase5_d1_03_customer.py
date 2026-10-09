# -*- coding: utf-8 -*-
"""D1-3「原值明细表（按客户）」—— sheet 层薄声明（只有数据，没有算法）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 15 · Requirements 2.1 / 2.2

═══ 三层架构里的位置（第 1 层：sheet 声明）═══

本模块只做一件事：把 D1-3 的几何/字段/store 形态声明成一个 `RowTableSheetSpec` 常量。
投影、合并、契约装配算法全在框架层 `phase5_row_table_sheet`；entry 级事实
（ENTRY_ID / 模板路径 / 受管 sheet 清单 / 灰度开关）在循环层 `phase5_d1_notes_receivable`。

═══ 几何来源（openpyxl 逐格实测，与 provider 现状逐字一致）═══

受管 sheet `原值明细表（按客户）D1-3`：单级表头行 10（15 列 A..O）、数据区 11..20、
A21 合计 footer、隐藏 UUID 列 P。G/J/L/O 四列逐行公式 `=D+E+F` / `=D+H-I` / `=J+K` /
`=L+M+N`（openpyxl 逐格实测）⇒ mode=formula；其余 11 列模板内无公式故判 editable。

🔴 J 列 xlsx 公式 `=D+H-I`（不含 E/F），前端 recalcRow 用 `priorAudited+inc-dec=G+H-I`，
   数值语义等价但**公式文本以 xlsx 为准** ⇒ J 声明为 formula，materialize 不覆盖公式格、
   由 OO 重算（D1-3 契约已立此纪律）。

🔴 本模块**不重复** provider 的常量：几何数字从 `phase5_d1_notes_receivable` 的冻结常量引用，
   避免两处各写一份而漂移（那正是本 spec 要消除的漂移面）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync import phase5_d1_notes_receivable as _entry
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = ["SPEC_D103"]


#: D1-3 的行表声明。字段 7 元组的第 7 位（group_header_cell）全为 ""：D1-3 单级表头无分组。
SPEC_D103: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=_entry.MANAGED_SHEET,
    sheet_key=_entry.SHEET_KEY,
    table_key=_entry.ROWS_TABLE_KEY,
    template_id=_entry.TEMPLATE_ID,
    table_name=_entry.TABLE_NAME,
    uuid_col=_entry.UUID_COL,
    first_data_row=_entry.FIRST_DATA_ROW,
    last_data_row=_entry.LAST_DATA_ROW,
    footer_row=_entry.FOOTER_ROW,
    header_row=_entry.HEADER_ROW,
    store_item_id=_entry.STORE_ITEM_ID,
    empty_payload=_entry.EMPTY_STORE_PAYLOAD,
    row_identity_key=_entry.ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=tuple((*row, "") for row in _entry.MANAGED_FIELD_SPECS),
    # 🔴 formula_mask 由引擎按 formula_columns 现算（不手写字面量，消除漂移面）
    formula_columns=("G", "J", "L", "O"),
    formula_templates=dict(_entry.FORMULA_TEMPLATES),
    footer_marker=_entry.FOOTER_MARKER,
    error_label="D1-3 原值明细表（按客户）",
)
