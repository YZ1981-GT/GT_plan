# -*- coding: utf-8 -*-
"""D6-6「合同资产检查表」—— 双区声明（区①本期变动 / 区②期后检查）。

spec: d567-sync-coverage-via-row-table-engine · Task 14 · Requirements 2.3

几何（openpyxl 直读 2026-09-26；spec oo-writeback-template-parity-closure R3 批 B2 逐格复核 2026-10-28）：
53r × 17c(Q)。两区都是两级表头（A/I/O/P/Q 跨两行合并，B..H「记账凭证」、J..N「核对内容」1~5 是组）：
区①（本期增减变动检查）：表头 R16 / R17，数据 R18-R30，footer R31「合计」（G/H 两列 SUM）。
区②（期后贴现\背书\调整等检查）：表头 R33 / R34，数据 R35-R39，footer R40「合计」（只 G 一列 SUM）。
  🔴 区② B..G 组只到 G = **贷方金额**，H:I 合并为「支持性文件」（值写主列 H）。原声明「为简化按区①同列声明」
  ⇒ G 接 debitAmount（区② 行没有这个键，恒空）、H 接 creditAmount（贷方金额写进了支持性文件列）、I 接 supportDoc；
  单级 `header_row` 还让 R17 / R34 叶子表头落进数据区。前端 `useD6Inspection` 区② 本来就只有 creditAmount。
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
    ("date", "B", "editable", "date", "date", "日期", "B16"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号", "B16"),
    ("business_content", "D", "editable", "text", "businessContent", "业务内容", "B16"),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", "B16"),
    ("counter_detail", "F", "editable", "text", "counterDetail", "对方明细科目", "B16"),
    ("debit_amount", "G", "editable", "amount", "debitAmount", "借方金额", "B16"),
    ("credit_amount", "H", "editable", "amount", "creditAmount", "贷方金额", "B16"),
    ("support_doc", "I", "editable", "text", "supportDoc", "支持性文件", ""),
    ("check1", "J", "editable", "text", "check1", "核对内容1", "J16"),
    ("check2", "K", "editable", "text", "check2", "核对内容2", "J16"),
    ("check3", "L", "editable", "text", "check3", "核对内容3", "J16"),
    ("check4", "M", "editable", "text", "check4", "核对内容4", "J16"),
    ("check5", "N", "editable", "text", "check5", "核对内容5", "J16"),
    ("index_ref", "O", "editable", "text", "indexRef", "索引号", ""),
    ("is_abnormal", "P", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "Q", "editable", "text", "remark", "备注说明", ""),
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
    header_group_row=16,
    header_leaf_row=17,
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

#: 区② 16 列：A..F 同区①（组标题行 R33），G = 贷方金额，H = 支持性文件（H:I 合并、值写主列 H，I 不声明），J..Q 同区①。
FIELD_SPECS_D606_B2: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    *(
        (key, col, mode, vt, jp, label, group.replace("16", "33"))
        for key, col, mode, vt, jp, label, group in FIELD_SPECS_D606_B1
        if col in ("A", "B", "C", "D", "E", "F")
    ),
    ("credit_amount", "G", "editable", "amount", "creditAmount", "贷方金额", "B33"),
    ("support_doc", "H", "editable", "text", "supportDoc", "支持性文件", ""),
    *(
        (key, col, mode, vt, jp, label, group.replace("16", "33"))
        for key, col, mode, vt, jp, label, group in FIELD_SPECS_D606_B1
        if col >= "J" and len(col) == 1
    ),
)

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
    header_group_row=33,
    header_leaf_row=34,
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
