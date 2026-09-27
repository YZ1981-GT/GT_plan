# -*- coding: utf-8 -*-
"""G4-7「有价证券盘点表」—— sheet 层薄声明（零公式 + 表头起于 B 列 + 无合计）。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 8 / 裁决 G46-H1

═══ 几何（openpyxl 逐格实测，禁推演）═══

`有价证券盘点表G4-7`：`max_row=29` / `max_col=7` / merged 3 / 19 sheets。

* **单级表头 R13**：表头起于 **B 列**（A 列空），有效列 6 个（B..G）。
  `B=证券名称` `C=面值` `D=数量` `E=总计` `F=票面利率` `G=到期日`
* 数据区 **R14-R22**（9 行）。
* **无合计行**（`R23` 是「三、审计说明：」，不是数值行）。
  ⇒ `footer_row=23` + `footer_marker="三、审计说明"` + `footer_carries_total_formula=False`。
* `formula_columns=()`（数据区零公式）。
* 有效列 7（A..G）但 A 列空 ⇒ uuid 取 **H 列**（有效列 +1）。
* 🔴 **表头起于 B 列**（A 列无内容，被 R12 的 `1、盘点情况` 行覆盖）。
  `ghost_row_anchor_index=0` 指 B 列（field_specs 第 0 个）。
* payload 列：**dual_write**（FD-1，remark + conclusion 逐字相同）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G407",
    "MANAGED_SHEET_G407",
    "STORE_ITEM_ID_G407",
    "FIELD_SPECS_G407",
    "FORMULA_COLUMNS_G407",
]

MANAGED_SHEET_G407: Final[str] = "有价证券盘点表G4-7"
TEMPLATE_ID_G407: Final[str] = "G407"
STORE_ITEM_ID_G407: Final[str] = "G4-7-items"
ROW_IDENTITY_STORE_KEY_G407: Final[str] = "id"

HEADER_ROW_G407: Final[int] = 13
FOOTER_ROW_G407: Final[int] = 23
FOOTER_MARKER_G407: Final[str] = "三、审计说明"

#: 零公式列
FORMULA_COLUMNS_G407: Final[tuple[str, ...]] = ()

#: 6 个受管字段（B..G），A 列空不声明。
FIELD_SPECS_G407: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("security_name", "B", "editable", "text", "securityName", "证券名称", ""),
    ("face_value", "C", "editable", "amount", "faceValue", "面值", ""),
    ("quantity", "D", "editable", "amount", "quantity", "数量", ""),
    ("total", "E", "editable", "amount", "total", "总计", ""),
    ("coupon_rate", "F", "editable", "rate", "couponRate", "票面利率", ""),
    ("maturity_date", "G", "editable", "text", "maturityDate", "到期日", ""),
)

SPEC_G407: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G407,
    sheet_key="g407-managed",
    table_key="g4_7_items",
    template_id=TEMPLATE_ID_G407,
    table_name="GT_G407_ITEMS",
    uuid_col="H",
    first_data_row=14,
    last_data_row=22,
    footer_row=FOOTER_ROW_G407,
    header_group_row=HEADER_ROW_G407,
    header_leaf_row=HEADER_ROW_G407,
    store_item_id=STORE_ITEM_ID_G407,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G407,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G407,
    formula_columns=FORMULA_COLUMNS_G407,
    formula_templates={},
    footer_marker=FOOTER_MARKER_G407,
    footer_carries_total_formula=False,
    error_label="G4-7 有价证券盘点表",
    ghost_row_anchor_index=0,
)
