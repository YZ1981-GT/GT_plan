"""H5-2「油气资产、累计折耗及减值准备明细表」—— sheet 层薄声明。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

═══ 🔴 先说结论：本 sheet 的映射率是全 H 最低档，10/54（19%）═══

不是漏做。前端 `H5DetailRow` 只有 **17 个字段**，模板有 **54 个有效列**：
  · **减值准备整块（AF..AT，15 列）前端一个字段都没有**；
  · 三个区块的「期初调整 / 账项调整 / 审定数」共 **24 列**在前端没有对端
    （H5 的行模型完全没有审定口径 —— 审定数在 `useH5Adjudication`/H5-1 审定表里，
     是**另一张表**，不是本 sheet 的列）；
  · 净值四列（AU/AV/AW/AX）也对不上，理由见下。

对照：H2 34/50（68%）· H3 成本 17/45（38%）· H8 58/58（100%）。
交付它的价值在于：**用户在 Excel 里真正手敲的那几格**（类别 / 名称 / 原值期初·增·减 /
增减方式 / 折耗期初·本期计提）能双向回来。剩下的要么是 Excel 自己算的公式列，
要么是前端根本不建模的审计调整段。

═══ 几何（openpyxl 逐格实测，禁推演）═══

册 `H/H5 油气资产.xlsx`（195,306 B）· **24 sheets** · 本 sheet
`有效内容列 54（A..BB）`，全 H 最宽。

* **四级**表头 **R9 / R10 / R11 / R12**（与 H4/H8/H2 同为四级；H3 是三级）
* 数据区 **R13-R32（20 行）**
* footer **R33**，`A33='合计'`，**全列 SUM**（无行内派生格）
* 数据行公式列 **19 个**（映射侧只有 1 个 `I` 进 `FORMULA_TEMPLATES`，理由见下）
* UUID 列 **BC** = 54 + 1（HC-13）

🔴 **footer 之后 R34-R39 是不受管的按类别小计区**，且与 H3/H4/H7 有一处不同：
行标签是**字面量**（`A35='探明矿区权益'` / `A36='未探明矿区权益'` /
`A37='井及相关设施'` / `A38='…'` / `A39='…'`），**不是** `=底稿目录!A9..A13` 引用。
照 H3/H7 的「标签取底稿目录」写判据会在这里假红。

═══ 三区块 × 四段（每块的「本期增减」再分两小列，四级表头的来源）═══

* **油气资产原值 D..P**（`D9`）
  - 未审数 `D10`：D 期初数 / E-F 本期增加（金额·增加方式）/ G-H 本期减少（金额·减少方式）/ I 期末数
  - 期初调整 `J10`（单列）· 账项调整 `K10`（K 本期增加 / L 本期减少）· 审定数 `M10`（M-P）
* **累计折耗 Q..AE**（`Q9`）
  - 未审数 `Q10`：Q 期初数 / R-S 本期增加（本期计提·其他增加）/ T-U 本期减少（处置·其他减少）/ V 期末数
  - 期初调整 `W10` · 账项调整 `X10`（X-Y 增 / Z-AA 减）· 审定数 `AB10`（AB-AE）
* **减值准备 AF..AT**（`AF9`）：与折耗块**逐列同构**
* 净值四列：`AU 期初净值·未审`（`=D-Q-AF`）/ `AV 期初净值·审定`（`=M-AB-AQ`）/
  `AW 期末净值·未审`（`=I-V-AK`）/ `AX 期末净值·审定`（`=P-AE-AT`）
* 尾部四个布尔列：`AY 是否提足折耗` · `AZ 是否闲置` · `BA 是否有权属证明` · `BB 是否抵押受限`

═══ 🔴 为什么 `V 折耗期末数` 与 `AW 期末净值` **不能**映射（关键判断）═══

按值取自 `useH5FormulaEngine` + `useH5Detail._recalcRow`：

    calcAssetEndBalance(begin, debit, credit) = begin + debit - credit
    calcContraEndBalance(begin, debit, credit) = begin + credit - debit
    calcNetValue(cost, accDepletion, impairment) = cost - accDepletion - impairment

    originalCostEnd = calcAssetEndBalance(begin, increase, decrease)   # = begin+inc-dec
    accDepletionEnd = calcContraEndBalance(begin, reversal, provision) # = begin+prov-rev
    netValue        = calcNetValue(originalCostEnd, accDepletionEnd, 0)   # 🔴 第三参是字面 0

① `I 原值期末数` 的模板式 `=SUM(D:E)-G` 即 `D+E-G`，与 `originalCostEnd` **逐项相等**
   ⇒ **可以**映射（本 sheet 唯一进 `FORMULA_TEMPLATES` 的公式列）。

② `V 折耗期末数` 的模板式 `=SUM(Q:S)-SUM(T:U)` 即 `Q+R+S-T-U`。前端的
   `accDepletionEnd = Q + R - reversal`，而 `reversal`（转回）**在模板里没有确定的列**：
   本期减少被拆成 `T 处置` 与 `U 其他减少` 两列，前端只有一个减项字段。
   若把 `accDepletionEnd` 映到 `V`：OO 侧 Excel 会按自己的 Q..U **重算** V（S/T/U 皆空 ⇒
   V = Q+R），回写时把这个**丢掉 reversal 的值**灌进 `accDepletionEnd` —— 静默错数。
   ⇒ `V` 判 template-only，`accDepletionReversal` / `accDepletionEnd` 判 store-only。
   🔴 也**不**把 `reversal` 猜成 `U 其他减少`：「转回是否属其他减少、还是应随处置走」
      是审计口径问题（带停下报告点，见 `DECLARED_COVERAGE_GAPS_H502` 的 H5-GAP-2）。

③ `AW 期末净值·未审` 的模板式 `=I-V-AK`（原值期末 − 折耗期末 − **减值期末**），
   而前端 `netValue` 把减值硬编码成 **0**（它没有减值字段）。两者只在减值恒为 0 时相等。
   ⇒ `AW` 判 template-only，`netValue` 判 store-only。映过去在有减值的项目上必错。

═══ 覆盖闭合 ═══

**10 映射 + 44 template-only == 54 有效列**，并集连续 A..BB 无缺口。
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H502",
    "MANAGED_SHEET_H502",
    "SHEET_KEY_H502",
    "STORE_ITEM_ID_H502",
    "ROW_IDENTITY_STORE_KEY_H502",
    "FORMULA_TEMPLATES_H502",
    "STORE_ONLY_FIELDS_H502",
    "TEMPLATE_ONLY_COLUMNS_H502",
    "DECLARED_COVERAGE_GAPS_H502",
    "DERIVED_TOTAL_KEYS_H502",
    "UNMANAGED_REGIONS_H502",
    "EFFECTIVE_COLUMNS_H502",
    "UUID_COL_H502",
]

MANAGED_SHEET_H502: Final[str] = "明细表H5-2"
TEMPLATE_ID_H502: Final[str] = "H52"
SHEET_KEY_H502: Final[str] = "h502-managed"
ROWS_TABLE_KEY_H502: Final[str] = "oil_gas_assets_detail_rows"

#: 🔴 **不是字面量**：`useH5Detail.ts` 的键由 `${ITEM_PREFIX}-rows` 拼接
#:    （`ITEM_PREFIX = 'H5-2'`，见 `useH5Detail.ts#L53`）⇒ 按值 grep `'H5-2-rows'`
#:    字面量**零命中**（HC-4 拼接解析：这是 slice 快照与实测不符的 5 处之一）。
STORE_ITEM_ID_H502: Final[str] = "H5-2-rows"

#: 行身份：`row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`（`addRow`）
#: / `row-${Math.random().toString(36).slice(2, 10)}`（载入回填）⇒ HC-7 族 A。
#: 🔴 全 H 里唯一**新增行自带随机后缀**的 entry（H3 的 `dc-${Date.now()}` 同毫秒会撞）。
ROW_IDENTITY_STORE_KEY_H502: Final[str] = "rowId"

HEADER_TOP_ROW_H502: Final[int] = 9
HEADER_GROUP_ROW_H502: Final[int] = 10
HEADER_SUB_ROW_H502: Final[int] = 11
HEADER_LEAF_ROW_H502: Final[int] = 12
FIRST_DATA_ROW_H502: Final[int] = 13
LAST_DATA_ROW_H502: Final[int] = 32
FOOTER_ROW_H502: Final[int] = 33
FOOTER_MARKER_H502: Final[str] = "合计"
EFFECTIVE_COLUMNS_H502: Final[int] = 54
UUID_COL_H502: Final[str] = "BC"

#: 🔴 footer 之后的**不受管区域**。与 H3/H4/H7 的同族区有一处关键不同：
#:    行标签是**字面量**（探明矿区权益 / 未探明矿区权益 / 井及相关设施 / … / …），
#:    **不是** `=底稿目录!A9..A13` 引用 ⇒ 照别条写「标签取底稿目录」的判据会在此假红。
UNMANAGED_REGIONS_H502: Final[tuple[dict[str, object], ...]] = (
    {
        "first_row": 34,
        "last_row": 39,
        "kind": "category_subtotal_block",
        "note": (
            "A34='其中：'；R35-R39 为 "
            "=SUMPRODUCT(($A$13:$A$32=$A35)*(D$13:D$32)) 形态的按类别小计。"
            "🔴 行标签是**字面量**（A35='探明矿区权益' / A36='未探明矿区权益' / "
            "A37='井及相关设施' / A38='…' / A39='…'），不是 =底稿目录!Ax 引用 —— "
            "与 H3/H4/H7 的同族区不同，不受管、不比对、不覆盖。"
        ),
    },
)

#: 🔴 模板有列但 HTML 无对端 ⇒ 不进 `field_specs`（Requirement 6.1）。**44 列**。
#: 三大成因：①前端无减值字段（AF..AT 整块 15 列）；②前端无审定口径（三块的
#: 期初调整 / 账项调整 / 审定数 共 24 列 —— 审定在 H5-1 是另一张表）；
#: ③算术不等（V / AU / AV / AW / AX，见 docstring 第 ②③ 条）。
TEMPLATE_ONLY_COLUMNS_H502: Final[tuple[tuple[str, str], ...]] = (
    ("B", "油气资产编号"),
    # ── 原值块：期初调整 / 账项调整 / 审定数 ─────────────────────────────────
    ("J", "期初调整"),
    ("K", "本期增加"),
    ("L", "本期减少"),
    ("M", "期初数"),
    ("N", "本期增加"),
    ("O", "本期减少"),
    ("P", "期末数"),
    # ── 累计折耗块：未审的其他增减两列 + 期末数 + 调整与审定 ──────────────────
    ("S", "其他增加"),
    ("T", "处置"),
    ("U", "其他减少"),
    ("V", "期末数"),
    ("W", "期初调整"),
    ("X", "本期计提"),
    ("Y", "其他增加"),
    ("Z", "处置"),
    ("AA", "其他减少"),
    ("AB", "期初数"),
    ("AC", "本期增加"),
    ("AD", "本期减少"),
    ("AE", "期末数"),
    # ── 减值准备整块（前端一个字段都没有）───────────────────────────────────
    ("AF", "期初数"),
    ("AG", "本期计提"),
    ("AH", "其他增加"),
    ("AI", "处置"),
    ("AJ", "其他减少"),
    ("AK", "期末数"),
    ("AL", "期初调整"),
    ("AM", "本期计提"),
    ("AN", "其他增加"),
    ("AO", "处置"),
    ("AP", "其他减少"),
    ("AQ", "期初数"),
    ("AR", "本期增加"),
    ("AS", "本期减少"),
    ("AT", "期末数"),
    # ── 净值四列（算术含减值项，前端 netValue 把减值写死 0）─────────────────
    ("AU", "未审净值"),
    ("AV", "审定净值"),
    ("AW", "未审净值"),
    ("AX", "审定净值"),
    # ── 尾部四个布尔列（前端本 sheet 无对应字段；闲置在 H5-4、权属在 H5-16）──
    ("AY", "是否提足折耗"),
    ("AZ", "是否闲置"),
    ("BA", "是否有权属证明"),
    ("BB", "是否抵押受限"),
)

#: HTML 有字段但模板无列（或算术不等不可映）⇒ store-only。
STORE_ONLY_FIELDS_H502: Final[tuple[str, ...]] = (
    # 模板本 sheet 无「油田 / 区块」列（B 是资产编号，与这两者都不是一回事）
    "oilField",
    "block",
    # 减项在模板里被拆成 处置/其他减少 两列，前端只有一个 ⇒ 不猜（H5-GAP-2）
    "accDepletionReversal",
    # 算术含未映射的 reversal ⇒ 映到 V 会被 Excel 重算覆盖（docstring ②）
    "accDepletionEnd",
    # 算术把减值写死 0，模板 AW 含减值项（docstring ③）
    "netValue",
    "remark",
)

#: 🔴 HC-6 派生合计副本 —— H5 的小计是 **computed**（`subtotalRow`）**不落库**，
#:    `_persist()` 只写 `rows.value` ⇒ **没有**派生合计键。显式声明空元组，
#:    免得复用 H4/H3 判据的人以为忘写了。
DERIVED_TOTAL_KEYS_H502: Final[tuple[str, ...]] = ()

DECLARED_COVERAGE_GAPS_H502: Final[tuple[dict[str, Any], ...]] = (
    {
        "gap_id": "H5-GAP-1",
        "title": "前端行模型完全没有**减值准备**与**审定口径**",
        "template_columns": [
            "J", "K", "L", "M", "N", "O", "P",
            "W", "X", "Y", "Z", "AA", "AB", "AC", "AD", "AE",
            "AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN", "AO", "AP",
            "AQ", "AR", "AS", "AT",
        ],
        "store_fields": [],
        "why_not_mapped": (
            "`H5DetailRow` 只有 17 个字段：类别 / 名称 / 油田 / 区块 / 原值四项 + 增减方式 / "
            "折耗四项 / 净值 / 备注。**没有任何减值字段**，也**没有任何审定字段** —— "
            "H5 的审定数在 `useH5Adjudication`（H5-1 审定表，键 `H5-1-cost-rows` / "
            "`H5-1-depletion-rows` / `H5-1-impairment-rows`），那是**另一张表**不是本 sheet 的列。"
            "39 列里没有一列有 store 对端 ⇒ 全判 template-only（OO 侧照旧可编辑，"
            "Excel 自己算自己的；只是不回写 HTML）。"
        ),
        "stop_and_report": (
            "要让这 31 列双向，需要给 `H5DetailRow` 补减值三项 + 三块审定四项"
            "（共约 19 个字段）并改 H5-2 的表格 UI ⇒ 属前端模型扩张 + 审计域确认"
            "（减值在明细表逐资产列示 vs 只在 H5-14 减值测算表汇总，是编制口径问题）。"
        ),
        "owner": "审计业务方 / spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
    {
        "gap_id": "H5-GAP-2",
        "title": "`accDepletionReversal`（转回）对应 `T 处置` / `U 其他减少` 哪一列，属审计口径",
        "template_columns": ["T", "U", "V"],
        "store_fields": ["accDepletionReversal", "accDepletionEnd"],
        "why_not_mapped": (
            "模板把折耗「本期减少」拆成 `T 处置` 与 `U 其他减少` 两列，前端只有一个减项字段"
            "`accDepletionReversal`（转回）。映到任一列都是对审计口径的猜测。"
            "连带 `V 期末数` 也不能映：模板式 =SUM(Q:S)-SUM(T:U)，Excel 会按自己的 Q..U 重算"
            "（S/T/U 皆空 ⇒ V=Q+R），回写时把**丢掉 reversal** 的值灌进 accDepletionEnd —— "
            "静默错数。前端式是 calcContraEndBalance(begin, reversal, provision) = begin+prov-rev。"
        ),
        "stop_and_report": (
            "「折耗转回是否计入其他减少、还是应随资产处置走」属审计口径裁决；"
            "定下来之后 T 或 U 之一 + V 可一并接通。"
        ),
        "owner": "审计业务方",
    },
    {
        "gap_id": "H5-GAP-3",
        "title": "`netValue` 把减值写死 0，模板 `AW` 含减值项",
        "template_columns": ["AU", "AV", "AW", "AX"],
        "store_fields": ["netValue"],
        "why_not_mapped": (
            "`useH5Detail._recalcRow` 里 netValue = calcNetValue(originalCostEnd, "
            "accDepletionEnd, **0**) —— 第三个实参是**字面 0**（前端没有减值字段）。"
            "模板 AW = I - V - AK（原值期末 − 折耗期末 − **减值期末**）。两者只在减值恒为 0 "
            "时相等 ⇒ 在有减值的项目上映过去必错。AU/AV/AX 另有期初/审定口径，前端更无对端。"
        ),
        "stop_and_report": "随 H5-GAP-1 一并解决（补上减值字段后 netValue 的第三参才有值可填）。",
        "owner": "同 H5-GAP-1",
    },
)

#: 10 个受管字段。**全部落在两个「未审数」段的手敲格上** —— 这正是本 sheet 唯一
#: 两侧口径一致的面（见 docstring）。
FIELD_SPECS_H502: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("category", "A", "editable", "text", "category", "油气资产类别", ""),
    ("name", "C", "editable", "text", "name", "油气资产名称", ""),
    # ── 油气资产原值 · 未审数 ────────────────────────────────────────────────
    ("cost_begin", "D", "editable", "amount", "originalCostBegin", "期初数", "D10"),
    ("cost_increase", "E", "editable", "amount", "originalCostIncrease", "金额", "E11"),
    ("increase_reason", "F", "editable", "text", "increaseReason", "增加方式", "E11"),
    ("cost_decrease", "G", "editable", "amount", "originalCostDecrease", "金额", "G11"),
    ("decrease_reason", "H", "editable", "text", "decreaseReason", "减少方式", "G11"),
    # 🔴 唯一可映的公式列：模板 `=SUM(D:E)-G` 与前端 calcAssetEndBalance 逐项相等
    ("cost_end", "I", "formula", "amount", "originalCostEnd", "期末数", "D10"),
    # ── 累计折耗 · 未审数（只有期初与本期计提两格口径一致）─────────────────────
    ("depletion_begin", "Q", "editable", "amount", "accDepletionBegin", "期初数", "Q10"),
    ("depletion_provision", "R", "editable", "amount", "accDepletionProvision", "本期计提", "R11"),
)

#: 🔴 只登记进了 `field_specs` 的公式列 —— 本 sheet 只有 `I` 一个。
#:    其余 18 个公式列（M/N/O/P · V/AB/AC/AD/AE · AK/AQ/AR/AS/AT · AU/AV/AW/AX）
#:    全是 template-only，由 Excel 自行重算。
FORMULA_TEMPLATES_H502: Final[dict[str, str]] = {
    "I": "=SUM(D{r}:E{r})-G{r}",
}

SPEC_H502: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H502,
    sheet_key=SHEET_KEY_H502,
    table_key=ROWS_TABLE_KEY_H502,
    template_id=TEMPLATE_ID_H502,
    table_name=f"GT_{TEMPLATE_ID_H502}_ROWS",
    uuid_col=UUID_COL_H502,
    first_data_row=FIRST_DATA_ROW_H502,
    last_data_row=LAST_DATA_ROW_H502,
    footer_row=FOOTER_ROW_H502,
    header_group_row=HEADER_TOP_ROW_H502,
    header_leaf_row=HEADER_LEAF_ROW_H502,
    store_item_id=STORE_ITEM_ID_H502,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H502,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H502,
    formula_columns=tuple(FORMULA_TEMPLATES_H502),
    formula_templates=FORMULA_TEMPLATES_H502,
    footer_marker=FOOTER_MARKER_H502,
    error_label="H5-2 油气资产明细表",
)
