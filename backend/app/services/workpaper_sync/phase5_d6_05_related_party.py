# -*- coding: utf-8 -*-
"""D6-5「关联关系及交易检查」—— sheet 层薄声明。

spec: d567-sync-coverage-via-row-table-engine · Task 9 · Requirements 2.2

几何（openpyxl 直读 2026-09-26）：30r × 14c(N) / 19f。
单级表头 R9（12 列 A..L）。数据区 R10-R12（3 行模板占位）。footer R13「合计」。
公式列 F(=C+D-E 期末余额) + H(=F-G 账面价值)。

🔴 spec oo-writeback-template-parity-closure R3 批 B2 逐格复核：模板 R9 的 I..L 是「发生时间及账龄 / 发生原因（款项性质）/
索引号 / 备注」。原声明照另一种关联方表写了 14 列（J 未结转原因 / K 至审计日结转金额 / L 处理计划 / M 索引号 / N 备注），
J~L 三列与模板错位、M / N 落在模板空列上。前端随本批补 `transactionReason`（发生原因）；「未结转原因 / 至审计日结转
金额 / 处理计划」三列模板没有，留在 HTML 侧、不进 OO。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D605", "MANAGED_SHEET_D605", "STORE_ITEM_ID_D605"]

MANAGED_SHEET_D605: Final[str] = "关联关系及交易检查D6-5"
TEMPLATE_ID_D605: Final[str] = "D65"
SHEET_KEY_D605: Final[str] = "d65-managed"
ROWS_TABLE_KEY_D605: Final[str] = "related_party_rows"
STORE_ITEM_ID_D605: Final[str] = "D6-5-rows"
ROW_IDENTITY_STORE_KEY_D605: Final[str] = "rowId"

HEADER_ROW_D605: Final[int] = 9
FIRST_DATA_ROW_D605: Final[int] = 10
LAST_DATA_ROW_D605: Final[int] = 12
FOOTER_ROW_D605: Final[int] = 13
FOOTER_MARKER_D605: Final[str] = "合计"
MANAGED_LAST_COL_D605: Final[str] = "L"
UUID_COL_D605: Final[str] = "O"  # 在模板已用列（max_column = N）之后

#: 12 列（= 模板 R9）。F(endBalance=formula) H(bookValue=formula)，其余 editable。
FIELD_SPECS_D605: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("party_name", "A", "editable", "text", "partyName", "关联方名称", ""),
    ("relationship", "B", "editable", "text", "relationship", "关联关系", ""),
    ("prior_balance", "C", "editable", "amount", "priorBalance", "期初余额", ""),
    ("debit_amount", "D", "editable", "amount", "debitAmount", "借方发生", ""),
    ("credit_amount", "E", "editable", "amount", "creditAmount", "贷方发生", ""),
    ("end_balance", "F", "formula", "amount", "endBalance", "期末余额", ""),
    ("impairment", "G", "editable", "amount", "impairment", "减：坏账准备", ""),
    ("book_value", "H", "formula", "amount", "bookValue", "账面价值", ""),
    ("aging_and_timing", "I", "editable", "text", "agingAndTiming", "发生时间及账龄", ""),
    ("transaction_reason", "J", "editable", "text", "transactionReason", "发生原因（款项性质）", ""),
    ("index_ref", "K", "editable", "text", "indexRef", "索引号", ""),
    ("remark", "L", "editable", "text", "remark", "备注", ""),
)

SPEC_D605: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D605,
    sheet_key=SHEET_KEY_D605,
    table_key=ROWS_TABLE_KEY_D605,
    template_id=TEMPLATE_ID_D605,
    table_name=f"GT_{TEMPLATE_ID_D605}_ROWS",
    uuid_col=UUID_COL_D605,
    first_data_row=FIRST_DATA_ROW_D605,
    last_data_row=LAST_DATA_ROW_D605,
    footer_row=FOOTER_ROW_D605,
    header_row=HEADER_ROW_D605,
    store_item_id=STORE_ITEM_ID_D605,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D605,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D605,
    formula_columns=("F", "H"),
    aging_layout=None,  # D6-5 本身无账龄组
    footer_marker=FOOTER_MARKER_D605,
    error_label="D6-5 关联关系及交易检查",
)
