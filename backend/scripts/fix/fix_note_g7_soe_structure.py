#!/usr/bin/env python
"""幂等脚本：G7 国企 `八、18 长期股权投资` 章节结构对齐。

**现状**（postgres 实证 + JSON 文件）：
- table[0] `长期股权投资分类`：5 行（缺源模板 R203「对子公司投资」）
- table[1] `长期股权投资明细`：`headers` 6 列（源模板两级 13 列），含 1 个
  `row_type: header_label` 假行
- table[2]/[4]（重要合营/联营企业主要财务信息）：`headers` 误用「（A公司）/（B公司）/
  （C公司）」矩阵列（那是**上市侧**的写法），源模板国企侧其实是**单主体 flat 3 列**
  （项目/期末数/期初数），行集也缺「其中：少数股东权益」「归属于母公司的所有者权益」
  两行的**没有**（国企侧本就比上市侧少两行，源模板逐字如此）
- table[3]/[5] **都叫 `续：`**（`sub_table_data` 以表名为键，同名互相覆盖丢整张表）
- table[6] `不重要合营企业和联营企业的汇总信息`：结构已对，只缺 `columns`
- table[7] `②对合营企业或联营企业发生超额亏损的分担额`：缺中间的空白可扩行
- table[8]/[9] 表名是段落文本泄漏（`C.在财务报表中确认的…比较。` /
  `本公司发起多个结构化主体…如下表所示：`），且各含 1 个 `header_label` 假行

**目标**：全部 10 张表补齐 `headers`/`columns`（含两级 `group`）/`rows`/`guidance`，
两张 `续：` 正名为不同表名，两张段落泄漏名正名为可读表名。

Usage::

    python backend/scripts/fix/fix_note_g7_soe_structure.py --dry-run
    python backend/scripts/fix/fix_note_g7_soe_structure.py
    python backend/scripts/fix/fix_note_g7_soe_structure.py --check

spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/ (Task 4.3)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
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
SOE_PATH = DATA_DIR / "note_template_soe.json"

SOE_SECTION = "八、18"
ALIGNED_BY = "fix_note_g7_soe_structure"


def _blanks(n: int) -> list[dict[str, Any]]:
    return [data_row() for _ in range(n)]


# ═══════ T0 长期股权投资分类（源 A202:F208）═══════

T0 = "长期股权投资分类"
T0_COLUMNS = flat_columns([
    ("item", "项  目", None),
    ("opening", "年初余额", AMOUNT),
    ("increase", "本期增加", AMOUNT),
    ("decrease", "本期减少", AMOUNT),
    ("closing", "期末余额", AMOUNT),
])
T0_ROWS = [
    data_row("对子公司投资"),
    data_row("对合营企业投资"),
    data_row("对联营企业投资"),
    subtotal_row("小  计"),
    data_row("减：长期股权投资减值准备"),
    total_row("合  计"),
]

# ═══════ T1 长期股权投资明细（源 A210:M222，两级 13 列）═══════

T1 = "长期股权投资明细"
_MOVE_GROUP = "本期增减变动"
T1_COLUMNS = grouped_columns(
    ("investee", "被投资单位"),
    [
        ("investmentCost", "投资成本", AMOUNT, None),
        ("opening", "期初余额", AMOUNT, None),
        ("addition", "追加投资", AMOUNT, _MOVE_GROUP),
        ("reduction", "减少投资", AMOUNT, _MOVE_GROUP),
        ("equityProfit", "权益法下确认的投资损益", AMOUNT, _MOVE_GROUP),
        ("oci", "其他综合收益调整", AMOUNT, _MOVE_GROUP),
        ("otherEquity", "其他权益变动", AMOUNT, _MOVE_GROUP),
        ("dividend", "宣告发放现金股利或利润", AMOUNT, _MOVE_GROUP),
        ("impairment", "计提减值准备", AMOUNT, _MOVE_GROUP),
        ("other", "其他", AMOUNT, _MOVE_GROUP),
        ("closing", "期末余额", AMOUNT, None),
        ("closingImpairment", "减值准备期末余额", AMOUNT, None),
    ],
)
# 源模板无「小计」，各组仅 1 个可扩行「……」后接下一组，末尾直接「合计」
T1_ROWS: list[dict[str, Any]] = [
    {"label": "一、合营企业", "row_type": "data"},
    {"label": "……", "row_type": "data"},
    {"label": "二、联营企业", "row_type": "data"},
    {"label": "……", "row_type": "data"},
    total_row("合  计"),
]

# ═══════ T2 重要合营企业的主要财务信息（源 A229:C241，flat 3 列）═══════
# 🔴 国企侧本就比上市侧少两行（无「其中：少数股东权益」「归属于母公司的所有者权益」），
#    源模板逐字如此，不是欠账。

T2 = "重要合营企业的主要财务信息（划分为持有待售的除外）"
_FS_COLUMNS = flat_columns([
    ("item", "项 目", None), ("current", "期末数", AMOUNT), ("prior", "期初数", AMOUNT),
])
_JV_FS_LABELS = [
    "流动资产", "非流动资产", "资产合计", "流动负债", "非流动负债", "负债合计", "净资产",
    "按持股比例计算的净资产份额", "调整事项", "对合营企业权益投资的账面价值 ",
    "存在公开报价的权益投资的公允价值 ",
]

# ═══════ T3 续：重要合营企业本期及上期经营成果（源 A243:C251）═══════

T3 = "续：重要合营企业本期及上期经营成果"
_PL_COLUMNS = flat_columns([
    ("item", "项  目", None), ("current", "本期发生额", AMOUNT), ("prior", "上期发生额", AMOUNT),
])
_JV_PL_LABELS = [
    "营业收入", "财务费用", "所得税费用", "净利润", "其他综合收益",
    "综合收益总额", "企业本期收到的来自合营企业的股利",
]

# ═══════ T4 重要联营企业的主要财务信息（源 A257:H269，非上市矩阵，flat 3 列）═══════
# 源模板 R268 字面「对合营企业权益投资的账面价值」处于联营表内属笔误，
# 沿用附注模板已修正口径「对联营企业权益投资的账面价值」（design.md R5.6 留证）。

T4 = "重要联营企业的主要财务信息"
_ASSOC_FS_LABELS = [
    "流动资产", "非流动资产", "资产合计", "流动负债", "非流动负债", "负债合计", "净资产",
    "按持股比例计算的净资产份额", "调整事项", "对联营企业权益投资的账面价值 ",
    "存在公开报价的权益投资的公允价值 ",
]

# ═══════ T5 续：重要联营企业本期及上期经营成果（源 A271:H277）═══════

T5 = "续：重要联营企业本期及上期经营成果"
_ASSOC_PL_LABELS = [
    "营业收入", "净利润", "其他综合收益", "综合收益总额", "企业本期收到的来自联营企业的股利",
]

# ═══════ T6 不重要合营企业和联营企业的汇总信息（源 A280:D292）═══════
# 结构已对，只补 columns

T6 = "不重要合营企业和联营企业的汇总信息"
T6_COLUMNS = flat_columns([
    ("item", "项  目", None), ("current", "本期数", AMOUNT), ("prior", "上期数", AMOUNT),
])
T6_LABELS = [
    "合营企业：", "投资账面价值合计", "下列各项按持股比例计算的合计数 ",
    "净利润", "其他综合收益", "综合收益总额",
    "联营企业：", "投资账面价值合计", "下列各项按持股比例计算的合计数 ",
    "净利润", "其他综合收益", "综合收益总额",
]

# ═══════ T7 ②对合营企业或联营企业发生超额亏损的分担额（源 A301:E312）═══════

T7 = "②对合营企业或联营企业发生超额亏损的分担额"
T7_COLUMNS = flat_columns([
    ("investee", "被投资单位名称", None),
    ("priorUnrecognised", "前期累积未确认的损失份额", AMOUNT),
    ("currentUnrecognised", "本期未确认的损失份额（或本期实现净利润的分享额）", AMOUNT),
    ("closingUnrecognised", "本期末累积未确认的损失份额", AMOUNT),
])
T7_ROWS = (
    [data_row("合营企业")] + _blanks(3) + [subtotal_row("小计")]
    + [data_row("联营企业")] + _blanks(3) + [subtotal_row("小计")]
    + [total_row("合  计")]
)

# ═══════ T8 结构化主体权益的账面价值和最大损失敞口（源 A323:F328，两级）═══════
# 原表名是段落文本泄漏：'C.在财务报表中确认的与企业在未纳入合并财务报表范围的
# 结构化主体中权益相关的资产和负债的账面价值与其最大损失敞口的比较。'

T8 = "结构化主体权益的账面价值和最大损失敞口"
T8_COLUMNS = grouped_columns(
    ("item", "项目"),
    [
        ("sponsorScale", "规模", None, "发起"),
        ("endBookValue", "账面价值", AMOUNT, "期末数"),
        ("endMaxLoss", "最大损失敞口", AMOUNT, "期末数"),
        ("beginBookValue", "账面价值", AMOUNT, "期初数"),
        ("beginMaxLoss", "最大损失敞口", AMOUNT, "期初数"),
        ("presentationItem", "列报项目", None, None),
    ],
)
T8_ROWS: list[dict[str, Any]] = [
    data_row("优先级债券"),
    data_row("次级债券"),
    data_row("信用违约互换（负债）"),
    {"label": "……", "row_type": "data"},
]

# ═══════ T9 结构化主体获得收益及转移资产情况（源 A340:D345，两级）═══════
# 原表名是段落文本泄漏：'本公司发起多个结构化主体，但在结构化中均不持有权益。
# 2023年，本公司从发起的结构化主体获得收益的情况以及当期向结构化主体转移资产
# 的情况如下表所示：'

T9 = "结构化主体获得收益及转移资产情况"
_INCOME_GROUP = "当期从结构化主体获得的收益"
T9_COLUMNS = grouped_columns(
    ("type", "类型"),
    [
        ("serviceFee", "服务收费", AMOUNT, _INCOME_GROUP),
        ("assetSaleGain", "向结构化主体出售资产的利得（损失）", AMOUNT, _INCOME_GROUP),
        ("incomeTotal", "合计", AMOUNT, _INCOME_GROUP),
        ("transferredAssets", "当期向结构化主体转移资产账面价值", AMOUNT, None),
    ],
)
T9_ROWS: list[dict[str, Any]] = [
    data_row("信用资产证券化"),
    data_row("投资基金"),
    {"label": "……", "row_type": "data"},
    total_row("合  计"),
]

# ═══════ guidance ═══════

_G0 = (
    "长期股权投资分类（源 A202:F208）：项目 = 对子公司投资/对合营企业投资/"
    "对联营企业投资/小计/减：长期股权投资减值准备/合计。数据来源：审定表 G7-1"
    "（小计=三类之和；合计=小计−减值准备，与 G7-1「二、减值准备」段勾稽）。"
)
_G1 = (
    "长期股权投资明细（源 A210:M222 两级表头）：被投资单位（标签列）+ 投资成本 + "
    "期初余额 + 本期增减变动（追加投资、减少投资、权益法下确认的投资损益、"
    "其他综合收益调整、其他权益变动、宣告发放现金股利或利润、计提减值准备、其他）+ "
    "期末余额 + 减值准备期末余额。行 = 一、合营企业（含动态明细行「……」）/ "
    "二、联营企业（含动态明细行「……」）/ 合计（源模板本表无小计层）。"
    "若对被投资单位持股比例与其在被投资单位表决权比例不一致，应说明原因"
    "（可索引至附注十一、3）。数据来源：明细表 G7-2。"
)
_G2 = (
    "重要合营企业的主要财务信息（源 A229:C241，划分为持有待售的除外）："
    "项目/期末数/期初数，主要财务信息按权益法调整后的金额披露；"
    "「调整事项」包括投资形成的正商誉、抵消的未实现内部交易损益、减值准备等。"
    "母公司为投资性主体时无需披露。数据来源：被投资单位财务信息 G7-5，"
    "权益法调节项来自权益法测算表 G7-14。"
)
_G3 = "续：重要合营企业本期及上期经营成果（源 A243:C251）。数据来源：被投资单位财务信息 G7-5。"
_G4 = (
    "重要联营企业的主要财务信息（源 A257:H269）：口径与重要合营企业主要财务信息表一致，"
    "项目/期末数/期初数。数据来源：被投资单位财务信息 G7-5，"
    "权益法调节项来自权益法测算表 G7-14。"
)
_G5 = "续：重要联营企业本期及上期经营成果（源 A271:H277）。数据来源：被投资单位财务信息 G7-5。"
_G6 = (
    "不重要合营企业和联营企业的汇总信息（源 A280:D292）：投资账面价值合计取明细表 G7-2；"
    "下列各项按持股比例计算的合计数取被投资单位财务信息 G7-5 × 持股比例。"
)
_G7 = (
    "②对合营企业或联营企业发生超额亏损的分担额（源 A301:E312，不适用的删除）："
    "合营企业、联营企业各自列示前期累积未确认损失份额、本期未确认损失份额"
    "（或本期实现净利润的分享额）、本期末累积未确认损失份额，各自小计后合计。"
    "数据来源：未确认投资损失测试表 G7-16。"
)
_G8 = (
    "结构化主体权益的账面价值和最大损失敞口（源 A323:F328）：披露在财务报表中确认的、"
    "与企业在未纳入合并财务报表范围的结构化主体中权益相关的资产和负债的账面价值及其"
    "列报项目，最大损失敞口及其确定方法（不能量化的应披露事实及原因），"
    "以及账面价值与最大损失敞口的比较。"
)
_G9 = (
    "结构化主体获得收益及转移资产情况（源 A340:D345）：企业作为未纳入合并财务报表范围"
    "结构化主体的发起人但没有权益时，应披露认定依据，并分类披露当期从该结构化主体获得"
    "的收益、收益类型（服务收费/出售资产利得），以及当期转移至该结构化主体的资产"
    "在转移时的账面价值。"
)


def _soe_plan() -> list[dict[str, Any]]:
    return [
        rule(T0, T0_COLUMNS, T0_ROWS, _G0),
        rule(T1, T1_COLUMNS, T1_ROWS, _G1),
        rule(T2, _FS_COLUMNS, [data_row(x) for x in _JV_FS_LABELS], _G2),
        rule(T3, _PL_COLUMNS, [data_row(x) for x in _JV_PL_LABELS], _G3, aliases=["续："]),
        rule(T4, _FS_COLUMNS, [data_row(x) for x in _ASSOC_FS_LABELS], _G4),
        rule(T5, _PL_COLUMNS, [data_row(x) for x in _ASSOC_PL_LABELS], _G5, aliases=["续："]),
        rule(T6, T6_COLUMNS, [data_row(x) for x in T6_LABELS], _G6),
        rule(T7, T7_COLUMNS, T7_ROWS, _G7),
        rule(
            T8, T8_COLUMNS, T8_ROWS, _G8,
            aliases=[
                "C.在财务报表中确认的与企业在未纳入合并财务报表范围的结构化主体中"
                "权益相关的资产和负债的账面价值与其最大损失敞口的比较。"
            ],
        ),
        rule(
            T9, T9_COLUMNS, T9_ROWS, _G9,
            aliases=[
                "本公司发起多个结构化主体，但在结构化中均不持有权益。2023年，"
                "本公司从发起的结构化主体获得收益的情况以及当期向结构化主体"
                "转移资产的情况如下表所示："
            ],
        ),
    ]


EXPECTED = {"soe": [T0, T1, T2, T3, T4, T5, T6, T7, T8, T9]}
_TARGETS = {"soe": (SOE_PATH, SOE_SECTION, _soe_plan)}
_LABELS = {"soe": "note_template_soe.json §八、18 长期股权投资（国企）"}


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
    )


main = build_cli(
    "附注 G7 长期股权投资章节结构对齐（幂等，仅国企 §八、18）",
    _runner,
    _LABELS,
)

if __name__ == "__main__":
    raise SystemExit(main())
