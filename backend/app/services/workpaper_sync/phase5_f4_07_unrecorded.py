# -*- coding: utf-8 -*-
"""F4-7「未入账检查表」五区 —— sheet 层薄声明。

spec: f4-sync-coverage-and-first-canary · Task 14 · Requirements 4.3, 4.4, 4.5
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 五区结构 ═══

| 区 | 节标题 | 表头 | 数据区 | footer | 公式列 | uuid |
|---|---|---|---|---|---|---|
| ① 期后付款（平均天数） | R13 | R14 单级 | R15-24 (10) | R25 | F,G,I | L |
| ② 暂估入库 | R26 | R27/R28 两级 | R29-44 (16) | R45 | F | M |
| ③ 未处理发票 | R46 | R47/R48 两级 | R49-59 (11) | R60 | () | N |
| ④ 期后付款核对 | R61 | R62/R63 两级 | R64-75 (12) | R76 | () | O |
| ⑤ 期后增加核对 | R77 | R78/R79 两级 | R80-91 (12) | R92 | () | P |

五区共享 `sheet_key="f47-managed"`（D3-4 先例），区级唯一性靠 `table_key` / `uuid_col`。

🔴 五区列集确实不同（spec Task 2 实测确认，裁决 F4-H3）：
- 区① 单级 11 列（A~K），3 个公式列，SUM 到 I 列（6 列 SUM）
- 区② 两级 11 列，1 个公式列，SUM 到 I 列（2 列 SUM）
- 区③ 两级 10 列，零公式列，SUM 到 I 列（2 列 SUM）
- 区④⑤ 两级 10 列（同构但与③微异），零公式列，SUM 到 I 列（2 列 SUM）

═══ 前端 composable ═══

`useF4UnrecordedCheck.ts` · 行接口 `F4UnrecordedStoredRow`（28 字段联合接口，各区只使用子集）。
五个主键：`F4-7-payment-window-rows` / `F4-7-estimated-inbound-rows` /
`F4-7-unprocessed-invoice-rows` / `F4-7-subsequent-payment-rows` / `F4-7-subsequent-increase-rows`。

store-only（全区共用）：`seq` / `attSlot`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F407_PAYMENT_WINDOW",
    "SPEC_F407_ESTIMATED_INBOUND",
    "SPEC_F407_UNPROCESSED_INVOICE",
    "SPEC_F407_SUBSEQUENT_PAYMENT",
    "SPEC_F407_SUBSEQUENT_INCREASE",
    "MANAGED_SHEET_F407",
    "STORE_ONLY_KEYS_F407",
]

MANAGED_SHEET_F407: Final[str] = "未入账检查表F4-7"
TEMPLATE_ID_F407: Final[str] = "F47"
SHEET_KEY_F407: Final[str] = "f47-managed"
ROW_IDENTITY_STORE_KEY_F407: Final[str] = "rowId"

#: store-only 键（五区共用，模板无对应列）。
STORE_ONLY_KEYS_F407: Final[tuple[tuple[str, str], ...]] = (
    ("seq", "前端序号"),
    ("attSlot", "附件槽位号"),
)

# ═══════════════════════════════════════════════════════════════════════════
# 区① 期后付款是否在平均付款天数内（单级表头 R14）
# ═══════════════════════════════════════════════════════════════════════════

FIELD_SPECS_PAYMENT_WINDOW: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("supplier_name", "B", "editable", "text", "supplierName", "供应商名称", ""),
    ("opening_balance", "C", "editable", "amount", "openingBalance", "期初余额", ""),
    ("current_debit", "D", "editable", "amount", "currentDebit", "本期借方", ""),
    ("current_credit", "E", "editable", "amount", "currentCredit", "本期贷方", ""),
    # F 公式 =C+E-D（期末余额）
    # G 公式 =365/(E/F)（平均付款天数）🔴 除零
    ("post_payment_amount", "H", "editable", "amount", "postPaymentAmount", "期后付款金额", ""),
    # I 公式 =H-F（差异）
    ("within_average_days", "J", "editable", "text", "withinAverageDays", "是否在平均付款天数内", ""),
    ("remark", "K", "editable", "text", "remark", "备注", ""),
)

SPEC_F407_PAYMENT_WINDOW: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F407,
    sheet_key=SHEET_KEY_F407,
    table_key="unrecorded_payment_window_rows",
    template_id=f"{TEMPLATE_ID_F407}PW",
    table_name=f"GT_{TEMPLATE_ID_F407}_PAYMENT_WINDOW",
    uuid_col="L",
    first_data_row=15,
    last_data_row=24,
    footer_row=25,
    header_row=14,
    store_item_id="F4-7-payment-window-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F407,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_PAYMENT_WINDOW,
    formula_columns=("F", "G", "I"),
    formula_templates={
        "F": "=C{r}+E{r}-D{r}",
        "G": "=365/(E{r}/F{r})",
        "I": "=H{r}-F{r}",
    },
    footer_marker="合计",
    footer_carries_total_formula=True,
    error_label="F4-7 未入账检查表（期后付款）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 区② 料到单未到——存货暂估入库（两级表头 R27/R28）
# ═══════════════════════════════════════════════════════════════════════════

FIELD_SPECS_ESTIMATED_INBOUND: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("receipt_date", "B", "editable", "text", "receiptDate", "日期", "B27"),
    ("receipt_no", "C", "editable", "text", "receiptNo", "编号", "B27"),
    ("quantity", "D", "editable", "amount", "quantity", "数量", ""),
    ("contract_unit_price", "E", "editable", "amount", "contractUnitPrice", "合同单价", ""),
    # F 公式 =D*E（暂估金额）
    ("voucher_date", "G", "editable", "text", "voucherDate", "日期", "G27"),
    ("voucher_no", "H", "editable", "text", "voucherNo", "凭证号", "G27"),
    ("voucher_amount", "I", "editable", "amount", "voucherAmount", "金额", "G27"),
    ("should_adjust", "J", "editable", "text", "shouldAdjust", "是否应调整", ""),
    ("remark", "K", "editable", "text", "remark", "备注", ""),
)

SPEC_F407_ESTIMATED_INBOUND: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F407,
    sheet_key=SHEET_KEY_F407,
    table_key="unrecorded_estimated_inbound_rows",
    template_id=f"{TEMPLATE_ID_F407}EI",
    table_name=f"GT_{TEMPLATE_ID_F407}_ESTIMATED_INBOUND",
    uuid_col="M",
    first_data_row=29,
    last_data_row=44,
    footer_row=45,
    header_group_row=27,
    header_leaf_row=28,
    store_item_id="F4-7-estimated-inbound-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F407,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_ESTIMATED_INBOUND,
    formula_columns=("F",),
    formula_templates={"F": "=D{r}*E{r}"},
    footer_marker="合计",
    footer_carries_total_formula=True,
    error_label="F4-7 未入账检查表（暂估入库）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 区③ 截止审计现场结束日未处理的供应商发票（两级表头 R47/R48）
# ═══════════════════════════════════════════════════════════════════════════

FIELD_SPECS_UNPROCESSED_INVOICE: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("invoice_date", "B", "editable", "text", "invoiceDate", "日期", "B47"),
    ("invoice_no", "C", "editable", "text", "invoiceNo", "编号", "B47"),
    ("quantity", "D", "editable", "amount", "quantity", "数量", "B47"),
    ("invoice_content", "E", "editable", "text", "invoiceContent", "发票内容", ""),
    ("amount", "F", "editable", "amount", "amount", "金额", ""),
    ("supplier_name", "G", "editable", "text", "supplierName", "供应商名称", ""),
    ("should_include_report_period", "H", "editable", "text", "shouldIncludeReportPeriod", "是否应计入报告期", ""),
    ("report_period_amount", "I", "editable", "amount", "reportPeriodAmount", "应计入报告期金额", ""),
    ("remark", "J", "editable", "text", "remark", "备注", ""),
)

SPEC_F407_UNPROCESSED_INVOICE: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F407,
    sheet_key=SHEET_KEY_F407,
    table_key="unrecorded_unprocessed_invoice_rows",
    template_id=f"{TEMPLATE_ID_F407}UI",
    table_name=f"GT_{TEMPLATE_ID_F407}_UNPROCESSED_INVOICE",
    uuid_col="N",
    first_data_row=49,
    last_data_row=59,
    footer_row=60,
    header_group_row=47,
    header_leaf_row=48,
    store_item_id="F4-7-unprocessed-invoice-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F407,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_UNPROCESSED_INVOICE,
    formula_columns=(),
    formula_templates={},
    footer_marker="合计",
    footer_carries_total_formula=True,
    error_label="F4-7 未入账检查表（未处理发票）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 区④ 应付账款期后付款核对（两级表头 R62/R63）
# ═══════════════════════════════════════════════════════════════════════════

FIELD_SPECS_SUBSEQUENT_PAYMENT: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期", "B62"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "编号", "B62"),
    ("bank_document_date", "D", "editable", "text", "bankDocumentDate", "日期", "D62"),
    ("bank_document_no", "E", "editable", "text", "bankDocumentNo", "编号", "D62"),
    ("amount", "F", "editable", "amount", "amount", "金额", ""),
    ("supplier_name", "G", "editable", "text", "supplierName", "供应商名称", ""),
    ("should_include_report_period", "H", "editable", "text", "shouldIncludeReportPeriod", "是否应计入报告期", ""),
    ("report_period_amount", "I", "editable", "amount", "reportPeriodAmount", "应计入报告期金额", ""),
    ("remark", "J", "editable", "text", "remark", "备注", ""),
)

SPEC_F407_SUBSEQUENT_PAYMENT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F407,
    sheet_key=SHEET_KEY_F407,
    table_key="unrecorded_subsequent_payment_rows",
    template_id=f"{TEMPLATE_ID_F407}SP",
    table_name=f"GT_{TEMPLATE_ID_F407}_SUBSEQUENT_PAYMENT",
    uuid_col="O",
    first_data_row=64,
    last_data_row=75,
    footer_row=76,
    header_group_row=62,
    header_leaf_row=63,
    store_item_id="F4-7-subsequent-payment-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F407,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_SUBSEQUENT_PAYMENT,
    formula_columns=(),
    formula_templates={},
    footer_marker="合计",
    footer_carries_total_formula=True,
    error_label="F4-7 未入账检查表（期后付款）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 区⑤ 应付账款期后增加额核对（两级表头 R78/R79）
# ═══════════════════════════════════════════════════════════════════════════

FIELD_SPECS_SUBSEQUENT_INCREASE: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期", "B78"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "编号", "B78"),
    ("purchase_invoice_date", "D", "editable", "text", "purchaseInvoiceDate", "日期", "D78"),
    ("purchase_invoice_no", "E", "editable", "text", "purchaseInvoiceNo", "编号", "D78"),
    ("amount", "F", "editable", "amount", "amount", "金额", ""),
    ("supplier_name", "G", "editable", "text", "supplierName", "供应商名称", ""),
    ("should_include_report_period", "H", "editable", "text", "shouldIncludeReportPeriod", "是否应计入报告期", ""),
    ("report_period_amount", "I", "editable", "amount", "reportPeriodAmount", "应计入报告期金额", ""),
    ("remark", "J", "editable", "text", "remark", "备注", ""),
)

SPEC_F407_SUBSEQUENT_INCREASE: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F407,
    sheet_key=SHEET_KEY_F407,
    table_key="unrecorded_subsequent_increase_rows",
    template_id=f"{TEMPLATE_ID_F407}SI",
    table_name=f"GT_{TEMPLATE_ID_F407}_SUBSEQUENT_INCREASE",
    uuid_col="P",
    first_data_row=80,
    last_data_row=91,
    footer_row=92,
    header_group_row=78,
    header_leaf_row=79,
    store_item_id="F4-7-subsequent-increase-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F407,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_SUBSEQUENT_INCREASE,
    formula_columns=(),
    formula_templates={},
    footer_marker="合计",
    footer_carries_total_formula=True,
    error_label="F4-7 未入账检查表（期后增加）",
)
