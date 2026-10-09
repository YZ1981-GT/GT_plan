# -*- coding: utf-8 -*-
"""G5-1「长期应收款审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: g-cycle-adjudication-sheets-coverage · Task 2
      Requirements 1.1, 1.3

═══ 几何（openpyxl 直读实测，2026-10-07）═══

六区 87r×13c, 501f, 61IF —— 全 G 第二复杂。
两大段各三区（款项性质三区 R7-R46 + 减值准备三区 R47-R74）：

段一「按款项性质」：
  余额     R7=标题, R8(标题行?), R9-R20 数据
           R9-R17 数据行, R18=小计, R19=减一年内, R20=余额小计
  坏账准备  R21=标题, R22-R33 数据
           A 列引用上区, R31=小计, R32=减一年内, R33=准备小计
  净值     R34=标题, R35-R46 数据
           A 列引用上区, 全公式=余额-坏账, R44=小计, R45=减一年内, R46=净值合计

段二「减值准备」：
  余额     R47=标题, R48(标题行?), R49-R56 数据
           R49=单项, R50=SUM(组合), R51-R53 子项, R54=小计, R55=减一年内, R56=余额小计
  坏账准备  R57=标题, R58-R65 数据
           A 列引用上区, R63=小计, R64=减一年内, R65=准备小计
  净值     R66=标题, R67-R74 数据
           全公式=余额-坏账, R72=小计, R73=减一年内, R74=净值合计

TB R75 / 差异 R76。两级表头 R5-R6。**13 列** A-M。
表头引用 E3/H3/L3（非标准）。

列结构（13 列，B-K 受管）：
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
  K   附注相关
  L-M 空 / 附注

🔴 G5-1 有**六个区**（两大段各三区）—— 全 G 表 section 数量最多。
🔴 G5-1!B35 越界缺陷（=B9-B225，B225 超出 max_row）。
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

__all__ = ["SPEC_G501", "MANAGED_SHEET_G501"]

MANAGED_SHEET_G501: Final[str] = "审定表G5-1"
TEMPLATE_ID_G501: Final[str] = "G51"
SHEET_KEY_G501: Final[str] = f"{TEMPLATE_ID_G501.lower()}-managed"

# ── 六区 section ──────────────────────────────────────────────────────────
# 段一「按款项性质」

SECTION_BAL_1: Final[AdjudicationSection] = AdjudicationSection(
    section_key="balance_1",
    table_key="adj_balance_1_rows",
    title_row=7,
    first_data_row=9,
    last_data_row=20,
    subtotal_row=20,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G501}BAL1",
)

SECTION_BAD_DEBT_1: Final[AdjudicationSection] = AdjudicationSection(
    section_key="bad_debt_1",
    table_key="adj_bad_debt_1_rows",
    title_row=21,
    first_data_row=22,
    last_data_row=33,
    subtotal_row=33,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G501}BD1",
)

SECTION_NET_1: Final[AdjudicationSection] = AdjudicationSection(
    section_key="net_1",
    table_key="adj_net_1_rows",
    title_row=34,
    first_data_row=35,
    last_data_row=46,
    subtotal_row=46,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G501}NET1",
)

# 段二「减值准备」

SECTION_BAL_2: Final[AdjudicationSection] = AdjudicationSection(
    section_key="balance_2",
    table_key="adj_balance_2_rows",
    title_row=47,
    first_data_row=49,
    last_data_row=56,
    subtotal_row=56,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G501}BAL2",
)

SECTION_BAD_DEBT_2: Final[AdjudicationSection] = AdjudicationSection(
    section_key="bad_debt_2",
    table_key="adj_bad_debt_2_rows",
    title_row=57,
    first_data_row=58,
    last_data_row=65,
    subtotal_row=65,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G501}BD2",
)

SECTION_NET_2: Final[AdjudicationSection] = AdjudicationSection(
    section_key="net_2",
    table_key="adj_net_2_rows",
    title_row=66,
    first_data_row=67,
    last_data_row=74,
    subtotal_row=74,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_G501}NET2",
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

    # ══ 段一「按款项性质」══

    # ── 余额区 R9-R20 ──
    # R18 小计, R20 余额小计（B-I 全公式）
    for sum_row in (18, 20):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R19 减一年内（B-I 公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}19")
    # R9-R17 数据行：D/G/H/I 公式
    for row in range(9, 18):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 坏账准备区 R22-R33 ──
    # R31 小计, R33 准备小计（B-I 全公式）
    for sum_row in (31, 33):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R32 减一年内（B-I 公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}32")
    # R22-R30 数据行：D/G/H/I 公式
    for row in range(22, 31):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 净值区 R35-R46（全公式 = 余额 - 坏账）──
    for row in range(35, 47):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ══ 段二「减值准备」══

    # ── 余额区 R49-R56 ──
    # R50 = SUM 汇总行（B-I 全公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}50")
    # R54 小计, R56 余额小计（B-I 全公式）
    for sum_row in (54, 56):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R55 减一年内（B-I 公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}55")
    # R49, R51-R53 数据行：D/G/H/I 公式
    for row in (49, 51, 52, 53):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 坏账准备区 R58-R65 ──
    # R63 小计, R65 准备小计（B-I 全公式）
    for sum_row in (63, 65):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{sum_row}")
    # R64 减一年内（B-I 公式）
    for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
        cells.append(f"{col}64")
    # R58-R62 数据行：D/G/H/I 公式
    for row in range(58, 63):
        for col in ("D", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 净值区 R67-R74（全公式 = 余额 - 坏账）──
    for row in range(67, 75):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            cells.append(f"{col}{row}")

    # ── 差异 R76 ──
    for col in ("D", "G"):
        cells.append(f"{col}76")

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

SPEC_G501: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_G501,
    sheet_key=SHEET_KEY_G501,
    template_id=TEMPLATE_ID_G501,
    header_rows=(5, 6),
    sections=(
        SECTION_BAL_1, SECTION_BAD_DEBT_1, SECTION_NET_1,
        SECTION_BAL_2, SECTION_BAD_DEBT_2, SECTION_NET_2,
    ),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=None,
    tb_row=75,
    diff_row=76,
    footer_marker="合计",
    store_item_id="",
    row_identity_key="",
    per_cell_key_template="",
    field_specs=_FIELD_SPECS,
    cell_mask=_CELL_MASK,
    value_sources=_VALUE_SOURCES,
)
