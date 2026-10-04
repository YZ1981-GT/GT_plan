# -*- coding: utf-8 -*-
"""G12-2「净敞口套期收益明细表」—— sheet 层薄声明（两级表头 + 零公式列 + 五处模板缺陷）。

spec: `g-cycle-single-region-detail-lanes` · Task 13 / C-12
　　　列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` + 本轮逐格实测

═══ 🔴 一：「无表头行」前提早已被推翻（裁决 G1R-H2 不适用）═══

spec 原文说 G12-2「无表头行（R9 即数据）」并据此立了裁决 G1R-H2（要框架层加
`has_header_row`）。Task 2 实测推翻：**R7/R8 是两级表头**、R9 起才是数据（整册比别家上移
两行）。⇒ 框架层**无需改**，本 Task 走通例分支。Task 0 §1.1 登记的缺口对 G12 不适用。

═══ 几何（openpyxl + XML 逐格实测，禁推演）═══

`明细表G12-2`：`max_row=25` / **`max_column=15`** / **0 definedName** / merged 9 个。

* **两级表头 R7/R8**：
  * 🔴 横向组**只有一个** `D7:G7`（套期工具公允价值）；
  * 纵向合并六列 `A7:A8` `B7:B8` `C7:C8` `H7:H8` `I7:I8` `J7:J8`。
  * `R6` 是段标题「二、审计过程：」只占 `A6`；`R5` 是审计目标。
* 数据区 **R9-R13（5 行）**：🔴 只有 **R9/R10 有预填**，R11-R13 整行全空（样式预留）。
  footer 的 SUM 区间是 `x9:x13` ⇒ 模板预期数据区到 R13，`last_data_row=13` 成立。
* footer **R14**「合计」/ `R15` 是「三、审计说明：」+ `E15`「四、审计结论：」。
* 🔴 有效内容列 **10**（A..J）**小于** `max_column=15` ⇒ 有 **5 个空尾列**
  ⇒ UUID 列按**有效列右移一列**取 `K`（GC-3 口径；取 `P` 会把 5 个空列圈进受管区）。
* 🔴 **整册裸 IF 7 格，受管 sheet 命中 0 格** ⇒ 中性化不动本表（同 G9/G10/G8/G14/G13）。

═══ 🔴 二：`formula_columns` 是**空的** —— 没有一列在 R9-R13 每行都有公式 ═══

逐格实测（`<f>` 计数，数据区 R9-R13）：

```
A 0 · B 0 · C 0 · D 0 · E 0 · F 0 · G **1**（只 R9）· H 0 · I **2**（只 R9/R10）· J 0
```

`G9 = =D9=SUM(E9:F9)`（布尔校验）· `I9 = =E9+H9` · `I10 = =E10+H10`。

框架层的 `mode` 是**列级**的，而 `formula` 要求该格**有**公式（`view.has_formula`）⇒
`G` 判 formula 会在 R10-R13 四格抛、`I` 判 formula 会在 R11-R13 三格抛
（`ProtectedRegionWriteError`）。⇒ 两列只能判 **`editable`**，`formula_columns=()`。

与 G13 的 `B`/`C` 同型但**结论不同的那一步**：G13 的 B/C 是核心业务列（未审数/调整数），
必须受管；G12 的 `G`/`I` 原本是**前端派生量**（`rowCalcs.fvCheckOk` / `netHedgePnl`，
由 `calcFvAllocationCheck` / `calcNetHedgePnl` 纯函数算），按「派生校验 vs 第二真源」的
判据本该「保留前端、后端不声明」。**但那样 R11-R13 的 G/I 在 Excel 里会永远是空格**
（模板缺公式、后端又不写）⇒ 用户新增的第 3 行在 Excel 里看不到校验与净敞口套期损益。

⇒ 裁决：两列判 `editable` 并让前端把派生值**落库**（`G12HedgeDetailRow` 本轮新增
`fvCheck` / `netHedgePnl` 两字段，单一真源仍是那两个纯函数，`rowCalcs` 改为从行模型读、
对外 API 不变）。代价：`G9`/`I9`/`I10` 三格的模板公式在 materialize 后变成字面量 ——
与 G13 父行三格同型，如实登记在 :data:`TEMPLATE_FORMULA_COVERAGE_DEFECTS_G1202`。

🔴 三格都是**普通公式**（`<f>D9=SUM(E9:F9)</f>` 等），**不是 shared 主格** ⇒ 写字面量不会
撞 `SharedFormulaMasterWriteError`。判据钉住这一点（模板一旦改成 shared 主格就必须重裁）。

⇒ 这也推翻了 Task 4 的 P9 判据对 G12 的期望（「布尔列声明为 `formula` + `boolean`」）：
`boolean` 成立、`formula` 不成立。判据已按实测改写，保护面不放宽（见判据 docstring）。

═══ 🔴 三：五处模板缺陷（两处 spec 已登记 + 三处本轮新发现）═══

| # | 位置 | 缺陷 | 性质 |
|---|---|---|---|
| ① | `B14` | `=SUM(B9,B12,B13:B13)` **漏加 B10/B11** | **数值错** |
| ② | `I14` | `=SUM(I7:I13)` 起点越到**表头组行 R7** | 区间错 |
| ③ | `G` 列 | 公式只填 `R9`，R10-R13 空 | 覆盖缺失 |
| ④ | `I` 列 | 公式只填 `R9`/`R10`，R11-R13 空 | 覆盖缺失 |
| ⑤ | `H14` | **整格无公式** —— footer 漏了 H 列合计 | 覆盖缺失 |

①② 是 Task 2 的发现 G；③④⑤ 本轮新发现。一律**逐字记模板原式**（`formula_templates`
为空 ⇒ 全落 :data:`TEMPLATE_FOOTER_FORMULAS_G1202` 与
:data:`TEMPLATE_FORMULA_COVERAGE_DEFECTS_G1202`），判据按格比对；**不改模板字节**
（`backend/wp_templates/` 运行时只读 + sha 冻结），会计正确口径由前端承担。

═══ 🔴 四：footer R14 的 shared 组 `F14:J14` 跨越五列 ═══

```
B14/C14/D14/E14  plain <f>SUM(x9:x13)</f>
F14              **shared 主格** ref=F14:J14，body=SUM(F9:F13)
G14/J14          shared 成员格（si 同 F14）
H14              🔴 **无公式**（缺陷⑤）
I14              plain <f>SUM(I7:I13)</f>（缺陷②）
```

⇒ 同一 footer 行里 `F14:J14` 这个组被 `H14`（无公式）与 `I14`（独立公式）**打断** ——
组区间覆盖 5 列但实际只有 3 格是它的成员。`footer_carries_total_formula=True` 成立，
但 roundtrip 判据**不得**假设 footer 全列同形态。

═══ 字段键逐字取自前端行接口 ═══

`useG12HedgeDetail.G12HedgeDetailRow` 的 10 个受管字段（与模板列序 A..J 逐列对应）。
另有 4 个**非模板列**字段不受管：`rowId`（行身份）· `seq`（纯显示序号，模板 A 列是「项目」
不是序号）· `rowKind`（`fv_allocation`/`amortization`，驱动两类行的取值口径）· `remark`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G1202",
    "MANAGED_SHEET_G1202",
    "STORE_ITEM_ID_G1202",
    "FORMULA_COLUMNS_G1202",
    "BOOLEAN_COLUMNS_G1202",
    "FRONTEND_DERIVED_COLUMNS_G1202",
    "TEMPLATE_ROW_FORMULAS_G1202",
    "TEMPLATE_FOOTER_FORMULAS_G1202",
    "TEMPLATE_FORMULA_COVERAGE_DEFECTS_G1202",
    "FOOTER_SHAPE_FACTS_G1202",
    "FRONTEND_ONLY_FIELDS_G1202",
    "FIELD_SPECS_G1202",
    "FOOTER_ROW_G1202",
    "SEEDED_DATA_ROWS_G1202",
    "BLANK_DATA_ROWS_G1202",
]

MANAGED_SHEET_G1202: Final[str] = "明细表G12-2"
TEMPLATE_ID_G1202: Final[str] = "G1202"
SHEET_KEY_G1202: Final[str] = "g1202-managed"

#: 按值取自 `useG12HedgeDetail.ts` 的 `ITEM_ID`
STORE_ITEM_ID_G1202: Final[str] = "G12-hedge-detail-rows"
ROW_IDENTITY_STORE_KEY_G1202: Final[str] = "rowId"

#: 🔴 两级表头（横向组只有 D7:G7；其余六列是 R7:R8 纵向合并）
HEADER_GROUP_ROW_G1202: Final[int] = 7
HEADER_LEAF_ROW_G1202: Final[int] = 8
FIRST_DATA_ROW_G1202: Final[int] = 9
LAST_DATA_ROW_G1202: Final[int] = 13
FOOTER_ROW_G1202: Final[int] = 14
FOOTER_MARKER_G1202: Final[str] = "合计"

#: 🔴 模板**只预填了两行**（R9 FV 分配行 / R10 摊销行），R11-R13 整行全空（样式预留）。
#:   登记出来是为了让「为什么 last_data_row=13 而不是 10」可复核：footer 的 SUM 区间是
#:   `x9:x13` ⇒ 模板自己把数据区画到 R13。
SEEDED_DATA_ROWS_G1202: Final[tuple[int, ...]] = (9, 10)
BLANK_DATA_ROWS_G1202: Final[tuple[int, ...]] = (11, 12, 13)

#: 🔴 **空的** —— 没有一列在 R9-R13 每行都有公式（见模块头「二」）
FORMULA_COLUMNS_G1202: Final[tuple[str, ...]] = ()

#: 布尔校验列（裁决 G1R-H4 的第三个位点）。🔴 `mode` 是 `editable` 而不是 `formula`
#:   —— 模板只在 R9 一格有公式，判 formula 会让 R10-R13 抛。
BOOLEAN_COLUMNS_G1202: Final[tuple[str, ...]] = ("G",)

#: 前端派生但**必须落库**的两列（否则 R11-R13 在 Excel 里永远空）。
#:   单一真源是 `g12NetHedgeDetailCalc` 的 `calcFvAllocationCheck` / `calcNetHedgePnl`。
FRONTEND_DERIVED_COLUMNS_G1202: Final[tuple[str, ...]] = ("G", "I")

#: 数据区里**确实存在**的公式（`(列, 行) -> 逐字公式`）。不进 `formula_templates` ——
#: 那张表驱动 `mode=formula` 的逐格比对，而这两列判 `editable`。
#: 判据按本表逐格比对模板：模板补齐了 fill-down（或改形）就打红，缺陷可见。
TEMPLATE_ROW_FORMULAS_G1202: Final[dict[tuple[str, int], str]] = {
    ("G", 9): "=D9=SUM(E9:F9)",
    ("I", 9): "=E9+H9",
    ("I", 10): "=E10+H10",
}

#: footer R14 逐格实测（含缺陷①②；`H14` 无公式 ⇒ 不在表内，见缺陷⑤）
TEMPLATE_FOOTER_FORMULAS_G1202: Final[dict[str, str]] = {
    "B": "=SUM(B9,B12,B13:B13)",   # 🔴 缺陷①：漏加 B10/B11
    "C": "=SUM(C9:C13)",
    "D": "=SUM(D9:D13)",
    "E": "=SUM(E9:E13)",
    "F": "=SUM(F9:F13)",
    "G": "=SUM(G9:G13)",
    "I": "=SUM(I7:I13)",           # 🔴 缺陷②：起点越到表头组行 R7
    "J": "=SUM(J9:J13)",
}

#: 🔴 五处模板缺陷台账（`(编号, 位置, 缺陷, 会计正确口径/应有形态)`）。
#:   一律**不改模板字节**（运行时只读 + sha 冻结）；会计正确口径由前端承担。
TEMPLATE_FORMULA_COVERAGE_DEFECTS_G1202: Final[
    tuple[tuple[str, str, str, str], ...]
] = (
    (
        "①", "B14", "=SUM(B9,B12,B13:B13) 漏加 B10/B11 —— **数值错**",
        "应为 =SUM(B9:B13)",
    ),
    (
        "②", "I14", "=SUM(I7:I13) 起点越到表头组行 R7（R7/R8 是表头，不是数据）",
        "应为 =SUM(I9:I13)",
    ),
    (
        "③", "G10:G13", "G 列公式只填 R9，R10-R13 整格无公式（fill-down 缺失）",
        "每行应为 =D{r}=SUM(E{r}:F{r})；本轮由前端 fvCheck 落库补齐",
    ),
    (
        "④", "I11:I13", "I 列公式只填 R9/R10，R11-R13 整格无公式（fill-down 缺失）",
        "每行应为 =E{r}+H{r}；本轮由前端 netHedgePnl 落库补齐",
    ),
    (
        "⑤", "H14", "footer 漏了 H 列合计（整格无公式，B/C/D/E/F/G/I/J 八列都有）",
        "应为 =SUM(H9:H13)",
    ),
)

#: 🔴 footer 形态：`F14:J14` 那个 shared 组被 `H14`（无公式）与 `I14`（独立公式）打断
FOOTER_SHAPE_FACTS_G1202: Final[dict[str, object]] = {
    "kind": "sum_with_interrupted_shared_group",
    "plain_sum_columns": ["B", "C", "D", "E", "I"],
    "shared_master": "F14",
    "shared_ref": "F14:J14",
    "shared_members": ["G14", "J14"],
    "no_formula_columns": ["A", "H"],
    "note": (
        "shared 组 ref 覆盖 F..J 五列，但 H14 无公式、I14 是独立 plain 公式 ⇒ 实际成员只有 "
        "G14/J14 两格。按「组 ref 覆盖的列都是成员」去验会有两格假红；按「footer 全列同形态」"
        "去验会在 H14 与 I14 各打一次红。"
    ),
}

#: 前端行接口里**不是模板列**的字段（都不受管）。
FRONTEND_ONLY_FIELDS_G1202: Final[tuple[str, ...]] = (
    "rowId",    # 行身份
    "seq",      # 🔴 纯显示序号 —— 模板 A 列是「项目」不是序号（与 G11 的 seq 不同）
    "rowKind",  # fv_allocation / amortization：驱动两类行各自的取值口径
    "remark",   # 平台增强
)

#: 10 个受管字段（7 元组 `(column_key, column, mode, value_type, json_key, header_text, group_header_cell)`）。
#:
#: 顺序即 Excel 列序 A→J；`header_text` 取两级表头（有叶子取叶子、纵向合并取 R7）；
#: `json_key` 逐字取 `useG12HedgeDetail.G12HedgeDetailRow`。
#: 🔴 全 10 列都是 `editable` —— `formula_columns` 为空（见模块头「二」）。
FIELD_SPECS_G1202: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("item", "A", "editable", "text", "item", "项目", ""),
    ("net_position", "B", "editable", "text", "netPosition", "净头寸", ""),
    ("hedging_instrument", "C", "editable", "text", "hedgingInstrument", "套期工具", ""),
    (
        "instrument_fv_cumulative", "D", "editable", "amount",
        "instrumentFvCumulative", "套期工具累计公允价值变动", "D7",
    ),
    (
        "sales_portion", "E", "editable", "amount",
        "salesPortion", "对应预期销售的部分（计入净敞口套期损益）", "D7",
    ),
    (
        "purchase_portion", "F", "editable", "amount",
        "purchasePortion", "对应预期采购的部分（套期调整）", "D7",
    ),
    #: 🔴 布尔校验列：`editable` + `boolean`（模板只有 R9 一格公式 ⇒ 判 formula 会抛）
    ("fv_check", "G", "editable", "boolean", "fvCheck", "校验", "D7"),
    (
        "hedge_adj_amortization", "H", "editable", "amount",
        "hedgeAdjAmortization", "套期调整摊销（计入净敞口套期损益）", "",
    ),
    #: 🔴 同 G 列：模板只有 R9/R10 两格公式 ⇒ `editable` + 前端派生值落库
    ("net_hedge_pnl", "I", "editable", "amount", "netHedgePnl", "净敞口套期损益", ""),
    ("index_ref", "J", "editable", "text", "indexRef", "索引号", ""),
)

SPEC_G1202: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G1202,
    sheet_key=SHEET_KEY_G1202,
    table_key="g12_hedge_detail_rows",
    template_id=TEMPLATE_ID_G1202,
    table_name=f"GT_{TEMPLATE_ID_G1202}_HEDGE_DETAIL_ROWS",
    #: 🔴 有效列 10（A..J）**小于** max_column=15（5 个空尾列）⇒ 按有效列右移一列取 K
    uuid_col="K",
    first_data_row=FIRST_DATA_ROW_G1202,
    last_data_row=LAST_DATA_ROW_G1202,
    footer_row=FOOTER_ROW_G1202,
    #: 🔴 两级表头（唯一横向组 D7:G7；纵向合并列取 R7）—— 推翻 spec 的「无表头行」前提
    header_group_row=HEADER_GROUP_ROW_G1202,
    header_leaf_row=HEADER_LEAF_ROW_G1202,
    store_item_id=STORE_ITEM_ID_G1202,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G1202,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G1202,
    #: 🔴 空元组：没有一列在 R9-R13 每行都有公式
    formula_columns=FORMULA_COLUMNS_G1202,
    formula_templates={},
    footer_marker=FOOTER_MARKER_G1202,
    #: footer R14 带合计公式（含两处缺陷 + 一处打断的 shared 组）⇒ 需要区间归一化
    footer_carries_total_formula=True,
    error_label="G12-2 净敞口套期收益明细表",
    #: 幽灵行锚点用默认 `[0]`（A 列「项目」）—— 🔴 模板只预填 R9/R10，R11-R13 的 A 列是空，
    #:   但那三行也没有别的非空列 ⇒ 锚点取 A 列与取任何一列等价。
)
