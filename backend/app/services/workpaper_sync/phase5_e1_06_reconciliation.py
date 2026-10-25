# -*- coding: utf-8 -*-
"""E1-6「银行存款余额调节表」—— 行表声明（结构化 JSON 行，每行=银行账户）。

spec: e1-sync-coverage-and-first-canary · Task 15 · Requirements 2.1 / 2.3
形态证据: docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json

═══ 几何（openpyxl 逐格实测）═══

模板 56r×17c / 14 公式。模板结构特殊：整个 sheet 只给一个银行账户的空间：
  - 企业侧 R16-R33（银行存款日记账 → 加银行已收企业未收 → 减银行已付企业未付 → 调节后余额）
  - 银行侧 R34-R52（对账单余额 → 加企业已收银行未收 → 减企业已付银行未付 → 调节后余额）
  - R13 单行表头（开户银行 / 银行账号 / 币种）
  - R52 一致性公式 `=IF(C33=C51,"调节一致","调节不一致")`
  - R53 审计说明 / 结论

前端 `useE1Reconciliation`(392) 把每个银行账户序列化为 `ReconciliationRow` JSON 对象（含 4 个
嵌套 `OutstandingItem[]` 子数组），以 `E1-reconciliation-rows` 存 `checklist_responses`。

⇒ 模板列 ↔ store 字段的映射是**顶层扁平字段**（bankName/accountNo/bookBalance/statementBalance
等 4 个金额 + 4 个合计 + diff + diffReason），嵌套子数组在 OO 侧不逐格映射。

🔴 **公式列**：C17=SUM(C20:C24) / C25=SUM(C28:C32) / C33=C16+C17-C25（企业侧调节后余额）
   C35=SUM(C38:C42) / C43=SUM(C46:C50) / C51=C34+C35-C43（银行侧调节后余额）
   C52=IF(C33=C51,...) —— 全在 C 列。

🔴 **行身份键**：`id`（与 E1 全族一致，不是 D 类的 `rowId`）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_E106",
    "MANAGED_SHEET_E106",
    "STORE_ITEM_ID_E106",
]

MANAGED_SHEET_E106: Final[str] = "银行存款余额调节表E1-6"
TEMPLATE_ID_E106: Final[str] = "E16"
SHEET_KEY_E106: Final[str] = f"{TEMPLATE_ID_E106.lower()}-managed"
ROWS_TABLE_KEY_E106: Final[str] = "reconciliation_rows"

#: 🔴 按值 grep 实测（useE1Reconciliation.ts:53）。
STORE_ITEM_ID_E106: Final[str] = "E1-reconciliation-rows"

#: 行身份键 —— E1 全族统一用 `id`。
ROW_IDENTITY_STORE_KEY_E106: Final[str] = "id"

#: 模板只给了一个银行账户的空间：R13 表头，R16 起始数据，最终到 R52。
#: 前端 addRow 多账户通过 JSON 数组扩展，不靠模板行扩展。
HEADER_ROW_E106: Final[int] = 13
FIRST_DATA_ROW_E106: Final[int] = 16
LAST_DATA_ROW_E106: Final[int] = 52
FOOTER_ROW_E106: Final[int] = 53
FOOTER_MARKER_E106: Final[str] = "三、审计说明"
MANAGED_LAST_COL_E106: Final[str] = "K"
UUID_COL_E106: Final[str] = "L"

#: 受管字段（顶层扁平字段，映射到模板中一个银行账户区块的关键格）。
#: 🔴 E1-6 的模板结构是「一个账户占 R16-R52 整个区块」，字段投影按**首行**映射。
#: 嵌套的 OutstandingItem[] 子数组不逐格映射——它们在 store 里以 JSON 数组存储。
FIELD_SPECS_E106: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("bank_name", "A", "editable", "text", "bankName", "开户银行", ""),
    ("account_no", "E", "editable", "text", "accountNo", "银行账号", ""),
    ("currency", "K", "editable", "text", "currency", "币种", ""),
    ("book_balance", "C", "editable", "amount", "bookBalance", "企业银行存款日记账余额", ""),
    ("statement_balance", "C", "editable", "amount", "statementBalance", "银行对账单余额", ""),
    ("bank_received", "C", "formula", "amount", "bankReceived", "银行已收企业未收款项", ""),
    ("bank_paid", "C", "formula", "amount", "bankPaid", "银行已付企业未付款项", ""),
    ("company_received", "C", "formula", "amount", "companyReceived", "企业已收银行未收款项", ""),
    ("company_paid", "C", "formula", "amount", "companyPaid", "企业已付银行未付款项", ""),
    ("diff", "C", "formula", "amount", "diff", "差额", ""),
    ("diff_reason", "G", "editable", "text", "diffReason", "差异原因", ""),
)

#: C 列公式模板（区块内多行，此处列出主要汇总公式）。
FORMULA_TEMPLATES_E106: Final[dict[str, str]] = {
    "C": "=SUM(range)",
}

SPEC_E106: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E106,
    sheet_key=SHEET_KEY_E106,
    table_key=ROWS_TABLE_KEY_E106,
    template_id=TEMPLATE_ID_E106,
    table_name=f"GT_{TEMPLATE_ID_E106}_ROWS",
    uuid_col=UUID_COL_E106,
    first_data_row=FIRST_DATA_ROW_E106,
    last_data_row=LAST_DATA_ROW_E106,
    footer_row=FOOTER_ROW_E106,
    header_row=HEADER_ROW_E106,
    store_item_id=STORE_ITEM_ID_E106,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_E106,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_E106,
    formula_columns=("C",),
    formula_templates=FORMULA_TEMPLATES_E106,
    footer_marker=FOOTER_MARKER_E106,
    error_label="E1-6 银行存款余额调节表",
)
