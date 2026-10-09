# -*- coding: utf-8 -*-
"""F4-8「应付账款检查表」双区 —— sheet 层薄声明。

spec: f4-sync-coverage-and-first-canary · Task 13 · Requirements 2.4, 4.2, 4.5
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 双区结构 ═══

| 区 | 标题 | 表头 | 数据区 | footer | SUM 列 | uuid_col |
|---|---|---|---|---|---|---|
| ① 本期借方 | R14 | R15/R16 | R17-37 (21行) | R38 | G,L,O | S |
| ② 本期贷方 | R39 | R40/R41 | R42-57 (16行) | R58 | G,N | T |

🔴 两区列集确实不同（spec Task 2 实测 + 本次逐格确认）：
- 区① 证据组：付款审批单(H~I) + 银行回单(J~L) = 5 列，SUM 到 O 列
- 区② 证据组：入库单/验收单(H~K) + 采购发票(L~N) = 7 列，SUM 到 N 列
  区② 比区① 证据组宽 2 列 ⇒ 区②后续列整体右移（与 F3-7 三区同型）。

🔴 两区数据区零公式（R17~R37 和 R42~R57 全空）⇒ `formula_columns=()` × 2。

两区共享 `sheet_key="f48-managed"`（D3-4 先例），区级唯一性靠 `table_key` / `uuid_col`。

═══ 前端 composable ═══

`useF4VoucherCheck.ts` · 行接口 `F4VoucherCheckRow`（26 字段联合接口，两区共用）。
主键：`F4-8-debit-rows`（借方）/ `F4-8-credit-rows`（贷方）。
零写入读键：`F4-8-debit-note` / `F4-8-credit-note`（在 provider `ZERO_WRITER_READ_KEYS` 登记）。

store-only（模板无对应列）：`seq` / `attSlot` / `issueDesc` / `sampleSource`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F408_DEBIT",
    "SPEC_F408_CREDIT",
    "MANAGED_SHEET_F408",
    "STORE_ITEM_ID_F408_DEBIT",
    "STORE_ITEM_ID_F408_CREDIT",
    "STORE_ONLY_KEYS_F408",
]

MANAGED_SHEET_F408: Final[str] = "应付账款检查表F4-8"
TEMPLATE_ID_F408: Final[str] = "F48"
SHEET_KEY_F408: Final[str] = "f48-managed"
STORE_ITEM_ID_F408_DEBIT: Final[str] = "F4-8-debit-rows"
STORE_ITEM_ID_F408_CREDIT: Final[str] = "F4-8-credit-rows"

ROW_IDENTITY_STORE_KEY_F408: Final[str] = "rowId"

#: store-only 键（两区共用，模板无对应列）。
STORE_ONLY_KEYS_F408: Final[tuple[tuple[str, str], ...]] = (
    ("seq", "前端序号"),
    ("attSlot", "附件槽位号"),
    ("issueDesc", "问题描述（模板无列，纯前端 store）"),
    ("sampleSource", "抽样来源（模板无列，纯前端 store）"),
)

# ── 区① 本期借方金额检查 ──

_DEBIT_TABLE_KEY: Final[str] = "voucher_debit_rows"
_DEBIT_HEADER_GROUP: Final[int] = 15
_DEBIT_HEADER_LEAF: Final[int] = 16
_DEBIT_FIRST_DATA: Final[int] = 17
_DEBIT_LAST_DATA: Final[int] = 37
_DEBIT_FOOTER: Final[int] = 38
_DEBIT_UUID_COL: Final[str] = "S"

#: 区① 12 个 editable 字段（A~O 共 15 列，减去 M「……」/ P/Q 是区② 偏移后的列）。
#: 🔴 注意 R15 的合并: A15:G15(记账凭证) / H15:I15(付款审批单) / J15:L15(银行回单) /
#: M15:M16(……) / N15:N16(索引号) / O15:O16(是否异常)
FIELD_SPECS_DEBIT: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("supplier_name", "A", "editable", "text", "supplierName", "供应商名称", "A15"),
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期", "A15"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号", "A15"),
    ("business_content", "D", "editable", "text", "businessContent", "业务内容", "A15"),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", "A15"),
    ("detail_account", "F", "editable", "text", "detailAccount", "明细科目", "A15"),
    ("amount", "G", "editable", "amount", "amount", "借方金额", "A15"),
    ("approval_date_no", "H", "editable", "text", "approvalDateNo", "日期/编号", "H15"),
    ("approval_proper", "I", "editable", "text", "approvalProper", "是否经过恰当审批", "H15"),
    ("bank_receipt_date", "J", "editable", "text", "bankReceiptDate", "日期", "J15"),
    ("bank_payee", "K", "editable", "text", "bankPayee", "收款方", "J15"),
    ("bank_amount", "L", "editable", "amount", "bankAmount", "金额", "J15"),
    ("other_evidence", "M", "editable", "text", "otherEvidence", "……", ""),
    ("index_no", "N", "editable", "text", "indexNo", "索引号", ""),
    ("is_abnormal", "O", "editable", "text", "isAbnormal", "是否异常", ""),
)

SPEC_F408_DEBIT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F408,
    sheet_key=SHEET_KEY_F408,
    table_key=_DEBIT_TABLE_KEY,
    template_id=f"{TEMPLATE_ID_F408}D",
    table_name=f"GT_{TEMPLATE_ID_F408}_DEBIT_ROWS",
    uuid_col=_DEBIT_UUID_COL,
    first_data_row=_DEBIT_FIRST_DATA,
    last_data_row=_DEBIT_LAST_DATA,
    footer_row=_DEBIT_FOOTER,
    header_group_row=_DEBIT_HEADER_GROUP,
    header_leaf_row=_DEBIT_HEADER_LEAF,
    store_item_id=STORE_ITEM_ID_F408_DEBIT,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F408,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_DEBIT,
    formula_columns=(),
    formula_templates={},
    footer_marker="合计",
    footer_carries_total_formula=True,
    error_label="F4-8 应付账款检查表（本期借方）",
)

# ── 区② 本期贷方金额检查 ──

_CREDIT_TABLE_KEY: Final[str] = "voucher_credit_rows"
_CREDIT_HEADER_GROUP: Final[int] = 40
_CREDIT_HEADER_LEAF: Final[int] = 41
_CREDIT_FIRST_DATA: Final[int] = 42
_CREDIT_LAST_DATA: Final[int] = 57
_CREDIT_FOOTER: Final[int] = 58
_CREDIT_UUID_COL: Final[str] = "T"

#: 区② 15 个 editable 字段（A~Q 共 17 列，减去 O「……」和 P/Q 但加了证据组 H~N）。
#: 🔴 区② 比区① 证据组宽 2 列：入库单(H~K) 4 列 + 采购发票(L~N) 3 列 = 7 列
#: （区①：付款审批单(H~I) 2 列 + 银行回单(J~L) 3 列 = 5 列）
FIELD_SPECS_CREDIT: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("supplier_name", "A", "editable", "text", "supplierName", "供应商名称", "A40"),
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期", "A40"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号", "A40"),
    ("business_content", "D", "editable", "text", "businessContent", "业务内容", "A40"),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", "A40"),
    ("detail_account", "F", "editable", "text", "detailAccount", "明细科目", "A40"),
    ("amount", "G", "editable", "amount", "amount", "贷方金额", "A40"),
    ("receipt_date_no", "H", "editable", "text", "receiptDateNo", "日期/编号", "H40"),
    ("receipt_product", "I", "editable", "text", "receiptProduct", "品名", "H40"),
    ("receipt_unit", "J", "editable", "text", "receiptUnit", "单位", "H40"),
    ("receipt_qty", "K", "editable", "amount", "receiptQty", "数量", "H40"),
    ("invoice_date_no", "L", "editable", "text", "invoiceDateNo", "日期/编号", "L40"),
    ("invoice_counterparty", "M", "editable", "text", "invoiceCounterparty", "对手方名称", "L40"),
    ("invoice_amount", "N", "editable", "amount", "invoiceAmount", "金额", "L40"),
    ("other_evidence", "O", "editable", "text", "otherEvidence", "……", ""),
    ("index_no", "P", "editable", "text", "indexNo", "索引号", ""),
    ("is_abnormal", "Q", "editable", "text", "isAbnormal", "是否异常", ""),
)

SPEC_F408_CREDIT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F408,
    sheet_key=SHEET_KEY_F408,
    table_key=_CREDIT_TABLE_KEY,
    template_id=f"{TEMPLATE_ID_F408}C",
    table_name=f"GT_{TEMPLATE_ID_F408}_CREDIT_ROWS",
    uuid_col=_CREDIT_UUID_COL,
    first_data_row=_CREDIT_FIRST_DATA,
    last_data_row=_CREDIT_LAST_DATA,
    footer_row=_CREDIT_FOOTER,
    header_group_row=_CREDIT_HEADER_GROUP,
    header_leaf_row=_CREDIT_HEADER_LEAF,
    store_item_id=STORE_ITEM_ID_F408_CREDIT,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F408,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_CREDIT,
    formula_columns=(),
    formula_templates={},
    footer_marker="合计",
    footer_carries_total_formula=True,
    error_label="F4-8 应付账款检查表（本期贷方）",
)
