# -*- coding: utf-8 -*-
"""G4-1「债权投资审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测，2026-10-07）═══

三区 46r×11c, 176f, 29IF：
  一、原值         R7=标题, R8-R15 数据
      R8 单项计提, R9=SUM(组合), R10-R12 组合子项, R13=小计, R14=减一年内, R15=原值小计
  二、减值准备     R16=标题, R17-R24 数据
      R17=A8 引用, R18=SUM(A9引用), R19-R21 引用, R22=小计, R23=减一年内, R24=小计
  三、净值         R25=标题, R26-R33 数据
      全公式=原值-减值, R31=合计, R32=减一年内, R33=净值合计

合计 R33（=净值合计） / TB R34 / 差异 R35。
R36 = 勾稽校验行。两级表头 R5-R6。11 列 A-K。

列结构：
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

🔴 原值区 R8 手工、R9=SUM、R10-R12 手工、R14 手工。
🔴 减值准备区 A 列引用原值区。
🔴 第三区（净值）全公式=原值-减值准备。
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

__all__ = ["SPEC_G401", "MANAGED_SHEET_G401"]

MANAGED_SHEET_G401: Final[str] = "审定表G4-1"
TEMPLATE_ID_G401: Final[str] = "G41"
SHEET_KEY_G401: Final[str] = f"{TEMPLATE_ID_G401.lower()}-managed"

# ── 三区 section ──────────────────────────────────────────────────────────

SECTION_ORIGINAL: Final[AdjudicationSection] = AdjudicationSection(
    section_key="original",
    table_key="adj_original_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=15,
    subtotal_row=15,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G401}ORI",
)

SECTION_IMPAIRMENT: Final[AdjudicationSection] = AdjudicationSection(
    section_key="impairment",
    table_key="adj_impairment_rows",
    title_row=16,
    first_data_row=17,
    last_data_row=24,
    subtotal_row=24,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G401}IMP",
)

SECTION_NET: Final[AdjudicationSection] = AdjudicationSection(
    section_key="net",
    table_key="adj_net_rows",
    title_row=25,
    first_data_row=26,
    last_data_row=33,
    subtotal_row=33,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G401}NET",
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

    # ── 原值区 R8-R15 ──
    # R9 = SUM 汇总行（B-I 全公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}9")
    # R13 小计, R15 原值小计（B-I 全公式）
    for sum_row in (13, 15):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R8, R10-R12, R14 数据行：D/G/H/I 公式
    for row in (8, 10, 11, 12, 14):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 减值准备区 R17-R24 ──
    # R18 = SUM 汇总行（B-I 全公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}18")
    # R22 小计, R24 小计（B-I 全公式）
    for sum_row in (22, 24):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R17, R19-R21, R23 数据行：D/G/H/I 公式
    for row in (17, 19, 20, 21, 23):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 净值区 R26-R33（全公式 = 原值 - 减值）──
    for row in range(26, 34):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 差异 R35 ──
    for col in ("D", "G"):
        cells.append(f"{col}35")

    # ── 勾稽校验 R36 ──
    for col in ("D", "G"):
        cells.append(f"{col}36")

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

SPEC_G401: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G401,
    sheet_key=SHEET_KEY_G401,
    template_id=TEMPLATE_ID_G401,
    header_rows=(5, 6),
    sections=(SECTION_ORIGINAL, SECTION_IMPAIRMENT, SECTION_NET),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=33,
    tb_row=34,
    diff_row=35,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
