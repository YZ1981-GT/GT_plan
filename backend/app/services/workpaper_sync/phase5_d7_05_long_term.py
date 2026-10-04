# -*- coding: utf-8 -*-
"""D7-5「账龄1年以上合同负债检查表」—— sheet 层薄声明。

spec: d567-sync-coverage-via-row-table-engine · Task 12 · Requirements 3.2

几何（openpyxl 直读 2026-09-26）：20r × 8c(H) / 9f。
🔴 与 D3-5 同型（同为「账龄1年以上…检查表」、几何逐项相同），声明骨架复制。
数据行无公式列（9 处公式全在 header/footer），`formula_columns` 不传。
单级表头 R10。数据区 R11-R13。footer R14（B14=SUM 实测）。
aging_layout=nested（D7 全家 nested）。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D705", "MANAGED_SHEET_D705", "STORE_ITEM_ID_D705"]

MANAGED_SHEET_D705: Final[str] = "账龄1年以上合同负债检查表D7-5"
TEMPLATE_ID_D705: Final[str] = "D75"
SHEET_KEY_D705: Final[str] = "d75-managed"
ROWS_TABLE_KEY_D705: Final[str] = "long_term_rows"
STORE_ITEM_ID_D705: Final[str] = "D7-5-rows"
ROW_IDENTITY_STORE_KEY_D705: Final[str] = "rowId"

HEADER_ROW_D705: Final[int] = 10
FIRST_DATA_ROW_D705: Final[int] = 11
LAST_DATA_ROW_D705: Final[int] = 13
FOOTER_ROW_D705: Final[int] = 14
FOOTER_MARKER_D705: Final[str] = ""  # A14 为空（纯数值 SUM 行），不声明 footer marker
MANAGED_LAST_COL_D705: Final[str] = "H"
UUID_COL_D705: Final[str] = "I"

#: 8 列。数据行无公式列（公式全在 header/footer）。
FIELD_SPECS_D705: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("end_balance", "B", "editable", "amount", "endBalance", "期末余额", ""),
    ("aging", "C", "editable", "text", "aging", "账龄", ""),
    ("business_description", "D", "editable", "text", "businessDescription", "经济业务说明", ""),
    ("reason", "E", "editable", "text", "reason", "未结转或未偿还的原因", ""),
    ("audit_date_transfer", "F", "editable", "amount", "auditDateTransfer", "至审计日结转或偿还金额", ""),
    ("plan", "G", "editable", "text", "plan", "处理计划", ""),
    ("remark", "H", "editable", "text", "remark", "备注", ""),
)

SPEC_D705: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D705,
    sheet_key=SHEET_KEY_D705,
    table_key=ROWS_TABLE_KEY_D705,
    template_id=TEMPLATE_ID_D705,
    table_name=f"GT_{TEMPLATE_ID_D705}_ROWS",
    uuid_col=UUID_COL_D705,
    first_data_row=FIRST_DATA_ROW_D705,
    last_data_row=LAST_DATA_ROW_D705,
    footer_row=FOOTER_ROW_D705,
    header_row=HEADER_ROW_D705,
    store_item_id=STORE_ITEM_ID_D705,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D705,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D705,
    formula_columns=(),  # 数据行无公式列
    aging_layout=None,  # D7-5 本身无账龄组
    footer_marker=FOOTER_MARKER_D705,
    footer_carries_total_formula=True,
    error_label="D7-5 账龄1年以上检查表",
)
