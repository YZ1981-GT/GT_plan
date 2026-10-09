# -*- coding: utf-8 -*-
"""G2-1「应收利息审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测）═══

三区 41r×11c, 132f, 19IF：
  一、应收利息原值   R7=标题, R8-R12 数据, R13 小计
  二、应收利息坏账准备 R14=标题, R15-R19 数据, R20 小计
  三、应收利息净值   R21=标题, R22-R26 数据, R27 合计

列结构（A-K, 11 列）：
  A  项目（editable；坏账/净值区 A 列是公式 =原值区同行 A）
  B  未审数-期初（R8 手工，R9 跨sheet，其余公式）
  C  AJE-期初（同 B 口径）
  D  审定数-期初（=B+C，formula）
  E  未审数-期末（同 B 口径）
  F  AJE-期末（同 B 口径）
  G  审定数-期末（=E+F，formula）
  H  变动额（=D-G，formula）
  I  变动率（=IF(...)，formula）
  J  审计说明标题（header only）
  K  空

🔴 无独立 sheet 级"试算平衡表数"行和"差异数"行（三区各有小计/合计行）。
🔴 R15-R19 坏账区、R22-R26 净值区 A 列是公式（=A8..=A12）。
🔴 净值区 B-I 全公式（=原值-坏账）。
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

__all__ = ["SPEC_G201", "MANAGED_SHEET_G201"]

MANAGED_SHEET_G201: Final[str] = "审定表G2-1"
TEMPLATE_ID_G201: Final[str] = "G21"
SHEET_KEY_G201: Final[str] = f"{TEMPLATE_ID_G201.lower()}-managed"

# ── 三区 section ──────────────────────────────────────────────────────────

SECTION_GROSS: Final[AdjudicationSection] = AdjudicationSection(
    section_key="gross",
    table_key="adj_gross_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=12,
    subtotal_row=13,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G201}GROSS",
)

SECTION_BAD_DEBT: Final[AdjudicationSection] = AdjudicationSection(
    section_key="bad_debt",
    table_key="adj_bad_debt_rows",
    title_row=14,
    first_data_row=15,
    last_data_row=19,
    subtotal_row=20,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G201}BD",
)

SECTION_NET: Final[AdjudicationSection] = AdjudicationSection(
    section_key="net",
    table_key="adj_net_rows",
    title_row=21,
    first_data_row=22,
    last_data_row=26,
    subtotal_row=27,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G201}NET",
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

    # ── 原值区 R8-R12 ──
    # D/G/H/I 数据行（公式列）
    for col in ("D", "G", "H", "I"):
        for row in range(8, 13):
            cells.append(f"{col}{row}")
    # R8/R9 的 B/C/E/F 部分有跨 sheet 公式（归 cross_sheet，也进 mask）
    for col in ("B", "C", "E", "F"):
        for row in (8, 9):
            cells.append(f"{col}{row}")
    # 小计 R13
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}13")

    # ── 坏账准备区 R15-R19 ──
    # A 列公式（=A8..=A12）
    for row in range(15, 20):
        cells.append(f"A{row}")
    # D/G/H/I 数据行
    for col in ("D", "G", "H", "I"):
        for row in range(15, 20):
            cells.append(f"{col}{row}")
    # R15/R16 的 B/C/E/F 有跨 sheet 公式
    for col in ("B", "C", "E", "F"):
        for row in (15, 16):
            cells.append(f"{col}{row}")
    # 小计 R20
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}20")

    # ── 净值区 R22-R26（全公式 = 原值 - 坏账）──
    # A 列公式
    for row in range(22, 27):
        cells.append(f"A{row}")
    # B-I 全列公式
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        for row in range(22, 27):
            cells.append(f"{col}{row}")
    # 合计 R27
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
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

SPEC_G201: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G201,
    sheet_key=SHEET_KEY_G201,
    template_id=TEMPLATE_ID_G201,
    header_rows=(5, 6),
    sections=(SECTION_GROSS, SECTION_BAD_DEBT, SECTION_NET),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=None,
    tb_row=None,
    diff_row=None,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
