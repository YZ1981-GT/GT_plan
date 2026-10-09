# -*- coding: utf-8 -*-
"""D7-6「关联方关系及交易检查表」—— sheet 层薄声明。

spec: d567-sync-coverage-via-row-table-engine · Task 12 · Requirements 3.3

几何（openpyxl 直读 2026-09-26）：31r × 11c(K) / 15f。
🔴 模板真名 = 「关联方关系及交易检查表D7-6」（不是 spec 原写的「关联方合同负债检查D7-6」）。
单级表头 R11。数据区 R12-R14。footer R15（C15+D15+E15+F15=SUM + I15=SUM）。
公式列 F(endBalance = C+E-D, 期末余额=期初+贷方-借方)。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D706", "MANAGED_SHEET_D706", "STORE_ITEM_ID_D706"]

MANAGED_SHEET_D706: Final[str] = "关联方关系及交易检查表D7-6"
TEMPLATE_ID_D706: Final[str] = "D76"
SHEET_KEY_D706: Final[str] = "d76-managed"
ROWS_TABLE_KEY_D706: Final[str] = "related_party_rows"
STORE_ITEM_ID_D706: Final[str] = "D7-6-rows"
ROW_IDENTITY_STORE_KEY_D706: Final[str] = "rowId"

HEADER_ROW_D706: Final[int] = 11
FIRST_DATA_ROW_D706: Final[int] = 12
LAST_DATA_ROW_D706: Final[int] = 14
FOOTER_ROW_D706: Final[int] = 15
FOOTER_MARKER_D706: Final[str] = ""  # A15 为空（纯数值 SUM 行），不声明 footer marker
MANAGED_LAST_COL_D706: Final[str] = "K"
UUID_COL_D706: Final[str] = "L"

#: 11 列。F(endBalance=formula)。
FIELD_SPECS_D706: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("party_name", "A", "editable", "text", "partyName", "关联方名称", ""),
    ("relationship", "B", "editable", "text", "relationship", "关联关系", ""),
    ("opening_balance", "C", "editable", "amount", "openingBalance", "期初余额", ""),
    ("debit_amount", "D", "editable", "amount", "debitAmount", "借方发生", ""),
    ("credit_amount", "E", "editable", "amount", "creditAmount", "贷方发生", ""),
    ("end_balance", "F", "formula", "amount", "endBalance", "期末余额", ""),
    ("aging_time", "G", "editable", "text", "agingTime", "发生时间及账龄", ""),
    ("reason", "H", "editable", "text", "reason", "未结转或未偿还的原因", ""),
    ("audit_date_transfer", "I", "editable", "amount", "auditDateTransfer", "至审计日结转或偿还金额", ""),
    ("plan", "J", "editable", "text", "plan", "处理计划", ""),
    ("remark", "K", "editable", "text", "remark", "备注", ""),
)

SPEC_D706: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D706,
    sheet_key=SHEET_KEY_D706,
    table_key=ROWS_TABLE_KEY_D706,
    template_id=TEMPLATE_ID_D706,
    table_name=f"GT_{TEMPLATE_ID_D706}_ROWS",
    uuid_col=UUID_COL_D706,
    first_data_row=FIRST_DATA_ROW_D706,
    last_data_row=LAST_DATA_ROW_D706,
    footer_row=FOOTER_ROW_D706,
    header_row=HEADER_ROW_D706,
    store_item_id=STORE_ITEM_ID_D706,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D706,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D706,
    formula_columns=("F",),
    aging_layout=None,  # D7-6 本身无账龄组
    footer_marker=FOOTER_MARKER_D706,
    error_label="D7-6 关联方检查表",
)
