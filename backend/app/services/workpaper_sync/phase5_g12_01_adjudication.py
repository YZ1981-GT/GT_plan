# -*- coding: utf-8 -*-
"""G12-1「净敞口套期收益审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测，2026-10-07）═══

单区 R7-R11（5 行数据：预期销售和预期采购的外汇净头寸 + 4 行空白预留）。
合计 R12 / 试算平衡表数 R13 / 差异 R14。两级表头 R5-R6。11 列 A-K。

列结构（与 G13/G14 同族，但 B/C 数据行**非**跨 sheet 引用）：
  A  项目（editable）
  B  未审数-期初（editable —— G12 无明细表引用）
  C  AJE-期初（editable）
  D  审定数-期初（=B+C，formula）
  E  未审数-期末（editable）
  F  AJE-期末（editable）
  G  审定数-期末（=E+F，formula）
  H  变动额（=D-G，formula）
  I  变动率（=IF(...)，formula）
  J  审计说明标题（header only）
  K  空

🔴 G12-1 是全 G 循环最简审定表（38 公式格 / 7 IF / 5 数据行）。
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

__all__ = ["SPEC_G1201", "MANAGED_SHEET_G1201"]

MANAGED_SHEET_G1201: Final[str] = "审定表G12-1"
TEMPLATE_ID_G1201: Final[str] = "G121"
SHEET_KEY_G1201: Final[str] = f"{TEMPLATE_ID_G1201.lower()}-managed"

SECTION_MAIN: Final[AdjudicationSection] = AdjudicationSection(
    section_key="main",
    table_key="adj_main_rows",
    title_row=7,
    first_data_row=7,
    last_data_row=11,
    subtotal_row=12,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G1201}MAIN",
)

_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "editable", "amount", "priorUnadjusted", "未审数", "B5"),
    ("prior_aje", "C", "editable", "amount", "priorAje", "审计调整数", "B5"),
    ("prior_audited", "D", "formula", "amount", "priorAudited", "审定数", "B5"),
    ("current_unadjusted", "E", "editable", "amount", "currentUnadjusted", "未审数", "E5"),
    ("current_aje", "F", "editable", "amount", "currentAje", "审计调整数", "E5"),
    ("current_audited", "G", "formula", "amount", "currentAudited", "审定数", "E5"),
    ("change_amount", "H", "formula", "amount", "changeAmount", "增减变动额", "H5"),
    ("change_rate", "I", "formula", "ratio", "changeRate", "增减变动率", "H5"),
)


def _build_cell_mask() -> tuple[str, ...]:
    """逐格 formula mask（大写 A1 形态，实测所有公式格）。"""
    cells: list[str] = []
    # D/G/H/I 数据行（R7-R11）
    for col in ("D", "G", "H", "I"):
        for row in range(7, 12):
            cells.append(f"{col}{row}")
    # 合计行 R12 全列 SUM
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}12")
    # 差异行 R14
    for col in ("D", "G"):
        cells.append(f"{col}14")
    return tuple(sorted(set(cells)))


_CELL_MASK: Final[tuple[str, ...]] = _build_cell_mask()

_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "prior_unadjusted": AdjudicationValueSource.manual,
    "prior_aje": AdjudicationValueSource.manual,
    "prior_audited": AdjudicationValueSource.computed,
    "current_unadjusted": AdjudicationValueSource.manual,
    "current_aje": AdjudicationValueSource.manual,
    "current_audited": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
}

SPEC_G1201: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G1201,
    sheet_key=SHEET_KEY_G1201,
    template_id=TEMPLATE_ID_G1201,
    header_rows=(5, 6),
    sections=(SECTION_MAIN,),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=12,
    tb_row=13,
    diff_row=14,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
