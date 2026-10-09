# -*- coding: utf-8 -*-
"""D7-4「合同负债分析表」—— 双区声明（区①借方发生额 / 区②贷方发生额+期末余额）。

spec: d567-sync-coverage-via-row-table-engine · Task 16 · Requirements 3.1

几何（openpyxl 直读 2026-09-26）：43r × 8c(H) / 32f。
区①借方分析：表头 R10，数据 R12-R15（对方科目行），footer R11「本期借方发生额合计」。
区②贷方+期末：表头 R18-19，数据 R27-R36（期末余额主要债权人），footer R20「本期贷方发生额合计」/ R37「小计」。
🔴 store keys = D7-4-debit-rows / D7-4-credit-rows（不是 D7-4-rows 聚合键！）。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D704_DEBIT", "SPEC_D704_CREDIT", "MANAGED_SHEET_D704"]

MANAGED_SHEET_D704: Final[str] = "合同负债分析表D7-4"

# ─── 区① 借方发生额分析 ──────────────────────────────────────────────────

TEMPLATE_ID_D704_DEBIT: Final[str] = "D74DEBIT"
SHEET_KEY_D704: Final[str] = "d74-managed"
STORE_ITEM_ID_D704_DEBIT: Final[str] = "D7-4-debit-rows"

FIELD_SPECS_D704_DEBIT: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item", "A", "editable", "text", "item", "项目", ""),
    ("amount", "B", "editable", "amount", "amount", "金额", ""),
    ("data_source", "C", "editable", "text", "dataSource", "数据来源", ""),
    ("remark", "D", "editable", "text", "remark", "备注", ""),
)

SPEC_D704_DEBIT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D704,
    sheet_key=SHEET_KEY_D704,
    table_key="analysis_debit_rows",
    template_id=TEMPLATE_ID_D704_DEBIT,
    table_name=f"GT_{TEMPLATE_ID_D704_DEBIT}_ROWS",
    uuid_col="H",
    first_data_row=13,  # R12 是「对方科目：」标签行，不是数据行
    last_data_row=14,  # R15 是排版续行省略号「……」不是业务行（BP-21）
    footer_row=16,  # R16「差异」行作为 footer（数据区之后第一行）
    header_row=10,
    store_item_id=STORE_ITEM_ID_D704_DEBIT,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D704_DEBIT,
    formula_columns=(),
    aging_layout=None,
    footer_marker="差异",
    error_label="D7-4 分析表 区①借方",
)

# ─── 区② 贷方+期末余额 ─────────────────────────────────────────────────

TEMPLATE_ID_D704_CREDIT: Final[str] = "D74CREDIT"
STORE_ITEM_ID_D704_CREDIT: Final[str] = "D7-4-credit-rows"

FIELD_SPECS_D704_CREDIT: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "债权人名称", ""),
    ("prior_balance", "B", "editable", "amount", "priorBalance", "期初余额", ""),
    ("current_balance", "C", "editable", "amount", "currentBalance", "期末余额", ""),
    ("change_amount", "D", "formula", "amount", "changeAmount", "变动额", ""),
    ("change_rate", "E", "formula", "amount", "changeRate", "变动率", ""),
    ("reason", "F", "editable", "text", "reason", "变动原因", ""),
    ("remark", "G", "editable", "text", "remark", "备注", ""),
)

SPEC_D704_CREDIT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D704,
    sheet_key=SHEET_KEY_D704,
    table_key="analysis_credit_rows",
    template_id=TEMPLATE_ID_D704_CREDIT,
    table_name=f"GT_{TEMPLATE_ID_D704_CREDIT}_ROWS",
    uuid_col="I",  # 🔴 不同区不同 UUID 列
    first_data_row=27,
    last_data_row=36,
    footer_row=37,  # R37「小计」（数据区 R27-R36 之后）
    header_row=26,
    store_item_id=STORE_ITEM_ID_D704_CREDIT,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D704_CREDIT,
    formula_columns=("D", "E"),
    aging_layout=None,
    footer_marker="小计",
    error_label="D7-4 分析表 区②贷方",
)
