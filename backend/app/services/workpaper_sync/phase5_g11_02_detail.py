# -*- coding: utf-8 -*-
"""G11-2「投资收益明细分析表」—— sheet 层薄声明（单级表头 + 21 行 + 占比列）。

spec: `g-cycle-single-region-detail-lanes` · Task 11 / C-10
　　　列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` §5 + 本轮逐格实测

═══ 几何（openpyxl 逐格实测，禁推演）═══

`明细分析表G11-2`：`max_row=39` / `max_column=13` / **0 个 definedName**。

* 🔴 **单级表头 R9**（九条里唯一一家；`R8` 是段标题「二、审计过程」，只占 `A8`，
  不是表头行）⇒ `header_group_row` 与 `header_leaf_row` 同取 9。
* 数据区 **R10-R30（21 行，九条最长）**，footer **R31** 合计。
* 🔴 `R32`「本年意润总额」是**手填分析行**，既不是 footer 也不受管
  （另有独立 store 键 `G11-detail-profit-total`）；R33「三、审计说明：」R34「1、」。
* 有效内容列 **13**（A..M）**恰等于** `max_column`（无空尾列）⇒ UUID 列取 `N`。

═══ 🔴 一：受管表自身有 44 格裸 IF ⇒ G/K 两列判 `auto_source` ═══

这是本 entry 与前四条（G9/G10/G8/G14）的**根本差异**：那四家的受管表都是零裸 IF，
中性化只动审定表；G11-2 自己就有 44 格（`G`/`K` 两列占比公式 21×2 + footer 2）。

`adapters/excel.py` 在 **materialize 之前**对 substrate 副本跑
`neutralize_oo_crash_if_formulas`，该函数把含词界 `IF(` 的 `<f>` 元素**整个摘掉**
（`<v>` 留着）。逐格实测（探针一次性件已删，结论落在这里）：

```
G10  before <f t="shared" ref="G10:G31" si="1">IF(F10=0,0,F10/$F$31)</f><v>0</v>
     after  <v>0</v>                                    ← 公式被摘
K10  同上（si="2"，引 $J$31）
G31/K31  shared 成员格 <f t="shared" si="1"/> 也被摘
数据区 R10-R30 逐列：F 21/21→21/21 · G 21/21→**0/21** · J 21/21→21/21
                     · K 21/21→**0/21** · L 21/21→21/21
```

⇒ 声明必须分两族（框架层两条检查是**反向**的，见 `excel_materialize`）：

| 族 | 列 | mode | materialize 侧检查 |
|---|---|---|---|
| 中性化后**仍有**公式 | `F` `J` `L`（不含 IF） | `formula` | 要求 `view.has_formula` ✅ |
| 中性化后**没有**公式 | `G` `K`（含 IF） | `auto_source` | 要求该格**不是**公式 ✅ |

若把 `G`/`K` 判 `formula`，materialize 会因 `has_formula=False` 抛
`ProtectedRegionWriteError`；判 `editable` 则 OO 侧可改、值会进 store 与前端派生双源。
`auto_source` 同属 `contracts.PROTECTED_MODES` ⇒ 不入 store、OO 改动不合并，
保护力度与 `formula` 相同。先例：`phase5_f1_05_long_term` 的 `J` 列
（「模板无公式 + 前端派生 + OO 改动不合并」⇒ `auto_source`）。

🔴 **这推翻了 Task 5 判据 `test_conclusion_g_and_k_stay_managed_as_formula_columns`
的后半句**：P10 的结论「G/K **受管**」成立（它们在 `field_specs` 里、OO 侧只读、
不入 store），但「受管为 **formula_columns**」不成立 —— 中性化后那两列没有公式可保护。
判据已按实测改写（保护力度不放宽）。

═══ 🔴 二：占比列引合计行的绝对引用（裁决 G1R-H5，Task 5 已实测）═══

`G10 = =IF(F10=0,0,F10/$F$31)` 引合计行 `$F$31`；`K10` 引 `$J$31`（**两个分母不同** ——
spec 原文只说「引 F31」，Task 2 发现 K 引 J31）。

Task 5 真跑 `excel_row_shift.shift_sheet_rows` 实测：插 3 行后既有行的主格
`$F$31 → $F$34`、`$J$31 → $J$34` ⇒ **位移分支成立**，G/K 不改判 HTML-only。

🔴 同时登记框架层真实缺陷（Task 5 新发现，spec 未预见）：**新插入行**的 fill-down
公式里的绝对引用**不位移**，仍是 `$F$31` —— 而 R31 位移后已是新行、不再是合计行。
根因：`excel_row_shift._build_inserted_row` 用
`translate_formula_rows(freeze_absolute_rows=True)`（Excel 填充柄语义），造出来的新行
公式随后没有再经过插行位移。Excel 自己的顺序是「先插行再填充」⇒ 结果是 `$F$34`。
本 spec 不修框架层（不在 lane 范围），缺陷判据在
`test_g_single_region_p10_p11_shift.py::test_newly_inserted_rows_keep_the_stale_absolute_denominator`
钉住当前行为。

⇒ 实践后果：G11-2 **不要在数据区插行**（21 行足够；真要扩行须先修框架层）。

═══ 🔴 三：footer 的占比格是 shared formula **成员格** ═══

`G31`/`K31` 是自闭合 `<f t="shared" si="1"/>`，**不带公式文本** —— 主格在 `G10`。
⇒ 判断「占比列是否指向真实合计行」必须看 **shared 组主格**；看成员格会得到 `None` 而误判
（Task 5 首版判据踩过）。

`footer_carries_total_formula=True`：footer 的 D/E/F/H/I/J/L 七列是 `=SUM(x10:x30)`
（G/K 是上述成员格）⇒ `_grow_managed_table_ref` 需要归一化 footer 区间。

═══ 字段键逐字取自前端行接口 ═══

`useG11DetailAnalysis.G11DetailRow` 的 13 个受管字段（与模板列序 A..M 逐列对应）。
🔴 该接口另有 8 个**非模板列**字段，都不受管：
`id`（行身份）· `rowKey`（与 G11-1 对齐的分项勾稽键）· `group`（分组）·
`tradingDisposeSubtype`（上市附注子表子类）· `changeRate`（变动率，模板只有变动额 L）·
`changeRateHighlight` / `reasonRequired`（阈值派生）· `isSkeleton`（骨架行不可删标记）。

🔴 **`seq` 在 G11 是真列**（A 列「序号」，模板 A10-A30 预填 1..21）—— 与 G9/G10/G8 的
`seq`（纯显示序号、不占模板列）不同，不可照抄那三家把它排除在受管面外。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G1102",
    "MANAGED_SHEET_G1102",
    "STORE_ITEM_ID_G1102",
    "FORMULA_TEMPLATES_G1102",
    "FORMULA_COLUMNS_G1102",
    "AUTO_SOURCE_COLUMNS_G1102",
    "RATIO_DENOMINATOR_REFS_G1102",
    "NEUTRALIZED_COLUMNS_G1102",
    "FRONTEND_ONLY_FIELDS_G1102",
    "FIELD_SPECS_G1102",
    "FOOTER_ROW_G1102",
    "PROFIT_TOTAL_ROW_G1102",
]

MANAGED_SHEET_G1102: Final[str] = "明细分析表G11-2"
TEMPLATE_ID_G1102: Final[str] = "G1102"
SHEET_KEY_G1102: Final[str] = "g1102-managed"

#: 🔴 按值取自 `useG11DetailAnalysis.ts` 的 `ITEM_ID_ROWS`，**不按 sheet 号推演**。
STORE_ITEM_ID_G1102: Final[str] = "G11-detail-rows"
ROW_IDENTITY_STORE_KEY_G1102: Final[str] = "id"

#: 🔴 单级表头（九条唯一）：R8 是段标题「二、审计过程」只占 A8，不是表头行。
HEADER_ROW_G1102: Final[int] = 9
FIRST_DATA_ROW_G1102: Final[int] = 10
LAST_DATA_ROW_G1102: Final[int] = 30
#: footer 合计行（**不受管**）：D/E/F/H/I/J/L 七列 `=SUM(x10:x30)`；G/K 是 shared 成员格
FOOTER_ROW_G1102: Final[int] = 31
FOOTER_MARKER_G1102: Final[str] = "合计"
#: 🔴 R32「本年利润总额」手填分析行 —— 既不是 footer 也不受管（另有独立 store 键
#:   `G11-detail-profit-total`）。登记出来是为了让「为什么受管区止于 R30」可复核。
PROFIT_TOTAL_ROW_G1102: Final[int] = 32

#: 公式列：中性化后**仍有**公式的三列（不含裸 IF）⇒ `mode=formula`
FORMULA_COLUMNS_G1102: Final[tuple[str, ...]] = ("F", "J", "L")

#: 🔴 中性化后**没有**公式的两列（占比，含裸 IF）⇒ `mode=auto_source`（见模块头）
AUTO_SOURCE_COLUMNS_G1102: Final[tuple[str, ...]] = ("G", "K")

#: 与上一条同义、换个角度登记：这两列的公式会被 `neutralize_oo_crash_if_formulas` 摘掉。
#: 判据按它现算「中性化前后各列 `<f>` 数量」，模板一旦改写成不含 IF 的形式就会打红。
NEUTRALIZED_COLUMNS_G1102: Final[tuple[str, ...]] = AUTO_SOURCE_COLUMNS_G1102

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R10 且 R10-R30 同型。
FORMULA_TEMPLATES_G1102: Final[dict[str, str]] = {
    "F": "=D{r}+E{r}",      # 本期审定数 = 本期未审 + 本期调整
    "J": "=H{r}+I{r}",      # 上年审定数 = 上年未审 + 上期调整
    "L": "=F{r}-J{r}",      # 变动额 = 本期审定 − 上年审定
}

#: 🔴 占比列的**逐字**模板与分母（裁决 G1R-H5）。不进 `formula_templates` ——
#: 那张表驱动 `mode=formula` 的逐格比对，而这两列判 `auto_source`。
#: 判据按本表逐格比对模板（shared 组**主格** G10/K10），并断言两个分母**不同**。
RATIO_DENOMINATOR_REFS_G1102: Final[dict[str, tuple[str, str]]] = {
    # 列 -> (主格公式逐字, 绝对分母)
    "G": ("IF(F10=0,0,F10/$F$31)", "$F$31"),
    "K": ("IF(J10=0,0,J10/$J$31)", "$J$31"),
}

#: 前端行接口里**不是模板列**的字段（都不受管、不进受管投影）。
FRONTEND_ONLY_FIELDS_G1102: Final[tuple[str, ...]] = (
    "id",                     # 行身份
    "rowKey",                 # 与 G11-1 对齐的分项勾稽键
    "group",                  # 分组（按项目名/rowKey 推断）
    "tradingDisposeSubtype",  # 上市附注子表子类
    "changeRate",             # 变动率（模板只有变动额 L）
    "changeRateHighlight",    # 阈值派生
    "reasonRequired",         # 阈值派生
    "isSkeleton",             # 骨架行不可删标记
)

#: 13 个受管字段（7 元组 `(column_key, column, mode, value_type, json_key, header_text, group_header_cell)`）。
#:
#: 顺序即 Excel 列序 A→M；`header_text` 逐字取**单级**表头 R9；`json_key` 逐字取
#: `useG11DetailAnalysis.G11DetailRow`；单级表头无分组 ⇒ `group_header_cell` 一律 `""`。
FIELD_SPECS_G1102: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    #: 🔴 A 列「序号」在 G11 是**真列**（模板 A10-A30 预填 1..21），不像 G9/G10/G8 的
    #:   `seq` 那样只是显示序号 ⇒ 必须受管。
    ("seq_no", "A", "editable", "integer", "seq", "序号", ""),
    ("item_name", "B", "editable", "text", "itemName", "项目", ""),
    ("investee_name", "C", "editable", "text", "investeeName", "被投资单位", ""),
    ("current_unadjusted", "D", "editable", "amount", "currentUnadjusted", "本期未审数", ""),
    ("current_adjustment", "E", "editable", "amount", "currentAdjustment", "本期调整", ""),
    ("current_audited", "F", "formula", "amount", "currentAudited", "本期审定数", ""),
    #: 🔴 占比列：中性化后无公式 ⇒ `auto_source`（见模块头「一」）
    ("current_share", "G", "auto_source", "amount", "currentShare", "各项目占比", ""),
    ("prior_unadjusted", "H", "editable", "amount", "priorUnadjusted", "上年未审数", ""),
    ("prior_adjustment", "I", "editable", "amount", "priorAdjustment", "上期调整", ""),
    ("prior_audited", "J", "formula", "amount", "priorAudited", "上年审定数", ""),
    #: 🔴 同 G 列（分母是 `$J$31`，与 G 列的 `$F$31` **不同**）
    ("prior_share", "K", "auto_source", "amount", "priorShare", "各项目占比", ""),
    ("change_amount", "L", "formula", "amount", "changeAmount", "变动额", ""),
    ("reason_index", "M", "editable", "text", "reasonIndex", "变动原因/索引号", ""),
)

SPEC_G1102: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G1102,
    sheet_key=SHEET_KEY_G1102,
    table_key="g11_detail_rows",
    template_id=TEMPLATE_ID_G1102,
    table_name=f"GT_{TEMPLATE_ID_G1102}_DETAIL_ROWS",
    #: 有效内容列 13（A..M）恰等于 `max_column`（无空尾列）⇒ 两个 uuid 口径重合，取 N
    uuid_col="N",
    first_data_row=FIRST_DATA_ROW_G1102,
    last_data_row=LAST_DATA_ROW_G1102,
    footer_row=FOOTER_ROW_G1102,
    #: 🔴 **单级**表头：`header_row` 单值，不设 group/leaf 两行（九条唯一一家）
    header_row=HEADER_ROW_G1102,
    store_item_id=STORE_ITEM_ID_G1102,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G1102,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G1102,
    formula_columns=FORMULA_COLUMNS_G1102,
    formula_templates=FORMULA_TEMPLATES_G1102,
    footer_marker=FOOTER_MARKER_G1102,
    #: footer 的 D/E/F/H/I/J/L 七列带 `=SUM(x10:x30)` ⇒ 需要区间归一化（P10 结论落地）
    footer_carries_total_formula=True,
    error_label="G11-2 投资收益明细分析表",
    #: 幽灵行锚点用默认 `[0]`（A 列「序号」）—— 模板 A10-A30 预填 1..21，恒非空。
)
