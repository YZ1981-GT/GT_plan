# -*- coding: utf-8 -*-
"""F5-7「成本倒轧表」—— sheet 层薄声明。

spec: f5-sync-coverage-and-first-canary · Task 18 · Requirements 5.1, 5.3, 5.4
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何 ═══

单级表头 **R10**：A 项目内容 / B 计算说明 / C 数据来源 / D 索引号 / E 未审数 / F 审计调整
/ G 审定数 / H 上期数。

21 固定行 **R11~R31**（`rowKey` 行身份），**无 footer 合计**。
R32 = `三、审计说明：`（锚行 footer，`footer_carries_total_formula=False`）。

═══ G 列处置（备选②：HTML-only）═══

🔴 G31 公式 `=G24+G56+G57-G58-G59-G60-G61` 引越界空区（sheet 仅 36 行）⇒
审定数列的主营业务成本漏掉 6 项（P15 已量化取证）。

Task 17*（模板覆盖层修 G31）卡外部阻塞 ⇒ 走**备选②**：
G 列整列 HTML-only，不进 field_specs。前端 `calcF57*` 函数口径正确，
G 列值由前端 computed 计算并展示，不写入 OO 侧。

═══ 公式分布（行级差异）═══

21 行分两种 rowType（前端 `F57_ROW_DEFS`）：

| rowType | 行号 | E 未审 | F 调整 | G 审定 | H 上期 |
|---------|------|--------|--------|--------|--------|
| input (17行) | R11~15,17~20,22~23,25~30 | editable | editable | 公式=E+F | editable |
| formula (4行) | R16,21,24,31 | 公式 | 公式 | 公式 | 公式 |

E/F/H 列在 input 行是 editable，在 formula 行是公式。
声明方式：E/F/H 声明为 `editable`，formula 行的公式格由引擎 materialize 在模板本身
有公式时自动跳过（不需要显式 formula_mask —— 模板里有公式就不写值）。

G 列不声明（HTML-only，备选②）。

═══ store 格式 ═══

🔴 store key **不带 `-rows` 后缀**：`F5-7-cost-rollforward`。
store 格式：`{ rows: { <rowKey>: { unadjusted, aje, prior, indexRef } } }`。

行身份 **`rowKey`**（21 个固定值，顺序敏感）。

═══ UUID 列 ═══

max_col=K(11)，I 列 non_null=0 ⇒ 取 **I**。🔴 超出 max_col=H(8) ⇒ 需扩列。

═══ 21 个 rowKey（逐字取 F57_ROW_DEFS，顺序敏感）═══

R11 openingMaterial · R12 materialPurchaseNet · R13 materialOtherIncrease ·
R14 closingMaterial · R15 materialOtherIssue · R16 directMaterialCost(formula) ·
R17 directLabor · R18 manufacturingOverhead · R19 overheadMaterialTransfer ·
R20 specialTooling · R21 productProductionCost(formula) ·
R22 openingWIP · R23 closingWIP · R24 finishedGoodsCost(formula) ·
R25 openingFG · R26 fgOtherIncrease · R27 closingFG ·
R28 selfUseProductCost · R29 internalUseProductCost · R30 fgOtherIssue ·
R31 mainBusinessCOGS(formula)
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F507",
    "MANAGED_SHEET_F507",
    "STORE_ITEM_ID_F507",
    "FORMULA_ROW_KEYS_F507",
    "HTML_ONLY_COLUMN_G_F507",
]

MANAGED_SHEET_F507: Final[str] = "成本倒轧表F5-7"
TEMPLATE_ID_F507: Final[str] = "F57"
SHEET_KEY_F507: Final[str] = "f57-managed"
ROWS_TABLE_KEY_F507: Final[str] = "cost_rollforward"
#: 🔴 不带 `-rows` 后缀（前端 STORAGE_KEY = 'F5-7-cost-rollforward'）。
STORE_ITEM_ID_F507: Final[str] = "F5-7-cost-rollforward"

ROW_IDENTITY_STORE_KEY_F507: Final[str] = "rowKey"

HEADER_ROW_F507: Final[int] = 10
FIRST_DATA_ROW_F507: Final[int] = 11
LAST_DATA_ROW_F507: Final[int] = 31
#: 🔴 无 footer 合计 ⇒ footer_carries_total_formula=False。
FOOTER_ROW_F507: Final[int] = 32
FOOTER_MARKER_F507: Final[str] = "三、审计说明："
MANAGED_LAST_COL_F507: Final[str] = "H"
UUID_COL_F507: Final[str] = "I"

#: 4 个 formula 行的 rowKey（这些行的 E/F/G/H 全是公式，不可编辑）。
FORMULA_ROW_KEYS_F507: Final[tuple[str, ...]] = (
    "directMaterialCost",      # R16 ⑹=⑴+⑵+⑶−⑷−⑸
    "productProductionCost",   # R21 ⑽=⑹+⑺+⑻+⑼
    "finishedGoodsCost",       # R24 ⒀=⑽+⑾−⑿
    "mainBusinessCOGS",        # R31 ⒇=⒀+⒁+⒂−⒃−⒄−⒅−⒆
)

#: G 列 HTML-only（备选②：模板 G31 越界公式未修，Task 17* 卡覆盖层）。
HTML_ONLY_COLUMN_G_F507: Final[tuple[str, str]] = (
    "G",
    "G31 公式引越界空区 G56:G61（sheet 仅 36 行），审定数列主营业务成本漏算 6 项。"
    "模板覆盖层修复后可接入（Task 17），当前走备选②：HTML-only。",
)

#: 3 个受管 editable 字段（G 列 HTML-only 不声明）。
#: E/F/H 在 input 行可编辑、在 formula 行由模板公式覆盖（引擎自动跳过有公式的格）。
FIELD_SPECS_F507: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("unadjusted", "E", "editable", "amount", "unadjusted", "未审数", ""),
    ("aje", "F", "editable", "amount", "aje", "审计调整", ""),
    # G 列 HTML-only（审定数）
    ("prior", "H", "editable", "amount", "prior", "上期数", ""),
)

SPEC_F507: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F507,
    sheet_key=SHEET_KEY_F507,
    table_key=ROWS_TABLE_KEY_F507,
    template_id=TEMPLATE_ID_F507,
    table_name=f"GT_{TEMPLATE_ID_F507}_ROWS",
    uuid_col=UUID_COL_F507,
    first_data_row=FIRST_DATA_ROW_F507,
    last_data_row=LAST_DATA_ROW_F507,
    footer_row=FOOTER_ROW_F507,
    header_row=HEADER_ROW_F507,
    store_item_id=STORE_ITEM_ID_F507,
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F507,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F507,
    formula_columns=(),  # 不做列级 formula_mask（E/F/H 在行级有差异，由模板公式兜底）
    formula_templates={},
    footer_marker=FOOTER_MARKER_F507,
    footer_carries_total_formula=False,
    error_label="F5-7 成本倒轧表",
)
