# -*- coding: utf-8 -*-
"""F4-1「审定表」—— 三区 sheet 层薄声明。

spec: f4-sync-coverage-and-first-canary · Task 19 · Requirements 6.1~6.4
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 三区结构（裁决 F4-H4，实测修正「两区」→「三区」）═══

**性质区 R8~R12**（5 行固定类别：货款/工程款/设备款/服务费/其他）：
  公式列 7：E(=B+C+D) / F(SUMIF) / G(SUMIF) / H(SUMIF) / I(=F+G+H) / J(=I-E) / K(变动率 IF)
  editable 列 4：B 期初未审 / C 期初调整 / D 期初重分 / L 原因分析
  🔴 A 列不可受管（SUMIF 匹配键）。

**账龄种子区 R17~R20**（4 行固定账龄段）：
  公式列 6：E(=B+C+D) / F(直引明细表合计行) / G(=I-F-H 倒算) / I(直引明细表) / J(=I-E) / K(变动率)
  editable 列 5：B 期初未审 / C 期初调整 / D 期初重分 / H 期末重分 / L 原因分析
  🔴 A 列是账龄标签（值，但 SUMIF 不引用它）。

**账龄空槽区 R21**（1 行预留扩展）：
  公式列 4：E(=B+C+D) / I(=F+G+H) / J(=I-E) / K(变动率)
  editable 列 8：A 类别名 / B 期初未审 / C 调整 / D 重分 / F 期末未审 / G 调整 / H 重分 / L 原因

三区共享 `sheet_key="f41-managed"`。uuid_col：性质 M / 种子 N / 空槽 O（max_col=L=12，M 起全空）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F401_NATURE",
    "SPEC_F401_AGING_SEED",
    "SPEC_F401_AGING_SLOT",
    "MANAGED_SHEET_F401",
]

MANAGED_SHEET_F401: Final[str] = "审定表F4-1"
SHEET_KEY_F401: Final[str] = "f41-managed"
ROW_IDENTITY_KEY: Final[str] = "rowKey"

# ═══════════════════════════════════════════════════════════════════════════
# 性质区（R8-R12）：货款/工程款/设备款/服务费/其他
# ═══════════════════════════════════════════════════════════════════════════

_FIELD_SPECS_NATURE: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    # A 列不可受管（SUMIF 匹配键）
    ("prior_unadjusted",   "B", "editable", "amount", "priorUnadjusted",  "期初未审数",       ""),
    ("prior_aje",          "C", "editable", "amount", "priorAje",         "期初账项调整",     ""),
    ("prior_rje",          "D", "editable", "amount", "priorRje",         "期初重分类调整",   ""),
    ("prior_audited",      "E", "formula",  "amount", "priorAudited",     "期初审定数",       ""),
    ("end_unadjusted",     "F", "formula",  "amount", "endUnadjusted",    "期末未审数",       ""),
    ("end_aje",            "G", "formula",  "amount", "endAje",           "期末账项调整",     ""),
    ("end_rje",            "H", "formula",  "amount", "endRje",           "期末重分类调整",   ""),
    ("end_audited",        "I", "formula",  "amount", "endAudited",       "期末审定数",       ""),
    ("change_amount",      "J", "formula",  "amount", "changeAmount",     "变动额",           ""),
    ("change_rate",        "K", "formula",  "amount", "changeRate",       "变动率",           ""),
    ("reason",             "L", "editable", "text",   "reason",           "原因分析",         ""),
)

SPEC_F401_NATURE: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F401,
    sheet_key=SHEET_KEY_F401,
    table_key="adjudication_nature_rows",
    template_id="F41N",
    table_name="GT_F41_NATURE_ROWS",
    uuid_col="M",
    first_data_row=8,
    last_data_row=12,
    footer_row=13,
    header_group_row=6,
    header_leaf_row=7,
    store_item_id="F4-1-adj-nature-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_NATURE,
    formula_columns=("E", "F", "G", "H", "I", "J", "K"),
    formula_templates={"E": "=B{r}+C{r}+D{r}"},
    footer_marker="合计",
    error_label="F4-1 审定表性质区（R8-R12）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 账龄种子区（R17-R20）：1年以内/1至2年/2至3年/3年以上
# ═══════════════════════════════════════════════════════════════════════════

_FIELD_SPECS_AGING_SEED: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    # A 列是账龄标签（值，SUMIF 不引用）
    ("prior_unadjusted",   "B", "editable", "amount", "priorUnadjusted",  "期初未审数",       ""),
    ("prior_aje",          "C", "editable", "amount", "priorAje",         "期初账项调整",     ""),
    ("prior_rje",          "D", "editable", "amount", "priorRje",         "期初重分类调整",   ""),
    ("prior_audited",      "E", "formula",  "amount", "priorAudited",     "期初审定数",       ""),
    ("end_unadjusted",     "F", "formula",  "amount", "endUnadjusted",    "期末未审数",       ""),
    ("end_aje",            "G", "formula",  "amount", "endAje",           "期末账项调整",     ""),
    ("end_rje",            "H", "editable", "amount", "endRje",           "期末重分类调整",   ""),
    ("end_audited",        "I", "formula",  "amount", "endAudited",       "期末审定数",       ""),
    ("change_amount",      "J", "formula",  "amount", "changeAmount",     "变动额",           ""),
    ("change_rate",        "K", "formula",  "amount", "changeRate",       "变动率",           ""),
    ("reason",             "L", "editable", "text",   "reason",           "原因分析",         ""),
)

SPEC_F401_AGING_SEED: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F401,
    sheet_key=SHEET_KEY_F401,
    table_key="adjudication_aging_seed_rows",
    template_id="F41A",
    table_name="GT_F41_AGING_SEED_ROWS",
    uuid_col="N",
    first_data_row=17,
    last_data_row=20,
    footer_row=22,
    header_group_row=15,
    header_leaf_row=16,
    store_item_id="F4-1-adj-aging-seed-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_AGING_SEED,
    formula_columns=("E", "F", "G", "I", "J", "K"),
    formula_templates={"E": "=B{r}+C{r}+D{r}"},
    footer_marker="合计",
    error_label="F4-1 审定表账龄种子区（R17-R20）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 账龄空槽区（R21）：预留扩展行
# ═══════════════════════════════════════════════════════════════════════════

_FIELD_SPECS_AGING_SLOT: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("category",           "A", "editable", "text",   "category",         "项目",             ""),
    ("prior_unadjusted",   "B", "editable", "amount", "priorUnadjusted",  "期初未审数",       ""),
    ("prior_aje",          "C", "editable", "amount", "priorAje",         "期初账项调整",     ""),
    ("prior_rje",          "D", "editable", "amount", "priorRje",         "期初重分类调整",   ""),
    ("prior_audited",      "E", "formula",  "amount", "priorAudited",     "期初审定数",       ""),
    ("end_unadjusted",     "F", "editable", "amount", "endUnadjusted",    "期末未审数",       ""),
    ("end_aje",            "G", "editable", "amount", "endAje",           "期末账项调整",     ""),
    ("end_rje",            "H", "editable", "amount", "endRje",           "期末重分类调整",   ""),
    ("end_audited",        "I", "formula",  "amount", "endAudited",       "期末审定数",       ""),
    ("change_amount",      "J", "formula",  "amount", "changeAmount",     "变动额",           ""),
    ("change_rate",        "K", "formula",  "amount", "changeRate",       "变动率",           ""),
    ("reason",             "L", "editable", "text",   "reason",           "原因分析",         ""),
)

SPEC_F401_AGING_SLOT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F401,
    sheet_key=SHEET_KEY_F401,
    table_key="adjudication_aging_slot_rows",
    template_id="F41T",
    table_name="GT_F41_AGING_SLOT_ROWS",
    uuid_col="O",
    first_data_row=21,
    last_data_row=21,
    footer_row=22,
    header_group_row=15,
    header_leaf_row=16,
    store_item_id="F4-1-adj-aging-slot-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_AGING_SLOT,
    formula_columns=("E", "I", "J", "K"),
    formula_templates={
        "E": "=B{r}+C{r}+D{r}",
        "I": "=F{r}+G{r}+H{r}",
    },
    footer_marker="合计",
    error_label="F4-1 审定表账龄空槽区（R21）",
)
