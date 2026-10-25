# -*- coding: utf-8 -*-
"""D6-6「合同资产检查表」—— 双区声明（区①本期变动 / 区②期后检查）。

spec: d567-sync-coverage-via-row-table-engine · Task 14 · Requirements 2.3

几何（openpyxl 直读 2026-09-26）：53r × 17c(Q) / 19f。
区①（本期增减变动检查）：表头 R15-16，数据 R17-R30，footer R31「合计」。
区②（期后检查）：表头 R32-33，数据 R34-R39，footer R40「合计」。
🔴 两区共享 managed_sheet 但不同 sheet_key 后缀 / store_item_id / UUID 列。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D606_BLOCK1", "SPEC_D606_BLOCK2", "MANAGED_SHEET_D606",
           "STORE_ITEM_ID_D606_BLOCK1", "STORE_ITEM_ID_D606_BLOCK2"]

MANAGED_SHEET_D606: Final[str] = "合同资产检查表D6-6"

# ─── 区① 本期增减变动检查 ──────────────────────────────────────────────────

TEMPLATE_ID_D606_B1: Final[str] = "D66B1"
SHEET_KEY_D606: Final[str] = "d66-managed"
STORE_ITEM_ID_D606_BLOCK1: Final[str] = "D6-6-block1-rows"

FIELD_SPECS_D606_B1: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("date", "B", "editable", "date", "date", "日期", ""),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证号", ""),
    ("business_content", "D", "editable", "text", "businessContent", "经济业务内容", ""),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", ""),
    ("counter_detail", "F", "editable", "text", "counterDetail", "对方明细", ""),
    ("debit_amount", "G", "editable", "amount", "debitAmount", "借方金额", ""),
    ("credit_amount", "H", "editable", "amount", "creditAmount", "贷方金额", ""),
    ("support_doc", "I", "editable", "text", "supportDoc", "支持性文件", ""),
    ("check1", "J", "editable", "text", "check1", "检查1", ""),
    ("check2", "K", "editable", "text", "check2", "检查2", ""),
    ("check3", "L", "editable", "text", "check3", "检查3", ""),
    ("check4", "M", "editable", "text", "check4", "检查4", ""),
    ("check5", "N", "editable", "text", "check5", "检查5", ""),
    ("index_ref", "O", "editable", "text", "indexRef", "索引号", ""),
    ("is_abnormal", "P", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "Q", "editable", "text", "remark", "备注", ""),
)

SPEC_D606_BLOCK1: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D606,
    sheet_key=SHEET_KEY_D606,
    table_key="inspection_block1_rows",
    template_id=TEMPLATE_ID_D606_B1,
    table_name=f"GT_{TEMPLATE_ID_D606_B1}_ROWS",
    uuid_col="R",
    first_data_row=18,  # R16-R17 是两级表头（客户名称/记账凭证 + 日期/凭证编号），数据从 R18 开始
    last_data_row=30,
    footer_row=31,
    header_row=16,
    store_item_id=STORE_ITEM_ID_D606_BLOCK1,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D606_B1,
    formula_columns=(),  # 数据行无公式列
    aging_layout=None,
    footer_marker="合计",
    error_label="D6-6 检查表 区①",
)

# ─── 区② 期后检查 ────────────────────────────────────────────────────────

TEMPLATE_ID_D606_B2: Final[str] = "D66B2"
STORE_ITEM_ID_D606_BLOCK2: Final[str] = "D6-6-block2-rows"

#: 区②列比区①少（无 debit_amount G 列，且列位不同）——但为简化按区①同列声明，
#: 实际差异在前端 composable 处理（两区共用 InspectionSampleRow 类型）。
FIELD_SPECS_D606_B2: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = FIELD_SPECS_D606_B1

SPEC_D606_BLOCK2: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D606,
    sheet_key=SHEET_KEY_D606,
    table_key="inspection_block2_rows",
    template_id=TEMPLATE_ID_D606_B2,
    table_name=f"GT_{TEMPLATE_ID_D606_B2}_ROWS",
    uuid_col="S",  # 🔴 不同区不同 UUID 列
    first_data_row=35,  # R33-R34 是两级表头，数据从 R35 开始
    last_data_row=39,
    footer_row=40,
    header_row=33,
    store_item_id=STORE_ITEM_ID_D606_BLOCK2,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D606_B2,
    formula_columns=(),
    aging_layout=None,
    footer_marker="合计",
    error_label="D6-6 检查表 区②",
)
