"""H2-2「在建工程明细表」—— sheet 层薄声明（H 循环第五张，**带两处声明出来的覆盖缺口**）。

spec: `h2-h6-h10-pilot-cross-reference-lanes`
现算底账：`.kiro/specs/h4-h8-sub-entry-lanes-and-seed-identity-defects/evidence/
h2-h4-h8-h10-mapping-facts.md` §7（含两处歧义的代码级结论）

═══ 与前四条的差异 ═══

H2 是**唯一带「声明出来的覆盖缺口」**的一条。前四条（H9/H6/H4/H8）的每个模板列要么有
store 字段、要么明确无对端；H2 有两处两侧**语义打架**，硬凑映射会造成静默错数，
因此按「宁可留可见缺口，不要不可见错数」处理 —— 两处都配停下报告点，
不由接线方替审计域拍板。

═══ 几何（openpyxl 逐格实测，禁推演）═══

册 `H/H2 在建工程.xlsx`（162,616 B）· **21 sheets（全 H 最多）** · 本 sheet
`max_row=48` / `max_column=50`，**有效内容列 50（A..AX）**。

* **四级**表头 **R9 / R10 / R11 / R12**（46 个合并域）
* 数据区 **R13-R20（8 行）** —— 全 H 最短（H8 20 行 / H4 16 行 / H9·H6 各 5 行）

  🔴 数据区 8 行但 footer 之下无扩展区，和 H4/H8 的 16/20 行不同步 ——
  受管区行数写死成别条的值会让 merge 越界写进 footer。
* footer **R21**，`A21='合计'`，多为 `=SUM(x13:x20)`；
  但 `AA21='=K21+T21'` / `AC21='=M21+V21'` / `AG21='=Z21+AB21-AD21-AE21'` /
  `AH21='=AA21+AC21-AF21'` 是**行内派生**而非列求和 —— footer 不是一律 SUM。
* 数据行公式列 **21 个**
* UUID 列 **AY** = 有效内容列（50）+ 1（HC-13）

🔴 **footer 之后没有 `其中：` SUMPRODUCT 小计区**（R22 直接是「三、审计说明：」）
⇒ 本 entry **无** `unmanaged_regions`。H4/H8 都有那个区块；照抄会把「审计说明」
误登记成小计区，然后守卫去比对一个不存在的 SUMPRODUCT。

═══ 分区（表头合并区逐字实测）═══

* **A..I 属性列**（皆 `R9:R12` 纵向合并）：A 工程项目名称 · B 预算金额 · C 资金来源 ·
  D 工程累计投入占预算比例%（**公式** `=IF(AH{r}=0,0,AH{r}/B{r})`）· E 预计完工时间 ·
  F 工程进度 · G 完工日期 · H 批准文号 · I 利息资本化率
* **原值 `J9:AH9`** —— 每组都带「其中：」子列（这是 H2 独有的形态）
  - 未审数 `J10:R10`：期初 J-K · 增加 L-M · 减少 N-P · 期末 Q-R
  - 期初调整 `S10:T11`：S 余额 · T 其中累计资本化
  - 账项调整 `U10:Y10`：增加 U-V · 减少 W-Y
  - 审定数 `Z10:AH10`：期初 Z-AA · 增加 AB-AC · 减少 AD-AF · 期末 AG-AH
* **减值准备 `AI9:AS9`**：未审 AI-AL · 期初调整 AM · 账项调整 AN-AO · 审定 AP-AS
* **期初净值 `AT9:AU10`**（AT 未审 / AU 审定）· **期末净值 `AV9:AW10`**（AV 未审 / AW 审定）
  🔴 H2 有**两对**净值，H8 只有一对（`BE8:BF9` 期初/期末各一列）—— 列位形态不同不能照抄。
* **AX 是否抵押**

═══ 🔴 缺口①：`L 增加` 不参与双向（两侧权威方向相反）═══

模板 `L` **没有公式**，是可输入格。而前端 `increaseTotal` 由 `_recalcFormulas`
（`useH2Detail.ts#L351`）从 5 个分项算出，且**不在 `_persist()` 的 56 键里**：

```
row.increaseTotal = increaseMaterial + increaseLabor + increaseMachinery
                  + increaseInterest + increaseOther
row.cipEnd = calcCipEndBalance(cipBegin, increaseTotal, …, transferAmount)
row.unadjustedEnd = row.cipEnd
```

OO 侧改 `L` ⇒ 回写无处可落（不知该摊给哪个分项）；HTML load 又会用 5 个分项覆盖。
⇒ `L` 进 `TEMPLATE_ONLY_COLUMNS`，5 个分项进 `STORE_ONLY_FIELDS`。
**停下报告点**：若审计侧要求 `L` 双向，需先裁决摊分规则（例如「差额全部计入
`increaseOther`」）—— 那是审计域决定，不由接线方定。

═══ ✅ 原缺口②（`O 其他减少` 1 格对 2 字段）**已从根上消除** ═══

原状：`_otherDecrease = decrease + transferOut`，而模板只有 `O 其他减少` 一格 ⇒
投影只能落一个字段，另一个的金额会静默消失在两侧差额里。

**没有按「登记缺口 + 停下报告」结案**，而是把根因做掉了 —— 三条按值取证的依据：
① 字段自带 `@deprecated 并入 decrease`（代码自己已宣布要合并，只是迁移没做完）；
② 全仓 grep **零 UI 写入点**（只在 `_normalizeRow` 读回、`_persist` 原样写出）；
③ 真库现算 `H2-2-rows` **0 行**，全表 `remark LIKE '%transferOut%'` 只命中
   `G1-note-listed-store` 与 `H3-disc-soe-rows-soe-cost` 两处**别 entry 的同名字段**
   （值分别为 0 与空串）⇒ H2 上下文零数据。

做法：`_normalizeRow` 载入期把 `transferOut` **一次性并进** `decrease` 并置 0
（幂等；历史非零值被**加进**而不是丢弃 —— 等于把 evidence 里开的「先做数据迁移」
做成了载入期归一化，任何环境都生效，不需要单独迁移脚本）。
此后 `其他减少 == decrease`，模板 `O` ↔ `decrease` 是 1:1。

守卫 `h2TransferOutFold.spec.ts`：3 条行为判据 + 4 条源码级判据。
🔴 变异反证的诚实结果：三个变异里「删归并」直接杀掉；「删显式清零」与
「口径改回累加」在纯行为层面是**等价变异**（归并已让字段恒 0），由源码级判据拦下 ——
它们虽无行为差异，却是**意图回退**，留着会让下一个人以为双口径还活着。

⇒ 本 entry 现在只剩**一处**声明缺口（GAP-1 的 `L 增加`）。
历史记录留在 `RESOLVED_COVERAGE_GAPS_H202`，免得 GAP 编号从 1 跳到 3 时看起来像丢了东西。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H202",
    "MANAGED_SHEET_H202",
    "SHEET_KEY_H202",
    "STORE_ITEM_ID_H202",
    "ROW_IDENTITY_STORE_KEY_H202",
    "FORMULA_TEMPLATES_H202",
    "STORE_ONLY_FIELDS_H202",
    "TEMPLATE_ONLY_COLUMNS_H202",
    "DECLARED_COVERAGE_GAPS_H202",
    "RESOLVED_COVERAGE_GAPS_H202",
    "LEGACY_FOLDED_FIELDS_H202",
    "SIBLING_TABLE_KEYS_H202",
    "EFFECTIVE_COLUMNS_H202",
    "UUID_COL_H202",
]

MANAGED_SHEET_H202: Final[str] = "明细表H2-2"
TEMPLATE_ID_H202: Final[str] = "H22"
SHEET_KEY_H202: Final[str] = "h202-managed"
ROWS_TABLE_KEY_H202: Final[str] = "construction_in_progress_detail_rows"

#: 按值取自 `useH2Detail.ts#L119` 的 `ROWS_KEY`，不按 sheet 号推演。
STORE_ITEM_ID_H202: Final[str] = "H2-2-rows"

#: 行身份 `row-${Date.now().toString(36)}-${Math.random()...}` ⇒ HC-7 族 A。
#: 🔴 slice 标 `row_identity_is_positional=True` 是**过期快照** —— 下标身份
#:    （`GtH2ConstructionInProgress.vue#616` 的 `seed-${i}`）已在 commit 91933bd68
#:    改为按科目编码的 `buildHSeedRowId`。判据按现状复核。
ROW_IDENTITY_STORE_KEY_H202: Final[str] = "rowId"

HEADER_TOP_ROW_H202: Final[int] = 9
HEADER_LEAF_ROW_H202: Final[int] = 12
FIRST_DATA_ROW_H202: Final[int] = 13
LAST_DATA_ROW_H202: Final[int] = 20
FOOTER_ROW_H202: Final[int] = 21
FOOTER_MARKER_H202: Final[str] = "合计"
EFFECTIVE_COLUMNS_H202: Final[int] = 50
UUID_COL_H202: Final[str] = "AY"

#: 🔴 **H2 无 footer 之下的不受管区域**（R22 直接是「三、审计说明：」）。
#: 显式声明空元组而不是省略该常量 —— 省略会让复用 H4/H8 判据的人以为「忘写了」。
UNMANAGED_REGIONS_H202: Final[tuple[dict[str, object], ...]] = ()

#: 模板有列但 HTML 无可映射字段 ⇒ 不进 `field_specs`。
#: 🔴 主体是「其中：」子列（H2 独有形态：每组金额都带资本化利息的 of-which 子列，
#:    前端只保留了其中几个）+ 缺口① 的 `L 增加`。
TEMPLATE_ONLY_COLUMNS_H202: Final[tuple[tuple[str, str], ...]] = (
    ("L", "增加（未审数·本期增加）—— 缺口①：两侧权威方向相反，见模块 docstring"),
    ("T", "其中：累计资本化金额（期初调整）"),
    ("AA", "其中：累计资本化金额（审定数·期初数）"),
    ("AC", "其中：本期利息资本化金额（审定数·本期增加）"),
    ("AE", "其他减少（审定数·本期减少）"),
    ("AF", "其中：利息资本化金额减少金额（审定数·本期减少）"),
    ("AH", "其中：累计资本化金额（审定数·期末数）"),
    ("AM", "期初调整（减值准备）"),
    ("AN", "本期增加（减值准备·账项调整）"),
    ("AO", "本期减少（减值准备·账项调整）"),
    ("AP", "期初数（减值准备·审定数）"),
    ("AQ", "本期增加（减值准备·审定数）"),
    ("AR", "本期减少（减值准备·审定数）"),
    ("AT", "未审净值（期初净值）"),
    ("AU", "审定净值（期初净值）"),
    ("AV", "未审净值（期末净值）"),
)

#: HTML 有字段但模板无列（或模板列已判为 template-only）⇒ store-only，不映射任何格。
STORE_ONLY_FIELDS_H202: Final[tuple[str, ...]] = (
    # 缺口①：`L 增加` 的 5 个分项（前端派生 increaseTotal 的输入）
    "increaseMaterial",
    "increaseLabor",
    "increaseMachinery",
    "increaseInterest",
    "increaseOther",
    # 🔴 已根治的旧字段（原缺口②）：载入期并进 decrease 后**恒 0**，仍落库只为不破坏
    #    可能存在的旧读取方。它与模板 `O 其他减少` 的双向回写无关 ⇒ store-only。
    "transferOut",
    # 前端派生列（`_recalcFormulas` 算出，不落库或落库但由客户端重算）
    "increaseTotal",
    "unadjustedEnd",
    "remainingCip",
    "completionRate",
    # 工程属性/说明类（模板本表无列）
    "projectCode",
    "contractor",
    "supervisor",
    "unitCost",
    "progressNote",
    "auditFlag",
    "indexRef",
    "category",
    "projectStatus",
    "transferDate",
    "transferToH1",
    "transferTo",
    # 净值四列在模板是 template-only（见上），前端字段随之 store-only
    "netBeginUnadj",
    "netBeginAud",
    "netEndUnadj",
    # 减值块前端侧的调整/审定字段（模板对应列已判 template-only）
    "impairOpenAdj",
    "impairIncAdj",
    "impairDecAdj",
    "impairBeginAud",
    "impairIncAud",
    "impairDecAud",
)

#: 🔴 **缺口② 已从根上消除（不是被文档绕开）** —— 本表现为空。
#:
#: 原状：`transferOut` 与 `decrease` 同时承载「其他减少」口径
#: （`useH2Detail.ts#L254 _otherDecrease = decrease + transferOut`），而模板只有
#: `O 其他减少` **一格** ⇒ 投影只能落一个字段，另一个的金额会静默消失在两侧差额里。
#:
#: 三条依据支持根治而非登记（都按值取证，非推测）：
#:   ① 字段自带 `@deprecated 并入 decrease`，代码自己已宣布要合并；
#:   ② 全仓 grep：**零 UI 写入点**（只在 `_normalizeRow` 读回、`_persist` 原样写出，
#:      没有任何 v-model / 导入 / 预填给它赋值）；
#:   ③ 真库现算：`H2-2-rows` **0 行**；全表 `remark LIKE '%transferOut%'` 只命中
#:      `G1-note-listed-store` 与 `H3-disc-soe-rows-soe-cost` 两处**同名但属别 entry**
#:      的字段（值分别为 0 与空串）⇒ H2 上下文零数据。
#:
#: 做法：`_normalizeRow` 载入期把 `transferOut` **一次性并进** `decrease` 并置 0
#: （幂等；历史非零值被**加进**而不是丢弃），`_otherDecrease` 改为单一字段。
#: 此后 `其他减少 == decrease`，模板 `O` 与 `decrease` 是 1:1 ⇒ 缺口消失。
#: 守卫：`h2TransferOutFold.spec.ts`（3 行为判据 + 4 源码级判据；三个变异全部被杀，
#: 其中两个是「行为等价但意图回退」的变异，由源码级判据拦下）。
LEGACY_FOLDED_FIELDS_H202: Final[dict[str, dict[str, str]]] = {}

#: 🔴 **声明出来的覆盖缺口** —— 两处两侧语义打架，硬凑映射会造成静默错数。
#: 契约 `review` 原样带出，供 roundtrip 判据跳过这两处并在报告里显示原因。
DECLARED_COVERAGE_GAPS_H202: Final[tuple[dict[str, str], ...]] = (
    {
        # 🔴 键名用 `gap_id` 不是 `id` —— `definitions._assert_no_self_reference`
        #    禁止 canonical payload 里出现 `id` 形态的字段（Requirement 6.2：digest 由
        #    payload 算出，payload 引用 artifact id/hash 会破坏可复现性）。写成 `id`
        #    时生成器在 `parse_contract` 阶段直接 IdentityError。
        "gap_id": "H2-GAP-1",
        "column": "L",
        "column_header": "增加（未审数·本期增加）",
        "kind": "authority_direction_conflict",
        "detail": (
            "模板 L 无公式、是可输入格；HTML 的 increaseTotal 由 5 个分项在 "
            "_recalcFormulas 派生且不在 _persist() 的 56 键里。OO 改 L 回写无处可落"
            "（不知该摊给哪个分项），HTML load 又会用分项覆盖 ⇒ 两侧权威方向相反。"
        ),
        "resolution": "L 判 template-only，5 个分项判 store-only；本格不参与双向同步。",
        "stop_and_report": (
            "若审计侧要求 L 双向，需先裁决摊分规则（如差额全部计入 increaseOther）——"
            "属审计域决定，不由接线方定。"
        ),
    },
)

#: 🔴 **已根治、不再是缺口**的历史条目 —— 登记它是为了留下「为什么现在只剩一条缺口」
#: 的可追溯记录，避免下一个人看到 GAP 编号从 1 跳到 3 时以为丢了东西。
RESOLVED_COVERAGE_GAPS_H202: Final[tuple[dict[str, str], ...]] = (
    {
        "gap_id": "H2-GAP-2",
        "column": "O",
        "column_header": "其他减少（未审数·本期减少）",
        "kind": "one_cell_two_fields",
        "was": (
            "`_otherDecrease = decrease + transferOut` ⇒ 模板 O 一格对两字段，"
            "投影只能落一个，另一个的金额静默消失在两侧差额里。"
        ),
        "root_caused_by": (
            "字段自带 @deprecated『并入 decrease』但迁移从未做完，于是「读取期累加」"
            "长期代偿；双向回写把这个代偿暴露成真实错数风险。"
        ),
        "fix": (
            "`_normalizeRow` 载入期把 transferOut 一次性并进 decrease 并置 0（幂等，"
            "历史非零值被加进不是丢弃）；`_otherDecrease` 改为单一字段。"
            "此后 O ↔ decrease 是 1:1。"
        ),
        "evidence": (
            "①字段 @deprecated 注释 ②全仓 grep 零 UI 写入点 "
            "③真库 H2-2-rows 0 行 + 全表 transferOut 仅命中 G1/H3 两处别 entry 同名字段"
            "（值 0 与空串）"
        ),
        "guard": (
            "h2TransferOutFold.spec.ts —— 3 条行为判据（历史值不丢 / 幂等 / 恒 0）"
            "+ 4 条源码级判据（口径不得再累加、必须显式清零、归并只发生一处、"
            "不得再从 raw 读回）；三个变异全部被杀。"
        ),
    },
)

#: 同模块但**另一张表**的键 —— 不是本表的合计副本，也不在本轮受管面。
SIBLING_TABLE_KEYS_H202: Final[tuple[str, ...]] = (
    "H2-2-audit-note",          # 同 owner 模块的 NOTE_KEY（审计说明，非行表）
    "H2-2-audit-conclusion",    # 同 owner 模块的 CONCLUSION_KEY
)

#: 34 个受管字段（7 元组，第 7 位 `group_header_cell`）。
#: 顺序即 Excel 列序；`header_text` 取该列**最下层**非空表头；
#: `group_header_cell` 取其上一层的合并起始格（纵向合并列留空）。
#: `json_key` 逐字取 `useH2Detail._persist()` 的 56 键（未映射的进 STORE_ONLY）。
FIELD_SPECS_H202: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    # ── 属性列（R9:R12 纵向合并 ⇒ group 留空）────────────────────────────────
    ("name", "A", "editable", "text", "name", "工程项目名称", ""),
    ("budget", "B", "editable", "amount", "budget", "预算金额", ""),
    ("fund_source", "C", "editable", "text", "fundSource", "资金来源", ""),
    ("completion_rate", "D", "formula", "amount", "completionRate", "工程累计投入占预算比例%", ""),
    ("planned_end_date", "E", "editable", "text", "plannedEndDate", "预计完工时间", ""),
    ("progress", "F", "editable", "text", "progressNote", "工程进度", ""),
    ("actual_end_date", "G", "editable", "text", "actualEndDate", "完工日期", ""),
    ("approval_doc_no", "H", "editable", "text", "approvalDocNo", "批准文号", ""),
    ("cap_rate", "I", "editable", "amount", "capRate", "利息资本化率", ""),
    # ── 原值 · 未审数（🔴 L 已判 template-only，见缺口①）──────────────────────
    ("cip_begin", "J", "editable", "amount", "cipBegin", "余额", "J11"),
    ("interest_begin", "K", "editable", "amount", "interestBegin", "其中：累计资本化金额", "J11"),
    ("increase_interest", "M", "editable", "amount", "increaseInterest", "其中：本期利息资本化金额", "L11"),
    ("transfer_amount", "N", "editable", "amount", "transferAmount", "本期转入固定资产", "N11"),
    ("decrease", "O", "editable", "amount", "decrease", "其他减少", "N11"),
    ("interest_dec", "P", "editable", "amount", "interestDec", "其中：利息资本化金额减少金额", "N11"),
    ("cip_end", "Q", "formula", "amount", "cipEnd", "余额", "Q11"),
    ("interest_end", "R", "formula", "amount", "interestEnd", "其中：累计资本化金额", "Q11"),
    # ── 原值 · 期初调整 ───────────────────────────────────────────────────────
    ("adjust_begin", "S", "editable", "amount", "adjustBegin", "余额", "S10"),
    # ── 原值 · 账项调整 ───────────────────────────────────────────────────────
    ("increase_adj", "U", "editable", "amount", "increaseAdj", "增加", "U11"),
    ("interest_inc_adj", "V", "editable", "amount", "interestIncAdj", "其中：本期利息资本化金额", "U11"),
    ("transfer_adj", "W", "editable", "amount", "transferAdj", "本期转入固定资产", "W11"),
    ("decrease_adj", "X", "editable", "amount", "decreaseAdj", "其他减少", "W11"),
    ("interest_dec_adj", "Y", "editable", "amount", "interestDecAdj", "其中：利息资本化金额减少金额", "W11"),
    # ── 原值 · 审定数 ─────────────────────────────────────────────────────────
    ("begin_audited", "Z", "formula", "amount", "beginAudited", "余额", "Z11"),
    ("increase_audited", "AB", "formula", "amount", "increaseAudited", "增加", "AB11"),
    ("transfer_audited", "AD", "formula", "amount", "transferAudited", "本期转入固定资产", "AD11"),
    ("end_audited", "AG", "formula", "amount", "endAudited", "余额", "AG11"),
    # ── 减值准备 · 未审数 ─────────────────────────────────────────────────────
    ("impairment_begin", "AI", "editable", "amount", "impairmentBegin", "期初数", "AI10"),
    ("impairment_increase", "AJ", "editable", "amount", "impairmentIncrease", "本期增加", "AI10"),
    ("impairment_decrease", "AK", "editable", "amount", "impairmentDecrease", "本期减少", "AI10"),
    ("impairment_end", "AL", "formula", "amount", "impairmentEnd", "期末数", "AI10"),
    ("impair_end_aud", "AS", "formula", "amount", "impairEndAud", "期末数", "AP10"),
    # ── 期末净值（🔴 AV 未审已判 template-only；AW 审定入映射）────────────────
    ("net_end_aud", "AW", "formula", "amount", "netEndAud", "审定净值", "AV9"),
    # ── 抵押标记 ──────────────────────────────────────────────────────────────
    ("is_mortgaged", "AX", "editable", "text", "isMortgaged", "是否抵押", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R13-R20。
#: 🔴 只登记进 `field_specs` 的公式列；template-only 的公式列（AA/AC/AE/AF/AH/
#:    AP/AQ/AR/AT/AU/AV）不在此表，由 Excel 自行重算。
#: 🔴 `Q` 用 `=J+L-N-O`（**含已判 template-only 的 L**）—— 缺口① 只表示 L 不参与
#:    「HTML↔OO 值映射」，不表示它不在 Excel 公式里；回写不动 L，Q 的重算仍由 Excel 做。
FORMULA_TEMPLATES_H202: Final[dict[str, str]] = {
    "D": "=IF(AH{r}=0,0,AH{r}/B{r})",
    "Q": "=J{r}+L{r}-N{r}-O{r}",
    "R": "=K{r}+M{r}-P{r}",
    "Z": "=J{r}+S{r}",
    "AB": "=L{r}+U{r}",
    "AD": "=N{r}+W{r}",
    "AG": "=Z{r}+AB{r}-AD{r}-AE{r}",
    "AL": "=AI{r}+AJ{r}-AK{r}",
    "AS": "=AP{r}+AQ{r}-AR{r}",
    "AW": "=AH{r}-AS{r}",
}

SPEC_H202: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H202,
    sheet_key=SHEET_KEY_H202,
    table_key=ROWS_TABLE_KEY_H202,
    template_id=TEMPLATE_ID_H202,
    table_name=f"GT_{TEMPLATE_ID_H202}_ROWS",
    uuid_col=UUID_COL_H202,
    first_data_row=FIRST_DATA_ROW_H202,
    last_data_row=LAST_DATA_ROW_H202,
    footer_row=FOOTER_ROW_H202,
    header_group_row=HEADER_TOP_ROW_H202,
    header_leaf_row=HEADER_LEAF_ROW_H202,
    store_item_id=STORE_ITEM_ID_H202,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H202,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H202,
    formula_columns=tuple(FORMULA_TEMPLATES_H202),
    formula_templates=FORMULA_TEMPLATES_H202,
    footer_marker=FOOTER_MARKER_H202,
    error_label="H2-2 在建工程明细表",
)
