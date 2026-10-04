# -*- coding: utf-8 -*-
"""D1-11「应收票据关联方关系及交易检查表」—— sheet 层薄声明（单区）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 28 · Requirements 5.1

═══ 几何（openpyxl 直读实测，2026-09-26）═══

单级表头 R10（13 列 A-M）。数据区 R11-R13（3 行）。footer R14 `合计`（[5408 8ba1]）。
🔴 **数据区有行级公式**：F=C+D-E（期末余额）/ H=F-G（账面价值）——引擎声明为 `formula`。
前端 `RelatedPartyRow` 的 `closingBalance`/`bookValue` 标注为"公式，只读"，语义一致。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = ["SPEC_D111", "MANAGED_SHEET_D111"]

MANAGED_SHEET_D111: Final[str] = "关联方关系及交易检查表D1-11"
TEMPLATE_ID_D111: Final[str] = "D111"
SHEET_KEY_D111: Final[str] = f"{TEMPLATE_ID_D111.lower()}-managed"

FOOTER_MARKER_D111: Final[str] = "合计"  # [5408 8ba1]

_FIELD_SPECS_D111: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("party_name", "A", "editable", "text", "partyName", "关联方名称", ""),
    ("relationship", "B", "editable", "text", "relationship", "关联关系", ""),
    ("opening_balance", "C", "editable", "amount", "openingBalance", "期初余额", ""),
    ("debit_occurrence", "D", "editable", "amount", "debitOccurrence", "借方发生", ""),
    ("credit_occurrence", "E", "editable", "amount", "creditOccurrence", "贷方发生", ""),
    ("closing_balance", "F", "formula", "amount", "closingBalance", "期末余额", ""),
    ("bad_debt_provision", "G", "editable", "amount", "badDebtProvision", "减：坏账准备", ""),
    ("book_value", "H", "formula", "amount", "bookValue", "账面价值", ""),
    ("aging_info", "I", "editable", "text", "agingInfo", "发生时间及账龄", ""),
    ("transaction_nature", "J", "editable", "text", "transactionNature", "发生原因（款项性质）", ""),
    ("post_honored", "K", "editable", "amount", "postHonored", "期后已兑现或已贴现", ""),
    ("index_ref", "L", "editable", "text", "indexRef", "索引号", ""),
    ("remark", "M", "editable", "text", "remark", "备注", ""),
)

_FORMULA_COLUMNS_D111: Final[tuple[str, ...]] = ("F", "H")
_FORMULA_TEMPLATES_D111: Final[dict[str, str]] = {
    "F": "=C{r}+D{r}-E{r}",
    "H": "=F{r}-G{r}",
}

SPEC_D111: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D111,
    sheet_key=SHEET_KEY_D111,
    table_key="related_party_rows",
    template_id=TEMPLATE_ID_D111,
    table_name=f"GT_{TEMPLATE_ID_D111}_ROWS",
    uuid_col="N",  # max_col=M=13, 注入列 N
    first_data_row=11,
    last_data_row=12,  # 🔴 R13 是「……」排版占位行，不是业务数据行（instrumentation gate 实测）
    footer_row=14,
    header_row=10,
    store_item_id="D1-rp-rows",
    empty_payload="[]",
    row_identity_key="id",  # 🔴 前端用 `id`（与 D1-12/D1-16 一致）
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_D111,
    formula_columns=_FORMULA_COLUMNS_D111,
    formula_templates=_FORMULA_TEMPLATES_D111,
    footer_marker=FOOTER_MARKER_D111,
    error_label="D1-11 关联方检查",
)
