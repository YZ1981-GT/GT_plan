# -*- coding: utf-8 -*-
"""F1-7「预付账款检查表」—— 三区薄声明。

spec: f1-sync-coverage-and-first-canary · Task 14

═══ 几何（openpyxl 逐格实测）═══

三个同 sheet 不同数据区（兄弟 Table ref 位移路径，D3-7 双区已验证）：
  区① 借方（current）：两级表头 R15/R16 · 数据 R17-37 · footer R38 · 数据区零公式
  区② 贷方（credit）：两级表头 R40/R41 · 数据 R42-64 · footer R65 · 数据区零公式
  区③ 期后（post）：两级表头 R67/R68 · 数据 R69-85 · footer R86 · 数据区零公式

🔴 三区列集不同（逐格实测）：
  区① R16 G=借方金额、H..O 为审批单/回单/合同证据、R=是否异常
  区②③ R41/R68 G=贷方金额、H..N 为入库单/发票证据、Q=是否异常

UUID 列 T（三区共用，sheet 只有一个 UUID 列）。

═══ FC-8 OCR 写入粒度 ═══

`F1VoucherCheckDialog.runOcr` 回填**单个弹窗表单**再由用户确认保存单行。
不是整表替换 → 不构成 E1 意义的第二批量写入方。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F107_CURRENT",
    "SPEC_F107_CREDIT",
    "SPEC_F107_POST",
]

MANAGED_SHEET_F107: Final[str] = "预付账款检查表F1-7"
UUID_COL_F107: Final[str] = "T"
ROW_IDENTITY_F107: Final[str] = "rowId"
FOOTER_MARKER_F107: Final[str] = "合计"


# ── 区① 借方（current）──────────────────────────────────────────────────

FIELD_SPECS_F107_CURRENT: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("seq_no", "A", "editable", "text", "seqNo", "序号", ""),
    ("supplier_name", "B", "editable", "text", "supplierName", "供应商名称", ""),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证号", ""),
    ("voucher_date", "D", "editable", "text", "voucherDate", "凭证日期", ""),
    ("abstract", "E", "editable", "text", "abstract", "摘要", ""),
    ("nature", "F", "editable", "text", "nature", "款项性质", ""),
    ("debit_amount", "G", "editable", "amount", "debitAmount", "借方金额", ""),
    ("approval_doc", "H", "editable", "text", "approvalDoc", "审批单据", ""),
    ("receipt", "I", "editable", "text", "receipt", "收据/回单", ""),
    ("contract", "J", "editable", "text", "contract", "合同/协议", ""),
    ("delivery", "K", "editable", "text", "delivery", "发货/出库单", ""),
    ("invoice", "L", "editable", "text", "invoice", "发票", ""),
    ("other_evidence", "M", "editable", "text", "otherEvidence", "其他支持性证据", ""),
    ("payment_method", "N", "editable", "text", "paymentMethod", "付款方式", ""),
    ("prepay_ratio", "O", "editable", "text", "prepayRatio", "预付比例", ""),
    ("settlement_method", "P", "editable", "text", "settlementMethod", "结算方式", ""),
    ("supplier_review", "Q", "editable", "text", "supplierReview", "供应商评审", ""),
    ("is_abnormal", "R", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "S", "editable", "text", "remark", "备注", ""),
)

SPEC_F107_CURRENT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F107,
    sheet_key="f17-current",
    table_key="voucher_check_current_rows",
    template_id="F17C",
    table_name="GT_F17C_ROWS",
    uuid_col=UUID_COL_F107,
    first_data_row=17,
    last_data_row=37,
    footer_row=38,
    header_group_row=15,
    header_leaf_row=16,
    store_item_id="F1-vc-current-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_F107,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F107_CURRENT,
    formula_columns=(),
    footer_marker=FOOTER_MARKER_F107,
    error_label="F1-7 检查表区①借方",
)


# ── 区② 贷方（credit）──────────────────────────────────────────────────

FIELD_SPECS_F107_CREDIT: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("seq_no", "A", "editable", "text", "seqNo", "序号", ""),
    ("supplier_name", "B", "editable", "text", "supplierName", "供应商名称", ""),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证号", ""),
    ("voucher_date", "D", "editable", "text", "voucherDate", "凭证日期", ""),
    ("abstract", "E", "editable", "text", "abstract", "摘要", ""),
    ("nature", "F", "editable", "text", "nature", "款项性质", ""),
    ("credit_amount", "G", "editable", "amount", "creditAmount", "贷方金额", ""),
    ("warehouse_receipt", "H", "editable", "text", "warehouseReceipt", "入库单", ""),
    ("invoice", "I", "editable", "text", "invoice", "发票", ""),
    ("contract", "J", "editable", "text", "contract", "合同/协议", ""),
    ("delivery", "K", "editable", "text", "delivery", "发货/出库单", ""),
    ("acceptance", "L", "editable", "text", "acceptance", "验收报告", ""),
    ("other_evidence", "M", "editable", "text", "otherEvidence", "其他支持性证据", ""),
    ("settlement_method", "N", "editable", "text", "settlementMethod", "结算方式", ""),
    ("supplier_review", "P", "editable", "text", "supplierReview", "供应商评审", ""),
    ("is_abnormal", "Q", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "R", "editable", "text", "remark", "备注", ""),
)

SPEC_F107_CREDIT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F107,
    sheet_key="f17-credit",
    table_key="voucher_check_credit_rows",
    template_id="F17R",
    table_name="GT_F17R_ROWS",
    uuid_col=UUID_COL_F107,
    first_data_row=42,
    last_data_row=64,
    footer_row=65,
    header_group_row=40,
    header_leaf_row=41,
    store_item_id="F1-vc-credit-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_F107,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F107_CREDIT,
    formula_columns=(),
    footer_marker=FOOTER_MARKER_F107,
    error_label="F1-7 检查表区②贷方",
)


# ── 区③ 期后（post）——与区②列集相同 ──────────────────────────────────

FIELD_SPECS_F107_POST: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("seq_no", "A", "editable", "text", "seqNo", "序号", ""),
    ("supplier_name", "B", "editable", "text", "supplierName", "供应商名称", ""),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证号", ""),
    ("voucher_date", "D", "editable", "text", "voucherDate", "凭证日期", ""),
    ("abstract", "E", "editable", "text", "abstract", "摘要", ""),
    ("nature", "F", "editable", "text", "nature", "款项性质", ""),
    ("credit_amount", "G", "editable", "amount", "creditAmount", "贷方金额", ""),
    ("warehouse_receipt", "H", "editable", "text", "warehouseReceipt", "入库单", ""),
    ("invoice", "I", "editable", "text", "invoice", "发票", ""),
    ("contract", "J", "editable", "text", "contract", "合同/协议", ""),
    ("delivery", "K", "editable", "text", "delivery", "发货/出库单", ""),
    ("acceptance", "L", "editable", "text", "acceptance", "验收报告", ""),
    ("other_evidence", "M", "editable", "text", "otherEvidence", "其他支持性证据", ""),
    ("settlement_method", "N", "editable", "text", "settlementMethod", "结算方式", ""),
    ("supplier_review", "P", "editable", "text", "supplierReview", "供应商评审", ""),
    ("is_abnormal", "Q", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "R", "editable", "text", "remark", "备注", ""),
)

SPEC_F107_POST: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F107,
    sheet_key="f17-post",
    table_key="voucher_check_post_rows",
    template_id="F17P",
    table_name="GT_F17P_ROWS",
    uuid_col=UUID_COL_F107,
    first_data_row=69,
    last_data_row=85,
    footer_row=86,
    header_group_row=67,
    header_leaf_row=68,
    store_item_id="F1-vc-post-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_F107,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F107_POST,
    formula_columns=(),
    footer_marker=FOOTER_MARKER_F107,
    error_label="F1-7 检查表区③期后",
)
