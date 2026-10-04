"""H3-2（**成本模式**）「投资性房地产明细表」—— sheet 层薄声明。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

═══ 本 sheet 在 H 循环里的位置 ═══

H3 是本 slice 唯二的**变体轴** entry（另一条是 H7）：同一 wp_code 下两套并列 sheet
（成本模式 / 公允价值模式），源模板 sheet 名不同但 sheet_code 尾码相同。
两套**各有独立持久化键**（不是 E1-3 那种两张同尾码 sheet 共用一个键）⇒ 两张都进受管面，
各自一个 `RowTableSheetSpec`。本文件是成本模式那张。

═══ 几何（openpyxl 逐格实测，禁推演）═══

册 `H/H3 投资性房地产.xlsx`（146,096 B）· **22 sheets** · 本 sheet
`max_row=48` / `max_column=49`，**有效内容列 45（A..AS）** —— `max_column=49` 是空列尾巴。

* **三级**表头 **R9 / R10 / R11**（H4/H8/H2 是四级 ⇒ `header_group_row` 不能照抄）
* 数据区 **R13-R27（15 行）**
* footer **R28**，`A28='合计'`，C28..AQ28 **全部** `=SUM(x13:x27)`
  （H2 的 footer 有 4 格行内派生 ⇒ 那条判据在本 sheet 不适用，这里是纯列 SUM）
* 数据行公式列 **17 个**（映射侧 7 个进 `FORMULA_TEMPLATES`）
* UUID 列 **AT** = 有效内容列（45）+ 1（HC-13）

🔴 **footer 之后还有第二区域 R29-R33，必须声明为不受管**：
`A29='其中：'` + R30-R33 四行按 `=SUMPRODUCT(($A$13:$A$27=$A30)*(C$13:C$27))` 做的
**按类别小计**，行标签取 `=底稿目录!A9..A12`。`RowTableSheetSpec` 只有一个 `footer_row`，
不显式登记这 5 行，merge 有可能把它们当数据行覆盖 —— 覆盖一次整块分类小计就写坏了。
（H2 的 footer 之下**没有**这个区，H4/H8 有 ⇒ 逐 sheet 现算，不按循环推演。）

═══ 三区块 × 四段（表头合并区逐字实测）═══

* **投资性房地产原值 C..O**（`C9`）
  - 未审数 `C10`：C 期初余额 / D 本年增加 / E 增加方式 / F 本年减少 / G 减少方式 / H 期末余额
  - 期初调整 `I10`（单列，纵向合并到 R12）
  - 账项调整 `J10`：J 本期增加 / K 本期减少
  - 审定数 `L10`：L 期初余额 / M 本年增加 / N 本年减少 / O 期末余额
* **累计折旧/累计摊销 P..AB**（`P9`）：同上四段（未审 P-U / 期初调整 V / 账项调整 W-X / 审定 Y-AB）
* **减值准备 AC..AO**（`AC9`）：同上四段（未审 AC-AH / 期初调整 AI / 账项调整 AJ-AK / 审定 AL-AO）
* 尾部四列：`AP 期初净值`（公式 `=L-Y-AL`）· `AQ 期末净值`（公式 `=O-AB-AO`）·
  `AR 是否有权属证明` · `AS 是否抵押受限`

═══ 🔴 核心缺口：模板四段与前端四分是**正交**的两套分类 ═══

模板把调整按**作用位置**分两段：`期初调整`（调期初余额）+ `账项调整`（调本期发生额）。
前端 `DetailCostRow` 把调整按**来源**分两档：`costAje`（审计调整）+ `costRje`（重分类调整），
且两者都作用在**期末**口径上（`costAudited = calcAuditedAmount(costUnadj, costAje, costRje)`
= `costUnadj + costAje + costRje`，而 `costUnadj` 默认取 `costEnd` 即期末）。

两套分类是**正交维度**，不存在 1:1 映射：
  · 把 `costAje` 映到 `I 期初调整` ⇒ 审计调整被当成调期初，`M/N` 会算错本期发生额；
  · 映到 `J 本期增加` ⇒ 丢掉减少方向，且 RJE 无处可落。
⇒ `I / J / K / L / M / N` 六列判 **template-only**，`costUnadj/costAje/costRje`
   三字段判 **store-only**；两侧只在**期末**这一点上对齐（`O ↔ costAudited`）。
折旧块（`V/W/X/Y/Z/AA`）与减值块（`AI/AJ/AK/AL/AM/AN`）同理。

🔴 这条缺口**带停下报告点**：把 AJE/RJE 摊到「期初 / 本期增加 / 本期减少」三个位置上
属审计域裁决（哪部分调整属于追溯调整期初、哪部分属于本期），不由接线方拍板。
形态与 H2-GAP-1 同族：宁可留**可见缺口**，不要**不可见错数**。

═══ 另两处 1 格对 2 字段（同样不硬凑）═══

* `D 本年增加` / `F 本年减少`：前端把增减各拆成两个字段
  —— `costIncrease`（本期增加）+ `transferIn`（他科目转入，如 H1→H3）
  / `costDecrease` + `transferOut`。`_normalize` 里 `costEnd = costBegin + costInc
  - costDec + transIn - transOut` ⇒ 要让模板 `H=C+D-F` 与前端 `costEnd` 相等，
  必须 `D = costIncrease + transferIn`、`F = costDecrease + transferOut`。
  映射任一分项都会让 Excel 的 H 与 HTML 的 costEnd 在转入/转出非零时**静默不等**。
  ⇒ D/F 判 template-only，四个分项判 store-only。
  （🔴 **不能**照 H2-GAP-2 那样折叠：`transferIn/transferOut` 是活字段 ——
   `useH3TransferEngine.ts` / `useH3TransferReview.ts` / `互转审核表H3-6` 在用，
   与 H2 那个自带 `@deprecated`、全仓零写入点的 `transferOut` 不是一回事。）
* `E 增加方式` / `G 减少方式`：前端只有**一个** `changeType`，其选项表
  （`CHANGE_TYPE_OPTIONS`）**混装双向** —— 增加类（购入 / 自建完工转入 / 自用转投资 /
  在建转投资）与减少类（处置 / 转为自用 / 转出）在同一个字段里。映到任一列都会把
  另一方向的取值写进错列 ⇒ 两列判 template-only，`changeType` 判 store-only。

═══ 🔴 `AR 是否有权属证明` 不是 `ownershipRestricted` ═══

前端 `ownershipRestricted` 的注释逐字是「是否权属受限」。「有产权证明」与「权属未受限」
是两个事实（有证也可能被抵押查封）。H3 的权属核对另有专表（`产权核对表H3-12` +
`useH3TitleCheck.ts`）⇒ `AR` 判 template-only，`ownershipRestricted` 判 store-only。
`AS 是否抵押受限` ↔ `mortgaged`（注释「是否抵押/质押」）语义一致，正常映射。

═══ 覆盖闭合 ═══

**17 映射 + 28 template-only == 45 有效列**，并集连续 A..AS 无缺口。
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H302_COST",
    "MANAGED_SHEET_H302_COST",
    "SHEET_KEY_H302_COST",
    "STORE_ITEM_ID_H302_COST",
    "ROW_IDENTITY_STORE_KEY_H302_COST",
    "FORMULA_TEMPLATES_H302_COST",
    "STORE_ONLY_FIELDS_H302_COST",
    "TEMPLATE_ONLY_COLUMNS_H302_COST",
    "DECLARED_COVERAGE_GAPS_H302_COST",
    "DERIVED_TOTAL_KEYS_H302_COST",
    "UNMANAGED_REGIONS_H302_COST",
    "EFFECTIVE_COLUMNS_H302_COST",
    "UUID_COL_H302_COST",
]

MANAGED_SHEET_H302_COST: Final[str] = "明细表（成本模式）H3-2"
TEMPLATE_ID_H302_COST: Final[str] = "H32C"
SHEET_KEY_H302_COST: Final[str] = "h302cost-managed"
ROWS_TABLE_KEY_H302_COST: Final[str] = "investment_property_cost_detail_rows"

#: 按值取自 `useH3DetailCost.ts#L73` 的 `ITEM_ID`，不按 sheet 号推演。
STORE_ITEM_ID_H302_COST: Final[str] = "H3-2-cost-rows"

#: 行身份：`dc-${Math.random().toString(36).slice(2, 8)}`（载入回填）
#: / `dc-${Date.now()}`（`addRow`）⇒ HC-7 族 A（非位置派生）。
#: 🔴 slice 的 `row_identity_note` 已说明：`_normalize(raw, i)` 的第二个实参是下标，
#:    但它绑给 `seq`（展示序号）不是 `rowId` —— 判据必须只取 `rowId:` 自己的值表达式。
#: 🔴 已知弱点（登记，不在本文件修）：`rowId` 缺失时每次载入生成**新**串（不稳定），
#:    且 `addRow` 用 `dc-${Date.now()}` 无随机后缀（同毫秒连加两行会撞 id）。
ROW_IDENTITY_STORE_KEY_H302_COST: Final[str] = "rowId"

HEADER_TOP_ROW_H302_COST: Final[int] = 9
HEADER_GROUP_ROW_H302_COST: Final[int] = 10
HEADER_LEAF_ROW_H302_COST: Final[int] = 11
FIRST_DATA_ROW_H302_COST: Final[int] = 13
LAST_DATA_ROW_H302_COST: Final[int] = 27
FOOTER_ROW_H302_COST: Final[int] = 28
FOOTER_MARKER_H302_COST: Final[str] = "合计"
EFFECTIVE_COLUMNS_H302_COST: Final[int] = 45
UUID_COL_H302_COST: Final[str] = "AT"

#: 🔴 footer 之后的**不受管区域**：R29 `其中：` + R30-R33 四行按类别 SUMPRODUCT 小计
#: （行标签取 `=底稿目录!A9..A12`）。不受管、不比对、不覆盖。
UNMANAGED_REGIONS_H302_COST: Final[tuple[dict[str, object], ...]] = (
    {
        "first_row": 29,
        "last_row": 33,
        "kind": "category_subtotal_block",
        "note": (
            "A29='其中：'；R30-R33 为 "
            "=SUMPRODUCT(($A$13:$A$27=$A30)*(C$13:C$27)) 形态的按类别小计，"
            "行标签取 =底稿目录!A9..A12（四行，H4 是五行 ⇒ 不照抄）。"
        ),
    },
)

#: 🔴 模板有列但 HTML 无对端字段 ⇒ 不进 `field_specs`（Requirement 6.1）。
#: 主体是**三个区块各自的「期初调整 / 账项调整 / 审定期初·增·减」六列**（四段与四分正交，
#: 见 docstring）+ 增减方式两列 + 增减金额两列（1 格对 2 字段）+ AP/AR。
TEMPLATE_ONLY_COLUMNS_H302_COST: Final[tuple[tuple[str, str], ...]] = (
    ("D", "本年增加"),
    ("E", "增加方式"),
    ("F", "本年减少"),
    ("G", "减少方式"),
    ("I", "期初调整"),
    ("J", "本期增加"),
    ("K", "本期减少"),
    ("L", "期初余额"),
    ("M", "本年增加"),
    ("N", "本年减少"),
    ("R", "增加方式"),
    ("T", "减少方式"),
    ("V", "期初调整"),
    ("W", "本期增加"),
    ("X", "本期减少"),
    ("Y", "期初余额"),
    ("Z", "本年增加"),
    ("AA", "本年减少"),
    ("AE", "增加方式"),
    ("AG", "减少方式"),
    ("AI", "期初调整"),
    ("AJ", "本期增加"),
    ("AK", "本期减少"),
    ("AL", "期初余额"),
    ("AM", "本年增加"),
    ("AN", "本年减少"),
    ("AP", "期初净值"),
    ("AR", "是否有权属证明"),
)

#: HTML 有字段但模板无列（或语义不可映）⇒ store-only，不映射任何格。
STORE_ONLY_FIELDS_H302_COST: Final[tuple[str, ...]] = (
    # 模板无对应列（A 是类别不是序号；位置/面积/取得日期/入账原值/凭证号/对方科目
    # 都不在本 sheet 的 45 列里）
    "seq",
    "location",
    "area",
    "acquireDate",
    "originalCost",
    "changeDate",
    "voucherNo",
    "counterAccount",
    # 1 格对 2 字段（D/F）⇒ 分项一律 store-only
    "costIncrease",
    "transferIn",
    "costDecrease",
    "transferOut",
    # 一个字段混装双向（E/G）
    "changeType",
    # 四段 ↔ 四分正交：三个区块的「未审/AJE/RJE」三档都无模板对端
    "costUnadj",
    "costAje",
    "costRje",
    "depUnadj",
    "depAje",
    "depRje",
    "impairUnadj",
    "impairAje",
    "impairRje",
    # 未审净值：模板 AP 是**审定**期初净值（=L-Y-AL），不是未审净值 ⇒ 无对端
    "netValue",
    # 语义 ≠ AR「是否有权属证明」（见 docstring）
    "ownershipRestricted",
    "remark",
)

#: 🔴 HC-6 派生合计副本：与主表同批写出，不参与 roundtrip 比对。
#: 逐字取自 `useH3CrossSheet.ts` / `useH3AdditionCheck.ts` 现算命中的键。
DERIVED_TOTAL_KEYS_H302_COST: Final[tuple[str, ...]] = (
    "H3-2-cost-begin-total",
    "H3-2-cost-increase-total",
    "H3-2-cost-decrease-total",
)

#: 🔴 声明出来的覆盖缺口（每条都带停下报告点；`gap_id` 不用 `id`
#: —— 契约 payload 禁 `id` 键，见 `definitions._assert_no_self_reference`）。
DECLARED_COVERAGE_GAPS_H302_COST: Final[tuple[dict[str, Any], ...]] = (
    {
        "gap_id": "H3C-GAP-1",
        "title": "模板四段（按作用位置）与前端四分（按调整来源）正交",
        "template_columns": [
            "I", "J", "K", "L", "M", "N",
            "V", "W", "X", "Y", "Z", "AA",
            "AI", "AJ", "AK", "AL", "AM", "AN",
        ],
        "store_fields": [
            "costUnadj", "costAje", "costRje",
            "depUnadj", "depAje", "depRje",
            "impairUnadj", "impairAje", "impairRje",
        ],
        "why_not_mapped": (
            "模板按**作用位置**分段（期初调整 / 账项调整本期增减 / 审定期初·增·减），"
            "前端按**调整来源**分档（AJE 审计调整 / RJE 重分类调整）且两档都作用在"
            "期末口径上（costAudited = costUnadj + costAje + costRje，costUnadj 默认取"
            "costEnd 即期末）。两套分类是正交维度，不存在 1:1 映射：映到 I 会把审计调整"
            "当成调期初、让 M/N 算错本期发生额；映到 J/K 会丢掉 RJE 且只剩单方向。"
        ),
        "what_still_syncs": (
            "两侧在**期末**这一点上对齐：O ↔ costAudited、AB ↔ depAudited、"
            "AO ↔ impairAudited、AQ ↔ netAudited。"
        ),
        "stop_and_report": (
            "把 AJE/RJE 摊到「期初 / 本期增加 / 本期减少」三个位置属**审计域裁决**"
            "（哪部分调整应追溯调整期初、哪部分归本期），不由接线方拍板。"
        ),
        "owner": "审计业务方 / spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
    {
        "gap_id": "H3C-GAP-2",
        "title": "`D 本年增加` / `F 本年减少` 各 1 格对 2 字段",
        "template_columns": ["D", "F"],
        "store_fields": ["costIncrease", "transferIn", "costDecrease", "transferOut"],
        "why_not_mapped": (
            "前端 `_normalize` 里 costEnd = costBegin + costIncrease - costDecrease"
            " + transferIn - transferOut；要让模板 H=C+D-F 与 costEnd 相等，必须"
            " D = costIncrease + transferIn、F = costDecrease + transferOut。"
            "映射任一分项都会在转入/转出非零时让 Excel 的 H 与 HTML 的 costEnd **静默不等**。"
        ),
        "why_not_folded": (
            "🔴 不能照 H2-GAP-2 折叠：transferIn/transferOut 是**活字段**"
            "（useH3TransferEngine.ts / useH3TransferReview.ts / 互转审核表H3-6 在用），"
            "与 H2 那个自带 @deprecated、全仓零 UI 写入点的 transferOut 不是一回事。"
        ),
        "stop_and_report": "摊分规则（转入是否计入「本年增加」）属审计域裁决。",
        "owner": "审计业务方",
    },
    {
        "gap_id": "H3C-GAP-3",
        "title": "`E 增加方式` / `G 减少方式` 两列对一个混装双向的字段",
        "template_columns": ["E", "G"],
        "store_fields": ["changeType"],
        "why_not_mapped": (
            "前端只有一个 changeType，其 CHANGE_TYPE_OPTIONS **混装双向**："
            "增加类（购入 / 自建完工转入 / 自用转投资 / 在建转投资）与减少类"
            "（处置 / 转为自用 / 转出）在同一字段里。映到任一列都会把另一方向的取值写进错列。"
        ),
        "stop_and_report": (
            "拆成 increaseType / decreaseType 两个字段属前端模型变更 + 存量数据迁移，"
            "超出接线范围。"
        ),
        "owner": "spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
    {
        "gap_id": "H3C-GAP-4",
        "title": "`AR 是否有权属证明` 与 `ownershipRestricted`「是否权属受限」不是同一事实",
        "template_columns": ["AR"],
        "store_fields": ["ownershipRestricted"],
        "why_not_mapped": (
            "「有产权证明」与「权属未受限」是两个事实（有证也可能被抵押查封）。"
            "H3 的权属核对另有专表（产权核对表H3-12 + useH3TitleCheck.ts）。"
            "按名字近似硬映会把两个不同结论混成一个。"
        ),
        "stop_and_report": "AR 的数据源应取 H3-12，跨 sheet 取数不在本 sheet 接线范围。",
        "owner": "spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
)

#: 17 个受管字段（7 元组，第 7 位 `group_header_cell`）。
#: 顺序即 Excel 列序；`header_text` 取该列**最下层**非空表头（逐字实测 R9/R10/R11）；
#: `group_header_cell` 取其上一层的合并起始格（纵向合并到顶的列留空）。
FIELD_SPECS_H302_COST: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("asset_type", "A", "editable", "text", "assetType", "投资性房地产类别", ""),
    ("asset_name", "B", "editable", "text", "assetName", "投资性房地产名称", ""),
    # ── 原值：只有「未审期初」「未审期末」「审定期末」三点能对上（见 GAP-1/2/3）──
    ("cost_begin", "C", "editable", "amount", "costBegin", "期初余额", "C10"),
    ("cost_end", "H", "formula", "amount", "costEnd", "期末余额", "C10"),
    ("cost_audited", "O", "formula", "amount", "costAudited", "期末余额", "L10"),
    # ── 累计折旧/累计摊销 ───────────────────────────────────────────────────
    ("dep_begin", "P", "editable", "amount", "accDepBegin", "期初余额", "P10"),
    ("dep_provision", "Q", "editable", "amount", "depProvision", "本年增加", "P10"),
    ("dep_reversal", "S", "editable", "amount", "depReversal", "本年减少", "P10"),
    ("dep_end", "U", "formula", "amount", "accDepEnd", "期末余额", "P10"),
    ("dep_audited", "AB", "formula", "amount", "depAudited", "期末余额", "Y10"),
    # ── 减值准备 ───────────────────────────────────────────────────────────
    ("impair_begin", "AC", "editable", "amount", "impairmentBegin", "期初余额", "AC10"),
    ("impair_provision", "AD", "editable", "amount", "impairmentProvision", "本年增加", "AC10"),
    ("impair_reversal", "AF", "editable", "amount", "impairmentReversal", "本年减少", "AC10"),
    ("impair_end", "AH", "formula", "amount", "impairmentEnd", "期末余额", "AC10"),
    ("impair_audited", "AO", "formula", "amount", "impairAudited", "期末余额", "AL10"),
    # ── 尾部（AP 期初净值是审定口径、AR 是产权证明 ⇒ 两者 template-only）────────
    ("net_audited", "AQ", "formula", "amount", "netAudited", "期末净值", ""),
    ("mortgaged", "AS", "editable", "text", "mortgaged", "是否抵押受限", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R13。
#: 🔴 只登记**进了 `field_specs`** 的公式列（同 H4 口径）；template-only 的公式列
#:    （L/M/N · Y/Z/AA · AL/AM/AN · AP）不在此表，由 Excel 自行重算。
FORMULA_TEMPLATES_H302_COST: Final[dict[str, str]] = {
    "H": "=C{r}+D{r}-F{r}",
    "O": "=L{r}+M{r}-N{r}",
    "U": "=P{r}+Q{r}-S{r}",
    "AB": "=Y{r}+Z{r}-AA{r}",
    "AH": "=AC{r}+AD{r}-AF{r}",
    "AO": "=AL{r}+AM{r}-AN{r}",
    "AQ": "=O{r}-AB{r}-AO{r}",
}

SPEC_H302_COST: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H302_COST,
    sheet_key=SHEET_KEY_H302_COST,
    table_key=ROWS_TABLE_KEY_H302_COST,
    template_id=TEMPLATE_ID_H302_COST,
    table_name=f"GT_{TEMPLATE_ID_H302_COST}_ROWS",
    uuid_col=UUID_COL_H302_COST,
    first_data_row=FIRST_DATA_ROW_H302_COST,
    last_data_row=LAST_DATA_ROW_H302_COST,
    footer_row=FOOTER_ROW_H302_COST,
    header_group_row=HEADER_TOP_ROW_H302_COST,
    header_leaf_row=HEADER_LEAF_ROW_H302_COST,
    store_item_id=STORE_ITEM_ID_H302_COST,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H302_COST,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H302_COST,
    formula_columns=tuple(FORMULA_TEMPLATES_H302_COST),
    formula_templates=FORMULA_TEMPLATES_H302_COST,
    footer_marker=FOOTER_MARKER_H302_COST,
    error_label="H3-2（成本模式）投资性房地产明细表",
)
