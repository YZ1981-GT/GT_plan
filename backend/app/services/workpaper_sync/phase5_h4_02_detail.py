"""H4-2「工程物资明细表」—— sheet 层薄声明（H 循环第三张，首个**四级表头 + 三区块**宽表）。

spec: `h4-h8-sub-entry-lanes-and-seed-identity-defects`
现算底账：`.kiro/specs/h4-h8-sub-entry-lanes-and-seed-identity-defects/evidence/
h2-h4-h8-h10-mapping-facts.md` §2（本文件所有数字与那份证据同源）

═══ 它凭什么是 H6/H9 之后的第三条 ═══

H 循环剩 7 条里只有 3 条不需要审计域裁决（H2 / H4 / H8），H4 的事实最完整：
歧义全部**从代码定死**而非靠命名推测（见下）。H10 与 H3/H5/H7 属结构性不匹配，
已登记阻塞（证据 §4/§5），本轮不碰。

═══ 几何（openpyxl 逐格实测，禁推演）═══

册 `H/H4 工程物资.xlsx`（112,937 B）· 13 sheets · 本 sheet `max_row=51` /
`max_column=67`，**有效内容列 49（A..AW）** —— `max_column=67` 是空列尾巴。

* **四级**表头 **R8 / R9 / R10 / R11**（`header_rows = 11 - 8 + 1 = 4`）
  🔴 这是 `contracts.MAX_HEADER_ROWS` 从 3 扩到 4 的真实用例之一
  （commit `91933bd68` 结清 `UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE`）。
* 数据区 **R12-R27（16 行）**
* footer **R28**，`A28='合计'`，`E28..AU28` 多为 `=SUM(x12:x27)`，
  单价列为 `=金额合计/数量合计`（如 `F28='=G28/E28'`）
* 数据行公式列 **25 个**
* UUID 列 **AX** = 有效内容列（49）+ 1（HC-13）

🔴 **footer 之后还有第二区域 R29-R34，必须声明为不受管**：
`A29='其中：'` + 5 行按 `=SUMPRODUCT(($B$12:$B$27=$A30)*(E$12:E$27))` 做的**按类别小计**，
行标签取 `=底稿目录!A9..A13`。`RowTableSheetSpec` 只有一个 `footer_row`，
若不显式登记这 6 行，merge 有可能把它们当数据行覆盖 —— 那会把整块分类小计写坏。

═══ 三区块（表头合并区逐字实测）═══

* **原值 E..AH**（`E8:AH8`）
  - 未审数 `E9:P9`：期初 E-G / 增加 H-J / 减少 K-M / 期末 N-P，每组皆 数量·单价·金额
  - 期初调整 `Q9:R9`：数量 Q / 金额 R
  - 账项调整 `S9:V9`：增加 S-T / 减少 U-V（各 数量·金额，**无单价**）
  - 审定数 `W9:AH9`：期初 W-Y / 增加 Z-AB / 减少 AC-AE / 期末 AF-AH
* **减值准备 AI..AS**（`AI8:AS8`）：未审 AI-AL / 期初调整 AM / 账项调整 AN-AO / 审定 AP-AS
* **期末净值 AT..AU**（`AT8:AU9`）：未审净值 AT / 审定净值 AU
* 尾部两列：`AV 库龄`（`AV8:AV11`）· `AW 品质状况（正常、残次、毁损、滞销等）`

═══ 🔴 三联列 ↔ 单标量的歧义：从代码定死，不是猜 ═══

模板在调整/审定块是 **数量·单价·金额 三联列**，前端 `H4DetailRow` 在同位置只有
**单个标量**（`ajeBegin` / `auditedBegin` …）。判据来自代码本身：

* `useH4Detail.ts#L63` 注释：`// 调整（金额口径 AJE，对齐 Excel 核实情况）`
* `#L140`：`const auditedBegin = calcAuditedAmount(row.beginAmount, row.ajeBegin, 0)`
  —— 以 `beginAmount`（**金额**）为基 ⇒ `ajeBegin` 必是金额口径

⇒ 调整/审定块的**数量列与单价列全部 template-only**，只有金额列进 `field_specs`。
若反过来把 `ajeBegin` 映到 `Q`（数量列），回写会把金额写进数量格 —— 数量栏出现金额级数字，
且单价公式 `=金额/数量` 立刻算出荒谬单价。

🔴 **`ajeImpair` 是 store-only（不映射任何格）**：前端把减值调整压成**一个**字段
（`auditedImpairEnd = calcAuditedAmount(impairEnd, ajeImpair, 0)`），模板却是
AM 期初调整 + AN 账项增加 + AO 账项减少**三列**，且 AS 走 `=AP+AQ-AR`。
一对三无法确定分摊 ⇒ 不映射；两侧口径差异写进契约 note。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H402",
    "MANAGED_SHEET_H402",
    "SHEET_KEY_H402",
    "STORE_ITEM_ID_H402",
    "ROW_IDENTITY_STORE_KEY_H402",
    "FORMULA_TEMPLATES_H402",
    "STORE_ONLY_FIELDS_H402",
    "TEMPLATE_ONLY_COLUMNS_H402",
    "DERIVED_TOTAL_KEYS_H402",
    "UNMANAGED_REGIONS_H402",
    "EFFECTIVE_COLUMNS_H402",
    "UUID_COL_H402",
]

MANAGED_SHEET_H402: Final[str] = "明细表H4-2"
TEMPLATE_ID_H402: Final[str] = "H42"
SHEET_KEY_H402: Final[str] = "h402-managed"
ROWS_TABLE_KEY_H402: Final[str] = "engineering_materials_detail_rows"

#: 按值取自 `useH4Detail.ts` 的 `ROWS_KEY`，不按 sheet 号推演。
STORE_ITEM_ID_H402: Final[str] = "H4-2-rows"

#: 行身份：`row-${Date.now().toString(36)}-${Math.random()...}` ⇒ HC-7 族 A。
#: 🔴 slice 把本 entry 标 `row_identity_is_positional=True`，那是**过期快照** ——
#:    下标身份（`h4DetailPrefill#50` 的 `seed-${i}`）已在 commit 91933bd68 改为
#:    按科目编码的 `buildHSeedRowId`。判据按现状复核，不照 slice 的布尔值写。
ROW_IDENTITY_STORE_KEY_H402: Final[str] = "rowId"

HEADER_TOP_ROW_H402: Final[int] = 8
HEADER_GROUP_ROW_H402: Final[int] = 9
HEADER_SUB_ROW_H402: Final[int] = 10
HEADER_LEAF_ROW_H402: Final[int] = 11
FIRST_DATA_ROW_H402: Final[int] = 12
LAST_DATA_ROW_H402: Final[int] = 27
FOOTER_ROW_H402: Final[int] = 28
FOOTER_MARKER_H402: Final[str] = "合计"
EFFECTIVE_COLUMNS_H402: Final[int] = 49
UUID_COL_H402: Final[str] = "AX"

#: 🔴 footer 之后的**不受管区域**（既非数据行也非 footer）。
#: R29 `其中：` 标题 + R30-R34 五行按类别 SUMPRODUCT 小计（行标签取 `=底稿目录!A9..A13`）。
#: 显式登记是为了让 merge 绝不把它们当数据行 —— 覆盖一次就把分类小计整块写坏。
UNMANAGED_REGIONS_H402: Final[tuple[dict[str, object], ...]] = (
    {
        "first_row": 29,
        "last_row": 34,
        "kind": "category_subtotal_block",
        "note": (
            "A29='其中：'；R30-R34 为 "
            "=SUMPRODUCT(($B$12:$B$27=$A30)*(E$12:E$27)) 形态的按类别小计，"
            "行标签取 =底稿目录!A9..A13。不受管、不比对、不覆盖。"
        ),
    },
)

#: 🔴 模板有列但 HTML 无字段 ⇒ 不进 `field_specs`（Requirement 6.1）。
#: 主体是**调整/审定块的数量列与单价列**（前端在这些位置只有金额标量，见 docstring）。
TEMPLATE_ONLY_COLUMNS_H402: Final[tuple[tuple[str, str], ...]] = (
    ("A", "序号"),
    ("Q", "期初调整·数量"),
    ("S", "账项调整·本期增加·数量"),
    ("U", "账项调整·本期减少·数量"),
    ("W", "审定数·期初数·数量"),
    ("X", "审定数·期初数·单价"),
    ("Z", "审定数·本期增加·数量"),
    ("AA", "审定数·本期增加·单价"),
    ("AC", "审定数·本期减少·数量"),
    ("AD", "审定数·本期减少·单价"),
    ("AF", "审定数·期末数·数量"),
    ("AG", "审定数·期末数·单价"),
    ("AM", "减值准备·期初调整"),
    ("AN", "减值准备·账项调整·本期增加"),
    ("AO", "减值准备·账项调整·本期减少"),
    ("AP", "减值准备·审定数·期初数"),
    ("AQ", "减值准备·审定数·本期增加"),
    ("AR", "减值准备·审定数·本期减少"),
)

#: HTML 有字段但模板无列 ⇒ store-only，不映射任何格。
#: 前 6 个是前端把模板单列 `增加金额 J` / `减少金额 M` 细分成的组成项。
STORE_ONLY_FIELDS_H402: Final[tuple[str, ...]] = (
    "spec",
    "supplier",
    "purchaseAmount",
    "otherIncrease",
    "usageAmount",
    "returnAmount",
    "scrapAmount",
    "otherDecrease",
    "ajeImpair",
    "bookValueBegin",
    "bookValueDiff",
)

#: 🔴 HC-6 派生合计副本：与主表同批写出，不参与 roundtrip 比对。
#: `H4-3-rows` **不在此列** —— 它是调整分录汇总表，是**另一张表**不是合计副本。
DERIVED_TOTAL_KEYS_H402: Final[tuple[str, ...]] = (
    "H4-2-detail-total",
    "H4-2-increase-total",
    "H4-2-decrease-total",
    "H4-2-impair-total",
)

#: 31 个受管字段（7 元组，第 7 位 `group_header_cell`）。
#: 顺序即 Excel 列序；`header_text` 取该列**最下层**非空表头；
#: `group_header_cell` 取其上一层的合并起始格（纵向合并列留空）。
FIELD_SPECS_H402: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("category", "B", "editable", "text", "category", "工程物资类别", ""),
    ("name", "C", "editable", "text", "name", "工程物资名称", ""),
    ("unit", "D", "editable", "text", "unit", "计量单位", ""),
    # ── 原值 · 未审数 ──────────────────────────────────────────────────────
    ("begin_qty", "E", "editable", "amount", "beginQty", "数量", "E10"),
    ("begin_unit_price", "F", "formula", "amount", "beginUnitPrice", "单价", "E10"),
    ("begin_amount", "G", "editable", "amount", "beginAmount", "金额", "E10"),
    ("increase_qty", "H", "editable", "amount", "increaseQty", "数量", "H10"),
    ("increase_unit_price", "I", "formula", "amount", "increaseUnitPrice", "单价", "H10"),
    ("increase_subtotal", "J", "editable", "amount", "increaseSubtotal", "金额", "H10"),
    ("decrease_qty", "K", "editable", "amount", "decreaseQty", "数量", "K10"),
    ("decrease_unit_price", "L", "formula", "amount", "decreaseUnitPrice", "单价", "K10"),
    ("decrease_total", "M", "editable", "amount", "decreaseTotal", "金额", "K10"),
    ("end_qty", "N", "formula", "amount", "endQty", "数量", "N10"),
    ("end_unit_price", "O", "formula", "amount", "endUnitPrice", "单价", "N10"),
    ("end_amount", "P", "formula", "amount", "endAmount", "金额", "N10"),
    # ── 原值 · 期初调整 / 账项调整（只取金额列，见 docstring）────────────────
    ("aje_begin", "R", "editable", "amount", "ajeBegin", "金额", "Q10"),
    ("aje_increase", "T", "editable", "amount", "ajeIncrease", "金额", "S10"),
    ("aje_decrease", "V", "editable", "amount", "ajeDecrease", "金额", "U10"),
    # ── 原值 · 审定数（只取金额列，全公式）──────────────────────────────────
    ("audited_begin", "Y", "formula", "amount", "auditedBegin", "金额", "W10"),
    ("audited_increase", "AB", "formula", "amount", "auditedIncrease", "金额", "Z10"),
    ("audited_decrease", "AE", "formula", "amount", "auditedDecrease", "金额", "AC10"),
    ("audited_end", "AH", "formula", "amount", "auditedEnd", "金额", "AF10"),
    # ── 减值准备 ───────────────────────────────────────────────────────────
    ("impair_begin", "AI", "editable", "amount", "impairBegin", "期初数", "AI9"),
    ("impair_increase", "AJ", "editable", "amount", "impairIncrease", "本期增加", "AI9"),
    ("impair_decrease", "AK", "editable", "amount", "impairDecrease", "本期减少", "AI9"),
    ("impair_end", "AL", "formula", "amount", "impairEnd", "期末数", "AI9"),
    ("audited_impair_end", "AS", "formula", "amount", "auditedImpairEnd", "期末数", "AP9"),
    # ── 期末净值 ───────────────────────────────────────────────────────────
    ("book_value_end", "AT", "formula", "amount", "bookValueEnd", "未审净值", "AT8"),
    ("audited_book_value", "AU", "formula", "amount", "auditedBookValue", "审定净值", "AT8"),
    # ── 尾部定性列 ─────────────────────────────────────────────────────────
    ("aging", "AV", "editable", "text", "aging", "库龄", ""),
    ("quality", "AW", "editable", "text", "quality", "品质状况（正常、残次、毁损、滞销等）", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R12-R27。
#: 🔴 单价列一律 `=金额/数量`（可能 `#DIV/0!`，模板原样如此，不做保护 —— 改了就不是模板权威）。
#: 🔴 只登记进 `field_specs` 的公式列；template-only 的公式列（W/X/Z/AA/AC/AD/AF/AG/
#:    AP/AQ/AR）不在此表，它们由 Excel 自行重算。
FORMULA_TEMPLATES_H402: Final[dict[str, str]] = {
    "F": "=G{r}/E{r}",
    "I": "=J{r}/H{r}",
    "L": "=M{r}/K{r}",
    "N": "=E{r}+H{r}-K{r}",
    "O": "=P{r}/N{r}",
    "P": "=G{r}+J{r}-M{r}",
    "Y": "=G{r}+R{r}",
    "AB": "=J{r}+T{r}",
    "AE": "=M{r}+V{r}",
    "AH": "=Y{r}+AB{r}-AE{r}",
    "AL": "=AI{r}+AJ{r}-AK{r}",
    "AS": "=AP{r}+AQ{r}-AR{r}",
    "AT": "=P{r}-AL{r}",
    "AU": "=AH{r}-AS{r}",
}

SPEC_H402: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H402,
    sheet_key=SHEET_KEY_H402,
    table_key=ROWS_TABLE_KEY_H402,
    template_id=TEMPLATE_ID_H402,
    table_name=f"GT_{TEMPLATE_ID_H402}_ROWS",
    uuid_col=UUID_COL_H402,
    first_data_row=FIRST_DATA_ROW_H402,
    last_data_row=LAST_DATA_ROW_H402,
    footer_row=FOOTER_ROW_H402,
    header_group_row=HEADER_TOP_ROW_H402,
    header_leaf_row=HEADER_LEAF_ROW_H402,
    store_item_id=STORE_ITEM_ID_H402,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H402,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H402,
    formula_columns=tuple(FORMULA_TEMPLATES_H402),
    formula_templates=FORMULA_TEMPLATES_H402,
    footer_marker=FOOTER_MARKER_H402,
    error_label="H4-2 工程物资明细表",
)
