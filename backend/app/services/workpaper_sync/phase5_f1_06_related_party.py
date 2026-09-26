# -*- coding: utf-8 -*-
"""F1-6「关联方及交易检查表」—— sheet 层薄声明（F1 首张接入 canary）。

spec: f1-sync-coverage-and-first-canary · Task 8

═══ 为什么选 F1-6 作 canary ═══

单级表头、无账龄组、3 行数据、无口径分歧、零跨 sheet 取数、
失败面最小（裁决 F1-H1，与 E1-2/D3-6 同一选择逻辑）。

═══ 几何（openpyxl 逐格实测，禁推演）═══

单级表头 R6（13 列 A..M）· 数据区 R7-9（3 行）· footer R10「合计」
公式列：F（`=C{r}+D{r}-E{r}` 期末余额=期初+借方-贷方）
       H（`=F{r}-G{r}` 账面价值=期末余额-坏账准备）

═══ footer 下保护区 ═══

R11「审计说明」/ R15-23 关系类型下拉源（「勿删、勿改」）
—— 不进 field_specs，登记 HTML-only。
数据验证 B7:B9 formula1=$B$16:$B$23（绝对引用，在 footer 之下），
位移链已支持 formula1 位移（excel_row_shift.py:183）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F106",
    "MANAGED_SHEET_F106",
    "STORE_ITEM_ID_F106",
]

MANAGED_SHEET_F106: Final[str] = "关联方及交易检查表F1-6"
TEMPLATE_ID_F106: Final[str] = "F16"
SHEET_KEY_F106: Final[str] = "f16-managed"
ROWS_TABLE_KEY_F106: Final[str] = "related_party_rows"
STORE_ITEM_ID_F106: Final[str] = "F1-rp-rows"
ROW_IDENTITY_STORE_KEY_F106: Final[str] = "rowId"

HEADER_ROW_F106: Final[int] = 6
FIRST_DATA_ROW_F106: Final[int] = 7
LAST_DATA_ROW_F106: Final[int] = 9
FOOTER_ROW_F106: Final[int] = 10
FOOTER_MARKER_F106: Final[str] = "合计"
UUID_COL_F106: Final[str] = "N"


#: 13 个受管字段（7 元组，末位 group_header_cell="" —— 单级表头无分组）。
#: 顺序即 Excel 列序 A→M；键名取自 useF1RelatedParty.RelatedPartyRow。
#: F/H 列模板逐行有真公式 ⇒ formula；其余 11 列无公式 ⇒ editable。
FIELD_SPECS_F106: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("party_name", "A", "editable", "text", "partyName", "关联方名称", ""),
    ("relationship", "B", "editable", "text", "relationship", "关联关系", ""),
    ("prior_balance", "C", "editable", "amount", "priorBalance", "期初余额", ""),
    ("debit", "D", "editable", "amount", "debit", "借方发生", ""),
    ("credit", "E", "editable", "amount", "credit", "贷方发生", ""),
    ("end_balance", "F", "formula", "amount", "endBalance", "期末余额", ""),
    ("bad_debt", "G", "editable", "amount", "badDebt", "坏账准备", ""),
    ("book_value", "H", "formula", "amount", "bookValue", "账面价值", ""),
    ("aging_description", "I", "editable", "text", "agingDescription", "发生时间及账龄", ""),
    ("nature_description", "J", "editable", "text", "natureDescription", "款项性质说明", ""),
    ("post_period_delivery", "K", "editable", "amount", "postPeriodDelivery", "期后结算", ""),
    ("index_ref", "L", "editable", "text", "indexRef", "索引号", ""),
    ("remark", "M", "editable", "text", "remark", "备注", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。
FORMULA_TEMPLATES_F106: Final[dict[str, str]] = {
    "F": "=C{r}+D{r}-E{r}",
    "H": "=F{r}-G{r}",
}

SPEC_F106: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F106,
    sheet_key=SHEET_KEY_F106,
    table_key=ROWS_TABLE_KEY_F106,
    template_id=TEMPLATE_ID_F106,
    table_name=f"GT_{TEMPLATE_ID_F106}_ROWS",
    uuid_col=UUID_COL_F106,
    first_data_row=FIRST_DATA_ROW_F106,
    last_data_row=LAST_DATA_ROW_F106,
    footer_row=FOOTER_ROW_F106,
    header_row=HEADER_ROW_F106,
    store_item_id=STORE_ITEM_ID_F106,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F106,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F106,
    formula_columns=("F", "H"),
    formula_templates=FORMULA_TEMPLATES_F106,
    footer_marker=FOOTER_MARKER_F106,
    error_label="F1-6 关联方及交易检查表",
)
