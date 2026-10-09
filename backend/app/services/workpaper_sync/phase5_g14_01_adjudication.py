# -*- coding: utf-8 -*-
"""G14-1「信用减值损失审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 4
      Requirements 1.1

═══ 几何（openpyxl 直读实测，2026-10-07）═══

单区 R7-R15（9 行数据）。合计 R16 / 试算平衡表数 R17 / 差异 R18。两级表头 R5-R6。

🔴 B/C 数据行是跨 sheet 引用（`='明细表G14-2'!...`）。
🔴 结构与 G13-1 同族，行数不同。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)

__all__ = ["SPEC_G1401", "MANAGED_SHEET_G1401"]

MANAGED_SHEET_G1401: Final[str] = "审定表G14-1"
TEMPLATE_ID_G1401: Final[str] = "G141"
SHEET_KEY_G1401: Final[str] = f"{TEMPLATE_ID_G1401.lower()}-managed"

SECTION_MAIN: Final[AdjudicationSection] = AdjudicationSection(
    section_key="main",
    table_key="adj_main_rows",
    title_row=7,
    first_data_row=7,
    last_data_row=15,
    subtotal_row=16,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G1401}MAIN",
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
    # B/C/D/G/H/I 数据行（R7-R15）
    for col in ("B", "C", "D", "G", "H", "I"):
        for row in range(7, 16):
            cells.append(f"{col}{row}")
    # 合计行 R16
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}16")
    # 差异行 R18
    for col in ("D", "G"):
        cells.append(f"{col}18")
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

SPEC_G1401: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G1401,
    sheet_key=SHEET_KEY_G1401,
    template_id=TEMPLATE_ID_G1401,
    header_rows=(5, 6),
    sections=(SECTION_MAIN,),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=16,
    tb_row=17,
    diff_row=18,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
