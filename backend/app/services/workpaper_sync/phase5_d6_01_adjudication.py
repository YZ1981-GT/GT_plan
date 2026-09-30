# -*- coding: utf-8 -*-
"""审定表D6-1 —— `AdjudicationSheetSpec` 实例声明。

spec: d567-sync-coverage-via-row-table-engine · Task 18 · Requirements 2.6

═══ 几何（openpyxl 直读 2026-09-26）═══

43r × 13c(M) / **177 公式**（四循环里最高，密度 32%）。

三区块：
  区1 原值(block1)：R7='一、合同资产原值'，数据 R8-R12（5行分类），小计 R13，
     减项 R14，合计 R15。
  区2 坏账准备(block2)：R16='二、合同资产坏账准备'，数据 R17-R21（5行=A8公式引用），
     小计 R22，减项 R23，合计 R24。
  区3 净值(block3)：R25='三、合同资产净值'，数据 R26-R30（=区1-区2 派生），
     小计 R31，减项 R32，合计 R33。
  调节：R34 TB / R35 差异（E35/I35）。

🔴 D6-1 前端用**动态行**（block1/block2 有 rowKeys 可增删），但模板是固定 5 行。
   声明仍按 fixed_rows 处理（模板几何固定，前端动态行在 JSON store 层面，不影响 Excel 行数）。

per-cell `D6-1-adj-{blockKey}-{rowKey}-{field}`, blockKey ∈ {block1, block2, block3}。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode, AdjudicationSection, AdjudicationSheetSpec, AdjudicationValueSource,
)

__all__ = ["SPEC_D601", "MANAGED_SHEET_D601"]

MANAGED_SHEET_D601: Final[str] = "审定表D6-1"
TEMPLATE_ID_D601: Final[str] = "D61"
SHEET_KEY_D601: Final[str] = f"{TEMPLATE_ID_D601.lower()}-managed"

SECTION_ORIGINAL: Final[AdjudicationSection] = AdjudicationSection(
    section_key="block1",
    table_key="adj_original_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=12,
    subtotal_row=13,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D601}BLOCK1",
)

SECTION_IMPAIRMENT: Final[AdjudicationSection] = AdjudicationSection(
    section_key="block2",
    table_key="adj_impairment_rows",
    title_row=16,
    first_data_row=17,
    last_data_row=21,
    subtotal_row=22,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D601}BLOCK2",
)

SECTION_NET: Final[AdjudicationSection] = AdjudicationSection(
    section_key="block3",
    table_key="adj_net_rows",
    title_row=25,
    first_data_row=26,
    last_data_row=30,
    subtotal_row=31,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D601}BLOCK3",
)

_FIELD_SPECS_D601: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "formula", "amount", "priorUnadjusted", "未审数", "B5"),
    ("prior_aje", "C", "formula", "amount", "priorAje", "账项调整", "B5"),
    ("prior_rje", "D", "formula", "amount", "priorRje", "重分类调整", "B5"),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "审定数", "B5"),
    ("current_unadjusted", "F", "formula", "amount", "currentUnadjusted", "未审数", "F5"),
    ("current_aje", "G", "formula", "amount", "currentAje", "账项调整", "F5"),
    ("current_rje", "H", "formula", "amount", "currentRje", "重分类调整", "F5"),
    ("current_audited", "I", "formula", "amount", "currentAudited", "审定数", "F5"),
    ("change_amount", "J", "formula", "amount", "changeAmount", "变动额", "J5"),
    ("change_rate", "K", "formula", "ratio", "changeRate", "变动率", "J5"),
    ("reason_analysis", "L", "editable", "text", "reasonAnalysis", "原因分析", ""),
)


def _build_cell_mask() -> tuple[str, ...]:
    cells: list[str] = []
    # 区1 原值 R8-R12 数据行：B-K 公式（SUMIF cross_sheet）
    for row in range(8, 13):
        for col in "BCDEFGHIJK":
            cells.append(f"{col}{row}")
    # 区1 小计 R13 + 减项 R14(仅 E/I/J/K) + 合计 R15
    for col in "BCDEFGHIJK":
        cells.append(f"{col}13")
    for col in ("E", "I", "J", "K"):
        cells.append(f"{col}14")
    for col in "BCDEFGHIJK":
        cells.append(f"{col}15")

    # 区2 坏账 R17-R21：B-K / 小计 R22 / 减项 R23(E/I/J/K) / 合计 R24
    for row in range(17, 22):
        for col in "BCDEFGHIJK":
            cells.append(f"{col}{row}")
    for col in "BCDEFGHIJK":
        cells.append(f"{col}22")
    for col in ("E", "I", "J", "K"):
        cells.append(f"{col}23")
    for col in "BCDEFGHIJK":
        cells.append(f"{col}24")

    # 区3 净值 R26-R30：B-H(=区1-区2 派生) + I/J/K
    for row in range(26, 31):
        for col in "BCDEFGHIJK":
            cells.append(f"{col}{row}")
    # 区3 小计 R31 / 减项 R32(B-I) / 合计 R33
    for col in "BCDEFGHIJK":
        cells.append(f"{col}31")
    for col in "BCDEFGHIJK":
        cells.append(f"{col}32")
    for col in "BCDEFGHIJK":
        cells.append(f"{col}33")

    # 差异 R35：E/I
    cells.append("E35")
    cells.append("I35")
    return tuple(sorted(set(cells)))


_CELL_MASK_D601: Final[tuple[str, ...]] = _build_cell_mask()

_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "prior_unadjusted": AdjudicationValueSource.cross_sheet,
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

_HTML_ONLY_ITEM_IDS_D601: Final[tuple[str, ...]] = (
    "D6-1-note-explanation",
    "D6-1-note-conclusion",
    "D6-1-adj-block1-rowKeys",
    "D6-1-adj-block2-rowKeys",
)

SPEC_D601: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_D601,
    sheet_key=SHEET_KEY_D601,
    template_id=TEMPLATE_ID_D601,
    header_rows=(5, 6),
    sections=(SECTION_ORIGINAL, SECTION_IMPAIRMENT, SECTION_NET),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=33,
    tb_row=34,
    diff_row=35,
    footer_marker="合同资产净值合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="D6-1-adj-{section}-{slug}-{field}",
    field_specs=_FIELD_SPECS_D601,
    cell_mask=_CELL_MASK_D601,
    value_sources=_VALUE_SOURCES,
    html_only_item_ids=_HTML_ONLY_ITEM_IDS_D601,
)
