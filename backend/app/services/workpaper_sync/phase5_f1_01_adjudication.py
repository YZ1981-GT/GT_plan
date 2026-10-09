# -*- coding: utf-8 -*-
"""F1-1「预付账款审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: f1-sync-coverage-and-first-canary · Task 20

═══ 几何（openpyxl 直读 + requirements.md §模板实测）═══

28 行 × M 列，93 公式，无 Excel Table。两区块：

- **区1 性质区**：两级表头 6-7；数据行 **8-12**（5 行固定：货款/工程款/设备款/服务费/其他，
  与 NATURE_ROWS `goods/construction/equipment/service/other` 逐字对应）；
  合计行 **13**（`B13=SUM(B8:B12)` 等）。
- **区2 账龄区**：两级表头 15-16；数据行 **17-21**（THREE_YEAR 4 行 + R21 模板空槽）；
  合计行 **22**（`B22=SUM(B17:B21)` 等）。
- 试算行 23（`A23='试算平衡表数'`）；差异行 24（`E24=E22-E23` 等）。

═══ row_mode = fixed_rows（需求 8.1）═══

两区都是固定行数。性质区 5 个 rowKey 与 NATURE_ROWS 逐字一致；
账龄区行随口径（THREE_YEAR 4 行 + 空槽），仅 THREE_YEAR 启用。

═══ 口径分歧（裁决 F1-H4）═══

🔴 F1-1 的性质区 F 列模板 = `SUMIF(F1-2!D, A8, F1-2!O)` = Σ明细 O（期末余额），
   前端 = `aggregateByNature(rows, 'endAudited')` = Σ明细 X（审定数）。
   对齐模板意味着 AJE 来源从「手填 per-cell」变为「汇总明细 V/W」—— 属业务口径变更。
   灰度开关 `_INCLUDE_F101 = False` 直到业务确认后才翻。

═══ per-cell 锚点 ═══

`F1-adj-{section}-{rowKey}-{field}`，section ∈ {nature, aging}。
field: priorUnadjusted / priorAje / priorRje / currentUnadjusted / currentAje /
       currentRje / reasonAnalysis（audited / change / changeRate = computed 不落库）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)

__all__ = ["SPEC_F101", "MANAGED_SHEET_F101"]

MANAGED_SHEET_F101: Final[str] = "审定表F1-1"
TEMPLATE_ID_F101: Final[str] = "F11"
SHEET_KEY_F101: Final[str] = "f11-managed"
F1_ADJ_PREFIX: Final[str] = "F1-adj-"


# ── 两个 section ────────────────────────────────────────────────────────

SECTION_NATURE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="nature",
    table_key="adj_nature_rows",
    title_row=5,
    first_data_row=8,
    last_data_row=12,
    subtotal_row=13,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_F101}NATURE",
)

SECTION_AGING: Final[AdjudicationSection] = AdjudicationSection(
    section_key="aging",
    table_key="adj_aging_rows",
    title_row=14,
    first_data_row=17,
    last_data_row=21,
    subtotal_row=22,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_F101}AGING",
)


# ── 受管字段（审定表列 A-M）──────────────────────────────────────────────
# 🔴 F1-1 的列布局与 D3-1（A-L）类似但多一列 M（结论/备注）。
# 模板实测 93 公式分布：性质区 SUMIF + computed / 账龄区部分手工部分公式。
# B-K 列级默认 formula（与 D3-1 同理），A/L/M = editable。

_FIELD_SPECS_F101: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "formula", "amount", "priorUnadjusted", "未审数", "B6"),
    ("prior_aje", "C", "formula", "amount", "priorAje", "账项调整", "B6"),
    ("prior_rje", "D", "formula", "amount", "priorRje", "重分类调整", "B6"),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "审定数", "B6"),
    ("current_unadjusted", "F", "formula", "amount", "currentUnadjusted", "未审数", "F6"),
    ("current_aje", "G", "formula", "amount", "currentAje", "账项调整", "F6"),
    ("current_rje", "H", "formula", "amount", "currentRje", "重分类调整", "F6"),
    ("current_audited", "I", "formula", "amount", "currentAudited", "审定数", "F6"),
    ("change_amount", "J", "formula", "amount", "changeAmount", "变动额", "J6"),
    ("change_rate", "K", "formula", "ratio", "changeRate", "变动率", "J6"),
    ("reason_analysis", "L", "editable", "text", "reasonAnalysis", "原因分析", ""),
    ("conclusion", "M", "editable", "text", "conclusion", "结论", ""),
)


# ── 逐格 mask（93 公式，按模板实测现算）─────────────────────────────────


def _build_cell_mask() -> tuple[str, ...]:
    """构建逐格 formula mask。

    F1-1 模板 93 公式分布（requirements.md §模板实测 + openpyxl 直读复核）：
    - 性质区 R8-12 数据行：E=B+C+D / F=SUMIF / G/H=SUMIF / I=F+G+H / J=I-E / K=IF
      行 8-12 每行 B-K 含公式（性质区 B/C/D 跨 sheet SUMIF，F/G/H 同）
    - 性质区 R13 合计行：B..I SUM + J + K
    - 账龄区 R17-21 数据行：E=B+C+D / I=F+G+H / J / K（B/C/D/F/G/H 部分为手工）
      🔴 F17 公式：F='明细表F1-2'!R35（直引汇总），I='明细表F1-2'!Y35，G倒挤=I-F-H
    - 账龄区 R22 合计行：B..I SUM + J + K
    - 差异行 R24：E/I 两格
    """
    cells: list[str] = []

    # 性质区数据行 8-12：每行 B-K 全为公式
    for row in range(8, 13):
        for col in "BCDEFGHIJK":
            cells.append(f"{col}{row}")
    # 性质区合计行 13：B..K
    for col in "BCDEFGHIJK":
        cells.append(f"{col}13")

    # 账龄区数据行 17-21：E/I/J/K 为公式
    # 🔴 F17 还有 F/G（直引+倒挤），但其他行 B/C/D/F/G/H 为手工空格
    # 按模板实测：17-21 每行至少 E/I/J/K 为公式
    for row in range(17, 22):
        for col in ("E", "I", "J", "K"):
            cells.append(f"{col}{row}")
    # 账龄区 R17 额外公式：F17/G17（直引明细/倒挤）
    cells.append("F17")
    cells.append("G17")
    # 账龄区合计行 22：B..K
    for col in "BCDEFGHIJK":
        cells.append(f"{col}22")

    # 差异行 24：E/I
    cells.append("E24")
    cells.append("I24")

    return tuple(sorted(set(cells)))


_CELL_MASK_F101: Final[tuple[str, ...]] = _build_cell_mask()


# ── 值来源 ──────────────────────────────────────────────────────────────
# 🔴 current_unadjusted 模板口径从 F1-2 跨 sheet 聚合（性质区 SUMIF / 账龄区直引），
#    前端当前以 endAudited 聚合（口径分歧，裁决 F1-H4 待业务确认后修）。

_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "prior_unadjusted": AdjudicationValueSource.manual,
    "prior_aje": AdjudicationValueSource.manual,
    "prior_rje": AdjudicationValueSource.manual,
    "prior_audited": AdjudicationValueSource.computed,
    "current_unadjusted": AdjudicationValueSource.cross_sheet,
    "current_aje": AdjudicationValueSource.manual,
    "current_rje": AdjudicationValueSource.manual,
    "current_audited": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
    "reason_analysis": AdjudicationValueSource.manual,
    "conclusion": AdjudicationValueSource.manual,
}

# ── HTML-only item 子集 ─────────────────────────────────────────────────

_HTML_ONLY_ITEM_IDS_F101: Final[tuple[str, ...]] = (
    "F1-adj-note-aging-reason",
    "F1-adj-note-change-analysis",
    "F1-adj-note-conclusion",
    "F1-adj-trial-balance-amount",
)

# ── spec 实例 ───────────────────────────────────────────────────────────

SPEC_F101: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_F101,
    sheet_key=SHEET_KEY_F101,
    template_id=TEMPLATE_ID_F101,
    header_rows=(6, 7, 15, 16),
    sections=(SECTION_NATURE, SECTION_AGING),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=22,
    tb_row=23,
    diff_row=24,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template=f"{F1_ADJ_PREFIX}{{section}}-{{slug}}-{{field}}",
    field_specs=_FIELD_SPECS_F101,
    cell_mask=_CELL_MASK_F101,
    value_sources=_VALUE_SOURCES,
    html_only_item_ids=_HTML_ONLY_ITEM_IDS_F101,
)
