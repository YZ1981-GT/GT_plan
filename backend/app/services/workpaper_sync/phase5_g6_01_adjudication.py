# -*- coding: utf-8 -*-
"""G6-1「其他债权投资审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测，2026-10-07）═══

三区 76r×11c, 340f, 48IF：
  公允价值/原值  R7=标题, R8-R21（15 行数据）
      R8-R10 A 列有明细表引用, R11-R16 无引用数据, R21=原值小计
  累计变动       R22=标题, R23-R36
      R36=变动小计
  账面余额       R37=标题, R38-R51
      全公式=原值+变动, R51=账面余额合计

合计 R51 / TB R52 / 差异 R53。两级表头 R5-R6。11 列 A-K。
表头引用 D3/G3/J3。

列结构（与 G10 同族，B-I 受管）：
  A  项目（editable）
  B  未审数-期初
  C  AJE-期初
  D  审定数-期初（=B+C，formula）
  E  未审数-期末
  F  AJE-期末
  G  审定数-期末（=E+F，formula）
  H  变动额（=G-D，formula）
  I  变动率（=IF(...)，formula）
  J-K 空

🔴 前两区数据行部分有 A/B/C 引用明细表（R8-R10）。
🔴 第三区（账面余额）全公式=公允价值+累计变动。
🔴 差异行只有 D/G。
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

__all__ = ["SPEC_G601", "MANAGED_SHEET_G601"]

MANAGED_SHEET_G601: Final[str] = "审定表G6-1"
TEMPLATE_ID_G601: Final[str] = "G61"
SHEET_KEY_G601: Final[str] = f"{TEMPLATE_ID_G601.lower()}-managed"

# ── 三区 section ──────────────────────────────────────────────────────────

SECTION_FAIR_VALUE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="fair_value",
    table_key="adj_fair_value_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=21,
    subtotal_row=21,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G601}FV",
)

SECTION_CUMULATIVE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="cumulative",
    table_key="adj_cumulative_rows",
    title_row=22,
    first_data_row=23,
    last_data_row=36,
    subtotal_row=36,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G601}CUM",
)

SECTION_CARRYING: Final[AdjudicationSection] = AdjudicationSection(
    section_key="carrying",
    table_key="adj_carrying_rows",
    title_row=37,
    first_data_row=38,
    last_data_row=51,
    subtotal_row=51,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G601}CAR",
)

# ── field_specs ──────────────────────────────────────────────────────────

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

    # ── 公允价值/原值区 R8-R21 ──
    # R21 = 原值小计（B-I 全公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}21")
    # 数据行内的 SUM 汇总（R8 SUM(R9:R10), R11 SUM(R12:R15) 等结构性子小计）
    # R8-R20 数据行：D/G/H/I 公式
    for row in range(8, 21):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 累计变动区 R23-R36 ──
    # R36 = 变动小计（B-I 全公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}36")
    # R23-R35 数据行：D/G/H/I 公式
    for row in range(23, 36):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 账面余额区 R38-R51（全公式 = 原值 + 变动）──
    for row in range(38, 52):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 差异 R53 ──
    for col in ("D", "G"):
        cells.append(f"{col}53")

    return tuple(sorted(set(cells)))


_CELL_MASK: Final[tuple[str, ...]] = _build_cell_mask()

_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "item_name": AdjudicationValueSource.manual,
    "prior_unadjusted": AdjudicationValueSource.manual,
    "prior_aje": AdjudicationValueSource.manual,
    "prior_audited": AdjudicationValueSource.computed,
    "current_unadjusted": AdjudicationValueSource.manual,
    "current_aje": AdjudicationValueSource.manual,
    "current_audited": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
}

SPEC_G601: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G601,
    sheet_key=SHEET_KEY_G601,
    template_id=TEMPLATE_ID_G601,
    header_rows=(5, 6),
    sections=(SECTION_FAIR_VALUE, SECTION_CUMULATIVE, SECTION_CARRYING),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=51,
    tb_row=52,
    diff_row=53,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
