# -*- coding: utf-8 -*-
"""G10-1「交易性金融负债审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测）═══

三区 58r×12c, 178f, 28IF：
  （一）初始金额       R7=标题, R8-R16 数据, 其中 R8/R12/R16 是 SUM 汇总行
  （二）累计公允价值变动 R17=标题, R18-R26 数据, 其中 R18/R22/R26 是 SUM 汇总行
  （三）账面余额（公允价值）R27=标题, R28-R36 数据, R28-R35 全公式(=初始+累计), R36 合计
  合计R36, TB R37, 差异R38

列结构（A-L, 12 列，受管区到 I 列）：
  A  项目（editable）
  B  未审数-期初（部分手工，部分SUM汇总）
  C  AJE-期初（同B口径）
  D  审定数-期初（=B+C，formula）
  E  未审数-期末（部分手工，部分SUM）
  F  AJE-期末（同E口径）
  G  审定数-期末（=E+F，formula）
  H  变动额（=D-G，formula）
  I  变动率（=IF(...)，formula）
  J-L  空

🔴 三区结构特殊：每区内部含 SUM 汇总行（小计性质）。
🔴 第三区（账面余额）全公式（=初始金额+累计公允价值变动）。
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

__all__ = ["SPEC_G1001", "MANAGED_SHEET_G1001"]

MANAGED_SHEET_G1001: Final[str] = "审定表G10-1"
TEMPLATE_ID_G1001: Final[str] = "G101"
SHEET_KEY_G1001: Final[str] = f"{TEMPLATE_ID_G1001.lower()}-managed"

# ── 三区 section ──────────────────────────────────────────────────────────

SECTION_INITIAL: Final[AdjudicationSection] = AdjudicationSection(
    section_key="initial",
    table_key="adj_initial_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=16,
    subtotal_row=16,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G1001}INIT",
)

SECTION_FV_CHANGE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="fv_change",
    table_key="adj_fv_change_rows",
    title_row=17,
    first_data_row=18,
    last_data_row=26,
    subtotal_row=26,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G1001}FV",
)

SECTION_CARRYING: Final[AdjudicationSection] = AdjudicationSection(
    section_key="carrying",
    table_key="adj_carrying_rows",
    title_row=27,
    first_data_row=28,
    last_data_row=36,
    subtotal_row=36,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G1001}CAR",
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

    # ── 初始金额区 R8-R16 ──
    # R8/R12/R16 是 SUM 汇总行（B-I 全公式）
    for sum_row in (8, 12, 16):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R9-R11, R13-R15 数据行：D/G/H/I 公式
    for row in list(range(9, 12)) + list(range(13, 16)):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 累计公允价值变动区 R18-R26 ──
    # R18/R22/R26 是 SUM 汇总行
    for sum_row in (18, 22, 26):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R19-R21, R23-R25 数据行：D/G/H/I 公式
    for row in list(range(19, 22)) + list(range(23, 26)):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 账面余额区 R28-R36（全公式 = 初始 + 累计）──
    # R28-R35：B-I 全列公式
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        for row in range(28, 36):
            cells.append(f"{col}{row}")
    # R36 合计
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}36")

    # ── 差异 R38 ──
    for col in ("D", "G"):
        cells.append(f"{col}38")

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

SPEC_G1001: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G1001,
    sheet_key=SHEET_KEY_G1001,
    template_id=TEMPLATE_ID_G1001,
    header_rows=(5, 6),
    sections=(SECTION_INITIAL, SECTION_FV_CHANGE, SECTION_CARRYING),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=36,
    tb_row=37,
    diff_row=38,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
