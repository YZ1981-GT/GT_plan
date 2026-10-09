# -*- coding: utf-8 -*-
"""G13-2「公允价值变动收益明细表」—— sheet 层薄声明（固定 10 行 + 父子行 + 布尔 footer）。

spec: `g-cycle-single-region-detail-lanes` · Task 12 / C-11
　　　列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` §7 + 本轮逐格实测

═══ 🔴 一：受管载体不是工具明细，是**分类骨架**（用户拍板选项 A）═══

模板 `明细表G13-2` 的 R11-R20 是**固定 10 个损益表项目**（交易性金融资产 / 其中：指定… /
衍生金融资产 / … / 以公允价值计量的投资性房地产 / 其他），带三层父子结构。
而前端 `G13-detail-rows` 存的是平台增强出来的**金融工具级明细**（`instrumentName` 用户
自填、`addRow`/`removeRow` 动态增删）⇒ 两侧行模型**不同构**：前端第 N 行明细根本不对应
模板第 N 个项目行。直接按顺序映射会把第 N 条工具写进第 N 个损益项目行 —— **产出错数**。

前端早有 `buildG13CategorySkeleton()` 按 10 个固定项目汇总出骨架（`g13Constants.
G13_ADJUDICATION_ITEMS` 的 `rowKey`/`label`/`kind`/`indent` 与模板 R11-R20 逐行对应），
但它是 `computed`、**不落库** ⇒ 双向回写没有载体。

⇒ 本轮把骨架**持久化**成独立 store item **`G13-detail-skeleton`**（前端
`g13SkeletonStore.ts`），受管它；工具明细 `G13-detail-rows` 保持 HTML-only 平台增强。
🔴 **`STORE_ITEM_ID_G1302` 不是 `G13-detail-rows`** —— 这是本 lane 与另八条最大的差异，
照抄别家的「store item = 前端主 rows 键」会接错载体。

🔴 手工覆盖优先：骨架值默认来自工具明细汇总；OO 侧改动回流后若被汇总无条件重算，等于
回流无效 ⇒ 落库行带 `manualOverride`，有标记的行用存库值。见 `g13SkeletonStore.ts` 模块头。

⇒ 推论：**前端 21 个工具明细字段一个都不用删**（`evidence` §7.2 的「删 5」建议基于
「受管工具明细」这个已被替换的前提；`instrumentType`/`remark` 还是骨架分类的驱动字段，
删了就分不出「其中：指定」与「衍生」两类子行）。

═══ 几何（openpyxl + XML 逐格实测，禁推演）═══

`明细表G13-2`：`max_row=34` / `max_column=12` / **0 definedName** / merged 8 个。

* **两级表头 R9/R10**：横向组 `B9:D9`（本期数）· `F9:J9`（对应科目-公允价值变动）；
  纵向合并 `A9:A10`（项目）· `E9:E10`（对应科目）· `K9:K10`（核对）· `L9:L10`（索引号）。
  `R8` 是段标题「二、审计过程：」只占 `A8`，不是表头行。
* 🔴 横向组 `F9:J9` **含 J 列**，而 `J10`=「计入损益」语义上不属「公允价值变动」组 ——
  evidence §7.1 写作 `F9:I10` 不准确。判据按**实测**的 `F9:J9` 钉住。
* 数据区 **R11-R20（固定 10 行）** / footer **R21**「合计」/ R22「三、审计说明：」/
  R26「编制说明：」。
* 有效内容列 **12**（A..L）**恰等于** `max_column` ⇒ UUID 列取 `M`。
* 🔴 **整册裸 IF 11 格，受管 sheet 命中 0 格** ⇒ 中性化不动本表（与 G9/G10/G8/G14 同族，
  与 G11 的 44 格相反）⇒ `D`/`I`/`J`/`K` 四列判 `formula` 成立。

═══ 🔴 二：B/C 两列判 `editable`（行级 mask 无解，裁决同 G8 的 R/T）═══

`B`/`C` 在数据区**只有 3 格有公式**（父行 R11/R14/R17 汇总子行），其余 7 格是空可填格：

```
B11 plain =B12+B13   B14 plain =B15+B16   B17 plain =B18     ← 三格普通公式（非 shared 主格）
B12 B13 B15 B16 B18 B19 B20  ← 无公式（空格）
C 列同形
```

框架层的 `mode` 是**列级**的，同一列无法表达「3 行 formula + 7 行 editable」：

| 候选 | 后果 |
|---|---|
| `formula` | 7 个无公式格触发 `ProtectedRegionWriteError`（`view.has_formula` 为假） |
| `auto_source` | 3 个公式格触发 `ProtectedRegionWriteError`（要求该格**不是**公式） |
| 拆多 spec | 父行 `{11,14,17}` **非连续**，`first_data_row`/`last_data_row` 是连续区间
  ⇒ 要 **7 个 spec**（R11 / R12-13 / R14 / R15-16 / R17 / R18 / R19-20），
  且 footer 只有一行 R21、归属不清 ⇒ 为保 3 格公式付出 7 份 instrumentation + 契约膨胀 |
| **`editable`** ✅ | 三个父行的模板公式在 materialize 后变成字面量（**公式丢失**） |

选 `editable`。三条依据：

1. 逐格实测三格是**普通公式**（`<f>B12+B13</f>`）而**不是 shared 主格** ⇒ 写字面量不会撞
   `SharedFormulaMasterWriteError`（`excel_materialize` 对非 formula/auto_source 的格只拦
   共享公式主格）。若哪天模板把它们改成 shared 主格，本裁决立即失效 ⇒ 判据钉住这一点。
2. 值仍然正确：前端 `buildG13CategorySkeleton` 的父行值 = 子行汇总，与模板公式**同口径**
   ⇒ 写进去的数与公式算出来的数相等。丢的只是「在 OO 里改子行后父行自动重算」这个
   Excel 内联动，而 OO 改动**必须回流**才算生效、回流后前端会重算骨架 ⇒ 窗口极小。
3. 与 G8 的 `R`/`T` 裁决同型（那两列模板整格无公式 ⇒ 判 `formula` 会抛 ⇒ 只能 `editable`，
   正是判据 P12 的技术根据）。

⇒ 🔴 **这推翻 tasks.md Task 12 原写的 `formula_columns=("B","C","D","I","J","K")`**：
`B`/`C` 不在公式列里。父行三格的逐行不同形公式落 :data:`TEMPLATE_PARENT_FORMULAS_G1302`
（照 G8 的 `TEMPLATE_ROW_FORMULAS_G802` 范式），由判据按行比对 —— 缺陷/漂移可见，
但不参与 materialize。

═══ 🔴 三：footer R21 是枚举相加 + 布尔混行 ═══

```
B21 = =B11+B14+B17+B19+B20      ← 五个**顶层**行枚举相加（非 SUM 区间）
C21 = shared 主格 ref=C21:D21，=C11+C14+C17+C19+C20
D21 = shared 成员格（展开 =D11+D14+D17+D19+D20）   ← 🔴 D21 也是枚举相加，不是 SUM
I21 = =SUM(I11:I20)   J21 = =SUM(J11:J20)          ← 只有 I/J 是 SUM 区间
K21 = shared 成员格（主格 K11），展开 =J21=D21       ← 🔴 footer 也是布尔（裁决 G1R-H4）
```

⇒ 同一 footer 行**三种约定**混行（枚举相加 3 格 + SUM 2 格 + 布尔 1 格）。
`footer_carries_total_formula=True`，但 roundtrip 判据**不得**假设 footer 全列同形态
（同 I2-2/I3-2 的 `row_formula_applied` 教训）。

═══ 🔴 四：shared 组的起点三列一样、K 列自成一格 ═══

逐格实测（首版按 D/I/J 的形态推演 K，判据打红后纠正）：

```
D/I/J：R11 普通公式 · **R12 是 shared 主格**（ref 分别 D12:D20 / I12:I20 / J12:J20）
       · R13-R20 成员格；footer R21 另有自己的公式（D21 属 C21:D21 组、I21/J21 是 SUM）
K    ：R11 与 R12 **两格都是普通公式** · **R13 才是 shared 主格**，
       且 ref = **K13:K21** —— 🔴 该组**跨越 footer 边界**，数据区与合计行共用同一份
       公式文本 ⇒ 改 K13 会同时改掉 footer 的布尔格。
```

四列**逐行同形**（`=B{r}+C{r}` / `=F{r}+H{r}` / `=G{r}` / `=J{r}=D{r}`）⇒ 都能进
:data:`FORMULA_TEMPLATES_G1302`、判据可逐格比对（openpyxl 会展开成员格）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G1302",
    "MANAGED_SHEET_G1302",
    "STORE_ITEM_ID_G1302",
    "LEGACY_INSTRUMENT_STORE_ITEM_ID_G1302",
    "FORMULA_TEMPLATES_G1302",
    "FORMULA_COLUMNS_G1302",
    "BOOLEAN_COLUMNS_G1302",
    "PARENT_ROWS_G1302",
    "CHILD_ROWS_G1302",
    "TOP_LEVEL_LEAF_ROWS_G1302",
    "TEMPLATE_PARENT_FORMULAS_G1302",
    "TEMPLATE_ROW_LABELS_G1302",
    "TEMPLATE_BELONG_LABELS_G1302",
    "FOOTER_SHAPE_FACTS_G1302",
    "FRONTEND_ONLY_FIELDS_G1302",
    "FIELD_SPECS_G1302",
    "FOOTER_ROW_G1302",
]

MANAGED_SHEET_G1302: Final[str] = "明细表G13-2"
TEMPLATE_ID_G1302: Final[str] = "G1302"
SHEET_KEY_G1302: Final[str] = "g1302-managed"

#: 🔴 受管载体 = **分类骨架**（按值取自 `useG13Detail.ts` 的 `ITEM_ID_SKELETON`）。
#:   不是工具明细键 —— 见模块头「一」。
STORE_ITEM_ID_G1302: Final[str] = "G13-detail-skeleton"
#: 工具明细（HTML-only 平台增强，**不受管**）。登记出来是为了让「为什么不受管它」可复核。
LEGACY_INSTRUMENT_STORE_ITEM_ID_G1302: Final[str] = "G13-detail-rows"
#: 固定行集 ⇒ 行身份是业务键 `rowKey`（同 G14；不是 G13 工具明细的 `rowId`）
ROW_IDENTITY_STORE_KEY_G1302: Final[str] = "rowKey"

#: 两级表头（横向组行 / 叶子行）
HEADER_GROUP_ROW_G1302: Final[int] = 9
HEADER_LEAF_ROW_G1302: Final[int] = 10
FIRST_DATA_ROW_G1302: Final[int] = 11
LAST_DATA_ROW_G1302: Final[int] = 20
FOOTER_ROW_G1302: Final[int] = 21
FOOTER_MARKER_G1302: Final[str] = "合计"

#: 🔴 有子行的父行（B/C 为汇总公式）—— **非连续**，这是「拆多 spec 不可行」的根据
PARENT_ROWS_G1302: Final[tuple[int, ...]] = (11, 14, 17)
#: 子行（B/C 手填）
CHILD_ROWS_G1302: Final[tuple[int, ...]] = (12, 13, 15, 16, 18)
#: 🔴 **无子行的顶层行**（B/C 手填）—— spec 原文把它们和父行混为一类，
#:   照那样把 B/C 判 formula 会覆盖用户手填值（与 G8 误标同型危害）
TOP_LEVEL_LEAF_ROWS_G1302: Final[tuple[int, ...]] = (19, 20)

#: 公式列：`B`/`C` **不在**其中（见模块头「二」）。四列逐行同形，可逐格比对。
FORMULA_COLUMNS_G1302: Final[tuple[str, ...]] = ("D", "I", "J", "K")

#: 🔴 布尔校验列（裁决 G1R-H4）：数据区 K11-K20 + **footer K21** 两个位点
BOOLEAN_COLUMNS_G1302: Final[tuple[str, ...]] = ("K",)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R11 且 R11-R20 同型。
FORMULA_TEMPLATES_G1302: Final[dict[str, str]] = {
    "D": "=B{r}+C{r}",      # 审定数 = 未审数 + 调整数
    "I": "=F{r}+H{r}",      # 公允价值 = 成本 + 累计公允价值变动
    "J": "=G{r}",           # 计入损益 = 本期公允价值变动
    "K": "=J{r}=D{r}",      # 🔴 布尔：计入损益 ↔ 审定数
}

#: 🔴 父行 `B`/`C` 的**逐行不同形**汇总公式（`(列, 行) -> 逐字公式`）。
#:
#: 不进 `formula_templates`（那张表驱动 `mode=formula` 的逐格比对，而 B/C 判 `editable`）。
#: 单条模板表达不了：R11 汇两个子行、R14 汇两个、**R17 只汇一个**（`=B18` 不是 SUM）。
#: 判据按本表逐格比对模板，模板一旦改形（例如统一成 SUM）就打红。
TEMPLATE_PARENT_FORMULAS_G1302: Final[dict[tuple[str, int], str]] = {
    ("B", 11): "=B12+B13",
    ("C", 11): "=C12+C13",
    ("B", 14): "=B15+B16",
    ("C", 14): "=C15+C16",
    ("B", 17): "=B18",
    ("C", 17): "=C18",
}

#: 🔴 模板 A11-A20 **逐字**行名（含缩进空格）。与前端
#: `g13SkeletonStore.TEMPLATE_ROW_LABELS_G13` 双向锁，判据再与模板 A 列比第三方。
#: 子行在模板里带 5 个前导空格，前端用 `indent` 渲染 ⇒ 两者**不是**逐字相等。
TEMPLATE_ROW_LABELS_G1302: Final[tuple[str, ...]] = (
    "交易性金融资产",
    "其中：指定为以公允价值计量且其变动计入当期损益的金融资产",
    "     衍生金融资产",
    "交易性金融负债",
    "其中：指定为以公允价值计量且其变动计入当期损益的金融负债",
    "     衍生金融负债",
    "其他非流动金融资产",
    "其中：指定为以公允价值计量且其变动计入当期损益的金融资产",
    "以公允价值计量的投资性房地产",
    "其他",
)

#: 🔴 模板 E11-E20 逐字预填的「对应科目」（**E20 模板为空** ⇒ 空串）
TEMPLATE_BELONG_LABELS_G1302: Final[tuple[str, ...]] = (
    "交易性金融资产",
    "交易性金融资产",
    #: 🔴 两个衍生子行的分隔符是 **`/`** 不是 `-`（首版按探针乱码写成 `-`，判据打红后实测纠正）
    "交易性金融资产/衍生金融资产",
    "交易性金融负债",
    "交易性金融负债",
    "交易性金融负债/衍生金融负债",
    "其他非流动金融资产",
    "其他非流动金融资产",
    "投资性房地产",
    "",
)

#: 🔴 footer R21 三种约定混行 —— roundtrip 判据不得假设全列同形态（见模块头「三」）
FOOTER_SHAPE_FACTS_G1302: Final[dict[str, object]] = {
    "kind": "mixed_enumerated_sum_and_boolean",
    #: 枚举相加（五个**顶层**行，非 SUM 区间）
    "enumerated_columns": ["B", "C", "D"],
    "enumerated_detail": {
        "B21": "=B11+B14+B17+B19+B20",
        "C21": "=C11+C14+C17+C19+C20",
        "D21": "=D11+D14+D17+D19+D20",
    },
    #: 纯 SUM 区间
    "pure_sum_columns": ["I", "J"],
    #: 🔴 布尔（裁决 G1R-H4 的第二个位点）
    "boolean_columns": ["K"],
    "boolean_detail": {"K21": "=J21=D21"},
    #: 无公式的列
    "empty_columns": ["E", "F", "G", "H", "L"],
    "note": (
        "同一 footer 行三种约定：枚举相加 3 格 + 纯 SUM 2 格 + 布尔 1 格。"
        "C21 是 shared 主格（ref=C21:D21）、D21 是它的成员格；"
        "🔴 K21 属于 **K13:K21** 那个 shared 组（主格 K13）—— 该组**跨越 footer 边界**，"
        "数据区与合计行共用一份公式文本 ⇒ 改 K13 会同时改掉 footer 的布尔格。"
        "⇒ 看 XML 会得到自闭合 <f/>，openpyxl 才展开；判 footer 形态必须分清两层口径。"
    ),
}

#: 骨架展示行（前端 `G13SkeletonDisplayRow`）里**不是模板列**的字段，都不受管。
FRONTEND_ONLY_FIELDS_G1302: Final[tuple[str, ...]] = (
    "rowKey",          # 行身份
    "kind",            # main / ofWhich / derivative（父子层级的语义来源）
    "indent",          # 缩进层级（模板用前导空格表达）
    "emphasize",       # 视觉强调（衍生工具红字）
    "bsReconciled",    # 成本+累计=公允价值 的本地校验（模板只有 K 一个核对列）
    "instrumentCount", # 该分类下的工具明细条数（平台增强）
    "manualOverride",  # 🔴 手工覆盖标记（骨架落库的控制位，不是模板列）
)

#: 12 个受管字段（7 元组 `(column_key, column, mode, value_type, json_key, header_text, group_header_cell)`）。
#:
#: 顺序即 Excel 列序 A→L；`header_text` 取两级表头（有叶子取叶子、纵向合并取 R9）；
#: `json_key` 逐字取 `g13SkeletonStore.G13SkeletonDisplayRow`。
FIELD_SPECS_G1302: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    #: A9:A10 纵向合并 ⇒ 取 R9「项目」；固定行集由 TEMPLATE_ROW_LABELS_G1302 锁死
    ("item_label", "A", "editable", "text", "label", "项目", ""),
    #: 🔴 B/C 判 editable 而非 formula（父行三格公式会被字面量覆盖，见模块头「二」）
    ("current_unadjusted", "B", "editable", "amount", "currentUnadjusted", "未审数", "B9"),
    ("adjustment", "C", "editable", "amount", "adjustment", "调整数", "B9"),
    ("current_audited", "D", "formula", "amount", "currentAudited", "审定数", "B9"),
    #: E9:E10 纵向合并 ⇒ 取 R9「对应科目」；模板预填科目名，允许现场改写
    ("belong_label", "E", "editable", "text", "belongLabel", "对应科目", ""),
    ("cost", "F", "editable", "amount", "cost", "成本", "F9"),
    ("period_fv_change", "G", "editable", "amount", "periodFvChange", "本期公允价值变动", "F9"),
    (
        "cumulative_fv_change", "H", "editable", "amount",
        "cumulativeFvChange", "累计公允价值变动", "F9",
    ),
    ("fair_value", "I", "formula", "amount", "fairValue", "公允价值", "F9"),
    #: 🔴 J 虽在「对应科目-公允价值变动」组标题 F9:J9 之内，语义上是独立的「计入损益」
    ("amount_in_pl", "J", "formula", "amount", "amountInPl", "计入损益", "F9"),
    #: 🔴 布尔校验列（K9:K10 纵向合并）：`=J{r}=D{r}` 求值 TRUE/FALSE
    ("cross_check", "K", "formula", "boolean", "plReconciled", "核对", ""),
    ("source_index", "L", "editable", "text", "sourceIndex", "索引号", ""),
)

SPEC_G1302: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G1302,
    sheet_key=SHEET_KEY_G1302,
    table_key="g13_detail_skeleton",
    template_id=TEMPLATE_ID_G1302,
    table_name=f"GT_{TEMPLATE_ID_G1302}_DETAIL_SKELETON",
    #: 有效内容列 12（A..L）恰等于 `max_column`（无空尾列）⇒ 两个 uuid 口径重合，取 M
    uuid_col="M",
    first_data_row=FIRST_DATA_ROW_G1302,
    last_data_row=LAST_DATA_ROW_G1302,
    footer_row=FOOTER_ROW_G1302,
    #: 🔴 两级表头（横向组 B9:D9 / F9:J9；纵向合并列取 R9）
    header_group_row=HEADER_GROUP_ROW_G1302,
    header_leaf_row=HEADER_LEAF_ROW_G1302,
    store_item_id=STORE_ITEM_ID_G1302,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G1302,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G1302,
    formula_columns=FORMULA_COLUMNS_G1302,
    formula_templates=FORMULA_TEMPLATES_G1302,
    footer_marker=FOOTER_MARKER_G1302,
    #: footer R21 带合计公式（三种约定混行）⇒ 需要区间归一化
    footer_carries_total_formula=True,
    error_label="G13-2 公允价值变动收益明细表",
    #: 幽灵行锚点用默认 `[0]`（A 列「项目」）—— 模板 A11-A20 预填 10 个项目名，恒非空。
)
