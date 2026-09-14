#!/usr/bin/env python
"""幂等脚本：G7 上市 `七、1 在其他主体中的权益` 章节结构重建。

**现状**（postgres 实证 + JSON 文件）：`note_template_listed.json` 该章节
`tables=0` / `text_sections=187` —— 整章零表格，187 段是 md 重建把源 xlsx
R26:R243 逐段落原样倾倒进 `text_sections`（含表头行、示例数字、【提示】括注），
未做任何结构化。

**目标**：按源模板 `附注披露信息（上市公司）!A26:M243` 重建 14 张表
（子公司权益 6 张 + 合营联营权益 7 张 + 共同经营 1 张）+ 10 段真实需要填写的
说明性 `text_sections`（剔除示例数字与【提示】括注 —— 那些是编制辅助不是披露正文）。

Usage::

    python backend/scripts/fix/fix_note_g7_listed_other_entities_structure.py --dry-run
    python backend/scripts/fix/fix_note_g7_listed_other_entities_structure.py
    python backend/scripts/fix/fix_note_g7_listed_other_entities_structure.py --check

spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/ (Task 4.2)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    PERCENT,
    build_cli,
    data_row,
    flat_columns,
    grouped_columns,
    rule,
    run_section,
    subtotal_row,
    total_row,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"

LISTED_SECTION = "七、1"
ALIGNED_BY = "fix_note_g7_listed_other_entities_structure"


def _blanks(n: int) -> list[dict[str, Any]]:
    return [data_row() for _ in range(n)]


# ═══════════════════════════ 1、在子公司中的权益 ═══════════════════════════

# T1 企业集团的构成（源 A28:G39）
T1 = "企业集团的构成"
# 🔴 标签列 key 统一为平台惯例 'label'（g7-column-alignment spec Task 5）：
# 平台 211 个标签列定义里 148 个用 'label'；本文件原用 'name'/'item'/'investee'/'seq'/'type'
# 等各表自拟 key，与运行时 buildG7*Columns() 的 'label' 不一致（B 类偏差）。
# is_label / label 显示文字均不动 —— 投影器 note_sub_table_projector._project_row 对
# 标签列有**双向兜底**（任意标签 key → 'label' 回填 / 反向回退），故改 key 零数据风险。
# 🔴 数据列 key 一律以**运行时**（`buildG7ListedColumns()`）为准（Task 9，量化闸裁决
# `SAFE_TO_RENAME_SEED`）：`g7DisclosureCrossSheet.ts` 用**字面量 key** 往 `row.values`
# 写跨表回填值（实测 56 处 `writeValue(row.values, '<key>', ...)`，本表命中
# `principalPlace`/`registeredPlace`/`businessNature`/`directHolding`/`indirectHolding`/
# `acquisitionMethod`），改运行时 key 会让这些回填**静默失效**；seed 侧无同类消费方
# ⇒ seed 服从运行时。改动前后 key 集合 == 运行时那一侧（禁第三套 key）。
T1_COLUMNS = grouped_columns(
    ("label", "子公司名称"),
    [
        ("principalPlace", "主要经营地", None, None),
        ("registeredPlace", "注册地", None, None),
        ("businessNature", "业务性质", None, None),
        ("directHolding", "直接", PERCENT, "持股比例%"),
        ("indirectHolding", "间接", PERCENT, "持股比例%"),
        ("acquisitionMethod", "取得方式", None, None),
    ],
)

# T2 重要的非全资子公司（源 A49:E54）
T2 = "重要的非全资子公司"
T2_COLUMNS = flat_columns([
    ("label", "子公司名称", None),
    # 数据列 key 服从运行时（同 T1 理由）：crossSheet 写 `currentProfit`/`closingEquity`
    ("holdingRatio", "少数股东持股比例%", PERCENT),
    ("currentProfit", "本期归属于少数股东的损益", AMOUNT),
    ("dividend", "本期向少数股东宣告分派的股利", AMOUNT),
    ("closingEquity", "期末少数股东权益余额", AMOUNT),
])

# T3 重要非全资子公司主要财务信息—期末数（源 A58:G64）
T3 = "重要非全资子公司主要财务信息—期末数"
_BALANCE_SUBS = [
    ("currentAssets", "流动资产", AMOUNT), ("nonCurrentAssets", "非流动资产", AMOUNT),
    ("totalAssets", "资产合计", AMOUNT), ("currentLiabilities", "流动负债", AMOUNT),
    ("nonCurrentLiabilities", "非流动负债", AMOUNT), ("totalLiabilities", "负债合计", AMOUNT),
]
T3_COLUMNS = grouped_columns(
    ("label", "子公司名称"),
    [(k, lbl, fmt, "期末数") for k, lbl, fmt in _BALANCE_SUBS],
)

# T4 续（1）—期初数（源 A65:G72，与 T3 同构，group 名换成「期初数」）
T4 = "续（1）"
T4_COLUMNS = grouped_columns(
    ("label", "子公司名称"),
    [(k, lbl, fmt, "期初数") for k, lbl, fmt in _BALANCE_SUBS],
)

# T5 续（2）—本期及上期发生额（源 A73:I81）
T5 = "续（2）"
_RESULT_SUBS = [
    ("revenue", "营业收入", AMOUNT), ("profit", "净利润", AMOUNT),
    ("comprehensive", "综合收益总额", AMOUNT), ("cashFlow", "经营活动现金流量", AMOUNT),
]
T5_COLUMNS = grouped_columns(
    ("label", "子公司名称"),
    [(f"current{k[0].upper()}{k[1:]}", lbl, fmt, "本期发生额") for k, lbl, fmt in _RESULT_SUBS]
    + [(f"prior{k[0].upper()}{k[1:]}", lbl, fmt, "上期发生额") for k, lbl, fmt in _RESULT_SUBS],
)

# T6 未丧失控制权的所有者权益份额变动影响（源 A96:G108，metric-rows × 公司 1~6 列）
T6 = "未丧失控制权的所有者权益份额变动影响"
# 🔴 动态列 key 取运行时 `buildG7SlotColumns()` 的稳定形态 `{slot}_{seq}`，
# **禁写死序号**（原为 `company1..company6`）：该表按被投资单位横向展开，审计师增删/
# 改名后写死序号无法跟随（改名只该改 `entityName` 即显示文字，key 必须不变，
# 否则已录数据丢落点）。slot 名与 `g7ListedDisclosureModel.OWNERSHIP_CHANGE_SLOT`
# 逐字一致，序号由下标+1 派生 —— 与运行时同一套规则，不各写一份字面量。
T6_SLOT = "ownership-change-company"
T6_DEFAULT_ENTITY_NAMES = [f"公司{i}" for i in range(1, 7)]
T6_COLUMNS = flat_columns([("label", "项  目", None)] + [
    (f"{T6_SLOT}_{i}", name, AMOUNT)
    for i, name in enumerate(T6_DEFAULT_ENTITY_NAMES, start=1)
])
T6_METRIC_LABELS = [
    "购买成本/处置对价：", "现金", "非现金资产的公允价值", "发行或承担的债务的账面价值",
    "发行的权益性证券的面值", "或有对价", "购买成本/处置对价合计",
    "减：按取得/处置的股权比例计算的子公司净资产份额", "差额",
    "其中：调整资本公积", "调整盈余公积", "调整未分配利润",
]

_S1_PLAN = [
    rule(T1, T1_COLUMNS, _blanks(3), (
        "企业集团的构成（源 A28:G39）：子公司名称 + 主要经营地 + 注册地 + 业务性质 + "
        "持股比例%（直接/间接）+ 取得方式。数据来源：被投资单位基本信息 G7-4。"
    ), insert=True),
    rule(T2, T2_COLUMNS, _blanks(3), (
        "重要的非全资子公司（源 A49:E54）：单个非全资子公司的少数股东权益对企业集团而言"
        "不重要时不需要披露。数据来源：被投资单位基本信息 G7-4。"
    ), insert=True),
    rule(T3, T3_COLUMNS, _blanks(3), (
        "重要非全资子公司主要财务信息—期末数（源 A58:G64）。财务数据以合并日子公司可辨认"
        "资产和负债的公允价值为基础调整；被划分为持有待售资产的不需披露。"
        "数据来源：被投资单位财务信息 G7-5。"
    ), insert=True),
    rule(T4, T4_COLUMNS, _blanks(3), (
        "续（1）—期初数（源 A65:G72），与「期末数」表同构，仅期初口径。"
        "数据来源：被投资单位财务信息 G7-5。"
    ), insert=True),
    rule(T5, T5_COLUMNS, _blanks(3), (
        "续（2）—本期及上期发生额（源 A73:I81）：营业收入/净利润/综合收益总额/"
        "经营活动现金流量，本期与上期各一组。数据来源：被投资单位财务信息 G7-5。"
    ), insert=True),
    rule(
        T6, T6_COLUMNS,
        [{"label": lbl, "row_type": "data"} for lbl in T6_METRIC_LABELS],
        (
            "未丧失控制权的所有者权益份额变动影响（源 A96:G108）：本期在子公司所有者权益"
            "份额发生变化但未丧失控制权的交易，按购买成本/处置对价与按比例计算的净资产份额"
            "差额，分析对少数股东权益及归属于母公司所有者权益的影响。"
            "15号文第三十五条要求披露变化情况、影响金额及计算依据。"
            "数据来源：处置子公司测试表 G7-10（NCI 部分股权处置）。"
        ),
        insert=True,
    ),
]

# ═══════════════ 2、在合营安排或联营企业中的权益 ═══════════════

# T7 重要的合营企业或联营企业（源 A111:G124）
T7 = "重要的合营企业或联营企业"
T7_COLUMNS = grouped_columns(
    ("label", "合营企业或联营企业名称"),
    [
        # 数据列 key 服从运行时（同 T1 理由）；末列运行时用 `accountingMethod`
        # （区别于 T1 子公司表的 `acquisitionMethod`「取得方式」，两者语义不同不可混）
        ("principalPlace", "主要经营地", None, None),
        ("registeredPlace", "注册地", None, None),
        ("businessNature", "业务性质", None, None),
        ("directHolding", "直接", PERCENT, "持股比例(%)"),
        ("indirectHolding", "间接", PERCENT, "持股比例(%)"),
        ("accountingMethod", "对合营企业或联营企业投资的会计处理方法", None, None),
    ],
)

# T8 重要合营企业主要财务信息（源 A132:C151，18 行）
T8 = "重要合营企业主要财务信息"
T8_COLUMNS = flat_columns([
    ("label", "项 目", None), ("current", "期末数", AMOUNT), ("prior", "期初数", AMOUNT),
])
T8_LABELS = [
    "流动资产", "其中：现金和现金等价物", "非流动资产", "资产合计", "流动负债", "非流动负债",
    "负债合计", "净资产", "  其中：少数股东权益", "归属于母公司的所有者权益",
    "按持股比例计算的净资产份额", "调整事项", "  其中：商誉", "   未实现内部交易损益",
    "   减值准备", "   其他", "对合营企业权益投资的账面价值 ", "存在公开报价的权益投资的公允价值 ",
]

# T9 续：重要合营企业本期及上期经营成果（源 A153:C163，8 行）
T9 = "续：重要合营企业本期及上期经营成果"
T9_COLUMNS = flat_columns([
    ("label", "项  目", None), ("current", "本期发生额", AMOUNT), ("prior", "上期发生额", AMOUNT),
])
T9_LABELS = [
    "营业收入", "财务费用", "所得税费用", "净利润", "终止经营的净利润",
    "其他综合收益", "综合收益总额", "企业本期收到的来自合营企业的股利",
]

# T10 重要联营企业主要财务信息（源 A169:G187，17 行，不含现金及现金等价物行）
T10 = "重要联营企业主要财务信息"
# 🔴 动态列：slot 名与 `g7ListedDisclosureModel.IMPORTANT_ASSOCIATE_SLOT` 逐字一致，
# key = `{slot}_{seq}_{subKey}`（原写死 `c1Current`/`c1Prior`，见 T6 处说明）。
# 🔴 T10（FS 表）与 T11（PL 表）**共用同一 slot** 但子列 label 不同 —— FS 取
# 「期末数/期初数」、PL 取「本期发生额/上期发生额」（源 A169:G187 vs A189:G196）。
# subKey 两表同为 `current`/`prior`（只有显示文字不同），故 key 天然一致。
IMPORTANT_ASSOCIATE_SLOT = "important-associate"
IMPORTANT_ASSOCIATE_DEFAULT_NAMES = ["联营企业1", "联营企业2", "联营企业3"]


def _associate_matrix_columns(
    label_header: str,
    current_label: str,
    prior_label: str,
) -> list[dict[str, Any]]:
    """联营企业矩阵动态列（每实体 current/prior 两子列，按实体名分组）。

    与运行时 `buildG7SlotColumns(IMPORTANT_ASSOCIATE_SLOT, names, sub)` 同规则派生，
    子列 label 由调用方按**本表**源文传入（禁两表共用一套 label，源文不同）。
    """
    subs = [("current", current_label), ("prior", prior_label)]
    return grouped_columns(
        ("label", label_header),
        [
            (f"{IMPORTANT_ASSOCIATE_SLOT}_{seq}_{sub_key}", sub_label, AMOUNT, name)
            for seq, name in enumerate(IMPORTANT_ASSOCIATE_DEFAULT_NAMES, start=1)
            for sub_key, sub_label in subs
        ],
    )


T10_COLUMNS = _associate_matrix_columns("项 目", "期末数", "期初数")
T10_LABELS = [
    "流动资产", "非流动资产", "资产合计", "流动负债", "非流动负债", "负债合计", "净资产",
    "  其中：少数股东权益", "归属于母公司的所有者权益", "按持股比例计算的净资产份额",
    "调整事项", "  其中：商誉", "   未实现内部交易损益", "   减值准备", "   其他",
    "对联营企业权益投资的账面价值", "存在公开报价的权益投资的公允价值 ",
]

# T11 续：重要联营企业本期及上期经营成果（源 A189:G196，6 行）
T11 = "续：重要联营企业本期及上期经营成果"
# 复用 T10 的 slot 与 key 规则，子列 label 取**本表**源文（A189:G196）。
T11_COLUMNS = _associate_matrix_columns("项  目", "本期发生额", "上期发生额")
T11_LABELS = [
    "营业收入", "净利润", "终止经营的净利润", "其他综合收益",
    "综合收益总额", "企业本期收到的来自联营企业的股利",
]

# T12 其他不重要合营企业和联营企业的汇总财务信息（源 A200:C212）
T12 = "其他不重要合营企业和联营企业的汇总财务信息"
T12_COLUMNS = flat_columns([
    ("label", "项  目", None),
    ("current", "期末数/本期发生额", AMOUNT),
    ("prior", "期初数/上期发生额", AMOUNT),
])
T12_LABELS = [
    "合营企业：", "投资账面价值合计", "下列各项按持股比例计算的合计数 ",
    "净利润", "其他综合收益", "综合收益总额",
    "联营企业：", "投资账面价值合计", "下列各项按持股比例计算的合计数 ",
    "净利润", "其他综合收益", "综合收益总额",
]

# T13 对合营企业或联营企业发生超额亏损的分担额（源 A221:D232）
T13 = "对合营企业或联营企业发生超额亏损的分担额"
# 🔴 三列 key 服从运行时（`priorCumulative` / `currentUnrecognized` / `closingCumulative`）：
# 该表是**已接线**的跨表回填目标 —— `g7DisclosureCrossSheet.ts` L1620~L1622 经
# `columnKeys.{prior,current,closing}`（L2783~L2785 映射表）把 G7-16 未确认亏损测算
# 结果写进 `row.values`，且 `g7UnrecognizedLossModel.ts` 亦按这三个 key 读写。
# 改运行时侧会让该回填静默失效（Vue 传不存在的字段不报错），故 seed 服从运行时。
# 另注 seed 原 key 用英式拼写 `Unrecognised`、运行时用美式 `Unrecognized`。
T13_COLUMNS = flat_columns([
    ("label", "被投资单位名称", None),
    ("priorCumulative", "前期累积未确认的损失份额", AMOUNT),
    ("currentUnrecognized", "本期未确认的损失份额（或本期实现净利润的分享额）", AMOUNT),
    ("closingCumulative", "本期末累积未确认的损失份额", AMOUNT),
])
T13_ROWS = (
    [data_row("合营企业")] + _blanks(3) + [subtotal_row("小计")]
    + [data_row("联营企业")] + _blanks(3) + [subtotal_row("小计")]
    + [total_row("合  计")]
)

_S2_PLAN = [
    rule(T7, T7_COLUMNS, _blanks(6), (
        "重要的合营企业或联营企业（源 A111:G124）：①合营企业 ②联营企业 分组列示，"
        "含主要经营地/注册地/业务性质/持股比例(%)（直接/间接）/会计处理方法。"
        "持有其他主体20%以下表决权但具有重大影响，或20%以上表决权但不具有重大影响的，"
        "应披露相关判断和依据。数据来源：被投资单位基本信息 G7-4。"
    ), insert=True),
    rule(T8, T8_COLUMNS, [data_row(x) for x in T8_LABELS], (
        "重要合营企业主要财务信息（源 A132:C151，18 行）：主要财务信息按权益法调整后的"
        "金额披露；「调整事项」包括投资形成的正商誉、抵消的未实现内部交易损益、减值准备等。"
        "母公司为投资性主体时无需披露。数据来源：被投资单位财务信息 G7-5，"
        "权益法调节项来自权益法测算表 G7-14。"
    ), insert=True),
    rule(T9, T9_COLUMNS, [data_row(x) for x in T9_LABELS], (
        "续：重要合营企业本期及上期经营成果（源 A153:C163）。"
        "存在终止经营净利润的，应在本表中单列项目披露。"
        "数据来源：被投资单位财务信息 G7-5。"
    ), insert=True),
    rule(T10, T10_COLUMNS, [data_row(x) for x in T10_LABELS], (
        "重要联营企业主要财务信息（源 A169:G187，17 行）：按联营企业分列期末数/期初数，"
        "口径与合营企业主要财务信息表一致（不含现金及现金等价物单列行 —— 源模板该行"
        "只在合营企业表出现）。数据来源：被投资单位财务信息 G7-5，"
        "权益法调节项来自权益法测算表 G7-14。"
    ), insert=True),
    rule(T11, T11_COLUMNS, [data_row(x) for x in T11_LABELS], (
        "续：重要联营企业本期及上期经营成果（源 A189:G196）。"
        "数据来源：被投资单位财务信息 G7-5。"
    ), insert=True),
    rule(T12, T12_COLUMNS, [data_row(x) for x in T12_LABELS], (
        "其他不重要合营企业和联营企业的汇总财务信息（源 A200:C212）：投资账面价值合计"
        "取明细表 G7-2；下列各项按持股比例计算的合计数取被投资单位财务信息 G7-5 × 持股比例。"
    ), insert=True),
    rule(T13, T13_COLUMNS, T13_ROWS, (
        "对合营企业或联营企业发生超额亏损的分担额（源 A221:D232，不适用的删除）："
        "合营企业、联营企业各自列示前期累积未确认损失份额、本期未确认损失份额（或本期"
        "实现净利润的分享额）、本期末累积未确认损失份额，各自小计后合计。"
        "数据来源：未确认投资损失测试表 G7-16。"
    ), insert=True),
]

# ═══════════════ （8）重要的共同经营 ═══════════════

T14 = "重要的共同经营"
# 🔴 数据列 key 服从运行时（`jointOperationColumns`）：`region`→`principalPlace` /
# `registered`→`registeredPlace` / `nature`→`businessNature`，且持股两列在本表是
# `directShare`/`indirectShare`（**不是** T1/T7 的 `directHolding`/`indirectHolding`
# —— 源模板本表口径为「持股比例或享有的份额」，运行时据此另起了列名）。
# 五者均被 `g7DisclosureCrossSheet.ts` 以字面量 `writeValue(row.values, '<key>', …)`
# 消费（实测 L690~L694），改运行时侧会让共同经营的跨表回填静默失效。
T14_COLUMNS = grouped_columns(
    ("label", "共同经营名称"),
    [
        ("principalPlace", "主要经营地", None, None),
        ("registeredPlace", "注册地", None, None),
        ("businessNature", "业务性质", None, None),
        # 源模板字面「持股比例/享有的份额(%)」含 '/'；group 禁 '/'（多级表头语义冲突，
        # 前端 activeTableColumns 只认扁平 {group,start,span}），改用等价无斜杠表述。
        ("directShare", "直接", PERCENT, "持股比例或享有的份额(%)"),
        ("indirectShare", "间接", PERCENT, "持股比例或享有的份额(%)"),
    ],
)

_S3_PLAN = [
    rule(T14, T14_COLUMNS, _blanks(4), (
        "重要的共同经营（源 A235:F240）：共同经营名称、主要经营地、注册地、业务性质、"
        "持股比例/享有的份额(%)（直接/间接）。持股比例或享有份额不同于表决权比例的，"
        "应说明表决权比例及差异原因；共同经营为单独主体的，应披露判断为共同经营的依据。"
        "数据来源：被投资单位基本信息 G7-4。"
    ), insert=True),
]

# ═══════════════ text_sections：真实需要填写的说明段（剔除示例与【提示】）═══════════════

_REQUIRED_TEXT_SECTIONS = [
    "#### 集团构成及控制判断说明",
    "说明持股比例与表决权比例的差异及原因；持有其他主体半数或以下表决权但仍控制该主体、"
    "或持有半数以上表决权但不控制该主体的相关判断和依据；确定公司是代理人还是委托人的"
    "判断和依据；对于纳入合并范围的重要结构化主体，披露控制的相关判断和依据。",
    "#### 资产证券化及结构化主体交易安排说明",
    "如适用，说明资产证券化业务的主要交易安排及会计处理，包括破产隔离条款；不适用时"
    "标记不适用。",
    "#### （4）使用资产和清偿负债存在的重大限制",
    "说明限制的性质和程度，包括对母公司或子公司与集团内其他主体相互转移现金或其他"
    "资产的限制、股利分配/贷款或垫款的限制、少数股东保护性权利对使用集团资产或清偿"
    "集团负债能力的限制，以及限制涉及的资产和负债在合并财务报表中的金额。",
    "#### （5）向纳入合并范围的结构化主体提供的财务支持或其他支持",
    "披露与结构化主体相关的风险信息，包括已提供财务支持或其他支持的合同条款/类型/"
    "金额/原因，以及存在提供支持意图时的说明。",
    "#### （6）所有者权益份额发生变化但仍控制子公司的交易说明",
    "说明子公司所有者权益份额发生变化的交易背景，及其对归属于母公司所有者权益和"
    "少数股东权益的影响金额和计算依据。",
    "#### 持股比例、重大影响及共同控制判断",
    "说明持股比例与表决权比例差异原因；持有其他主体20%以下表决权但具有重大影响，"
    "或20%以上表决权但不具有重大影响的相关判断和依据；对合营企业具有共同控制的依据。",
    "#### 重要会计政策和会计估计差异说明",
    "说明合营企业、联营企业的重要会计政策、会计估计与本公司的会计政策、会计估计"
    "存在的重大差异及相应调整。",
    "#### （5）转移资金能力存在的重大限制",
    "说明合营企业或联营企业向本公司转移资金的能力存在的重大限制。",
    "#### （7）未确认承诺及或有负债",
    "披露与对合营企业投资相关的未确认承诺，以及与对合营企业或联营企业投资相关的"
    "或有负债。",
    "#### 共同经营判断依据",
    "说明持股比例或享有的份额不同于表决权比例的差异及原因；共同经营为单独主体的，"
    "说明判断为共同经营的依据。",
]

EXPECTED = {"listed": [T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T13, T14]}
_TARGETS = {"listed": (LISTED_PATH, LISTED_SECTION, lambda: _S1_PLAN + _S2_PLAN + _S3_PLAN)}
_LABELS = {"listed": "note_template_listed.json §七、1 在其他主体中的权益（上市）"}


def _runner(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn = _TARGETS[key]
    return run_section(
        path,
        section_number,
        plan_fn(),
        EXPECTED[key],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        text_sections=_REQUIRED_TEXT_SECTIONS,
    )


main = build_cli(
    "附注 G7「在其他主体中的权益」章节结构重建（幂等，仅上市）",
    _runner,
    _LABELS,
)

if __name__ == "__main__":
    raise SystemExit(main())
