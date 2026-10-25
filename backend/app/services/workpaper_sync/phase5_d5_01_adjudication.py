# -*- coding: utf-8 -*-
"""审定表D5 —— `AdjudicationSheetSpec` 实例声明。

spec: d567-sync-coverage-via-row-table-engine · Task 7 / 18 · Requirements 1.2

═══ 几何（openpyxl 直读 2026-09-26）═══

🔴 `managed_sheet="审定表D5"`——**无 -1 后缀**（裁决 G3 三处实证必错之首）。
18r × 12c(L) / 52f。两级表头 R5-R6。

逻辑上是**单区块**（不像 D3-1 有性质/账龄两区）：
  R7  应收票据（cross_sheet 从 D5-2 聚合）
  R8  应收账款（cross_sheet 从 D5-2 聚合）
  R9  小计 = SUM(R7:R8)
  R10 减：其他综合收益-公允价值变动（cross_sheet 从 D5-4）
  R11 应收款项融资公允价值合计 = R9 - R10
  R12 试算平衡表数
  R13 差异数 = R11 - R12

row_mode=fixed_rows。per-cell `D5-1-adj-{rowKey}-{field}`（无 section 维度）。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode, AdjudicationSection, AdjudicationSheetSpec, AdjudicationValueSource,
)

__all__ = ["SPEC_D501", "MANAGED_SHEET_D501"]

MANAGED_SHEET_D501: Final[str] = "审定表D5"  # 🔴 无 -1 后缀！
TEMPLATE_ID_D501: Final[str] = "D51"
SHEET_KEY_D501: Final[str] = f"{TEMPLATE_ID_D501.lower()}-managed"

#: 单区块：数据 R7-R8（应收票据/应收账款），小计 R9。
SECTION_MAIN: Final[AdjudicationSection] = AdjudicationSection(
    section_key="main",
    table_key="adj_main_rows",
    title_row=5,
    first_data_row=7,
    last_data_row=8,
    subtotal_row=9,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D501}MAIN",
)

_FIELD_SPECS_D501: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
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
    # R7-R8 数据行：B-I SUMIF / E=B+C+D / I=F+G+H / J / K
    for row in range(7, 9):
        for col in "BCDEFGHIJK":
            cells.append(f"{col}{row}")
    # R9 小计：B-I SUM + J + K
    for col in "BCDEFGHIJK":
        cells.append(f"{col}9")
    # R10 减:OCI：E/I/J/K
    for col in ("E", "I", "J", "K"):
        cells.append(f"{col}10")
    # R11 合计：B-I + J + K
    for col in "BCDEFGHIJK":
        cells.append(f"{col}11")
    # R13 差异：E/I
    cells.append("E13")
    cells.append("I13")
    return tuple(sorted(set(cells)))


_CELL_MASK_D501: Final[tuple[str, ...]] = _build_cell_mask()

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

_HTML_ONLY_ITEM_IDS_D501: Final[tuple[str, ...]] = (
    "D5-1-note-explanation",
    "D5-1-note-conclusion",
    "D5-1-adj-trial-balance-amount",
)

SPEC_D501: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_D501,
    sheet_key=SHEET_KEY_D501,
    template_id=TEMPLATE_ID_D501,
    header_rows=(5, 6),
    sections=(SECTION_MAIN,),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=11,
    tb_row=12,
    diff_row=13,
    footer_marker="应收款项融资公允价值合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="D5-1-adj-{slug}-{field}",
    field_specs=_FIELD_SPECS_D501,
    cell_mask=_CELL_MASK_D501,
    value_sources=_VALUE_SOURCES,
    html_only_item_ids=_HTML_ONLY_ITEM_IDS_D501,
)
