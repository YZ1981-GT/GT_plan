# -*- coding: utf-8 -*-
"""G8-1「其他权益工具投资审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测）═══

单区 29r×11c, 100f, 12IF：
  R7=标题"公允价值", R8-R17 数据(10行), 合计R18, TB R19, 差异R20。

列结构（A-K, 11 列）：
  A  项目（R8-R9 跨sheet，R10-R17 editable）
  B  未审数-期初（跨sheet ='明细表G8-2'!...）
  C  AJE-期初（跨sheet）
  D  审定数-期初（=B+C，formula）
  E  未审数-期末（跨sheet）
  F  AJE-期末（跨sheet）
  G  审定数-期末（=E+F，formula）
  H  变动额（=D-G，formula）
  I  变动率（=IF(...)，formula）
  J  审计说明标题（header only）
  K  空

🔴 R8-R9 的 A/B/C/E/F 列是跨sheet公式。
🔴 R10-R17 的 A 列空（可编辑占位），B-I 有公式但 A 列非公式。
🔴 `row_mode = fixed_rows`：数据行由模板固定。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)

__all__ = ["SPEC_G801", "MANAGED_SHEET_G801"]

MANAGED_SHEET_G801: Final[str] = "审定表G8-1"
TEMPLATE_ID_G801: Final[str] = "G81"
SHEET_KEY_G801: Final[str] = f"{TEMPLATE_ID_G801.lower()}-managed"

SECTION_MAIN: Final[AdjudicationSection] = AdjudicationSection(
    section_key="main",
    table_key="adj_main_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=17,
    subtotal_row=18,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G801}MAIN",
)

# ── field_specs（9 元组）──────────────────────────────────────────────────

_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "editable", "amount", "priorUnadjusted", "未审数", ""),
    ("prior_aje", "C", "editable", "amount", "priorAje", "审计调整数", ""),
    ("prior_audited", "D", "formula", "amount", "priorAudited", "审定数", ""),
    ("current_unadjusted", "E", "editable", "amount", "currentUnadjusted", "未审数", ""),
    ("current_aje", "F", "editable", "amount", "currentAje", "审计调整数", ""),
    ("current_audited", "G", "formula", "amount", "currentAudited", "审定数", ""),
    ("change_amount", "H", "formula", "amount", "changeAmount", "增减变动额", ""),
    ("change_rate", "I", "formula", "ratio", "changeRate", "增减变动率", ""),
)


def _build_cell_mask() -> tuple[str, ...]:
    """逐格 formula mask（大写 A1 形态，实测所有公式格）。"""
    cells: list[str] = []

    # R8-R9：A/B/C/E/F 跨sheet + D/G/H/I 公式
    for col in ("A", "B", "C", "D", "E", "F", "G", "H", "I"):
        for row in range(8, 10):
            cells.append(f"{col}{row}")
    # R10-R17：D/G/H/I 公式（A 空，B/C/E/F 可编辑）
    for col in ("D", "G", "H", "I"):
        for row in range(10, 18):
            cells.append(f"{col}{row}")
    # 合计 R18
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}18")
    # 差异 R20 (D/G 列)
    for col in ("D", "G"):
        cells.append(f"{col}20")

    return tuple(sorted(set(cells)))


_CELL_MASK: Final[tuple[str, ...]] = _build_cell_mask()

_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "item_name": AdjudicationValueSource.manual,
    "prior_unadjusted": AdjudicationValueSource.cross_sheet,
    "prior_aje": AdjudicationValueSource.cross_sheet,
    "prior_audited": AdjudicationValueSource.computed,
    "current_unadjusted": AdjudicationValueSource.cross_sheet,
    "current_aje": AdjudicationValueSource.cross_sheet,
    "current_audited": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
}

SPEC_G801: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G801,
    sheet_key=SHEET_KEY_G801,
    template_id=TEMPLATE_ID_G801,
    header_rows=(5, 6),
    sections=(SECTION_MAIN,),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=18,
    tb_row=19,
    diff_row=20,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
