# -*- coding: utf-8 -*-
"""G1-2「交易性金融资产明细表」—— sheet 层薄声明（三区 + 区① 独有跨表 T 列）。

spec: `g-cycle-single-region-detail-lanes` · Task 14 / C-13（九条**最后一条**）

═══ 几何（openpyxl 逐格实测，禁推演）═══

`明细表G1-2`：`max_row=52` / **`max_column=35`** / **0 definedName** / merged 19 / 18 sheets。

* **两级表头 R9/R10**：横向组 5 个（`C9:E9` 期初余额 · `F9:G9` 期初账项调整 · `H9:J9`
  期初审定数 · `M9:O9` 本期变动 · `P9:R9` 期末余额 · `S9:T9` 账项调整 · `U9:W9` 期末审定数
  —— 实测 **7 个**）；纵向合并 6 列（`A9:A10` `B9:B10` `K9:K10` `L9:L10` `X9:X10` `Y9:Y10`
  `Z9:Z10` `AA9:AA10` —— 实测 **8 个**）。
* 🔴 **三区**（区标题行不受管）：
  * 区① `R11`「交易性金融资产」→ 数据 **R12-R16**（5 行）→ 小计 `R17`
  * 区② `R18`「划分为以公允价值计量且其变动计入当期损益的金融资产」→ **R19-R23**（5 行）→ `R24`
  * 区③ `R25`「指定为以公允价值计量且其变动计入当期损益的金融资产」→ **R26-R28**（3 行）→ `R29`
* 合计 `R30` = `=SUM(C17,C24,C29)`（枚举三个小计）。
* `R31` 是注1「相关金融工具已到期可收取但于资产负债表日尚未收到的利息在'应收利息'反映」
  ⇒ **G1 无期末应收利息列**（那部分推给 G2 底稿），`R32` 是「三、审计说明：」。
* 🔴 有效内容列 **27**（A..AA）**小于** `max_column=35`（8 个空尾列）⇒ 三区 uuid 列按**有效列
  之后**逐区错开取 `AB`/`AC`/`AD`（同 G9 的做法：一区一列，避免三区写同一格）。
* 🔴 整册裸 IF **0 格**（G1 册 18 sheet 全零）⇒ 中性化对本册是空操作；per-file 照挂（GC-2）。

═══ 🔴 一：三区共用一个 store 键（引擎 `row_section_field` 过滤）═══

前端把三区的行存在**同一个** `G1-2-rows` 数组里、用 `acctClass` 字段标记区归属
（`trading` / `classified_fvpl` / `designated_fvpl`）。⇒ 照 G9 的范式声明
`row_section_field="acctClass"` + 各段 `row_section_value`；`iter_store_rows` 按它过滤、
`merge_projection_into_store_rows` 给新增行补它（两处成对，缺一就「读得出但写不回」）。

🔴 payload 列是 **`conclusion`** 不是 `remark`（FD-1 的 `conclusion_only` 族，与 G3 同）。

═══ 🔴 二：区① 独有跨表 `T` 列 ⇒ 三区**不得共用** `formula_columns` ═══

逐格实测：

```
区① R12-R16：T12 = ='公允价值测试表G1-6'!H10-'明细表G1-2'!R12   （逐行引 G1-6 的 H10..H14）
区② R19-R23：T 列**整格无公式**
区③ R26-R28：T 列**整格无公式**
```

⇒ 区① 公式列 **13** 个（含 `T`）、区②③ **12** 个（不含）。这正是判据 P6「G1 ≠ G9」要断言的
那个**唯一**不等点 —— G9 三区的公式列完全相同、可共用一份；G1 不行，抄三份共用必漂移。

多区拆 spec 正好表达这个行级差异：`T` 在区① 判 `formula`、在区②③ 判 `editable`
（判 formula 会让 materialize 在区②③ 的 8 格抛 `ProtectedRegionWriteError`）。
比 G12/G13 那种「一个 spec 内部行级混合」更干净 —— 因为 G1 的区间本来就是连续三段。

`T` 的跨表公式**逐行不同**（引 `G1-6!H10`..`H14`）⇒ 单条模板表达不了 ⇒ 落
:data:`TEMPLATE_CROSS_SHEET_FORMULAS_G102`，判据按行逐格比对（照 G8 的
`TEMPLATE_ROW_FORMULAS_G802` 范式）。

═══ 🔴 三：前端列模型口径本轮按模板改齐（用户拍板「跟模板一致」）═══

改造前有 6 处与模板不一致，本轮全部按模板改：

| 模板公式 | 改造前前端 | 本轮 |
|---|---|---|
| `P=C+M`（起点**期初余额成本 C**） | `审定成本 H + 增 − 减` | `openingCost + periodCostChange` |
| `Q=D+N`（起点**期初余额累计 FV D**） | `审定累计 FV + 变动` | `openingCumulativeFv + periodFvChange` |
| `R=P+Q` | 有市价时用市价覆盖 | 恒为双桶合计（市价只做非受管的验算列） |
| `W=U+V` | 含 `aje`/`rje` | 不含（两列不在模板 27 列内、不受管） |
| `L=J+K` / `Y=W+X`（**加**） | 减 | 加（`K`/`X` 列名「减：…」⇒ **存负数**，UI 标签已改） |
| `M` **净额单列** | `addedCost` / `reducedCost` 两列 | 合并为 `periodCostChange`（两列实测**零生产消费方**） |

另**新补** `confirmationRequested`（模板 `AA` 是否函证，前端原先没有 ⇒ 不补则该列脱管）。
旧载荷的 `addedCost`/`reducedCost` 由 `migratePartial` 迁成净额。

═══ 🔴 四：29 个非模板列字段**不删、不受管**（实测推翻 tasks.md 的「删列」建议）═══

tasks.md 按「类 I 去范围」写「删 ~29」。本轮按值普查真消费方（先筛出 import 了
`useG1Detail`/`TradingDetailRow` 的 **10** 个文件，再在其中统计 —— 按名字全仓统计毫无意义，
`remark` 在全仓命中 11083 次、`aje` 1886 次，全是别的 composable 的同名字段）：

* **17 个有生产代码消费方**（删了要同时改 5 个兄弟表 composable 的数据源，那是另一条 lane
  的作业面）：`securityCode`(g1CrossHelpers/useG1FairValueTest/useG1IncomeCalc/useG1Inventory)
  · `investType`(useG1IncomeCalc/useG1Adjudication/G1TabDetail) · `market`(useG1Inventory)
  · `soldQuantity`(useG1IncomeCalc) · `closingQuantity`(G1TabDetail)
  · `unitFairValue`/`quoteDate`(useG1FairValueTest) · `fairValueSource`(useG1FairValueTest/G1TabDetail)
  · `fairValueChange`(G1TabDetail) · `realizedGain`(useG1IncomeCalc/G1TabDetail)
  · `totalIncome`/`unadjusted`/`adjusted`/`rollForwardDiff`(G1TabDetail)
  · `variance`(useG1FairValueTest/G1TabDetail)
  · `indexRef`(useG1IncomeCalc/g1CrossHelpers/useG1FairValueTest/useG1Inventory)
  · `remark`(6 个消费方)
* **12 个只有自己的 spec 在用**（真冗余，可删清单见 evidence，本轮**不删** —— 受管面已严格
  27 列，删它们是前端瘦身、与「跟模板一致」无关且要改 12 处测试断言）：
  `acquisitionDate` `initialCost` `originalCurrency` `exchangeRate` `openingQuantity`
  `boughtQuantity` `disposalProceeds` `disposalCost` `fvChangeInPL` `aje` `rje` `pledged`

⇒ 与 G13「工具明细整体不受管 ⇒ 21 字段一个都不用删」同一条道理：**不受管 ≠ 必须删**。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G102_R1",
    "SPEC_G102_R2",
    "SPEC_G102_R3",
    "ALL_SPECS_G102",
    "MANAGED_SHEET_G102",
    "STORE_ITEM_ID_G102",
    "ROW_SECTION_FIELD_G102",
    "SECTION_TITLE_ROWS_G102",
    "SUBTOTAL_ROWS_G102",
    "GRAND_TOTAL_ROW_G102",
    "FORMULA_COLUMNS_R1_G102",
    "FORMULA_COLUMNS_R23_G102",
    "FORMULA_TEMPLATES_G102",
    "TEMPLATE_CROSS_SHEET_FORMULAS_G102",
    "BOOLEAN_COLUMNS_G102",
    "FRONTEND_ONLY_FIELDS_G102",
    "FRONTEND_ONLY_FIELD_OWNERS_G102",
    "REMOVABLE_FRONTEND_FIELDS_G102",
    "FIELD_SPECS_G102",
]

MANAGED_SHEET_G102: Final[str] = "明细表G1-2"
TEMPLATE_ID_G102: Final[str] = "G102"
#: 按值取自 `useG1Detail.ts` 的 `DATA_KEY`
STORE_ITEM_ID_G102: Final[str] = "G1-2-rows"
ROW_IDENTITY_STORE_KEY_G102: Final[str] = "id"
#: 行的区归属字段（前端 `TradingDetailRow.acctClass`）—— 引擎据此把同一数组的行分到三区
ROW_SECTION_FIELD_G102: Final[str] = "acctClass"

HEADER_GROUP_ROW_G102: Final[int] = 9
HEADER_LEAF_ROW_G102: Final[int] = 10
#: 区标题行（**不受管**）
SECTION_TITLE_ROWS_G102: Final[tuple[int, ...]] = (11, 18, 25)
#: 各区小计行
SUBTOTAL_ROWS_G102: Final[tuple[int, ...]] = (17, 24, 29)
#: 合计行 `=SUM(C17,C24,C29)`（枚举三个小计）
GRAND_TOTAL_ROW_G102: Final[int] = 30
FOOTER_MARKER_G102: Final[str] = "小计"

#: 🔴 区① 公式列 **13** 个（含跨表 `T`）
FORMULA_COLUMNS_R1_G102: Final[tuple[str, ...]] = (
    "E", "H", "I", "J", "L", "P", "Q", "R", "T", "U", "V", "W", "Y",
)
#: 🔴 区②③ 公式列 **12** 个（`T` 整格无公式 ⇒ 判 editable）
FORMULA_COLUMNS_R23_G102: Final[tuple[str, ...]] = (
    "E", "H", "I", "J", "L", "P", "Q", "R", "U", "V", "W", "Y",
)

#: 三区共用的逐行同形公式（`{r}` 为行号）。`T` 不在此表（跨表且逐行不同）。
FORMULA_TEMPLATES_G102: Final[dict[str, str]] = {
    "E": "=C{r}+D{r}",      # 期初公允价值 = 期初成本 + 期初累计公允价值变动
    "H": "=C{r}+F{r}",      # 期初审定成本 = 期初成本 + 期初账项调整-成本
    "I": "=D{r}+G{r}",      # 期初审定累计 FV = 期初累计 FV + 期初账项调整-公允变动
    "J": "=H{r}+I{r}",      # 期初审定公允价值
    "L": "=J{r}+K{r}",      # 🔴 期初报表数 = 期初审定 **+** 扣减列（K 存负数）
    "P": "=C{r}+M{r}",      # 🔴 期末成本 = **期初余额成本** + 本期变动（净额）
    "Q": "=D{r}+N{r}",      # 🔴 期末累计 FV = **期初余额累计 FV** + 本期公允变动
    "R": "=P{r}+Q{r}",      # 期末公允价值 = 双桶合计（市价只做非受管验算）
    "U": "=P{r}+S{r}",      # 期末审定成本
    "V": "=Q{r}+T{r}",      # 期末审定累计 FV
    "W": "=U{r}+V{r}",      # 🔴 期末审定公允价值（**不含** AJE/RJE）
    "Y": "=W{r}+X{r}",      # 🔴 期末报表数 = 期末审定 **+** 扣减列（X 存负数）
}

#: 🔴 区① 独有的跨表 `T` 列公式（`行 -> 逐字公式`）。引 `公允价值测试表G1-6!H10..H14`。
#:   不进 `formula_templates`（逐行引不同的源格，单条模板表达不了）⇒ 判据按行比对。
TEMPLATE_CROSS_SHEET_FORMULAS_G102: Final[dict[int, str]] = {
    12: "='公允价值测试表G1-6'!H10-'明细表G1-2'!R12",
    13: "='公允价值测试表G1-6'!H11-'明细表G1-2'!R13",
    14: "='公允价值测试表G1-6'!H12-'明细表G1-2'!R14",
    15: "='公允价值测试表G1-6'!H13-'明细表G1-2'!R15",
    16: "='公允价值测试表G1-6'!H14-'明细表G1-2'!R16",
}

#: 两个布尔列（`Z` 变现是否存在限制 · `AA` 是否函证）。模板整格无公式 ⇒ `editable`。
BOOLEAN_COLUMNS_G102: Final[tuple[str, ...]] = ("Z", "AA")

#: 前端行接口里**不是模板列**的字段（29 个，都不受管）。见模块头「四」。
FRONTEND_ONLY_FIELDS_G102: Final[tuple[str, ...]] = (
    "id", "seq",
    "securityCode", "investType", "market", "acquisitionDate", "initialCost",
    "originalCurrency", "exchangeRate",
    "openingQuantity", "boughtQuantity", "soldQuantity", "closingQuantity",
    "unitFairValue", "fairValueSource", "fairValueChange", "quoteDate",
    "disposalProceeds", "disposalCost", "realizedGain", "totalIncome", "fvChangeInPL",
    "unadjusted", "aje", "rje", "adjusted", "variance", "rollForwardDiff", "indexRef",
    "pledged", "remark",
)

#: 🔴 非模板列字段的**真消费方**（按值普查：先筛 import 了 `useG1Detail`/`TradingDetailRow`
#:   的 10 个文件，再在其中统计）。删任何一条前先看这里 —— 有生产消费方的删了会打断兄弟表。
FRONTEND_ONLY_FIELD_OWNERS_G102: Final[dict[str, tuple[str, ...]]] = {
    "securityCode": (
        "g1CrossHelpers.ts", "useG1FairValueTest.ts", "useG1IncomeCalc.ts",
        "useG1Inventory.ts",
    ),
    "investType": ("useG1IncomeCalc.ts", "useG1Adjudication.ts", "G1TabDetail.vue"),
    "market": ("useG1Inventory.ts",),
    "soldQuantity": ("useG1IncomeCalc.ts",),
    "closingQuantity": ("G1TabDetail.vue",),
    "unitFairValue": ("useG1FairValueTest.ts",),
    "fairValueSource": ("useG1FairValueTest.ts", "G1TabDetail.vue"),
    "fairValueChange": ("G1TabDetail.vue",),
    "quoteDate": ("useG1FairValueTest.ts",),
    "realizedGain": ("useG1IncomeCalc.ts", "G1TabDetail.vue"),
    "totalIncome": ("G1TabDetail.vue",),
    "unadjusted": ("G1TabDetail.vue",),
    "adjusted": ("G1TabDetail.vue",),
    "variance": ("useG1FairValueTest.ts", "G1TabDetail.vue"),
    "rollForwardDiff": ("G1TabDetail.vue",),
    "indexRef": (
        "useG1IncomeCalc.ts", "g1CrossHelpers.ts", "useG1FairValueTest.ts",
        "useG1Inventory.ts",
    ),
    "remark": (
        "useG1FairValueTest.ts", "useG1Inventory.ts", "useG1IncomeCalc.ts",
        "g1CrossHelpers.ts", "useG1Adjudication.ts", "G1TabDetail.vue",
    ),
}

#: 🔴 **零生产消费方**的 12 个字段（只有自己的 spec 在用）—— 可删清单，本轮**不删**
#:   （受管面已严格 27 列；删它们属前端瘦身、与「跟模板一致」无关，且要改 12 处测试断言）。
REMOVABLE_FRONTEND_FIELDS_G102: Final[tuple[str, ...]] = (
    "acquisitionDate", "initialCost", "originalCurrency", "exchangeRate",
    "openingQuantity", "boughtQuantity", "disposalProceeds", "disposalCost",
    "fvChangeInPL", "aje", "rje", "pledged",
)

#: 27 个受管字段（7 元组）。顺序即 Excel 列序 A→AA；`header_text` 取两级表头（有叶子取叶子、
#: 纵向合并取 R9）；`json_key` 逐字取 `useG1Detail.TradingDetailRow`。
#: 🔴 `T` 列的 mode 逐区不同（区① `formula` / 区②③ `editable`）⇒ 由 `_section_field_specs()`
#:   在建 spec 时按区替换，本常量记**区①** 的形态（含 T=formula）。
FIELD_SPECS_G102: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("acct_class", "A", "editable", "text", "acctClass", "类别", ""),
    (
        "security_name", "B", "editable", "text", "securityName",
        "投资项目【按明细项目列示，如证券名称或被投资单位名称】", "",
    ),
    ("opening_cost", "C", "editable", "amount", "openingCost", "成本", "C9"),
    (
        "opening_cumulative_fv", "D", "editable", "amount",
        "openingCumulativeFv", "累计公允价值变动", "C9",
    ),
    ("opening_fair_value", "E", "formula", "amount", "openingFairValue", "公允价值", "C9"),
    ("opening_cost_adj", "F", "editable", "amount", "openingCostAdj", "成本", "F9"),
    ("opening_fv_adj", "G", "editable", "amount", "openingFvAdj", "公允价值变动", "F9"),
    ("audited_opening_cost", "H", "formula", "amount", "auditedOpeningCost", "成本", "H9"),
    (
        "audited_opening_cumulative_fv", "I", "formula", "amount",
        "auditedOpeningCumulativeFv", "累计公允价值变动", "H9",
    ),
    (
        "audited_opening_fv_total", "J", "formula", "amount",
        "auditedOpeningFvTotal", "公允价值", "H9",
    ),
    #: 🔴 K/X 两列模板名带「减：」且 `L=J+K` / `Y=W+X` 是**加** ⇒ 存负数
    (
        "opening_lt_deduction", "K", "editable", "amount",
        "openingLtDeduction", "减：期初超过一年到期的部分", "",
    ),
    ("opening_reported", "L", "formula", "amount", "openingReported", "期初报表数", ""),
    #: 🔴 M 是**净额单列**（模板「本期变动（增加为正数）」）—— 前端原两列已合并
    ("period_cost_change", "M", "editable", "amount", "periodCostChange", "成本", "M9"),
    (
        "period_fv_change", "N", "editable", "amount",
        "periodFvChange", "本期公允价值变动", "M9",
    ),
    (
        "dividend_income", "O", "editable", "amount",
        "dividendIncome", "计入投资收益的股息", "M9",
    ),
    ("closing_cost", "P", "formula", "amount", "closingCost", "成本", "P9"),
    (
        "cumulative_fv_change", "Q", "formula", "amount",
        "cumulativeFVChange", "累计公允价值变动", "P9",
    ),
    ("closing_fair_value", "R", "formula", "amount", "closingFairValue", "公允价值", "P9"),
    ("closing_cost_adj", "S", "editable", "amount", "closingCostAdj", "成本", "S9"),
    #: 🔴 区① 是跨表公式（引 G1-6）、区②③ 整格无公式 —— mode 逐区不同，见模块头「二」
    ("closing_fv_adj", "T", "formula", "amount", "closingFvAdj", "公允价值变动", "S9"),
    ("audited_closing_cost", "U", "formula", "amount", "auditedClosingCost", "成本", "U9"),
    (
        "audited_closing_cumulative_fv", "V", "formula", "amount",
        "auditedClosingCumulativeFv", "累计公允价值变动", "U9",
    ),
    (
        "audited_closing_fv_total", "W", "formula", "amount",
        "auditedClosingFvTotal", "公允价值", "U9",
    ),
    (
        "closing_lt_deduction", "X", "editable", "amount",
        "closingLtDeduction", "减：超过一年到期的部分", "",
    ),
    ("closing_reported", "Y", "formula", "amount", "closingReported", "期末报表数", ""),
    (
        "realization_restricted", "Z", "editable", "boolean",
        "realizationRestricted", "变现是否存在限制", "",
    ),
    #: 🔴 本轮新补的模板 AA 列（前端原先没有这个字段 ⇒ 不补则该列脱管）
    (
        "confirmation_requested", "AA", "editable", "boolean",
        "confirmationRequested", "是否函证", "",
    ),
)


def _section_field_specs(
    *, include_cross_sheet_t: bool
) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    """按区产出 field_specs：区②③ 的 `T` 列改判 `editable`（模板那 8 格无公式）。"""
    if include_cross_sheet_t:
        return FIELD_SPECS_G102
    return tuple(
        (k, c, "editable" if c == "T" else m, v, j, h, g)
        for (k, c, m, v, j, h, g) in FIELD_SPECS_G102
    )


def _section_spec(
    *,
    table_key: str,
    template_suffix: str,
    uuid_col: str,
    first_data_row: int,
    last_data_row: int,
    footer_row: int,
    section_value: str,
    formula_columns: tuple[str, ...],
    include_cross_sheet_t: bool,
    error_label: str,
) -> RowTableSheetSpec:
    """建一个区的 spec。

    三区只在行号区间、`uuid_col`、`table_key`、`template_id` 后缀、`row_section_value`、
    **以及 `formula_columns`/`T` 列 mode** 上不同 —— 最后那一项是 G1 与 G9 的唯一不等点
    （G9 三区公式列完全相同、可共用一份；G1 区① 多一个跨表 `T`）。

    🔴 `template_id` 必须**逐区不同**：instrumentation 的 definedName 按它派生，撞名会让
    三区写到同一个受管表。
    """
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_G102,
        sheet_key="g102-managed",
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_G102}{template_suffix}",
        table_name=f"GT_{TEMPLATE_ID_G102}_{table_key.upper()}",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=footer_row,
        header_group_row=HEADER_GROUP_ROW_G102,
        header_leaf_row=HEADER_LEAF_ROW_G102,
        store_item_id=STORE_ITEM_ID_G102,
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY_G102,
        store_kind=StoreKind.rows,
        field_specs=_section_field_specs(include_cross_sheet_t=include_cross_sheet_t),
        formula_columns=formula_columns,
        formula_templates=FORMULA_TEMPLATES_G102,
        footer_marker=FOOTER_MARKER_G102,
        #: 各区小计行逐列 `=SUM(x{first}:x{last})` ⇒ 需要区间归一化
        footer_carries_total_formula=True,
        error_label=error_label,
        row_section_field=ROW_SECTION_FIELD_G102,
        row_section_value=section_value,
        #: 🔴 幽灵行锚点指 **B 列「投资项目」**（真正的业务名称）而不是默认的 `[0]`：
        #:   A 列是「类别」枚举（债务工具投资 / 权益工具投资 / …）且模板预填，用它判空会
        #:   把「只填了类别、其余全空」的行当成有数据的行（G9 同因同改）。
        ghost_row_anchor_index=1,
    )


#: 区① 交易性金融资产（模板区标题 R11）—— 🔴 唯一含跨表 `T` 列的区
SPEC_G102_R1: Final[RowTableSheetSpec] = _section_spec(
    table_key="g1_2_rows_r1",
    template_suffix="R1",
    uuid_col="AB",
    first_data_row=12,
    last_data_row=16,
    footer_row=17,
    section_value="trading",
    formula_columns=FORMULA_COLUMNS_R1_G102,
    include_cross_sheet_t=True,
    error_label="G1-2 交易性金融资产明细表（交易性金融资产）",
)

#: 区② 划分为以公允价值计量且其变动计入当期损益的金融资产（模板区标题 R18）
SPEC_G102_R2: Final[RowTableSheetSpec] = _section_spec(
    table_key="g1_2_rows_r2",
    template_suffix="R2",
    uuid_col="AC",
    first_data_row=19,
    last_data_row=23,
    footer_row=24,
    section_value="classified_fvpl",
    formula_columns=FORMULA_COLUMNS_R23_G102,
    include_cross_sheet_t=False,
    error_label="G1-2 交易性金融资产明细表（划分为FVTPL）",
)

#: 区③ 指定为以公允价值计量且其变动计入当期损益的金融资产（模板区标题 R25）
SPEC_G102_R3: Final[RowTableSheetSpec] = _section_spec(
    table_key="g1_2_rows_r3",
    template_suffix="R3",
    uuid_col="AD",
    first_data_row=26,
    last_data_row=28,
    footer_row=29,
    section_value="designated_fvpl",
    formula_columns=FORMULA_COLUMNS_R23_G102,
    include_cross_sheet_t=False,
    error_label="G1-2 交易性金融资产明细表（指定为FVTPL）",
)

ALL_SPECS_G102: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_G102_R1,
    SPEC_G102_R2,
    SPEC_G102_R3,
)
