# -*- coding: utf-8 -*-
"""F3-1「审定表」—— 双区 sheet 层薄声明。

spec: f3-sync-coverage-and-first-canary · Task 19 · Requirements 6.1~6.4
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何 ═══

两级表头 **R5/R6**：
  R5: A 项目 / B:E 期初数 / F:J 期末数（A5:A6 / B5:E5 / F5:J5 三处合并）
  R6: B 未审数 / C 账项调整 / D 重分类调整 / E 审定数 / F 未审数 / G 账项调整 /
      H 重分类调整 / I 审定数 / J 索引

═══ 双区结构（裁决 F3-H4，D3-4 先例）═══

**种子区（R7-R8）**：银行承兑汇票 / 商业承兑汇票——固定类别行。
  公式列：B（SUMPRODUCT）/ E（=B+C+D）/ F（SUMPRODUCT）/ G（SUMPRODUCT）/
          H（SUMPRODUCT）/ I（SUMPRODUCT）= 6 列全公式。
  editable 列：C 期初账项调整 / D 期初重分类调整 / J 索引。
  🔴 A 列不可受管：A7/A8 是 SUMPRODUCT 匹配键，改标签会让取数静默归零。

**空槽区（R9-R10）**：预留扩展行。
  公式列：E（=B+C+D）/ I（=F+G+H）= 2 列公式。
  editable 列：A 类别名 / B 期初未审 / C 期初调整 / D 期初重分 / F 期末未审 /
              G 期末调整 / H 期末重分 / J 索引。

两区共享 `sheet_key="f31-managed"`，区级唯一性靠 `table_key` + `uuid_col`。
uuid_col 种子 K / 空槽 L（max_col=L 以内，无需扩列）。

═══ 口径说明 ═══

列的 editable / formula 分配**由模板物理公式决定**（实测事实），不依赖三家统一口径裁决。
口径裁决（F1 spec 需求 7.3）影响的是前端 `buildRow` 的取数源（从 TB 还是从明细表
SUMPRODUCT 取值），属前端逻辑层面，不影响本声明文件的 field_specs。

R11 = `合计`（`=SUM(B7:B10)` 全列），不进受管区（由模板 SUM 覆盖）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F301_SEED",
    "SPEC_F301_SLOT",
    "MANAGED_SHEET_F301",
]

MANAGED_SHEET_F301: Final[str] = "审定表F3-1"
SHEET_KEY_F301: Final[str] = "f31-managed"

ROW_IDENTITY_KEY: Final[str] = "rowKey"

# ═══════════════════════════════════════════════════════════════════════════
# 种子区（R7-R8）：银行承兑汇票 / 商业承兑汇票
# ═══════════════════════════════════════════════════════════════════════════
#
# 6 列公式（B/E/F/G/H/I），A 不可受管，C/D/J 可编辑。

_FIELD_SPECS_SEED: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    # A 列不可受管（SUMPRODUCT 匹配键）
    ("prior_unadjusted",   "B", "formula",  "amount", "priorUnadjusted",  "期初未审数",       ""),
    ("prior_aje",          "C", "editable", "amount", "priorAje",         "期初账项调整",     ""),
    ("prior_rje",          "D", "editable", "amount", "priorRje",         "期初重分类调整",   ""),
    ("prior_audited",      "E", "formula",  "amount", "priorAudited",     "期初审定数",       ""),
    ("end_unadjusted",     "F", "formula",  "amount", "endUnadjusted",    "期末未审数",       ""),
    ("end_aje",            "G", "formula",  "amount", "endAje",           "期末账项调整",     ""),
    ("end_rje",            "H", "formula",  "amount", "endRje",           "期末重分类调整",   ""),
    ("end_audited",        "I", "formula",  "amount", "endAudited",       "期末审定数",       ""),
    ("index_ref",          "J", "editable", "text",   "indexRef",         "索引",             ""),
)

SPEC_F301_SEED: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F301,
    sheet_key=SHEET_KEY_F301,
    table_key="adjudication_seed_rows",
    template_id="F31S",
    table_name="GT_F31_SEED_ROWS",
    uuid_col="K",
    first_data_row=7,
    last_data_row=8,
    footer_row=11,
    header_group_row=5,
    header_leaf_row=6,
    store_item_id="F3-1-adj-seed-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_SEED,
    formula_columns=("B", "E", "F", "G", "H", "I"),
    formula_templates={
        "E": "=B{r}+C{r}+D{r}",
    },
    footer_marker="合计",
    error_label="F3-1 审定表种子区（R7-R8）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 空槽区（R9-R10）：预留扩展行
# ═══════════════════════════════════════════════════════════════════════════
#
# 2 列公式（E/I），其余可编辑（A/B/C/D/F/G/H/J）。

_FIELD_SPECS_SLOT: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("category",           "A", "editable", "text",   "category",         "项目",             ""),
    ("prior_unadjusted",   "B", "editable", "amount", "priorUnadjusted",  "期初未审数",       ""),
    ("prior_aje",          "C", "editable", "amount", "priorAje",         "期初账项调整",     ""),
    ("prior_rje",          "D", "editable", "amount", "priorRje",         "期初重分类调整",   ""),
    ("prior_audited",      "E", "formula",  "amount", "priorAudited",     "期初审定数",       ""),
    ("end_unadjusted",     "F", "editable", "amount", "endUnadjusted",    "期末未审数",       ""),
    ("end_aje",            "G", "editable", "amount", "endAje",           "期末账项调整",     ""),
    ("end_rje",            "H", "editable", "amount", "endRje",           "期末重分类调整",   ""),
    ("end_audited",        "I", "formula",  "amount", "endAudited",       "期末审定数",       ""),
    ("index_ref",          "J", "editable", "text",   "indexRef",         "索引",             ""),
)

SPEC_F301_SLOT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F301,
    sheet_key=SHEET_KEY_F301,
    table_key="adjudication_slot_rows",
    template_id="F31T",
    table_name="GT_F31_SLOT_ROWS",
    uuid_col="L",
    first_data_row=9,
    last_data_row=10,
    footer_row=11,
    header_group_row=5,
    header_leaf_row=6,
    store_item_id="F3-1-adj-slot-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_SLOT,
    formula_columns=("E", "I"),
    formula_templates={
        "E": "=B{r}+C{r}+D{r}",
        "I": "=F{r}+G{r}+H{r}",
    },
    footer_marker="合计",
    error_label="F3-1 审定表空槽区（R9-R10）",
)
