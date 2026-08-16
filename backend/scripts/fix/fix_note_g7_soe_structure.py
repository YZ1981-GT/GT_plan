#!/usr/bin/env python
"""幂等脚本：G7 国企 `八、18 长期股权投资` 章节结构对齐。

**现状**（postgres 实证 + JSON 文件）：
- table[0] `长期股权投资分类`：5 行（缺源模板 R203「对子公司投资」）
- table[1] `长期股权投资明细`：`headers` 6 列（源模板两级 13 列），含 1 个
  `row_type: header_label` 假行
- table[2]（重要**合营**企业主要财务信息）：`headers` 误用「（A公司）/（B公司）/
  （C公司）」矩阵列（那是**上市侧**的写法），源模板国企侧合营表其实是**单主体 flat 3 列**
  （项目/期末数/期初数），行集也缺「其中：少数股东权益」「归属于母公司的所有者权益」
  两行的**没有**（国企侧本就比上市侧少两行，源模板逐字如此）
- 🔴 table[4]/[5]（重要**联营**企业主要财务信息 + 其续表）**不能套用合营表的单主体 3 列**
  —— 2026-08-08 openpyxl 直读推翻本脚本早期结论：源模板 `附注披露信息（国企）`
  ``r257`` 是 ``A257='项  目' | C257=G7-5!E8 | E257=G7-5!G8 | G257=G7-5!I8``、
  ``r258`` 是 ``C258/E258/G258='期末数'`` + ``D258/F258/H258='期初数'``，
  合并区 ``A257:B258`` / ``C257:D257`` / ``E257:F257`` / ``G257:H257`` ⇒
  **3 个被投资单位 × {期末数, 期初数} = 6 个数据列**（续表 ``r271/r272`` 同构，
  子列为 本期发生额 / 上期发生额）。合营表只 1 个主体是因为它引用 ``G7-5!C8``
  单列（``r229`` 合并区仅 ``C229:D229``），两张表**结构本就不同**，
  早期把合营表结论套到联营表，导致 seed 只有 3 列而运行时载荷是 7 列
  （`g7SoeDisclosureModel` 的 `associate-fs-company` / `associate-pl-company`
  槽位），seed 与推送两侧列数不一致。
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

# `row_type` 判据单一真源（kit 已把 backend/ 加进 sys.path）。
# 🔴 `……` 是源模板可扩位（零可见内容），禁硬编码 `row_type: "data"`，
# 否则与 `fix_note_expandable_rows.py` 互相翻转。
from app.services.note_expandable_markers import (  # noqa: E402
    row_type_for_label as _row_type_for_label,
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
# 🔴 标签列 key 统一为平台惯例 'label'（g7-column-alignment spec Task 5）：
# 平台 211 个标签列定义里 148 个用 'label'；本文件原用 'name'/'item'/'investee'/'seq'/'type'
# 等各表自拟 key，与运行时 buildG7*Columns() 的 'label' 不一致（B 类偏差）。
# is_label / label 显示文字均不动 —— 投影器 note_sub_table_projector._project_row 对
# 标签列有**双向兜底**（任意标签 key → 'label' 回填 / 反向回退），故改 key 零数据风险。
T0_COLUMNS = flat_columns([
    ("label", "项  目", None),
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
    ("label", "被投资单位"),
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
    data_row("一、合营企业"),
    data_row("……"),
    data_row("二、联营企业"),
    data_row("……"),
    total_row("合  计"),
]

# ═══════ T2 重要合营企业的主要财务信息（源 A229:C241，flat 3 列）═══════
# 🔴 国企侧本就比上市侧少两行（无「其中：少数股东权益」「归属于母公司的所有者权益」），
#    源模板逐字如此，不是欠账。

T2 = "重要合营企业的主要财务信息（划分为持有待售的除外）"
_FS_COLUMNS = flat_columns([
    ("label", "项 目", None), ("current", "期末数", AMOUNT), ("prior", "期初数", AMOUNT),
])
_JV_FS_LABELS = [
    "流动资产", "非流动资产", "资产合计", "流动负债", "非流动负债", "负债合计", "净资产",
    "按持股比例计算的净资产份额", "调整事项", "对合营企业权益投资的账面价值 ",
    "存在公开报价的权益投资的公允价值 ",
]

# ═══════ T3 续：重要合营企业本期及上期经营成果（源 A243:C251）═══════

T3 = "续：重要合营企业本期及上期经营成果"
_PL_COLUMNS = flat_columns([
    ("label", "项  目", None), ("current", "本期发生额", AMOUNT), ("prior", "上期发生额", AMOUNT),
])
_JV_PL_LABELS = [
    "营业收入", "财务费用", "所得税费用", "净利润", "其他综合收益",
    "综合收益总额", "企业本期收到的来自合营企业的股利",
]

# ═══════ T4 重要联营企业的主要财务信息（源 A257:H269，**3 主体两级 7 列**）═══════
# 源模板 R268 字面「对合营企业权益投资的账面价值」处于联营表内属笔误，
# 沿用附注模板已修正口径「对联营企业权益投资的账面价值」（design.md R5.6 留证）。
#
# 🔴 列结构**不同于合营表**（见模块 docstring 的 openpyxl 实证）：
#    3 个被投资单位（源模板引用 G7-5!E8 / G8 / I8 = 合营企业2 / 联营企业1 / 联营企业2）
#    × {期末数, 期初数}。第一槽名「合营企业2」是源模板 G7-5 列布局的忠实直译
#    —— G7-5 只有 4 个主体列（C8 合营企业1 / E8 合营企业2 / G8 联营企业1 / I8 联营企业2），
#    国企披露表的联营段从 E8 起取三列，把一个**合营**企业带进了联营表，属源模板缺陷；
#    运行时可由审计师改名（`entitySlots`），故此处只作 seed 骨架、不擅自改语义。
#
# 🔴 列 key 必须与运行时 `buildG7SlotColumns(ASSOCIATE_FS_SLOT, names, ASSOCIATE_FS_SUB)`
#    产出逐字一致（`{slot}_{seq}_{sub}`），否则推送后列对不上、已录数据落不到位。

T4 = "重要联营企业的主要财务信息"
_ASSOC_FS_SLOT = "associate-fs-company"
_ASSOC_PL_SLOT = "associate-pl-company"
#: 三个槽位的默认名（与 `g7SoeDisclosureModel.ASSOCIATE_*_SLOT_DEFAULT_NAMES` 同源）
_ASSOC_SLOT_NAMES = ("合营企业2", "联营企业1", "联营企业2")


def _assoc_columns(slot: str, current_label: str, prior_label: str) -> list[dict[str, Any]]:
    """3 主体 × {current, prior} 的两级列定义（key 与前端 slot 列生成器一致）。"""
    leaves: list[tuple[str, str, str | None, str | None]] = []
    for seq, entity in enumerate(_ASSOC_SLOT_NAMES, start=1):
        leaves.append((f"{slot}_{seq}_current", current_label, AMOUNT, entity))
        leaves.append((f"{slot}_{seq}_prior", prior_label, AMOUNT, entity))
    # 标签列头逐字取源 xlsx A257（两个空格），与 A229 合营表的「项 目」（一个空格）不同
    return grouped_columns(("label", "项  目"), leaves)


_ASSOC_FS_COLUMNS = _assoc_columns(_ASSOC_FS_SLOT, "期末数", "期初数")
_ASSOC_FS_LABELS = [
    "流动资产", "非流动资产", "资产合计", "流动负债", "非流动负债", "负债合计", "净资产",
    "按持股比例计算的净资产份额", "调整事项", "对联营企业权益投资的账面价值 ",
    "存在公开报价的权益投资的公允价值 ",
]

# ═══════ T5 续：重要联营企业本期及上期经营成果（源 A271:H277，**3 主体两级 7 列**）═══════

T5 = "续：重要联营企业本期及上期经营成果"
_ASSOC_PL_COLUMNS = _assoc_columns(_ASSOC_PL_SLOT, "本期发生额", "上期发生额")
_ASSOC_PL_LABELS = [
    "营业收入", "净利润", "其他综合收益", "综合收益总额", "企业本期收到的来自联营企业的股利",
]

# ═══════ T6 不重要合营企业和联营企业的汇总信息（源 A280:D292）═══════
# 结构已对，只补 columns

T6 = "不重要合营企业和联营企业的汇总信息"
T6_COLUMNS = flat_columns([
    ("label", "项  目", None), ("current", "本期数", AMOUNT), ("prior", "上期数", AMOUNT),
])
T6_LABELS = [
    "合营企业：", "投资账面价值合计", "下列各项按持股比例计算的合计数 ",
    "净利润", "其他综合收益", "综合收益总额",
    "联营企业：", "投资账面价值合计", "下列各项按持股比例计算的合计数 ",
    "净利润", "其他综合收益", "综合收益总额",
]

# ═══════ T7 ②对合营企业或联营企业发生超额亏损的分担额（源 A301:E312）═══════

T7 = "②对合营企业或联营企业发生超额亏损的分担额"
# 🔴 数据列 key 服从运行时（`g7SoeDisclosureModel` 的 `unrecognizedLossColumns`）：
# `g7UnrecognizedLossModel.ts` / `g7DisclosureCrossSheet.ts` 用 `priorCumulative` /
# `currentUnrecognized` / `closingCumulative` 字面量往 `row.values` 写跨表回填值
# （crossSheet L1620~L1622 + L2783~L2785 的 `columnKeys` 映射），改运行时会静默失效。
# 量化闸（Task 8）裁决 = SAFE_TO_RENAME_SEED（该表无一行用 seed key 落过非空值）。
T7_COLUMNS = flat_columns([
    ("label", "被投资单位名称", None),
    ("priorCumulative", "前期累积未确认的损失份额", AMOUNT),
    ("currentUnrecognized", "本期未确认的损失份额（或本期实现净利润的分享额）", AMOUNT),
    ("closingCumulative", "本期末累积未确认的损失份额", AMOUNT),
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
    ("label", "项目"),
    [
        # 🔴 数据列 key 服从运行时（`g7SoeDisclosureModel.sponsorInterestColumns`）：
        # 期末/期初用 `closing`/`opening` 前缀而非 `end`/`begin`。
        # 量化闸裁决 = SAFE_TO_RENAME_SEED（该表未推送过，0 行对象）。
        ("sponsorScale", "规模", None, "发起"),
        ("closingCarrying", "账面价值", AMOUNT, "期末数"),
        ("closingMaxLoss", "最大损失敞口", AMOUNT, "期末数"),
        ("openingCarrying", "账面价值", AMOUNT, "期初数"),
        ("openingMaxLoss", "最大损失敞口", AMOUNT, "期初数"),
        ("presentationItem", "列报项目", None, None),
    ],
)
T8_ROWS: list[dict[str, Any]] = [
    data_row("优先级债券"),
    data_row("次级债券"),
    data_row("信用违约互换（负债）"),
    data_row("……"),
]

# ═══════ T9 结构化主体获得收益及转移资产情况（源 A340:D345，两级）═══════
# 原表名是段落文本泄漏：'本公司发起多个结构化主体，但在结构化中均不持有权益。
# 2023年，本公司从发起的结构化主体获得收益的情况以及当期向结构化主体转移资产
# 的情况如下表所示：'

T9 = "结构化主体获得收益及转移资产情况"
_INCOME_GROUP = "当期从结构化主体获得的收益"
T9_COLUMNS = grouped_columns(
    # 🔴 标签列头取源 xlsx **纵向拆分两格的拼接值**：A340='结构化主体' + A341='类型'
    #    ⇒ '结构化主体类型'。改造前只写了下半格 '类型'，与运行时（已正确拼接）不一致，
    #    被 Task 12 扩容后的契约 P5（labelHeader ↔ seed headers[0]）抓出。
    #    这不是「转角标题」（那类是标签列两行各自标注表头行本身，源未给行标识列名）——
    #    本表两格合起来正是行标识列名，故 facts 判 kind='name'、逐字拼接可比。
    ("label", "结构化主体类型"),
    [
        # 🔴 `incomeTotal` → `total`：服从运行时（`sponsorIncomeColumns`）。
        # 量化闸裁决 = SAFE_TO_RENAME_SEED（该表未推送过，0 行对象）。
        ("serviceFee", "服务收费", AMOUNT, _INCOME_GROUP),
        ("assetSaleGain", "向结构化主体出售资产的利得（损失）", AMOUNT, _INCOME_GROUP),
        ("total", "合计", AMOUNT, _INCOME_GROUP),
        ("transferredAssets", "当期向结构化主体转移资产账面价值", AMOUNT, None),
    ],
)
T9_ROWS: list[dict[str, Any]] = [
    data_row("信用资产证券化"),
    data_row("投资基金"),
    data_row("……"),
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
    "重要联营企业的主要财务信息（源 A257:H269，两级表头）：项  目（标签列）+ "
    "3 个被投资单位 ×（期末数、期初数）。行口径与重要合营企业主要财务信息表一致，"
    "但列结构不同 —— 合营表只 1 个主体（源模板引用 G7-5!C8），"
    "联营表 3 个主体（引用 G7-5!E8/G8/I8）。被投资单位列可增删改名；"
    "源模板首列取自 G7-5!E8「合营企业2」属源模板缺陷，实际编制时应改为联营企业名。"
    "数据来源：被投资单位财务信息 G7-5，权益法调节项来自权益法测算表 G7-14。"
)
_G5 = (
    "续：重要联营企业本期及上期经营成果（源 A271:H277，两级表头）：项  目（标签列）+ "
    "3 个被投资单位 ×（本期发生额、上期发生额）。存在终止经营的净利润的，"
    "应在本表中单列项目披露。数据来源：被投资单位财务信息 G7-5。"
)
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
        rule(T4, _ASSOC_FS_COLUMNS, [data_row(x) for x in _ASSOC_FS_LABELS], _G4),
        rule(
            T5, _ASSOC_PL_COLUMNS, [data_row(x) for x in _ASSOC_PL_LABELS], _G5,
            aliases=["续："],
        ),
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
