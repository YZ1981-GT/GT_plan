# -*- coding: utf-8 -*-
"""F4-5「长期挂账检查表」—— sheet 层薄声明。

spec: f4-sync-coverage-and-first-canary · Task 12 · Requirements 4.1
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何（openpyxl 逐格实测）═══

单级表头 **R8**（A~K 十一列：债权人名称/期末余额/账龄/经济业务说明/未偿还或未结转的原因/
是否无法支付/是否诉讼/支付计划/审定金额/支持性证据/备注）。

数据区 **R9~R14**（6 行）· footer **R15** 合计。
R7 「二、审计过程：」是节标题，非表头。

═══ footer ═══

`A15 = '合计'`，footer_carries_total_formula=True（B15 应有 SUM）。

═══ 公式列 ═══

数据区零公式 ⇒ `formula_columns=()`。

═══ UUID 列 ═══

max_col=K(11)，L 列 non_null=0 ⇒ 取 **L**。

═══ 字段（逐列对齐前端 `useF4LongOutstanding.StoredLongOutstandingRow`）═══

行身份 **`rowId`**。前端 `STORAGE_KEY = 'F4-5-rows'`。

store-only 键：`seq`（前端序号）/ `attSlot`（附件槽位）/ `sourceRowId`（F4-2 归集行 ID）/
`disposalConclusion`（处置结论，模板无列）/ `remark`（备注列不在模板 K 之后但实测 K 列
就是备注 ⇒ 对齐模板 K 列）。

🔴 实测修正 spec：备注是模板 K 列（表头「备注」），而非 store-only。
前端 `StoredLongOutstandingRow` 的 `remark` 对应 K 列。
`disposalConclusion`（处置结论）模板无列 ⇒ 真正的 store-only。

🔴 前端派生字段（`LongOutstandingRow` 多出的）不进 field_specs：
`linked`(bool) / `adjustmentAmount`(number) / `riskFlags`(string[]) / `highlightLevel`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F405",
    "MANAGED_SHEET_F405",
    "STORE_ITEM_ID_F405",
    "STORE_ONLY_KEYS_F405",
]

MANAGED_SHEET_F405: Final[str] = "长期挂账检查表F4-5"
TEMPLATE_ID_F405: Final[str] = "F45"
SHEET_KEY_F405: Final[str] = "f45-managed"
ROWS_TABLE_KEY_F405: Final[str] = "long_outstanding_rows"
STORE_ITEM_ID_F405: Final[str] = "F4-5-rows"

ROW_IDENTITY_STORE_KEY_F405: Final[str] = "rowId"

HEADER_ROW_F405: Final[int] = 8
FIRST_DATA_ROW_F405: Final[int] = 9
LAST_DATA_ROW_F405: Final[int] = 14
FOOTER_ROW_F405: Final[int] = 15
FOOTER_MARKER_F405: Final[str] = "合计"
MANAGED_LAST_COL_F405: Final[str] = "K"
UUID_COL_F405: Final[str] = "L"

#: store-only 键（模板无对应列）。
STORE_ONLY_KEYS_F405: Final[tuple[tuple[str, str], ...]] = (
    ("seq", "前端序号（模板 A 列是债权人名称，序号由前端维护）"),
    ("attSlot", "附件槽位号"),
    ("sourceRowId", "F4-2 归集行 ID 组合；空表示手工行"),
    ("disposalConclusion", "处置结论（模板无该列，纯前端 store）"),
)

#: 11 个受管字段（7 元组）。数据区零公式。
FIELD_SPECS_F405: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("creditor", "A", "editable", "text", "creditor", "债权人名称", ""),
    ("closing_balance", "B", "editable", "amount", "closingBalance", "期末余额", ""),
    ("aging", "C", "editable", "text", "aging", "账龄", ""),
    ("business_description", "D", "editable", "text", "businessDescription", "经济业务说明", ""),
    ("unsettled_reason", "E", "editable", "text", "unsettledReason", "未偿还或未结转的原因", ""),
    ("unable_to_pay", "F", "editable", "text", "unableToPay", "是否无法支付", ""),
    ("litigation", "G", "editable", "text", "litigation", "是否诉讼", ""),
    ("payment_plan", "H", "editable", "text", "paymentPlan", "支付计划", ""),
    ("audited_amount", "I", "editable", "amount", "auditedAmount", "审定金额", ""),
    ("supporting_evidence", "J", "editable", "text", "supportingEvidence", "支持性证据", ""),
    ("remark", "K", "editable", "text", "remark", "备注", ""),
)

SPEC_F405: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F405,
    sheet_key=SHEET_KEY_F405,
    table_key=ROWS_TABLE_KEY_F405,
    template_id=TEMPLATE_ID_F405,
    table_name=f"GT_{TEMPLATE_ID_F405}_ROWS",
    uuid_col=UUID_COL_F405,
    first_data_row=FIRST_DATA_ROW_F405,
    last_data_row=LAST_DATA_ROW_F405,
    footer_row=FOOTER_ROW_F405,
    header_row=HEADER_ROW_F405,
    store_item_id=STORE_ITEM_ID_F405,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F405,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F405,
    formula_columns=(),
    formula_templates={},
    footer_marker=FOOTER_MARKER_F405,
    footer_carries_total_formula=True,
    error_label="F4-5 长期挂账检查表",
)
