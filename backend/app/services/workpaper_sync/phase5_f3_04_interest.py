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

模板 G 列 number_format = `0.00%`（Excel 存小数 0.036），前端 `interestRate` 存百分数（3.6）
⇒ value_type = `percent_points`（FC-10，物化 ÷100 / 回写 ×100，与 F2-47 同）。

═══ 字段名对齐前端（spec oo-writeback-template-parity-closure R3 任务 9.4c）═══

json 键逐字取前端 `useF3InterestCalc.F3InterestCalcRow`：原写 noteNumber / maturityDate / term /
faceAmount / accruedInterest / diff / remark，前端存 ticketNo / dueDate / termDays / faceValue /
payableInterest / variance / note ⇒ 整表不通。列键不变。
C / D 出票日 / 到期日模板是日期格式（`mm-dd-yy`），前端存 'YYYY-MM-DD' ⇒ value_type = date（同册 F3-5）。
E 期限模板无公式，前端按到期日 − 出票日现算、载入时覆盖存值 ⇒ auto_source（HTML 侧带出，OO 改了报受保护冲突，
不让两侧来回变值；同 E1-4 序号）。

🔴 H 列计息口径仍待用户确认（前端 票面金额 × 利率% × 期限 / 360，有日期时与模板 ROUND(F*G,2) 不同）：
H 是 formula 不回写，两侧各按自己的口径显示；对拍守卫逐样本登记（`termDays > 0` 时）。

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

#: 11 列受管字段（7 元组）；json 键逐字取前端 F3InterestCalcRow（见模块 docstring）。
FIELD_SPECS_F304: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("note_type",         "A", "editable",    "text",           "noteType",        "票据类别",     ""),
    ("note_number",       "B", "editable",    "text",           "ticketNo",        "票据号",       ""),
    ("issue_date",        "C", "editable",    "date",           "issueDate",       "出票日",       ""),
    ("maturity_date",     "D", "editable",    "date",           "dueDate",         "到期日",       ""),
    # E 期限：前端按到期日 − 出票日现算（载入即覆盖存值）⇒ HTML 侧带出
    ("term",              "E", "auto_source", "integer",        "termDays",        "期限",         ""),
    ("face_amount",       "F", "editable",    "amount",         "faceValue",       "票面金额",     ""),
    ("interest_rate",     "G", "editable",    "percent_points", "interestRate",    "票面利率",     ""),
    # H 列 = 应计利息 = ROUND(F*G,2)，mode=formula（方向③不受管；计息口径待用户确认）
    ("accrued_interest",  "H", "formula",     "amount",         "payableInterest", "应计利息",     ""),
    ("book_interest",     "I", "editable",    "amount",         "bookInterest",    "账面已计利息", ""),
    # J 列 = 差异 = H-I，mode=formula
    ("diff",              "J", "formula",     "amount",         "variance",        "差异",         ""),
    ("remark",            "K", "editable",    "text",           "note",            "说明",         ""),
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
