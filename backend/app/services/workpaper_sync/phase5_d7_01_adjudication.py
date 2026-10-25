# -*- coding: utf-8 -*-
"""审定表D7-1 —— `AdjudicationSheetSpec` 实例声明。

spec: d567-sync-coverage-via-row-table-engine · Task 19 · Requirements 3.5

═══ 几何（openpyxl 直读 2026-09-26）═══

32r × 12c(L) / 84f。与 D3-1 结构高度相似（两区：性质+账龄）。

区1 性质分类(R5)：表头 R6-R7，数据 R8-R13（6行：预收货款/开发项目/预收工程款/空/空/其他），
  小计 R14，减项 R15，合计 R16。
区2 账龄分类(R17)：表头 R18-R19，数据 R20-R23（4行），合计 R24。
调节：R25 TB / R26 差异（E26/I26）。

per-cell `D7-1-adj-{block}-{rowKey}-{field}`, block ∈ {nature, aging}。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode, AdjudicationSection, AdjudicationSheetSpec, AdjudicationValueSource,
)

__all__ = ["SPEC_D701", "MANAGED_SHEET_D701"]

MANAGED_SHEET_D701: Final[str] = "审定表D7-1"
TEMPLATE_ID_D701: Final[str] = "D71"
SHEET_KEY_D701: Final[str] = f"{TEMPLATE_ID_D701.lower()}-managed"

SECTION_NATURE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="nature",
    table_key="adj_nature_rows",
    title_row=5,
    first_data_row=8,
    last_data_row=13,
    subtotal_row=14,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D701}NATURE",
)

SECTION_AGING: Final[AdjudicationSection] = AdjudicationSection(
    section_key="aging",
    table_key="adj_aging_rows",
    title_row=17,
    first_data_row=20,
    last_data_row=23,
    subtotal_row=24,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D701}AGING",
)

_FIELD_SPECS_D701: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
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
)


def _build_cell_mask() -> tuple[str, ...]:
    cells: list[str] = []
    # 区1 数据行 R8-R13：**只有 E/I/J/K 是公式**（E=B+C+D / I=F+G+H / J=I-E / K=IF）。
    #
    # 🔴 修正（spec d567-sync-coverage Task 20）：原声明按 `B-K` 整行 mask，注释写「性质区有
    #    SUMIF cross_sheet 公式」——**模板实测该前提不成立**：`审定表D7-1` 的 R8-R13 里
    #    B/C/D/F/G/H **全部为空**（无任何公式），SUMIF 只存在于 D5-1 那种表。整行 mask
    #    把审计师手工录入的期初未审/AJE/RJE/期末 AJE/RJE **锁死 36 格**（OO 里改不了）
    #    = D4-1 踩过的「列向区间把受管金额字段整列误判只读」同型 fail-closed 缺陷。
    #
    # 🔴 表内自证：**同一张表**的区2（账龄 R20-R23）模板形态与区1 完全一致，声明却只 mask
    #    E/I/J/K —— 两区声明自相矛盾，坐实区1 是错的一侧。
    for row in range(8, 14):
        for col in ("E", "I", "J", "K"):
            cells.append(f"{col}{row}")
    # 区1 小计 R14
    for col in "BCDEFGHIJK":
        cells.append(f"{col}14")
    # 区1 减项 R15：E/I/J/K
    for col in ("E", "I", "J", "K"):
        cells.append(f"{col}15")
    # 区1 合计 R16
    for col in "BCDEFGHIJK":
        cells.append(f"{col}16")
    # 区2 数据行 R20-R23：E/I/J/K（账龄区无 SUMIF，B/C/D/F/G/H 手工）
    for row in range(20, 24):
        for col in ("E", "I", "J", "K"):
            cells.append(f"{col}{row}")
    # 区2 合计 R24
    for col in "BCDEFGHIJK":
        cells.append(f"{col}24")
    # 差异 R26：E/I
    cells.append("E26")
    cells.append("I26")
    return tuple(sorted(set(cells)))


_CELL_MASK_D701: Final[tuple[str, ...]] = _build_cell_mask()

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
}

_HTML_ONLY_ITEM_IDS_D701: Final[tuple[str, ...]] = (
    "D7-1-note-explanation",
    "D7-1-note-conclusion",
    "D7-1-note-aging-explanation",
    "D7-1-adj-aging-trial-balance-currentAudited",
)

SPEC_D701: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_D701,
    sheet_key=SHEET_KEY_D701,
    template_id=TEMPLATE_ID_D701,
    header_rows=(6, 7, 18, 19),
    sections=(SECTION_NATURE, SECTION_AGING),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=24,
    tb_row=25,
    diff_row=26,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="D7-1-adj-{section}-{slug}-{field}",
    field_specs=_FIELD_SPECS_D701,
    cell_mask=_CELL_MASK_D701,
    value_sources=_VALUE_SOURCES,
    html_only_item_ids=_HTML_ONLY_ITEM_IDS_D701,
)
