# -*- coding: utf-8 -*-
"""G1-1「交易性金融资产审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测，2026-10-07）═══

三区 98r×11c, 504f, 63IF —— 全 G 最复杂：
  （一）投资成本   R7=标题, R8-R27 数据
        R8=SUM(B9:B15), R16=SUM, R24=SUM, R27=投资成本小计
  （二）累计公允价值变动  R28=标题, R29-R48 数据
        R29=SUM, R37=SUM, R45=SUM, R48=公允价值变动小计
  （三）账面余额（公允价值） R49=标题, R50-R71 数据
        R50-R68 全公式=成本+变动, R69=小计, R70=减超一年, R71=合计

合计 R71 / TB R72 / 差异 R73。两级表头 R5-R6。11 列 A-K。
表头引用 D3/G3/J3。

列结构（与 G10 同族，B-I 受管）：
  A  项目（editable）
  B  未审数-期初（editable / SUM 汇总行）
  C  AJE-期初（editable / SUM 汇总行）
  D  审定数-期初（=B+C，formula）
  E  未审数-期末（editable / SUM 汇总行）
  F  AJE-期末（editable / SUM 汇总行）
  G  审定数-期末（=E+F，formula）
  H  变动额（=G-D，formula）
  I  变动率（=IF(...)，formula）
  J  审计说明（header only）
  K  空

🔴 第三区（账面余额）全公式（=初始成本+累计公允价值变动）。
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

__all__ = ["SPEC_G101", "MANAGED_SHEET_G101"]

MANAGED_SHEET_G101: Final[str] = "审定表G1-1"
TEMPLATE_ID_G101: Final[str] = "G11"
SHEET_KEY_G101: Final[str] = f"{TEMPLATE_ID_G101.lower()}-managed"

# ── 三区 section ──────────────────────────────────────────────────────────

SECTION_COST: Final[AdjudicationSection] = AdjudicationSection(
    section_key="cost",
    table_key="adj_cost_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=27,
    subtotal_row=27,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G101}COST",
)

SECTION_FV_CHANGE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="fv_change",
    table_key="adj_fv_change_rows",
    title_row=28,
    first_data_row=29,
    last_data_row=48,
    subtotal_row=48,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G101}FV",
)

SECTION_CARRYING: Final[AdjudicationSection] = AdjudicationSection(
    section_key="carrying",
    table_key="adj_carrying_rows",
    title_row=49,
    first_data_row=50,
    last_data_row=71,
    subtotal_row=71,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G101}CAR",
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

    # ── 投资成本区 R8-R27 ──
    # SUM 汇总行（B-I 全公式）: R8, R16, R24, R27
    for sum_row in (8, 16, 24, 27):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # 数据行 D/G/H/I 公式
    for row in (
        list(range(9, 16)) + list(range(17, 24)) + list(range(25, 27))
    ):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 累计公允价值变动区 R29-R48 ──
    # SUM 汇总行: R29, R37, R45, R48
    for sum_row in (29, 37, 45, 48):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # 数据行 D/G/H/I 公式
    for row in (
        list(range(30, 37)) + list(range(38, 45)) + list(range(46, 48))
    ):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 账面余额区 R50-R71（全公式 = 成本 + 变动）──
    # R50-R68: B-I 全列公式
    for row in range(50, 69):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{row}")
    # R69 小计 / R70 减超一年 / R71 合计
    for row in (69, 70, 71):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 差异 R73 ──
    for col in ("D", "G"):
        cells.append(f"{col}73")

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

SPEC_G101: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G101,
    sheet_key=SHEET_KEY_G101,
    template_id=TEMPLATE_ID_G101,
    header_rows=(5, 6),
    sections=(SECTION_COST, SECTION_FV_CHANGE, SECTION_CARRYING),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=71,
    tb_row=72,
    diff_row=73,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
