# -*- coding: utf-8 -*-
"""F3-4「应付票据（带息）利息测算表」—— sheet 层薄声明。

spec: f3-sync-coverage-and-first-canary · Task 16 · Requirements 4.1~4.4
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何 ═══

两级表头 **R9/R10**：R9 = A 票据类别 / B 票据号 / C 票据期限(合并 C:E) / F 票面金额 /
G 票面利率 / H 应计利息 / I 账面已计利息 / J 差异 / K 说明。
R10 = C 出票日 / D 到期日 / E 期限。

21 行数据 **R11~R31**。footer R32 `合  计`（双空格，D6-9 同型先例）。
R33 = `三、审计说明：`。

═══ 口径裁决（F3-H2，默认方向③）═══

模板 H 列：`=ROUND(F{r}*G{r},2)`（应计利息 = 票面金额 × 票面利率）
前端 H 列：`principal * rate / 100 * days / 360`（含天数分数）

两侧算法不同（模板不含天数，前端含 days/360）。三个方向：
  ① 改前端去掉 days/360 → 业务精度损失
  ② 模板覆盖层改 H 加 days → 改权威模板语义
  ③ **H 列 mode=formula 不受管**（DEFAULT）→ OO 侧用模板公式，HTML 侧用前端公式

方向③ 是安全默认：H 列是公式、不写回、不产生数据分歧。
方向①②作为 follow-up 登记，需业务确认后另行裁决。

═══ J 列 ═══

`=H{r}-I{r}`（差异 = 应计利息 - 账面已计利息），整列公式。

═══ footer 双空格 ═══

A32 = `合  计`（两个全角空格），与 F3-2 R31 同型（D6-9 先例）。

═══ G 列（票面利率）═══

模板 G 列 number_format 含 `%` —— 属 FC-10 候选。但方向③下 H 列不受管，
G 值不参与 OO→HTML 同步计算（前端有自己的 rate 字段），不阻塞受管。
G 列声明为 editable（用户在 OO 侧按模板格式输入）。

═══ UUID 列 ═══

max_col=M(13)，N 列全空 → 取 **N**。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F304",
    "MANAGED_SHEET_F304",
    "STORE_ITEM_ID_F304",
]

MANAGED_SHEET_F304: Final[str] = "应付票据（带息）利息测算表F3-4"
TEMPLATE_ID_F304: Final[str] = "F34"
SHEET_KEY_F304: Final[str] = "f34-managed"
ROWS_TABLE_KEY_F304: Final[str] = "interest_accrual_rows"
STORE_ITEM_ID_F304: Final[str] = "F3-4-rows"

ROW_IDENTITY_STORE_KEY_F304: Final[str] = "rowId"

HEADER_GROUP_ROW_F304: Final[int] = 9
HEADER_LEAF_ROW_F304: Final[int] = 10
FIRST_DATA_ROW_F304: Final[int] = 11
LAST_DATA_ROW_F304: Final[int] = 31
FOOTER_ROW_F304: Final[int] = 32
UUID_COL_F304: Final[str] = "N"

#: 🔴 footer 双空格「合  计」（D6-9 / F3-2 同型先例）
FOOTER_MARKER_F304: Final[str] = "合  计"

#: editable 字段（H/J 是公式不声明）。
#: G 列票面利率是 FC-10 百分比候选但方向③下不阻塞。
FIELD_SPECS_F304: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("note_type",         "A", "editable", "text",   "noteType",       "票据类别",       ""),
    ("note_number",       "B", "editable", "text",   "noteNumber",     "票据号",         ""),
    ("issue_date",        "C", "editable", "text",   "issueDate",      "出票日",         ""),
    ("maturity_date",     "D", "editable", "text",   "maturityDate",   "到期日",         ""),
    ("term",              "E", "editable", "text",   "term",           "期限",           ""),
    ("face_amount",       "F", "editable", "amount", "faceAmount",     "票面金额",       ""),
    ("interest_rate",     "G", "editable", "amount", "interestRate",   "票面利率",       ""),
    # H 列 = 应计利息 = ROUND(F*G,2)，mode=formula（方向③不受管）
    ("accrued_interest",  "H", "formula",  "amount", "accruedInterest", "应计利息",      ""),
    ("book_interest",     "I", "editable", "amount", "bookInterest",   "账面已计利息",   ""),
    # J 列 = 差异 = H-I，mode=formula
    ("diff",              "J", "formula",  "amount", "diff",           "差异",           ""),
    ("remark",            "K", "editable", "text",   "remark",         "说明",           ""),
)

FORMULA_COLUMNS_F304: Final[tuple[str, ...]] = ("H", "J")
FORMULA_TEMPLATES_F304: Final[dict[str, str]] = {
    "H": "=ROUND(F{r}*G{r},2)",
    "J": "=H{r}-I{r}",
}

SPEC_F304: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F304,
    sheet_key=SHEET_KEY_F304,
    table_key=ROWS_TABLE_KEY_F304,
    template_id=TEMPLATE_ID_F304,
    table_name=f"GT_{TEMPLATE_ID_F304}_ROWS",
    uuid_col=UUID_COL_F304,
    first_data_row=FIRST_DATA_ROW_F304,
    last_data_row=LAST_DATA_ROW_F304,
    footer_row=FOOTER_ROW_F304,
    header_group_row=HEADER_GROUP_ROW_F304,
    header_leaf_row=HEADER_LEAF_ROW_F304,
    store_item_id=STORE_ITEM_ID_F304,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F304,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F304,
    formula_columns=FORMULA_COLUMNS_F304,
    formula_templates=FORMULA_TEMPLATES_F304,
    footer_marker=FOOTER_MARKER_F304,
    error_label="F3-4 应付票据利息测算表",
)
