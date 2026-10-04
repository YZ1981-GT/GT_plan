# -*- coding: utf-8 -*-
"""D5-4「应收款项融资公允价值测算表」—— sheet 层薄声明。

spec: d567-sync-coverage-via-row-table-engine · Task 6 · Requirements 1.1, 1.4

═══ 几何（openpyxl 直读实测，2026-09-26）═══

26r × 13c(M) / 18 公式。单级表头 R10-R11（A='类别' B='明细项目' ... M='备注'）。
数据区 R12-R16（5 行模板占位）。footer R17「合计」。

公式列 4 条（数据行列向）：
  G = F{r}-E{r}          剩余天数 = 到期日-计量日
  I = D{r}*H{r}*G{r}/365 贴现利息 = 票面×利率×天数÷365
  J = D{r}-I{r}          贴现金额 = 票面-利息
  K = J{r}               期末公允价值 = 贴现金额

🔴 前端 recalcFairValueRow 用 ÷360 而模板公式用 ÷365——这是模板与前端的既有落差
   （双读单写时以模板为准），声明按模板实测。

UUID 动态行，`aging_layout=None`（D5 无账龄组）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = ["SPEC_D504", "MANAGED_SHEET_D504", "STORE_ITEM_ID_D504"]

#: 🔴 模板实测真名（openpyxl 直读确认）。
MANAGED_SHEET_D504: Final[str] = "应收款项融资公允价值测算表D5-4"
TEMPLATE_ID_D504: Final[str] = "D54"
SHEET_KEY_D504: Final[str] = "d54-managed"
ROWS_TABLE_KEY_D504: Final[str] = "fair_value_rows"
#: 🔴 按值 grep 实测，不是按编号推演。
STORE_ITEM_ID_D504: Final[str] = "D5-4-rows"

ROW_IDENTITY_STORE_KEY_D504: Final[str] = "rowId"

#: 两级表头：R10 组标题 / R11 子标题（实测 A10 空、B10 空、D10='票面金额'...）
HEADER_ROW_D504: Final[int] = 11
FIRST_DATA_ROW_D504: Final[int] = 12
LAST_DATA_ROW_D504: Final[int] = 16
FOOTER_ROW_D504: Final[int] = 17
FOOTER_MARKER_D504: Final[str] = "合计"
MANAGED_LAST_COL_D504: Final[str] = "M"
#: N 列实测全空，是最靠近数据区（A-M）的候选空列。
UUID_COL_D504: Final[str] = "N"

#: 13 个受管字段（7 元组）。
#: G/I/J/K 四列模板内逐行有真公式 ⇒ formula；其余 9 列无公式 ⇒ editable。
FIELD_SPECS_D504: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("category", "A", "editable", "enum", "category", "类别", ""),
    ("item_name", "B", "editable", "text", "itemName", "明细项目", ""),
    ("bill_no", "C", "editable", "text", "billNo", "票据号", ""),
    ("face_value", "D", "editable", "amount", "faceValue", "票面金额", ""),
    ("measurement_date", "E", "editable", "date", "measurementDate", "计量日", ""),
    ("maturity_date", "F", "editable", "date", "maturityDate", "到期日", ""),
    ("remaining_days", "G", "formula", "amount", "remainingDays", "剩余天数", ""),
    ("discount_rate", "H", "editable", "ratio", "discountRate", "市场贴现利率", ""),
    ("discount_interest", "I", "formula", "amount", "discountInterest", "贴现利息", ""),
    ("discount_amount", "J", "formula", "amount", "discountAmount", "贴现金额", ""),
    ("fair_value", "K", "formula", "amount", "fairValue", "期末公允价值", ""),
    ("fv_hierarchy", "L", "editable", "text", "fvHierarchy", "公允价值层次", ""),
    ("remark", "M", "editable", "text", "remark", "备注", ""),
)

FORMULA_TEMPLATES_D504: Final[dict[str, str]] = {
    "G": "=F{r}-E{r}",
    "I": "=D{r}*H{r}*G{r}/365",
    "J": "=D{r}-I{r}",
    "K": "=J{r}",
}

SPEC_D504: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D504,
    sheet_key=SHEET_KEY_D504,
    table_key=ROWS_TABLE_KEY_D504,
    template_id=TEMPLATE_ID_D504,
    table_name=f"GT_{TEMPLATE_ID_D504}_ROWS",
    uuid_col=UUID_COL_D504,
    first_data_row=FIRST_DATA_ROW_D504,
    last_data_row=LAST_DATA_ROW_D504,
    footer_row=FOOTER_ROW_D504,
    header_row=HEADER_ROW_D504,
    store_item_id=STORE_ITEM_ID_D504,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D504,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D504,
    formula_columns=("G", "I", "J", "K"),
    formula_templates=FORMULA_TEMPLATES_D504,
    aging_layout=None,
    footer_marker=FOOTER_MARKER_D504,
    error_label="D5-4 公允价值测算表",
)
