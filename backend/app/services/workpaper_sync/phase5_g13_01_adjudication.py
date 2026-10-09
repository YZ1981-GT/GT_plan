# -*- coding: utf-8 -*-
"""G13-1「公允价值变动收益审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 3
      Requirements 1.1

═══ 几何（openpyxl 直读实测，2026-10-07）═══

单区 R7-R16（10 行数据）。合计 R17 / 试算平衡表数 R18 / 差异 R19。两级表头 R5-R6。

🔴 B/C 数据行是跨 sheet 引用（`='明细表G13-2'!...`）—— 与 G12 不同。
🔴 R7 的 B/C 是 SUM 汇总行（=B8+B9），I7 引用 G9 而非 G7（模板原文，不修）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)

__all__ = ["SPEC_G1301", "MANAGED_SHEET_G1301"]

MANAGED_SHEET_G1301: Final[str] = "审定表G13-1"
TEMPLATE_ID_G1301: Final[str] = "G131"
SHEET_KEY_G1301: Final[str] = f"{TEMPLATE_ID_G1301.lower()}-managed"

SECTION_MAIN: Final[AdjudicationSection] = AdjudicationSection(
    section_key="main",
    table_key="adj_main_rows",
    title_row=7,
    first_data_row=7,
    last_data_row=16,
    subtotal_row=17,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G1301}MAIN",
)

_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "formula", "amount", "priorUnadjusted", "未审数", "B5"),
    ("prior_aje", "C", "formula", "amount", "priorAje", "审计调整数", "B5"),
    ("prior_audited", "D", "formula", "amount", "priorAudited", "审定数", "B5"),
    ("current_unadjusted", "E", "editable", "amount", "currentUnadjusted", "未审数", "E5"),
    ("current_aje", "F", "editable", "amount", "currentAje", "审计调整数", "E5"),
    ("current_audited", "G", "formula", "amount", "currentAudited", "审定数", "E5"),
    ("change_amount", "H", "formula", "amount", "changeAmount", "增减变动额", "H5"),
    ("change_rate", "I", "formula", "ratio", "changeRate", "增减变动率", "H5"),
)


def _build_cell_mask() -> tuple[str, ...]:
    cells: list[str] = []
    # B/C/D/G/H/I 数据行（R7-R16）
    for col in ("B", "C", "D", "G", "H", "I"):
        for row in range(7, 17):
            cells.append(f"{col}{row}")
    # 合计行 R17
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}17")
    # 差异行 R19
    for col in ("D", "G"):
        cells.append(f"{col}19")
    return tuple(sorted(set(cells)))


_CELL_MASK: Final[tuple[str, ...]] = _build_cell_mask()

_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "prior_unadjusted": AdjudicationValueSource.cross_sheet,
    "prior_aje": AdjudicationValueSource.cross_sheet,
    "prior_audited": AdjudicationValueSource.computed,
    "current_unadjusted": AdjudicationValueSource.manual,
    "current_aje": AdjudicationValueSource.manual,
    "current_audited": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
}

SPEC_G1301: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G1301,
    sheet_key=SHEET_KEY_G1301,
    template_id=TEMPLATE_ID_G1301,
    header_rows=(5, 6),
    sections=(SECTION_MAIN,),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=17,
    tb_row=18,
    diff_row=19,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
