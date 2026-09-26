# -*- coding: utf-8 -*-
"""D1-15「应收票据坏账准备测算表」—— sheet 层薄声明（**双区**）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 28 · Requirements 5.1 / 5.8

═══ 几何（openpyxl 直读实测，2026-09-26）═══

| 区 | 标题 | 表头 | 数据行 | footer | 公式列 | store 键 | UUID 列 |
|---|---|---|---|---|---|---|---|
| 单项计提 | R11（一） | R12-13（两级） | R14-R17 (4行) | R18 `小计` | D/E/F 行级 | `D1-ecl-individual-rows` | I |
| 组合计提 | R19（二） | R20-21（两级） | R22-R24 (3行) | R25 `小计` | D/E/F 行级 | `D1-ecl-portfolio-rows` | J |

两区共 managed_sheet 与 sheet_key，各自独立 UUID 列（I/J，max_col=H=8 后紧跟）。

🔴 **数据区有行级乘法公式** D=B*C（期末应计提 = 余额 × 损失率），这是 D1 首次非加减派生。
引擎声明为 `formula`，materialize 不覆盖公式格、由 OO 重算。E=B-D（期末坏账余额）、
F=D-E（差异）也是行级公式。tasks.md 明确标注"确认 `mode=formula` 路径不依赖算式形态"——
引擎按 `mode=formula` 统一跳过该列的写盘，与算式是乘法还是加减无关。

🔴 footer marker 是 `小计`（不是 `合计`）—— 与 D1-3/D1-4/D1-8/D1-16 的 `合计` 不同。

🔴 `row_identity_key = "id"`（与 D1-11/D1-12/D1-16 一致）。

🔴 **`autoPulled: boolean`** 字段（前端标注"由 D1-4 自动取数填充"）**不进 field_specs**——
它是前端 UI 提示字段（控制行背景色），不映射到 Excel 列、不参与 materialize。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D115_INDIVIDUAL",
    "SPEC_D115_PORTFOLIO",
    "SPECS_D115",
    "MANAGED_SHEET_D115",
]

MANAGED_SHEET_D115: Final[str] = "应收票据坏账准备测试表D1-15"
TEMPLATE_ID_D115: Final[str] = "D115"
SHEET_KEY_D115: Final[str] = f"{TEMPLATE_ID_D115.lower()}-managed"

HEADER_GROUP_ROW_INDIVIDUAL: Final[int] = 12
HEADER_LEAF_ROW_INDIVIDUAL: Final[int] = 13
HEADER_GROUP_ROW_PORTFOLIO: Final[int] = 20
HEADER_LEAF_ROW_PORTFOLIO: Final[int] = 21

FOOTER_ROW_INDIVIDUAL: Final[int] = 18
FOOTER_ROW_PORTFOLIO: Final[int] = 25
#: 🔴 footer marker 是「小计」（codepoints 5c0f 8ba1），不是其他 D1 sheet 的「合计」。
FOOTER_MARKER_D115: Final[str] = "小计"

#: 两区共用字段骨架（8 列 A-H）。D/E/F 三列有行级公式：
#: D=B*C（乘法！）/ E=B-D / F=D-E —— 声明为 formula。
_FIELD_SPECS_D115: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("debtor", "A", "editable", "text", "debtor", "债务人名称", ""),
    ("balance", "B", "editable", "amount", "balance", "审定应收票据账面余额", ""),
    ("loss_rate", "C", "editable", "amount", "lossRate", "预期信用损失率", ""),
    ("should_provision", "D", "formula", "amount", "shouldProvision", "期末应计提坏账准备", ""),
    ("actual_provision", "E", "formula", "amount", "actualProvision", "期末坏账准备账面余额", ""),
    ("difference", "F", "formula", "amount", "difference", "差异", ""),
    ("basis", "G", "editable", "text", "basis", "坏账准备计提依据及文件", ""),
    ("index_ref", "H", "editable", "text", "indexRef", "索引号", ""),
)

_FORMULA_COLUMNS_D115: Final[tuple[str, ...]] = ("D", "E", "F")
#: 🔴 D 列是**乘法**公式（D=B*C），非加减。引擎按 mode=formula 统一不写该格（算式形态无关），
#: 但 formula_templates 用于 verify_unmanaged_regions 的区间扩张比对。
_FORMULA_TEMPLATES_INDIVIDUAL: Final[dict[str, str]] = {
    "D": "=B{r}*C{r}",
    "E": "=B{r}-D{r}",
    "F": "=D{r}-E{r}",
}
_FORMULA_TEMPLATES_PORTFOLIO: Final[dict[str, str]] = {
    "D": "=B{r}*C{r}",
    "E": "=B{r}-D{r}",
    "F": "=D{r}-E{r}",
}


SPEC_D115_INDIVIDUAL: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D115,
    sheet_key=SHEET_KEY_D115,
    table_key="ecl_individual_rows",
    template_id=f"{TEMPLATE_ID_D115}IND",
    table_name=f"GT_{TEMPLATE_ID_D115}_INDIVIDUAL_ROWS",
    uuid_col="I",
    first_data_row=14,
    last_data_row=17,
    footer_row=FOOTER_ROW_INDIVIDUAL,
    header_group_row=HEADER_GROUP_ROW_INDIVIDUAL,
    header_leaf_row=HEADER_LEAF_ROW_INDIVIDUAL,
    store_item_id="D1-ecl-individual-rows",
    empty_payload="[]",
    row_identity_key="id",
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_D115,
    formula_columns=_FORMULA_COLUMNS_D115,
    formula_templates=_FORMULA_TEMPLATES_INDIVIDUAL,
    footer_marker=FOOTER_MARKER_D115,
    error_label="D1-15 单项计提",
)

SPEC_D115_PORTFOLIO: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D115,
    sheet_key=SHEET_KEY_D115,
    table_key="ecl_portfolio_rows",
    template_id=f"{TEMPLATE_ID_D115}PORT",
    table_name=f"GT_{TEMPLATE_ID_D115}_PORTFOLIO_ROWS",
    uuid_col="J",
    first_data_row=22,
    last_data_row=24,
    footer_row=FOOTER_ROW_PORTFOLIO,
    header_group_row=HEADER_GROUP_ROW_PORTFOLIO,
    header_leaf_row=HEADER_LEAF_ROW_PORTFOLIO,
    store_item_id="D1-ecl-portfolio-rows",
    empty_payload="[]",
    row_identity_key="id",
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_D115,
    formula_columns=_FORMULA_COLUMNS_D115,
    formula_templates=_FORMULA_TEMPLATES_PORTFOLIO,
    footer_marker=FOOTER_MARKER_D115,
    error_label="D1-15 组合计提",
)

SPECS_D115: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_D115_INDIVIDUAL,
    SPEC_D115_PORTFOLIO,
)
