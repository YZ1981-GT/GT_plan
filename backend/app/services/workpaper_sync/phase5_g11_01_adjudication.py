# -*- coding: utf-8 -*-
"""G11-1「投资收益审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测）═══

单区 79r×11c, 161f, 19IF：
  R7-R24 数据(18行), 合计R25, TB R26, 差异R27。

列结构（A-K, 11 列）：
  A  项目（editable）
  B  未审数-期初（cross_sheet，SUMIF 跨sheet 明细分析表G11-2）
  C  AJE-期初（cross_sheet）
  D  审定数-期初（=B+C，formula）
  E  未审数-期末（cross_sheet）
  F  AJE-期末（cross_sheet）
  G  审定数-期末（=E+F，formula）
  H  变动额（=D-G，formula）
  I  变动率（=IF(...)，formula）
  J  审计说明标题（header only）
  K  空

🔴 表头区列引用是 C3/G3/K3（不是其他表的 D3/G3/J3）。
🔴 B-I 数据行全公式（SUMIF 跨 sheet 明细分析表 G11-2）。
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

__all__ = ["SPEC_G1101", "MANAGED_SHEET_G1101"]

MANAGED_SHEET_G1101: Final[str] = "审定表G11-1"
TEMPLATE_ID_G1101: Final[str] = "G111"
SHEET_KEY_G1101: Final[str] = f"{TEMPLATE_ID_G1101.lower()}-managed"

SECTION_MAIN: Final[AdjudicationSection] = AdjudicationSection(
    section_key="main",
    table_key="adj_main_rows",
    title_row=7,
    first_data_row=7,
    last_data_row=24,
    subtotal_row=25,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G1101}MAIN",
)

# ── field_specs（9 元组）──────────────────────────────────────────────────

_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "cross_sheet", "amount", "priorUnadjusted", "未审数", "C3"),
    ("prior_aje", "C", "cross_sheet", "amount", "priorAje", "审计调整数", "C3"),
    ("prior_audited", "D", "formula", "amount", "priorAudited", "审定数", "C3"),
    ("current_unadjusted", "E", "cross_sheet", "amount", "currentUnadjusted", "未审数", "G3"),
    ("current_aje", "F", "cross_sheet", "amount", "currentAje", "审计调整数", "G3"),
    ("current_audited", "G", "formula", "amount", "currentAudited", "审定数", "G3"),
    ("change_amount", "H", "formula", "amount", "changeAmount", "增减变动额", "K3"),
    ("change_rate", "I", "formula", "ratio", "changeRate", "增减变动率", "K3"),
)


def _build_cell_mask() -> tuple[str, ...]:
    """逐格 formula mask（大写 A1 形态，实测所有公式格）。"""
    cells: list[str] = []

    # B-I 数据行全公式（R7-R24）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        for row in range(7, 25):
            cells.append(f"{col}{row}")
    # 合计 R25
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}25")
    # 差异 R27 (D/G 列)
    for col in ("D", "G"):
        cells.append(f"{col}27")

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

SPEC_G1101: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G1101,
    sheet_key=SHEET_KEY_G1101,
    template_id=TEMPLATE_ID_G1101,
    header_rows=(5, 6),
    sections=(SECTION_MAIN,),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=25,
    tb_row=26,
    diff_row=27,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
