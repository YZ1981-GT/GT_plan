# -*- coding: utf-8 -*-
"""I1-2「无形资产明细表」—— sheet 层薄声明（全 I 最宽，47 有效列）。

spec: `i1-i3-disclosure-positional-identity-and-classification-source` · Task 14

═══ 🔴 全 I 最宽：47 有效列 / 三大滚动区 + 净值区 + 合规区 ═══

```
A     无形资产项目              ← editable（🔴 模板预填占位符 'A'/'B'/'C'/'D'/'…'）
B     无形资产类别              ← editable（第二区按它 SUMPRODUCT 回汇总）
C..O  无形资产原值（13 列）      ← 未审 C-H + 期初/账项调整 I-K + 审定 L-O
P..AB 累计摊销（13 列）         ← 未审 P-U + 期初/账项调整 V-X + 审定 Y-AB
AC..AO 减值准备（13 列）        ← 未审 AC-AH + 期初/账项调整 AI-AK + 审定 AL-AO
AP..AS 净值（4 列，**全公式**） ← AP=C-P-AC · AQ=L-Y-AL · AR=H-U-AH · AS=O-AB-AO
AT    是否有权属证明            ← editable 文本
AU    是否抵押受限              ← editable 文本
```

三大区**结构同构**（各 13 列：期初 + 增加 2 列 + 减少 2 列 + 期末 + 期初调整 + 账调 2 列 +
审定 4 列），但公式口径**逐区不同**：

| 区 | 未审期末 | 审定本期增加 | 审定本期减少 |
|---|---|---|---|
| 原值 | `H=SUM(C:D)-F` | `M=D+J`（**两项**） | `N=F+K`（**两项**） |
| 累计摊销 | `U=SUM(P:Q)-S` | `Z=Q+W+R`（**三项**） | `AA=S+X+T`（**三项**） |
| 减值准备 | 🔴 `AH=SUM(AC:AE)-SUM(AF:AG)` | `AM=AD+AJ+AE`（三项） | `AN=AF+AK+AG`（三项） |

🔴 **减值区的未审期末是两个 SUM 相减**（`SUM(AC:AE)-SUM(AF:AG)`），与前两区的
`SUM(x:y)-z` 形态**不同** —— 抄前两区的形态会漏掉「其他减少 AG」。

🔴 **摊销/减值区的审定本期增减是三项相加**（含「其他增加 R/AE」与「其他减少 T/AG」），
而原值区是两项 —— 三区用同一套模板会算错两区。

═══ 双区：R12-17 业务区 + R19-30 派生区（IC-19 / ID-4）═══

* 第 1 区 **R12-R17**（**仅 6 行**，全 I 最少）：受管业务行
  🔴 A 列模板预填的是**占位符** `A`/`B`/`C`/`D`/`…` 不是业务名 ⇒ 用户覆盖
* footer **R18**「合计」：`C18..AS18` **41 格全部纯 SUM**（`=SUM(x12:x17)`）
  ⇒ 本表 footer 是全 I **唯一单一形态**（I2 有 1 格例外、I3 有 5 格 + 4 格缺陷）
* 🔴 第 2 区 **R19「其中：」+ R20-R30**（**11 行**）：**派生区不受管**
  - A 列逐格 `=底稿目录!A9`..`=底稿目录!A19`（11 类），
    🔴 **R29 例外是字面 `数据资源`**（真源断链，登记不修）
  - C/D/F/H/I/J/K 等列是 **ArrayFormula / SUMPRODUCT**
    （`=SUMPRODUCT(($B$12:$B$17=$A20)*(F$12:F$17))`）按 **B 列类别**回汇总第 1 区
  ⇒ 按 IC-19 标 `derived` + `editable_labels=false`

═══ 几何（openpyxl 逐格实测）═══

`max_row=41` / `max_column=56` / **有效内容列 47（A..AU）** / definedName **0** /
merged **72（全 I 最多）** / 无 Excel Table / `ws.protection.sheet=False` / 179 公式。

* 🔴 **四级表头 R8 / R9 / R10 / R11**（`header_group_row=8` + `header_leaf_row=11`
  ⇒ `header_rows = 4`，与 I3 同为平台上界）
* 数据区 **R12-R17**（6 行）
* 公式列 **19 个**：H/L/M/N/O · U/Y/Z/AA/AB · AH/AL/AM/AN/AO · AP/AQ/AR/AS
* UUID 列 **AV**（= 有效内容列 47 + 1）。🔴 **不得放 57** —— `max_column` 是 56，
  有效与 max 之间 9 列全空，放 57 会让 OO 打开后列宽错位。

🔴 **`locked` 同样惰性**（`ws.protection.sheet=False`）。

═══ CD-1：分类 MATCH 但 impl 边是**双定义**（ID-2 本轮新发现）═══

`I1_DEFAULT_CATEGORIES` 在**两处**独立定义：
`i1CategoryScope.ts#L19`（`I1CategorySlot[]` 有 key/label/seq/removable）与
`useI1Adjudication.ts#L105`（纯中文串数组）。两边 11 条 label **有序完全一致**（本轮现算确认），
但它们是**两个独立真源** —— 改一处不传播。

🔴 CD-1 判据 SHALL **同时比对两处**；变异「只改 `i1CategoryScope.ts` 的第 8 条 `软件`」
SHALL 打红（单边判据会静默通过 = 假绿）。
**已收敛**：`useI1Adjudication.ts#L105` 改为 `I1_DEFAULT_CATEGORIES.map(c => c.label)` 派生。

═══ BP-7：`I1_SOE_CATEGORIES` 与两个真源都不符（登记不修）═══

impl 12 条 vs 源 `附注披露信息（国有企业）!A9:A19` **11 格**，五项差异：
条数 12↔11 · `软件` 位次 1↔8 · `房屋使用权`↔`住房使用权` ·
`特许权`/`采矿权`↔`特许经营权`/`矿产权` · 多出 `探矿权`。
🔴 修法归**业务确认**（国企附注该用哪套分类名是会计披露口径问题）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 几何常量（逐格实测）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_I102: Final[str] = "明细表I1-2"
SHEET_KEY_I102: Final[str] = "i12-managed"
ROWS_TABLE_KEY_I102: Final[str] = "intangible_assets_rows"
TEMPLATE_ID_I102: Final[str] = "I12"
UUID_COL_I102: Final[str] = "AV"
#: 🔴 四级表头：group=R8 / leaf=R11 ⇒ header_rows=4（与 I3 同为平台上界）
HEADER_GROUP_ROW_I102: Final[int] = 8
HEADER_LEAF_ROW_I102: Final[int] = 11
FIRST_DATA_ROW_I102: Final[int] = 12
LAST_DATA_ROW_I102: Final[int] = 17
FOOTER_ROW_I102: Final[int] = 18
FOOTER_MARKER_I102: Final[str] = "合计"
EFFECTIVE_COLUMNS_I102: Final[int] = 47
MAX_COLUMN_I102: Final[int] = 56

#: 🔴 IC-19 / ID-4：第二区派生不受管。
DERIVED_REGION_I102: Final[dict[str, object]] = {
    "marker_row": 19,
    "marker_label": "其中：",
    "rows": [20, 30],
    "row_count": 11,
    "label_source": "底稿目录!A9:A19",
    "label_form": "A 列逐格 =底稿目录!A9..=底稿目录!A19（11 类）",
    "label_source_break": (
        "🔴 **R29 例外是字面 `数据资源`**（其余 10 行都是 =底稿目录!Ax）⇒ "
        "改 `底稿目录!A18` **不会传播**到 R29。登记不修（不改模板字节）。"
    ),
    "value_form": (
        "C/D/F/H/I/J/K 等列是 ArrayFormula / SUMPRODUCT —— "
        "`=SUMPRODUCT(($B$12:$B$17=$A20)*(F$12:F$17))` 按 **B 列类别**回汇总第 1 区"
    ),
    "editable_labels": False,
    "note": (
        "按 IC-19 标 derived、不纳入业务行比对。🔴 A 列标签由 `底稿目录` 下发 ⇒ "
        "允许用户改会被下次 render 静默覆盖。"
    ),
}

#: 🔴 本表 footer 是全 I **唯一单一形态**（41 格全纯 SUM）。
FOOTER_SHAPE_FACTS_I102: Final[dict[str, object]] = {
    "kind": "pure_sum",
    "convention_split": False,
    "pure_sum_column_count": 41,
    "pure_sum_range": "C18..AS18 各 =SUM(x12:x17)",
    "empty_columns": ["B", "AT", "AU"],
    "note": (
        "🔴 全 I **唯一单一形态**的 footer（I2 有 1 格例外 R23=P23-Q23、"
        "I3 有 5 格套用行公式 + 4 格引错区间、I5/I6 各有多 footer）⇒ "
        "本表可以安全用 `pure_sum` 口径，但**该口径不得复用到 I2/I3**。"
    ),
}

TEMPLATE_CELL_LOCK_FACTS_I102: Final[dict[str, object]] = {
    "sheet_protection_enabled": False,
    "note": "ws.protection.sheet=False ⇒ locked 惰性；mode 按「该格逐行有没有真公式」判。",
}

#: CD-1：分类 MATCH 但 impl 边是双定义（本轮已收敛）。
CLASSIFICATION_FACTS_I102: Final[dict[str, object]] = {
    "impl_constants": [
        "composables/i1CategoryScope.ts#I1_DEFAULT_CATEGORIES",
        "composables/useI1Adjudication.ts#I1_DEFAULT_CATEGORIES",
    ],
    "impl_count": 11,
    "source_ref": "底稿目录!A9:A19",
    "source_real_count": 11,
    "verdict": "MATCH",
    "status": "clean",
    "dual_definition": True,
    "dual_definition_note": (
        "🔴 **本轮新发现（ID-2）**：`I1_DEFAULT_CATEGORIES` 在**两处**独立定义 —— "
        "`i1CategoryScope.ts#L19`（`I1CategorySlot[]` 有 key/label/seq/removable）与 "
        "`useI1Adjudication.ts#L105`（纯中文串数组）。两边 11 条 label **有序完全一致**"
        "（现算确认），但它们是**两个独立真源** —— 改一处不传播。"
        "平台在 `i1ListedDisclosureModel.ts#L41` 收敛过一次却**漏掉了 useI1Adjudication.ts**。"
        "🔴 CD-1 判据 SHALL **同时比对两处**；变异「只改 i1CategoryScope.ts 的第 8 条 `软件`」"
        "SHALL 打红（单边判据会静默通过 = 假绿）。"
    ),
    "dual_definition_converged": True,
    "dual_definition_converged_note": (
        "✅ 已收敛：`useI1Adjudication.ts#L105` 改为 "
        "`I1_DEFAULT_CATEGORIES.map(c => c.label)` 派生，保留导出名与 `as const` 语义；"
        "零回归跑 `i1CategoryScope.spec.ts` / `useI1Adjudication.spec.ts` **16 tests passed**。"
    ),
}

#: BP-7（2026-10-01 resolved）：SOE 分类此前是 impl 独立写死的 12 条，与**单一真源**
#: `i1CategoryScope.ts#I1_DEFAULT_CATEGORIES`（11 条，与源模板 `底稿目录!A9:A19` /
#: `附注披露信息（国有企业）!A9:A19` 及准则映射 `note_template_soe.json` 三方一致）分叉。
#: 这是 CD-1（Task 10）收敛 listed 侧双定义时漏掉的 soe 侧遗留，属 impl 偏离既有单一真源，
#: 非会计裁决。现把 `I1_SOE_CATEGORIES` 收敛为派生自单一真源（11 条、软件第 8、住房使用权 /
#: 特许经营权、采矿+探矿并入矿产权，经 `I1_STANDARD_TO_LEGACY` 转回 soe 短 key）。
#: 影响面已 grep 实证：`I1_SOE_CATEGORIES` 消费方全在 I1 自身；附注子表契约用独立的
#: `I1_SOE_COLUMNS`（固定列头，不从分类派生）⇒ 收敛不改列头、不影响附注同步链
#: （原 fix_blocked_note 所称「改列头涉已归档附注同步 spec」经实证为过度保守）。
SOE_CLASSIFICATION_FACTS_I102: Final[dict[str, object]] = {
    "impl_constant": "composables/i1SoeDisclosureModel.ts#I1_SOE_CATEGORIES",
    "impl_count": 11,
    "source_ref": "附注披露信息（国有企业）!A9:A19",
    "source_real_count": 11,
    "verdict": "ALIGNED_TO_SINGLE_SOURCE",
    "status": "resolved",
    "single_source_ref": "composables/i1CategoryScope.ts#I1_DEFAULT_CATEGORIES",
    "second_source_ref": "backend/data/note_template_soe.json",
    "resolution": "I1_SOE_CATEGORIES 收敛为派生自单一真源 i1CategoryScope（原 12 条独立写死已移除）",
    "diffs_fixed": [
        "条数 12 → 11",
        "`软件`：impl 第 1 条（label 带「其中：」）→ 源第 8 条、label「软件」",
        "`房屋使用权` → `住房使用权`",
        "`特许权` → `特许经营权`",
        "`采矿权`+`探矿权`（2 条）→ `矿产权`（1 条，exploration 并入 mining，与 I1_LEGACY_KEY_MAP 既有口径一致）",
    ],
    "backward_compat": (
        "mapToI1SoeCategoryKey 的 采矿/探矿/矿权 分支统一归 mining；"
        "真库 I1-soe% 0 行，无 key 迁移丢数据风险。"
    ),
    "business_backlog_ref": (
        "evidence/classification-decision-and-business-checklist-2026-10-01.md B-1"
        "（探矿/采矿是否需对矿业客户分列，低风险、默认合并）"
    ),
}

#: 模板有列、store 侧是前端重算的派生值 ⇒ 只进 FORMULA_MASK。
TEMPLATE_ONLY_FORMULA_COLUMNS_I102: Final[tuple[tuple[str, str], ...]] = (
    ("H", "原值期末数（未审）= SUM(C:D)-F"),
    ("L", "原值期初数（审定）= C+I"),
    ("M", "原值本期增加（审定）= D+J　🔴 **两项**"),
    ("N", "原值本期减少（审定）= F+K　🔴 **两项**"),
    ("O", "原值期末数（审定）= L+M-N"),
    ("U", "摊销期末数（未审）= SUM(P:Q)-S"),
    ("Y", "摊销期初数（审定）= P+V"),
    ("Z", "摊销本期增加（审定）= Q+W+R　🔴 **三项**（含其他增加 R）"),
    ("AA", "摊销本期减少（审定）= S+X+T　🔴 **三项**（含其他减少 T）"),
    ("AB", "摊销期末数（审定）= Y+Z-AA"),
    ("AH", "减值期末数（未审）= 🔴 **SUM(AC:AE)-SUM(AF:AG)**（两个 SUM 相减，与前两区不同）"),
    ("AL", "减值期初数（审定）= AC+AI"),
    ("AM", "减值本期增加（审定）= AD+AJ+AE　🔴 **三项**"),
    ("AN", "减值本期减少（审定）= AF+AK+AG　🔴 **三项**"),
    ("AO", "减值期末数（审定）= AL+AM-AN"),
    ("AP", "期初未审净值 = C-P-AC"),
    ("AQ", "期初审定净值 = L-Y-AL"),
    ("AR", "期末未审净值 = H-U-AH"),
    ("AS", "期末审定净值 = O-AB-AO"),
)

# ═══════════════════════════════════════════════════════════════════════════
# 2. store 形态
# ═══════════════════════════════════════════════════════════════════════════

STORE_ITEM_ID_I102: Final[str] = "I1-2-rows"
ROW_IDENTITY_STORE_KEY_I102: Final[str] = "rowId"
EMPTY_PAYLOAD_I102: Final[str] = "[]"

# ═══════════════════════════════════════════════════════════════════════════
# 3. 字段声明（7 元组，顺序即 Excel 列序；跳过 19 个公式列）
# ═══════════════════════════════════════════════════════════════════════════

#: 28 个受管字段。`header_text` 取**该列最深的非空标题**
#: （A/B/AT/AU 在 R8 · C/F/I/P/S/V/AC/AF/AI 等在 R10 · D/E/G/Q/R/T/AD/AE/AG 在 R11）；
#: `group_header_cell` 给上一层组标题格坐标；`json_key` 逐字取 `useI1Detail.I1DetailRow`。
FIELD_SPECS_I102: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    # ── 基础 ──
    ("name", "A", "editable", "text", "name", "无形资产项目", ""),
    ("category", "B", "editable", "text", "category", "无形资产类别", ""),
    # ── 原值未审 C-G ──
    ("cost_begin", "C", "editable", "amount", "costBegin", "期初数", "C9"),
    ("cost_increase", "D", "editable", "amount", "costIncrease", "金额", "D10"),
    (
        "cost_increase_method",
        "E",
        "editable",
        "text",
        "costIncreaseMethod",
        "增加方式",
        "D10",
    ),
    ("cost_decrease", "F", "editable", "amount", "costDecrease", "金额", "F10"),
    (
        "cost_decrease_method",
        "G",
        "editable",
        "text",
        "costDecreaseMethod",
        "减少方式",
        "F10",
    ),
    # ── 原值调整 I-K ──
    ("cost_begin_adj", "I", "editable", "amount", "costBeginAdj", "账项调整", "I9"),
    ("cost_adj_inc", "J", "editable", "amount", "costAdjInc", "本期增加", "J9"),
    ("cost_adj_dec", "K", "editable", "amount", "costAdjDec", "本期减少", "J9"),
    # ── 摊销未审 P-T ──
    ("acc_amort_begin", "P", "editable", "amount", "accAmortBegin", "期初数", "P9"),
    (
        "amort_provision",
        "Q",
        "editable",
        "amount",
        "amortProvision",
        "本期摊销",
        "Q10",
    ),
    (
        "amort_other_increase",
        "R",
        "editable",
        "amount",
        "amortOtherIncrease",
        "其他增加",
        "Q10",
    ),
    ("amort_disposal", "S", "editable", "amount", "amortDisposal", "处置", "S10"),
    (
        "amort_other_decrease",
        "T",
        "editable",
        "amount",
        "amortOtherDecrease",
        "其他减少",
        "S10",
    ),
    # ── 摊销调整 V-X ──
    (
        "acc_amort_begin_adj",
        "V",
        "editable",
        "amount",
        "accAmortBeginAdj",
        "账项调整",
        "V9",
    ),
    ("amort_adj_inc", "W", "editable", "amount", "amortAdjInc", "本期增加", "W9"),
    ("amort_adj_dec", "X", "editable", "amount", "amortAdjDec", "本期减少", "W9"),
    # ── 减值未审 AC-AG ──
    (
        "impairment_begin",
        "AC",
        "editable",
        "amount",
        "impairmentBegin",
        "期初数",
        "AC9",
    ),
    (
        "impairment_provision",
        "AD",
        "editable",
        "amount",
        "impairmentProvision",
        "本期计提",
        "AD10",
    ),
    (
        "impair_other_increase",
        "AE",
        "editable",
        "amount",
        "impairOtherIncrease",
        "其他增加",
        "AD10",
    ),
    ("impair_disposal", "AF", "editable", "amount", "impairDisposal", "处置", "AF10"),
    (
        "impair_other_decrease",
        "AG",
        "editable",
        "amount",
        "impairOtherDecrease",
        "其他减少",
        "AF10",
    ),
    # ── 减值调整 AI-AK ──
    (
        "impairment_begin_adj",
        "AI",
        "editable",
        "amount",
        "impairmentBeginAdj",
        "账项调整",
        "AI9",
    ),
    ("impair_adj_inc", "AJ", "editable", "amount", "impairAdjInc", "本期增加", "AJ9"),
    ("impair_adj_dec", "AK", "editable", "amount", "impairAdjDec", "本期减少", "AJ9"),
    # ── 合规 AT/AU ──
    (
        "has_title_evidence",
        "AT",
        "editable",
        "text",
        "hasTitleEvidence",
        "是否有权属证明",
        "",
    ),
    (
        "mortgage_restricted",
        "AU",
        "editable",
        "text",
        "mortgageRestricted",
        "是否抵押受限",
        "",
    ),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R12/R13。
#: 🔴 **三区口径各不相同**，用同一套模板会算错两区：
#:   原值区审定增减是**两项**（M=D+J / N=F+K）；
#:   摊销/减值区是**三项**（Z=Q+W+R / AA=S+X+T / AM=AD+AJ+AE / AN=AF+AK+AG）；
#:   减值区未审期末是**两个 SUM 相减**（AH=SUM(AC:AE)-SUM(AF:AG)）而非 SUM(x:y)-z。
FORMULA_TEMPLATES_I102: Final[dict[str, str]] = {
    # 原值区
    "H": "=SUM(C{r}:D{r})-F{r}",
    "L": "=C{r}+I{r}",
    "M": "=D{r}+J{r}",
    "N": "=F{r}+K{r}",
    "O": "=L{r}+M{r}-N{r}",
    # 累计摊销区
    "U": "=SUM(P{r}:Q{r})-S{r}",
    "Y": "=P{r}+V{r}",
    "Z": "=Q{r}+W{r}+R{r}",
    "AA": "=S{r}+X{r}+T{r}",
    "AB": "=Y{r}+Z{r}-AA{r}",
    # 减值准备区
    "AH": "=SUM(AC{r}:AE{r})-SUM(AF{r}:AG{r})",
    "AL": "=AC{r}+AI{r}",
    "AM": "=AD{r}+AJ{r}+AE{r}",
    "AN": "=AF{r}+AK{r}+AG{r}",
    "AO": "=AL{r}+AM{r}-AN{r}",
    # 净值区（全公式）
    "AP": "=C{r}-P{r}-AC{r}",
    "AQ": "=L{r}-Y{r}-AL{r}",
    "AR": "=H{r}-U{r}-AH{r}",
    "AS": "=O{r}-AB{r}-AO{r}",
}
FORMULA_COLUMNS_I102: Final[tuple[str, ...]] = (
    "H", "L", "M", "N", "O",
    "U", "Y", "Z", "AA", "AB",
    "AH", "AL", "AM", "AN", "AO",
    "AP", "AQ", "AR", "AS",
)

# ═══════════════════════════════════════════════════════════════════════════
# 4. spec
# ═══════════════════════════════════════════════════════════════════════════

SPEC_I102: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_I102,
    sheet_key=SHEET_KEY_I102,
    table_key=ROWS_TABLE_KEY_I102,
    template_id=TEMPLATE_ID_I102,
    table_name=f"GT_{TEMPLATE_ID_I102}_ROWS",
    uuid_col=UUID_COL_I102,
    first_data_row=FIRST_DATA_ROW_I102,
    last_data_row=LAST_DATA_ROW_I102,
    footer_row=FOOTER_ROW_I102,
    header_group_row=HEADER_GROUP_ROW_I102,
    header_leaf_row=HEADER_LEAF_ROW_I102,
    store_item_id=STORE_ITEM_ID_I102,
    empty_payload=EMPTY_PAYLOAD_I102,
    row_identity_key=ROW_IDENTITY_STORE_KEY_I102,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_I102,
    formula_columns=FORMULA_COLUMNS_I102,
    formula_templates=FORMULA_TEMPLATES_I102,
    footer_marker=FOOTER_MARKER_I102,
    error_label="I1-2 无形资产明细表",
)
