# -*- coding: utf-8 -*-
"""G9-1「其他非流动金融资产审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测，2026-10-07）═══

三区 74r×15c, 390f, 42IF：
  初始成本      R7=标题, R8-R21 数据
      R8=SUM, R13=SUM, R18=SUM, R21=投资成本小计
  累计公允价值变动 R22=标题, R23-R36 数据
      R23=SUM, R28=SUM, R33=SUM, R36=变动小计
  账面余额      R37=标题, R38-R51 数据
      全公式=成本+变动, R51=合计

合计 R51 / TB R52 / 差异 R53。两级表头 R5-R6。**15 列** A-O。
表头引用 E3/H3/L3（非标准，与 G5 相似）。

列结构（15 列，B-K 受管）：
  A   项目（editable）
  B   未审数-期初
  C   AJE-期初
  D   审定数-期初（=B+C，formula）
  E   未审数-期末
  F   AJE-期末
  G   审定数-期末（=E+F，formula）
  H   变动额（=G-D，formula）
  I   变动率（=IF(...)，formula）
  J   审计说明标题（header）
  K   变动率（附加列）
  L-O 空 / 附注

🔴 与 G1/G10 同族的三区结构（成本/变动/余额），但有 **15 列**。
🔴 第三区（账面余额）全公式=初始成本+累计变动。
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

__all__ = ["SPEC_G901", "MANAGED_SHEET_G901"]

MANAGED_SHEET_G901: Final[str] = "审定表G9-1"
TEMPLATE_ID_G901: Final[str] = "G91"
SHEET_KEY_G901: Final[str] = f"{TEMPLATE_ID_G901.lower()}-managed"

# ── 三区 section ──────────────────────────────────────────────────────────

SECTION_COST: Final[AdjudicationSection] = AdjudicationSection(
    section_key="cost",
    table_key="adj_cost_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=21,
    subtotal_row=21,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G901}COST",
)

SECTION_FV_CHANGE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="fv_change",
    table_key="adj_fv_change_rows",
    title_row=22,
    first_data_row=23,
    last_data_row=36,
    subtotal_row=36,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G901}FV",
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
    template_id=f"{TEMPLATE_ID_G901}CAR",
)

# ── field_specs（B-K 受管，与标准 9 列相同 —— J/K 是 header/附加） ─────

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

    # ── 初始成本区 R8-R21 ──
    # SUM 汇总行（B-I 全公式）: R8, R13, R18, R21
    for sum_row in (8, 13, 18, 21):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R9-R12, R14-R17, R19-R20 数据行：D/G/H/I 公式
    for row in (
        list(range(9, 13)) + list(range(14, 18)) + list(range(19, 21))
    ):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 累计公允价值变动区 R23-R36 ──
    # SUM 汇总行: R23, R28, R33, R36
    for sum_row in (23, 28, 33, 36):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R24-R27, R29-R32, R34-R35 数据行：D/G/H/I 公式
    for row in (
        list(range(24, 28)) + list(range(29, 33)) + list(range(34, 36))
    ):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 账面余额区 R38-R51（全公式 = 成本 + 变动）──
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

SPEC_G901: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G901,
    sheet_key=SHEET_KEY_G901,
    template_id=TEMPLATE_ID_G901,
    header_rows=(5, 6),
    sections=(SECTION_COST, SECTION_FV_CHANGE, SECTION_CARRYING),
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
