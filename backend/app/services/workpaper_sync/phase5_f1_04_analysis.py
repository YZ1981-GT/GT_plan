# -*- coding: utf-8 -*-
"""F1-4「实质性分析」区④ 大额供应商 —— sheet 层薄声明。

spec: f1-sync-coverage-and-first-canary · Task 15

═══ 几何（openpyxl 逐格实测）═══

区④ 大额供应商：header R40 · 数据 R41-50 · footer R51「小计」
公式列 E（`=B{r}+C{r}-D{r}` 期末余额）和 G（`=E{r}-F{r}` 差异）
UUID 列 S（Task 2 复核：L..R 逐格核空，S 是最靠近数据区的空列）

═══ dict 子数组形态（裁决 F1-H5）═══

store 是 `StoreKind.dict`（`F1-ana-pack`，9 个顶层键），但区④ `suppliers[]`
子数组走 provider 专用 merge 门面（D4 `merge_d*_from_projection` 范式），
合并时保留 pack 其余 8 个顶层键逐字不变（P11）。

区①②③ 核后登记 HTML-only（裁决 F1-H5：收益低于风险，默认不受管）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F104_SUPPLIERS",
    "MANAGED_SHEET_F104",
    "STORE_ITEM_ID_F104",
]

MANAGED_SHEET_F104: Final[str] = "实质性分析F1-4"
TEMPLATE_ID_F104: Final[str] = "F14"
SHEET_KEY_F104: Final[str] = "f14-suppliers"
ROWS_TABLE_KEY_F104: Final[str] = "top_supplier_rows"
#: 🔴 store_item_id 是整个 pack（dict），不是 suppliers 子数组本身。
#: 投影/合并走 provider 专用门面，只替换 `suppliers[]`，其余 8 键保留。
STORE_ITEM_ID_F104: Final[str] = "F1-ana-pack"
ROW_IDENTITY_F104: Final[str] = "rowId"

HEADER_ROW_F104: Final[int] = 40
FIRST_DATA_ROW_F104: Final[int] = 41
LAST_DATA_ROW_F104: Final[int] = 50
FOOTER_ROW_F104: Final[int] = 51
FOOTER_MARKER_F104: Final[str] = "小计"
UUID_COL_F104: Final[str] = "S"


#: 区④ 大额供应商 7 个受管字段。键名取自 useF1Analysis.SupplierRow。
#: E/G 列模板逐行有真公式 ⇒ formula；其余 5 列无公式 ⇒ editable。
FIELD_SPECS_F104: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("supplier_name", "A", "editable", "text", "supplierName", "供应商名称", ""),
    ("prior_balance", "B", "editable", "amount", "priorBalance", "期初余额", ""),
    ("debit", "C", "editable", "amount", "debit", "本期借方", ""),
    ("credit", "D", "editable", "amount", "credit", "本期贷方", ""),
    ("end_balance", "E", "formula", "amount", "endBalance", "期末余额", ""),
    ("audited_balance", "F", "editable", "amount", "auditedBalance", "审定数", ""),
    ("difference", "G", "formula", "amount", "difference", "差异", ""),
)

FORMULA_TEMPLATES_F104: Final[dict[str, str]] = {
    "E": "=B{r}+C{r}-D{r}",
    "G": "=E{r}-F{r}",
}

SPEC_F104_SUPPLIERS: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F104,
    sheet_key=SHEET_KEY_F104,
    table_key=ROWS_TABLE_KEY_F104,
    template_id=TEMPLATE_ID_F104,
    table_name=f"GT_{TEMPLATE_ID_F104}_ROWS",
    uuid_col=UUID_COL_F104,
    first_data_row=FIRST_DATA_ROW_F104,
    last_data_row=LAST_DATA_ROW_F104,
    footer_row=FOOTER_ROW_F104,
    header_row=HEADER_ROW_F104,
    store_item_id=STORE_ITEM_ID_F104,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_F104,
    store_kind=StoreKind.dedicated,  # 🔴 dict 子数组走专用 merge 门面
    field_specs=FIELD_SPECS_F104,
    formula_columns=("E", "G"),
    formula_templates=FORMULA_TEMPLATES_F104,
    footer_marker=FOOTER_MARKER_F104,
    error_label="F1-4 实质性分析区④大额供应商",
)
