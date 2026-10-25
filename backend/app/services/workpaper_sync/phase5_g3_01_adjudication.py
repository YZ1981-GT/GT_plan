# -*- coding: utf-8 -*-
"""G3-1「应收股利审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测）═══

三区 48r×22c, 120f, 18IF：
  一、账面余额   R7=标题, R8-R9 数据, R10 合计
  二、减值准备   R11=标题, R12-R13 数据, R14 合计
  三、账面价值   R15=标题, R16-R17 数据, R18 合计

列结构（A-V, 22 列，受管区 A-M 13 列）：
  A  项目（editable；减值/净值区 A 列是公式 =A8/=A9）
  B  期初余额（cross_sheet 明细表G3-2）
  C  本期增加（cross_sheet）
  D  其中转入（cross_sheet）
  E  审定数-期初（=B+C+D，formula）
  F  本期减少（cross_sheet）
  G  本期增加-期末（cross_sheet）
  H  其中转入-期末（cross_sheet）
  I  审定数-期末（formula）
  J  变动额（formula）
  K  变动率（=IF(...)，formula）
  L  减值准备相关（cross_sheet）
  M  附注（editable）

🔴 22 列但受管区只到 M（13 列），N-V 为空。
🔴 减值区和净值区 A 列是公式。
🔴 B-L 数据行全公式（跨 sheet 明细表 G3-2）。
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

__all__ = ["SPEC_G301", "MANAGED_SHEET_G301"]

MANAGED_SHEET_G301: Final[str] = "审定表G3-1"
TEMPLATE_ID_G301: Final[str] = "G31"
SHEET_KEY_G301: Final[str] = f"{TEMPLATE_ID_G301.lower()}-managed"

# ── 三区 section ──────────────────────────────────────────────────────────

SECTION_BALANCE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="balance",
    table_key="adj_balance_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=9,
    subtotal_row=10,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G301}BAL",
)

SECTION_IMPAIRMENT: Final[AdjudicationSection] = AdjudicationSection(
    section_key="impairment",
    table_key="adj_impairment_rows",
    title_row=11,
    first_data_row=12,
    last_data_row=13,
    subtotal_row=14,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G301}IMP",
)

SECTION_CARRYING: Final[AdjudicationSection] = AdjudicationSection(
    section_key="carrying",
    table_key="adj_carrying_rows",
    title_row=15,
    first_data_row=16,
    last_data_row=17,
    subtotal_row=18,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G301}CAR",
)

# ── field_specs（9 元组）──────────────────────────────────────────────────

_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("opening_balance", "B", "cross_sheet", "amount", "openingBalance", "期初余额", ""),
    ("increase", "C", "cross_sheet", "amount", "increase", "本期增加", ""),
    ("transfer_in", "D", "cross_sheet", "amount", "transferIn", "其中转入", ""),
    ("audited_opening", "E", "formula", "amount", "auditedOpening", "审定数-期初", ""),
    ("decrease", "F", "cross_sheet", "amount", "decrease", "本期减少", ""),
    ("increase_end", "G", "cross_sheet", "amount", "increaseEnd", "本期增加-期末", ""),
    ("transfer_in_end", "H", "cross_sheet", "amount", "transferInEnd", "其中转入-期末", ""),
    ("audited_closing", "I", "formula", "amount", "auditedClosing", "审定数-期末", ""),
    ("change_amount", "J", "formula", "amount", "changeAmount", "变动额", ""),
    ("change_rate", "K", "formula", "ratio", "changeRate", "变动率", ""),
    ("impairment_related", "L", "cross_sheet", "amount", "impairmentRelated", "减值准备", ""),
    ("note_ref", "M", "editable", "text", "noteRef", "附注", ""),
)


def _build_cell_mask() -> tuple[str, ...]:
    """逐格 formula mask（大写 A1 形态，实测所有公式格）。"""
    cells: list[str] = []

    # ── 余额区 R8-R9 ──
    # B-L 数据行全公式（跨 sheet）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"):
        for row in range(8, 10):
            cells.append(f"{col}{row}")
    # 合计 R10
    for col in ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"):
        cells.append(f"{col}10")

    # ── 减值区 R12-R13 ──
    # A 列公式（=A8, =A9）
    for row in range(12, 14):
        cells.append(f"A{row}")
    # B-L 数据行全公式
    for col in ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"):
        for row in range(12, 14):
            cells.append(f"{col}{row}")
    # 合计 R14
    for col in ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"):
        cells.append(f"{col}14")

    # ── 账面价值区 R16-R17（全公式 = 余额 - 减值）──
    # A 列公式
    for row in range(16, 18):
        cells.append(f"A{row}")
    # B-L 全列公式
    for col in ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"):
        for row in range(16, 18):
            cells.append(f"{col}{row}")
    # 合计 R18
    for col in ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"):
        cells.append(f"{col}18")

    return tuple(sorted(set(cells)))


_CELL_MASK: Final[tuple[str, ...]] = _build_cell_mask()

_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "item_name": AdjudicationValueSource.manual,
    "opening_balance": AdjudicationValueSource.cross_sheet,
    "increase": AdjudicationValueSource.cross_sheet,
    "transfer_in": AdjudicationValueSource.cross_sheet,
    "audited_opening": AdjudicationValueSource.computed,
    "decrease": AdjudicationValueSource.cross_sheet,
    "increase_end": AdjudicationValueSource.cross_sheet,
    "transfer_in_end": AdjudicationValueSource.cross_sheet,
    "audited_closing": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
    "impairment_related": AdjudicationValueSource.cross_sheet,
    "note_ref": AdjudicationValueSource.manual,
}

SPEC_G301: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G301,
    sheet_key=SHEET_KEY_G301,
    template_id=TEMPLATE_ID_G301,
    header_rows=(5, 6),
    sections=(SECTION_BALANCE, SECTION_IMPAIRMENT, SECTION_CARRYING),
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
