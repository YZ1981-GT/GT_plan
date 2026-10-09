# -*- coding: utf-8 -*-
"""E1-7 / E1-8 / E1-9 三张盘点表 —— **一个文件**声明三张（共享 useE1CashCount，只差 variant）。

spec: e1-sync-coverage-and-first-canary · Task 16 · Requirements 2.1 / 2.3 / 2.4 / 2.5
形态证据: docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json

═══ 三张共享 `useE1CashCount`(534) 且只差 `variant` 参数 ═══

| variant | sheet | 几何 | store 键 | footer |
|---|---|---|---|---|
| rmb | 库存现金（人民币）盘点表E1-7 | 67r×9c/27f | `E1-cash-count-rmb-rows` | R29「合计」 |
| fx | 库存现金（外币）盘点表E1-8 | 78r×12c/48f | `E1-cash-count-fx-rows` | R31「合计」 |
| cert | 银行存单盘点表E1-9 | 34r×15c/7f | `E1-cash-count-cert-rows` | — |

🔴 **三张的 `RowTableSheetSpec` 只应差 `variant` 与列集，不得复制三份** ——
   与 D5/D6/D7 共享 33 个同名函数、只差 `aging_layout` 一参是同一范式。

🔴 **副键**：`${storageKey}-summary`（E1-7/E1-8 的结转 summary，cert 无）。
   另有 legacy 兜底键 `E1-cashcount-fx-summary-fx`（双 `-fx` 后缀，历史键，
   `useE1CashCount:268` 仍在读）⇒ 投影须能读到历史底稿，不得只认新键。
   `E1-cert-signatures` 是 cert 独有的签章键。

🔴 **连字符陷阱**：同一 composable 里并存 `E1-cash-count-{variant}-rows`（新键）
   与 `E1-cashcount-audit-note-{variant}`（无连字符的 legacy 文本键）。
   `cash-count` 与 `cashcount` 只差一个连字符。

═══ HTML_ONLY_ITEM_IDS_E1（spec Task 16 产出）═══

三张各有 `elements` / `audit-note` / `audit-conclusion` 三个 per-variant 文本键，
与 `HTML_ONLY_ITEM_IDS_D45` 的 `D4-5-credit-policy` / `-audit-note` / `-audit-conclusion`
**形态逐一对应**（D4-5 正因此被判 HTML-only：footer 下 `static_row` 与插行 fail-closed 冲突）。

═══ 几何实测 ═══

E1-7（rmb）：
  R14 双级表头（R14 清点实有现金 | 核对及追溯纪录）/ R15 叶子（面值/张数/余额 | 项目/金额）
  数据区 R16-28（面值行 100/50/20/10/5/2/1/0.5/0.2/0.1/0.05/0.02/0.01）
  footer R29「合计」= SUM(C16:C28)
  公式列 C（=A*B 乘法）/ G（核对追溯纪录的公式区）

E1-8（fx）：
  R14 双级表头 / R15 叶子（面值/张数/原币金额/本位币金额 | 项目/金额）
  数据区 R16-29（面值行 + 汇率行 R36）
  footer R31「合计」
  公式列 C/D（C=A*B, D=C*汇率） / H（核对追溯纪录公式区）

E1-9（cert）：
  R12 双级表头 / R13 叶子（开户银行/账号/币种/户名/存入日/到期日/金额/利率）
  数据区 R14-19
  签章区 R20 / 说明区 R21-R29
  🔴 **cert 无 footer 合计行**
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_E107",
    "SPEC_E108",
    "SPEC_E109",
    "MANAGED_SHEET_E107",
    "MANAGED_SHEET_E108",
    "MANAGED_SHEET_E109",
    "STORE_ITEM_ID_E107",
    "STORE_ITEM_ID_E108",
    "STORE_ITEM_ID_E109",
    "HTML_ONLY_ITEM_IDS_E1",
    "LEGACY_SUMMARY_KEY_FX",
    "CERT_SIGNATURES_KEY",
]

# ═══════════════════════════════════════════════════════════════════════════
# 共享常量
# ═══════════════════════════════════════════════════════════════════════════

#: 行身份键 —— E1 全族统一用 `id`。
ROW_IDENTITY_STORE_KEY: Final[str] = "id"

#: 🔴 HTML-only item：三张各有 elements / audit-note / audit-conclusion 三个 per-variant
#:    文本键，在 footer 下 static_row 与插行 fail-closed 冲突 ⇒ 不受管，登记 HTML-only。
#:    与 D4-5 的 HTML_ONLY_ITEM_IDS_D45 形态逐一对应。
HTML_ONLY_ITEM_IDS_E1: Final[tuple[str, ...]] = (
    # rmb (E1-7)
    "E1-cashcount-elements-rmb",
    "E1-cashcount-audit-note-rmb",
    "E1-cashcount-audit-conclusion-rmb",
    # fx (E1-8)
    "E1-cashcount-elements-fx",
    "E1-cashcount-audit-note-fx",
    "E1-cashcount-audit-conclusion-fx",
    # cert (E1-9)
    "E1-cashcount-elements-cert",
    "E1-cashcount-audit-note-cert",
    "E1-cashcount-audit-conclusion-cert",
)

#: legacy 兜底键（双 -fx 后缀，历史键，useE1CashCount:268 仍在读）。
LEGACY_SUMMARY_KEY_FX: Final[str] = "E1-cashcount-fx-summary-fx"

#: cert 独有的签章键。
CERT_SIGNATURES_KEY: Final[str] = "E1-cert-signatures"


# ═══════════════════════════════════════════════════════════════════════════
# E1-7 库存现金（人民币）盘点表
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_E107: Final[str] = "库存现金（人民币）盘点表E1-7"
TEMPLATE_ID_E107: Final[str] = "E17"
SHEET_KEY_E107: Final[str] = f"{TEMPLATE_ID_E107.lower()}-managed"
ROWS_TABLE_KEY_E107: Final[str] = "cash_count_rmb_rows"

#: 🔴 按值 grep 实测（useE1CashCount.ts:98-99 模板化 `E1-cash-count-${variant}-rows`）。
STORE_ITEM_ID_E107: Final[str] = "E1-cash-count-rmb-rows"

HEADER_GROUP_ROW_E107: Final[int] = 14
HEADER_LEAF_ROW_E107: Final[int] = 15
FIRST_DATA_ROW_E107: Final[int] = 16
LAST_DATA_ROW_E107: Final[int] = 28
FOOTER_ROW_E107: Final[int] = 29
FOOTER_MARKER_E107: Final[str] = "合计"
MANAGED_LAST_COL_E107: Final[str] = "G"
UUID_COL_E107: Final[str] = "H"

#: 受管字段（7 元组）。
#: 左侧清点区 A/B/C + 右侧核对区 D/G。C 列公式 =A*B（面值×张数）。
FIELD_SPECS_E107: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("denomination", "A", "editable", "amount", "denomination", "货币面值", ""),
    ("count", "B", "editable", "integer", "count", "张数", ""),
    ("amount", "C", "formula", "amount", "amount", "人民币余额", ""),
    ("item", "D", "editable", "text", "item", "项目", ""),
    ("check_amount", "G", "editable", "amount", "checkAmount", "金额", ""),
)

FORMULA_TEMPLATES_E107: Final[dict[str, str]] = {
    "C": "=A{r}*B{r}",
}

SPEC_E107: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E107,
    sheet_key=SHEET_KEY_E107,
    table_key=ROWS_TABLE_KEY_E107,
    template_id=TEMPLATE_ID_E107,
    table_name=f"GT_{TEMPLATE_ID_E107}_ROWS",
    uuid_col=UUID_COL_E107,
    first_data_row=FIRST_DATA_ROW_E107,
    last_data_row=LAST_DATA_ROW_E107,
    footer_row=FOOTER_ROW_E107,
    header_group_row=HEADER_GROUP_ROW_E107,
    header_leaf_row=HEADER_LEAF_ROW_E107,
    store_item_id=STORE_ITEM_ID_E107,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_E107,
    formula_columns=("C",),
    formula_templates=FORMULA_TEMPLATES_E107,
    footer_marker=FOOTER_MARKER_E107,
    html_only_item_ids=tuple(k for k in HTML_ONLY_ITEM_IDS_E1 if k.endswith("-rmb")),
    error_label="E1-7 库存现金(人民币)盘点表",
)


# ═══════════════════════════════════════════════════════════════════════════
# E1-8 库存现金（外币）盘点表
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_E108: Final[str] = "库存现金（外币）盘点表E1-8"
TEMPLATE_ID_E108: Final[str] = "E18"
SHEET_KEY_E108: Final[str] = f"{TEMPLATE_ID_E108.lower()}-managed"
ROWS_TABLE_KEY_E108: Final[str] = "cash_count_fx_rows"

#: 🔴 按值 grep 实测。
STORE_ITEM_ID_E108: Final[str] = "E1-cash-count-fx-rows"

HEADER_GROUP_ROW_E108: Final[int] = 14
HEADER_LEAF_ROW_E108: Final[int] = 15
FIRST_DATA_ROW_E108: Final[int] = 16
LAST_DATA_ROW_E108: Final[int] = 29
FOOTER_ROW_E108: Final[int] = 31
FOOTER_MARKER_E108: Final[str] = "合计"
MANAGED_LAST_COL_E108: Final[str] = "H"
UUID_COL_E108: Final[str] = "I"

#: 受管字段。C=A*B（原币）/ D=C*汇率（本位币），右侧 E/H 核对区。
FIELD_SPECS_E108: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("denomination", "A", "editable", "amount", "denomination", "货币面值", ""),
    ("count", "B", "editable", "integer", "count", "张数", ""),
    ("amount_original", "C", "formula", "amount", "amountOriginal", "原币金额", ""),
    ("amount_local", "D", "formula", "amount", "amountLocal", "本位币金额", ""),
    ("item", "E", "editable", "text", "item", "项目", ""),
    ("check_amount", "H", "editable", "amount", "checkAmount", "金额", ""),
)

FORMULA_TEMPLATES_E108: Final[dict[str, str]] = {
    "C": "=A{r}*B{r}",
    "D": "=C{r}*$H$36",
}

SPEC_E108: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E108,
    sheet_key=SHEET_KEY_E108,
    table_key=ROWS_TABLE_KEY_E108,
    template_id=TEMPLATE_ID_E108,
    table_name=f"GT_{TEMPLATE_ID_E108}_ROWS",
    uuid_col=UUID_COL_E108,
    first_data_row=FIRST_DATA_ROW_E108,
    last_data_row=LAST_DATA_ROW_E108,
    footer_row=FOOTER_ROW_E108,
    header_group_row=HEADER_GROUP_ROW_E108,
    header_leaf_row=HEADER_LEAF_ROW_E108,
    store_item_id=STORE_ITEM_ID_E108,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_E108,
    formula_columns=("C", "D"),
    formula_templates=FORMULA_TEMPLATES_E108,
    footer_marker=FOOTER_MARKER_E108,
    html_only_item_ids=tuple(k for k in HTML_ONLY_ITEM_IDS_E1 if k.endswith("-fx")),
    error_label="E1-8 库存现金(外币)盘点表",
)


# ═══════════════════════════════════════════════════════════════════════════
# E1-9 银行存单盘点表
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_E109: Final[str] = "银行存单盘点表E1-9"
TEMPLATE_ID_E109: Final[str] = "E19"
SHEET_KEY_E109: Final[str] = f"{TEMPLATE_ID_E109.lower()}-managed"
ROWS_TABLE_KEY_E109: Final[str] = "cash_count_cert_rows"

#: 🔴 按值 grep 实测。
STORE_ITEM_ID_E109: Final[str] = "E1-cash-count-cert-rows"

#: 🔴 cert 无 footer 合计行。R12 双级表头 / R13 叶子 / 数据区 R14-19 / 签章区 R20。
HEADER_GROUP_ROW_E109: Final[int] = 12
HEADER_LEAF_ROW_E109: Final[int] = 13
FIRST_DATA_ROW_E109: Final[int] = 14
LAST_DATA_ROW_E109: Final[int] = 19
FOOTER_ROW_E109: Final[int] = 20
FOOTER_MARKER_E109: Final[str] = "出纳"
MANAGED_LAST_COL_E109: Final[str] = "O"
UUID_COL_E109: Final[str] = "P"

#: 受管字段。cert 变体字段更多（开户银行/账号/币种/户名/存入日/到期日/金额/利率/结果/…）。
FIELD_SPECS_E109: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("bank", "A", "editable", "text", "bank", "开户银行（或机构）", ""),
    ("account_no", "B", "editable", "text", "accountNo", "账号", ""),
    ("currency", "C", "editable", "text", "currency", "币种", ""),
    ("account_name", "D", "editable", "text", "accountName", "户名", ""),
    ("deposit_date", "E", "editable", "text", "depositDate", "存入日期", ""),
    ("maturity_date", "F", "editable", "text", "maturityDate", "到期日", ""),
    ("amount", "G", "editable", "amount", "amount", "金额", ""),
    ("interest_rate", "H", "editable", "text", "interestRate", "…", ""),
    ("check_result", "I", "editable", "text", "result", "是否与账面记录核对一致", ""),
    ("inconsistency", "J", "editable", "text", "inconsistency", "不一致的情况描述", ""),
    ("pledge_status", "K", "editable", "text", "pledgeStatus", "是否抵押、质押受限", ""),
    ("cert_index", "L", "editable", "text", "certIndex", "银行存单原件索引号", ""),
    ("proof_index", "M", "editable", "text", "proofIndex", "开户证明索引号", ""),
    ("custody_index", "N", "editable", "text", "custodyIndex", "银行代保管证明索引号", ""),
    ("remark", "O", "editable", "text", "remark", "备注", ""),
)

FORMULA_TEMPLATES_E109: Final[dict[str, str]] = {}

SPEC_E109: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E109,
    sheet_key=SHEET_KEY_E109,
    table_key=ROWS_TABLE_KEY_E109,
    template_id=TEMPLATE_ID_E109,
    table_name=f"GT_{TEMPLATE_ID_E109}_ROWS",
    uuid_col=UUID_COL_E109,
    first_data_row=FIRST_DATA_ROW_E109,
    last_data_row=LAST_DATA_ROW_E109,
    footer_row=FOOTER_ROW_E109,
    header_group_row=HEADER_GROUP_ROW_E109,
    header_leaf_row=HEADER_LEAF_ROW_E109,
    store_item_id=STORE_ITEM_ID_E109,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_E109,
    formula_columns=(),
    formula_templates=FORMULA_TEMPLATES_E109,
    footer_marker=FOOTER_MARKER_E109,
    html_only_item_ids=tuple(k for k in HTML_ONLY_ITEM_IDS_E1 if k.endswith("-cert")),
    error_label="E1-9 银行存单盘点表",
)
