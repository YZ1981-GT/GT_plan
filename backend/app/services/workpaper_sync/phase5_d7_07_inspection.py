# -*- coding: utf-8 -*-
"""D7-7「合同负债检查表」—— 双区声明（区①本期变动 / 区②期后检查）。

spec: d567-sync-coverage-via-row-table-engine · Task 16 · Requirements 3.4

几何（openpyxl 直读 2026-09-26）：48r × 21c(U) / 19f。
与 D6-6 同型（检查表双区，本期+期后）。
区①：表头 R15-16，数据 R17-R30，footer R31「合计」。
区②：表头 R32-33，数据 R34-R39，footer R40「合计」。
🔴 store keys = D7-7-period-rows / D7-7-post-rows（不是 D7-7-rows 聚合键！）。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D707_PERIOD", "SPEC_D707_POST", "MANAGED_SHEET_D707"]

MANAGED_SHEET_D707: Final[str] = "合同负债检查表D7-7"

# ─── 区① 本期增减变动检查 ──────────────────────────────────────────────────

TEMPLATE_ID_D707_PERIOD: Final[str] = "D77PERIOD"
SHEET_KEY_D707: Final[str] = "d77-managed"
STORE_ITEM_ID_D707_PERIOD: Final[str] = "D7-7-period-rows"

#: D7-7 区① 21 列（A-U），与 D6-6 区①类似但多几列。
FIELD_SPECS_D707_PERIOD: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("date", "B", "editable", "date", "date", "日期", ""),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证号", ""),
    ("business_content", "D", "editable", "text", "businessContent", "经济业务内容", ""),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", ""),
    ("debit_amount", "F", "editable", "amount", "debitAmount", "借方金额", ""),
    ("credit_amount", "G", "editable", "amount", "creditAmount", "贷方金额", ""),
    ("support_doc", "H", "editable", "text", "supportDoc", "支持性文件", ""),
    ("check1", "I", "editable", "text", "check1", "检查1", ""),
    ("check2", "J", "editable", "text", "check2", "检查2", ""),
    ("check3", "K", "editable", "text", "check3", "检查3", ""),
    ("check4", "L", "editable", "text", "check4", "检查4", ""),
    ("check5", "M", "editable", "text", "check5", "检查5", ""),
    ("check6", "N", "editable", "text", "check6", "检查6", ""),
    ("check7", "O", "editable", "text", "check7", "检查7", ""),
    ("index_ref", "P", "editable", "text", "indexRef", "索引号", ""),
    ("is_abnormal", "Q", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "R", "editable", "text", "remark", "备注", ""),
)

SPEC_D707_PERIOD: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D707,
    sheet_key=SHEET_KEY_D707,
    table_key="inspection_period_rows",
    template_id=TEMPLATE_ID_D707_PERIOD,
    table_name=f"GT_{TEMPLATE_ID_D707_PERIOD}_ROWS",
    uuid_col="S",  # 必须在受管列 R 之后
    first_data_row=18,  # R16-R17 是两级表头，数据从 R18 开始
    last_data_row=30,
    footer_row=31,
    header_row=16,
    store_item_id=STORE_ITEM_ID_D707_PERIOD,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D707_PERIOD,
    formula_columns=(),
    aging_layout=None,
    footer_marker="合计",
    error_label="D7-7 检查表 区①本期",
)

# ─── 区② 期后检查 ────────────────────────────────────────────────────────

TEMPLATE_ID_D707_POST: Final[str] = "D77POST"
STORE_ITEM_ID_D707_POST: Final[str] = "D7-7-post-rows"

FIELD_SPECS_D707_POST: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = FIELD_SPECS_D707_PERIOD

SPEC_D707_POST: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D707,
    sheet_key=SHEET_KEY_D707,
    table_key="inspection_post_rows",
    template_id=TEMPLATE_ID_D707_POST,
    table_name=f"GT_{TEMPLATE_ID_D707_POST}_ROWS",
    uuid_col="T",  # 🔴 不同区不同 UUID 列，在 S 之后
    first_data_row=35,  # R33-R34 是两级表头，数据从 R35 开始
    last_data_row=39,
    footer_row=40,
    header_row=33,
    store_item_id=STORE_ITEM_ID_D707_POST,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D707_POST,
    formula_columns=(),
    aging_layout=None,
    footer_marker="合计",
    error_label="D7-7 检查表 区②期后",
)
