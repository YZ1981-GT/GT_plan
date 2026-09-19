#!/usr/bin/env python
"""幂等脚本：G7 国企章 `七、合并范围的变化` 下 13 个 level-2 节结构对齐。

**现状**（postgres 实证 + JSON 文件）：13 个节里多数表名是表头首格泄漏
（`序号`/`公司名称`），全部 `columns=0`，多数 `rows=0`；另有一处命名漂移
（「本期出售的子公司**处置日**的经营成果」，源模板逐字为「**出售日**的经营成果」）。
两个纯文本节（子公司使用企业集团资产和清偿企业集团债务的重大限制 / 纳入合并财务
报表范围的结构化主体的相关信息）源模板本无表格，只补 `text_sections`。

Usage::

    python backend/scripts/fix/fix_note_g7_soe_scope_change_structure.py --dry-run
    python backend/scripts/fix/fix_note_g7_soe_scope_change_structure.py
    python backend/scripts/fix/fix_note_g7_soe_scope_change_structure.py --check

spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/ (Task 4.4)
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
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
SOE_PATH = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "fix_note_g7_soe_scope_change_structure"


def _blanks(n: int) -> list[dict[str, Any]]:
    return [data_row() for _ in range(n)]


def _numbered(n: int) -> list[dict[str, Any]]:
    """源模板序号列的占位行（1..n 编号，其余留空录入）。"""
    return [data_row(str(i)) for i in range(1, n + 1)]


# ═══════════════════════ 动态列槎位（与运行时同一真源） ═══════════════════════
#
# 🔴 槎位名与 key 拼接规则**逐字**取运行时
# `g7SoeDisclosureModel.ts` 的 `*_SLOT` 常量 + `g7SlotColumns.buildG7SlotColumns()`
# （`{slot}_{seq}` / `{slot}_{seq}_{subKey}`）。
#
# seed 侧原先写死序号前缀（`c1Current` / `aPrior` / `company1`），与动态列**不兼容**：
# 审计师增删被投资单位或改名后，写死序号无法跟随，seed 与运行时会永久错位。改为按
# 同一规则派生 ⇒ 两侧 key 恒等，且默认实体名只作占位（改名只动 `group` 显示，不动 key）。
MINORITY_FS_SLOT = "minority-fs-company"
MINORITY_FS_DEFAULT_NAMES = ["公司1", "公司2", "公司3", "公司4", "公司5"]
SOLD_FS_POSITION_SLOT = "sold-fs-position-company"
SOLD_FS_POSITION_DEFAULT_NAMES = ["公司1", "公司2"]
SOLD_FS_RESULT_SLOT = "sold-fs-result-company"
SOLD_FS_RESULT_DEFAULT_NAMES = ["A公司", "B公司", "C公司", "D公司", "E公司"]
OWNERSHIP_CHANGE_SLOT = "ownership-change-company"
OWNERSHIP_CHANGE_DEFAULT_NAMES = ["公司1", "公司2", "公司3"]


def _slot_matrix(
    slot: str,
    names: list[str],
    subs: list[tuple[str, str, str | None]],
) -> list[tuple[str, str, str | None, str]]:
    """按实体横向展开的矩阵列（`grouped_columns` 的数据列入参形态）。

    与运行时 `buildG7SlotColumns(slot, names, sub)` 同构：外层遍历实体（序号
    1-based），内层遍历子列，key = `{slot}_{seq}_{subKey}`，父分组名 = 实体名。
    """
    return [
        (f"{slot}_{seq}_{sub_key}", sub_label, fmt, name)
        for seq, name in enumerate(names, start=1)
        for sub_key, sub_label, fmt in subs
    ]


def _slot_flat(slot: str, names: list[str], fmt: str | None) -> list[tuple[str, str, str | None]]:
    """按实体横向展开的**单子列**形态（无 sub ⇒ key = `{slot}_{seq}`）。"""
    return [
        (f"{slot}_{seq}", name, fmt)
        for seq, name in enumerate(names, start=1)
    ]


# ═══ （一）本期纳入合并报表范围的子公司基本情况（源 A9:M19）═══
SEC_01 = "七、本期纳入合并报表"
T01 = "本期纳入合并报表范围的子公司基本情况"
# 🔴 标签列 key 统一为平台惯例 'label'（g7-column-alignment spec Task 5）：
# 平台 211 个标签列定义里 148 个用 'label'；本文件原用 'name'/'item'/'investee'/'seq'/'type'
# 等各表自拟 key，与运行时 buildG7*Columns() 的 'label' 不一致（B 类偏差）。
# is_label / label 显示文字均不动 —— 投影器 note_sub_table_projector._project_row 对
# 标签列有**双向兜底**（任意标签 key → 'label' 回填 / 反向回退），故改 key 零数据风险。
# 🔴 数据列 key 服从运行时（`subsidiaryBasicColumns`）：`registered`→`registeredPlace`
# / `region`→`principalPlace` / `nature`→`businessNature` / `paidRatio`→`paidInRatio`
# / `method`→`acquisitionMethod`。理由 = `g7DisclosureCrossSheet.ts` 用**字面量 key**
# 往 `row.values` 写跨表回填值，改运行时会静默失效；seed 侧无此类消费方。
# 量化闸裁决 = SAFE_TO_RENAME_SEED（1 个行对象、0 处用消失 key 落值）。
#
# 🔴 `name`（企业名称）**保留为数据列**：源 xlsx A9:M9 行标识列是「序号」而
# 「企业名称」是第 1 个数据列（共 12 个数据列）⇒ E 类裁决为「运行时缺列」，
# 由运行时补 `name` 列，不是 seed 删列。列序逐位对齐源 xlsx。
T01_COLUMNS = flat_columns([
    ("label", "序号", None), ("name", "企业名称", None), ("level", "级次", None),
    ("enterpriseType", "企业类型", None), ("registeredPlace", "注册地", None),
    ("principalPlace", "主要经营地", None), ("businessNature", "业务性质", None),
    ("paidInCapital", "实收资本", AMOUNT),
    ("subscribedRatio", "认缴持股比例（%）", PERCENT),
    ("paidInRatio", "实缴持股比例（%）", PERCENT),
    ("votingRights", "享有的表决权（%）", PERCENT),
    ("investmentAmount", "投资额", AMOUNT), ("acquisitionMethod", "取得方式", None),
])
T01_G = (
    "本期纳入合并报表范围的子公司基本情况（源 A9:M19）：大型企业集团可披露到二级"
    "子公司，重要子公司不分级次全部披露。企业类型：1.境内非金融子企业/2.境内金融"
    "子企业/3.境外子企业/4.事业单位/5.基建单位；取得方式：1.投资设立/2.同一控制下"
    "的企业合并/3.非同一控制下的企业合并/4.其他。持股比例不同于表决权比例的应说明"
    "表决权比例及差异原因；级次为在整个中央企业集团内的法人级次。"
    "数据来源：被投资单位基本信息 G7-4；投资额←明细表 G7-2。"
)

# ═══ （二）母公司拥有被投资单位表决权不足半数但能形成控制的原因（源 A25:H35）═══
SEC_02 = "七、母公司拥有被投资"
T02 = "母公司拥有被投资单位表决权不足半数但能对被投资单位形成控制的原因"
_CONTROL_EXCEPTION_COLS = [
    # 首元组是标签列 → key 统一为平台惯例 'label'（91% 占比，跨 70 文件）；
    # 显示文字仍是源 xlsx 的「序号」，不受影响。
    ("label", "序号", None), ("name", "企业名称", None),
    ("subscribedRatio", "认缴持股比例（%）", PERCENT), ("votingRights", "享有的表决权", PERCENT),
    ("registeredCapital", "注册资本", AMOUNT), ("investmentAmount", "投资额", AMOUNT),
    ("level", "级次", None),
]
T02_COLUMNS = flat_columns(_CONTROL_EXCEPTION_COLS + [("reason", "纳入合并范围原因", None)])
T02_G = (
    "母公司拥有被投资单位表决权不足半数但能对被投资单位形成控制的原因（源 A25:H35）。"
    "数据来源：G7-4 表决权≤50%但纳入合并的条件筛选。"
)

# ═══ （三）表决权过半但未形成控制的原因（源 A37:H52，按合营/联营/其他分组）═══
SEC_03 = "七、母公司直接或通过"
T03 = "母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的原因"
T03_COLUMNS = flat_columns(_CONTROL_EXCEPTION_COLS + [("reason", "未纳入合并范围原因", None)])
T03_ROWS: list[dict[str, Any]] = (
    [{"label": "合营企业", "row_type": "data"}] + _blanks(5)
    + [{"label": "联营企业", "row_type": "data"}] + _blanks(5)
    + [{"label": "其他（含共同经营等）", "row_type": "data"}] + _blanks(2)
)
T03_G = (
    "母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成"
    "控制的原因（源 A37:H52），按合营企业/联营企业/其他（含共同经营等）分组列示。"
    "数据来源：G7-4 表决权＞50%但未纳入合并的条件筛选。"
)

# ═══ （四）重要非全资子公司情况 ═══
SEC_04 = "七、重要非全资子公司"

# 1、少数股东（源 A55:F60）
T04A = "少数股东"
# 🔴 数据列 key 服从运行时（`minorityColumns`）：`minorityRatio`→`holdingRatio` /
# `minorityProfit`→`currentProfit` / `minorityDividend`→`dividend` /
# `minorityEquity`→`closingEquity`（`currentProfit`/`closingEquity` 被
# `g7DisclosureCrossSheet.ts` 字面量写值消费）。`name` 保留为数据列：源 xlsx
# A55:F55 行标识列是「序号」，「企业名称」是第 1 个数据列（共 5 个）。
T04A_COLUMNS = flat_columns([
    ("label", "序号", None), ("name", "企业名称", None),
    ("holdingRatio", "少数股东持股比例", PERCENT),
    ("currentProfit", "当期归属于少数股东的损益", AMOUNT),
    ("dividend", "当期向少数股东支付的股利", AMOUNT),
    ("closingEquity", "期末累计少数股东权益", AMOUNT),
])
T04A_G = "1、少数股东（源 A55:F60）：重要非全资子公司的少数股东持股比例及权益变动。"

# 2、主要财务信息（源 A62:L73，两级：项目 + 5 家子公司×期末数/本期发生额,期初数/上期发生额）
T04B = "主要财务信息"
_T04B_METRICS = [
    "流动资产", "非流动资产", "资产合计", "流动负债", "非流动负债", "负债合计",
    "营业收入", "净利润", "综合收益总额", "经营活动现金流量",
]
# 🔴 动态列 key 必须服从运行时的 `{slot}_{seq}_{subKey}` 形态（不得写死 `c1Current`）：
# 该表按「重要非全资子公司」横向展开，审计师可增删改名，写死序号后 seed key 无法跟随
# （改名即丢落点）。运行时真源 = `g7SoeDisclosureModel.MINORITY_FS_SLOT`
# + `buildG7SlotColumns()`（key = `${slot}_${seq}_${sub.key}`）。
T04B_COLUMNS = grouped_columns(
    ("label", "项  目"),
    _slot_matrix(
        MINORITY_FS_SLOT, MINORITY_FS_DEFAULT_NAMES,
        [("current", "期末数/本期发生额", AMOUNT), ("prior", "期初数/上期发生额", AMOUNT)],
    ),
)
T04B_G = (
    "2、主要财务信息（源 A62:L73）：按重要非全资子公司横向展开期末数/本期发生额、"
    "期初数/上期发生额对照。数据来源：被投资单位财务信息 G7-5。"
)

# ═══ （六）本期不再纳入合并范围的原子公司 ═══
SEC_05 = "七、本期不再纳入合并"

# (1) 原子公司的基本情况（源 A78:G83）
T05A = "原子公司的基本情况"
# 🔴 数据列 key 服从运行时（`formerSubsidiaryColumns`）：`registered`→`registeredPlace` /
# `nature`→`businessNature` / `votingRatio`→`votingRights`（三者均被
# `g7DisclosureCrossSheet.ts` 字面量写值消费）。`name` 保留为数据列：源 xlsx
# A78:G78 行标识列是「序号」，「企业名称」是第 1 个数据列（共 6 个）。
T05A_COLUMNS = flat_columns([
    ("label", "序号", None), ("name", "企业名称", None),
    ("registeredPlace", "注册地", None),
    ("businessNature", "业务性质", None), ("holdingRatio", "持股比例（%）", PERCENT),
    ("votingRights", "表决权比例（%）", PERCENT),
    ("reason", "本期不再成为子公司的原因", None),
])
T05A_G = "（1）原子公司的基本情况（源 A78:G83）。数据来源：处置子公司测试表 G7-11/12。"

# (2) 本期出售的子公司出售日的财务状况（源 A87:F96，两家公司×出售日,期初余额）
T05B = "本期出售的子公司出售日的财务状况"
# 🔴 动态列：key 服从运行时 `SOLD_FS_POSITION_SLOT` + `buildG7SlotColumns()`。
# 注意 `saleDate` 子列是**文本**（出售日日期），不是金额 ⇒ fmt 传 None。
T05B_COLUMNS = grouped_columns(
    ("label", "项目"),
    _slot_matrix(
        SOLD_FS_POSITION_SLOT, SOLD_FS_POSITION_DEFAULT_NAMES,
        [("saleDate", "出售日", None), ("opening", "期初余额", AMOUNT)],
    ),
)
T05B_LABELS = [
    "流动资产", "长期股权投资", "固定资产", "无形资产", "其他非流动资产",
    "流动负债", "非流动负债", "所有者权益",
]
T05B_G = (
    "（2）本期出售的子公司出售日的财务状况（源 A87:F96）。数据来源："
    "处置子公司测试表 G7-11/12。"
)

# (3) 本期出售的子公司出售日的经营成果（源 A98:L106，5家公司×本年年初-出售日,上年发生额）
# 🔴 源模板逐字为「出售日」，模板 JSON 曾漂移写成「处置日」，本脚本正名。
T05C = "本期出售的子公司出售日的经营成果"
# 🔴 动态列：key 服从运行时 `SOLD_FS_RESULT_SLOT` + `buildG7SlotColumns()`。
# seed 原用字母序前缀（`aCurrent`/`bPrior`…），与动态列不兼容。
T05C_COLUMNS = grouped_columns(
    ("label", "项目"),
    _slot_matrix(
        SOLD_FS_RESULT_SLOT, SOLD_FS_RESULT_DEFAULT_NAMES,
        [("current", "本年年初-出售日", AMOUNT), ("prior", "上年发生额", AMOUNT)],
    ),
)
T05C_LABELS = ["营业收入", "营业成本", "期间费用", "营业利润", "利润总额", "所得税费用", "净利润"]
T05C_G = (
    "（3）本期出售的子公司出售日的经营成果（源 A98:L106）。若本期因处置部分股权投资"
    "或其他原因丧失控制权的，还应按《企业会计准则解释第4号》披露处置后剩余股权在"
    "丧失控制权日的公允价值及重新计量利得或损失。数据来源：处置子公司测试表 G7-11/12。"
)

# ═══ （七）本期新纳入合并范围的主体（源 A109:D119）═══
SEC_06 = "七、本期新纳入合并范"
T06 = "本期新纳入合并范围的主体"
T06_COLUMNS = flat_columns([
    ("label", "公司名称", None),
    ("closingNetAssets", "期末净资产", AMOUNT),
    ("currentNetProfit", "本期净利润", AMOUNT),
])
T06_G = "本期新纳入合并范围的主体（源 A109:D119）。数据来源：G7-4「本期新增=是」筛选。"

# ═══ （八）本期发生的同一控制下企业合并情况（源 A122:J126）═══
SEC_07 = "七、本期发生的同一控"
T07 = "本期发生的同一控制下企业合并情况"
_YEAR_START_GROUP = "本年初至合并日的相关情况"
T07_COLUMNS = grouped_columns(
    ("label", "公司名称"),
    [
        ("consolidationDate", "合并日", None, None),
        ("bookNetAssets", "账面净资产", AMOUNT, None),
        ("consideration", "交易对价", AMOUNT, None),
        # 🔴 key 服从运行时（`commonControlColumns` 的 `ultimateController`）：
        # `g7DisclosureCrossSheet.ts` 用字面量 `writeValue(row.values, 'ultimateController', …)`
        # 从合并范围底稿回填最终控制人，改运行时会让该回填静默失效。
        ("ultimateController", "实际控制人", None, None),
        ("revenue", "收入", AMOUNT, _YEAR_START_GROUP),
        ("netProfit", "净利润", AMOUNT, _YEAR_START_GROUP),
        ("cashIncrease", "现金净增加额", AMOUNT, _YEAR_START_GROUP),
        ("operatingCashFlow", "经营活动现金流量净额", AMOUNT, _YEAR_START_GROUP),
    ],
)
T07_G = (
    "本期发生的同一控制下企业合并情况（源 A122:J126）：说明合并日的确定依据、支付的"
    "对价及被合并方的账面净资产，并披露被合并方自合并当年年初至合并日的收入、净利润、"
    "现金流量等情况。"
)

# ═══ （九）本期发生的非同一控制下企业合并情况（源 A129:M134，购买日被购买方三级压平）═══
SEC_08 = "七、本期发生的非同一"
T08 = "本期发生的非同一控制下企业合并情况"
_PURCHASE_DAY_GROUP = "购买日被购买方"
T08_COLUMNS = grouped_columns(
    ("label", "被购买方名称"),
    [
        ("purchaseDate", "购买日", None, None),
        ("purchaseDateBasis", "购买日的确定依据", None, None),
        # 🔴 4 处数据列 key 服从运行时（`nonCommonControlColumns`）：
        # `preHoldingRatio`→`preHolding` / `atCombinationHoldingRatio`→`atCombinationHolding`
        # / `fvIdentifiableAmount`→`fvIdentifiable` / `fvIdentifiableMethod`→`fvMethod`。
        # 四者**全部**被 `g7DisclosureCrossSheet.ts` 以字面量 key 往 `row.values` 写值
        # （L2140~L2143），改运行时侧会让 G7-11/12 处置测试表到附注的跨表回填静默失效；
        # seed 侧无同类消费方 ⇒ seed 服从运行时。
        ("preHolding", "购买日前持有被购买方权益比例", PERCENT, None),
        (
            "atCombinationHolding",
            "形成合并时持有的被购买方权益比例（不含合并后的股权增减）",
            PERCENT, None,
        ),
        ("bookNetAssets", "账面净资产总额", AMOUNT, _PURCHASE_DAY_GROUP),
        # 源模板此处「可辨认净资产公允价值总额」下再分「金额/确定方法」两个三级子列；
        # group 只支持单级（禁 '/'），故把二级子标题并入叶子列名。
        ("fvIdentifiable", "可辨认净资产公允价值总额（金额）", AMOUNT, _PURCHASE_DAY_GROUP),
        ("fvMethod", "可辨认净资产公允价值总额（确定方法）", None, _PURCHASE_DAY_GROUP),
        ("consideration", "交易对价", AMOUNT, None),
        ("goodwill", "形成商誉", AMOUNT, None),
        ("postRevenue", "购买日至期末被购买方的收入", AMOUNT, None),
        ("postProfit", "购买日至期末被购买方的净利润", AMOUNT, None),
        ("postCashFlow", "购买日至期末被购买方的现金流量", AMOUNT, None),
    ],
)
T08_G = (
    "本期发生的非同一控制下企业合并情况（源 A129:M134）：说明购买日或出售日的确定"
    "方法、合并日相关交易公允价值的确定方法、商誉的金额及其计算方法。购买日前后持有"
    "权益比例、或有对价安排及变动、业绩承诺对商誉减值测试的影响、分步实现企业合并的"
    "分别说明前期和本期取得股权的时点/成本/比例/方式。"
)

# ═══ （十）本期发生的吸收合并（源 A139:F172，两级：并入的主要资产/负债 各{项目,金额}）═══
SEC_09 = "七、本期发生的吸收合"
T09 = "本期发生的吸收合并"
T09_COLUMNS = grouped_columns(
    ("label", "吸收合并的类型"),
    [
        ("assetItem", "项目", None, "并入的主要资产"),
        ("assetAmount", "金额", AMOUNT, "并入的主要资产"),
        ("liabilityItem", "项目", None, "并入的主要负债"),
        ("liabilityAmount", "金额", AMOUNT, "并入的主要负债"),
    ],
)
T09_ROWS: list[dict[str, Any]] = (
    [{"label": "同一控制下吸收合并", "row_type": "data"}] + _blanks(5)
    + [{"label": "非同一控制下吸收合并", "row_type": "data"}] + _blanks(5)
)
T09_G = (
    "本期发生的吸收合并（源 A139:F172）：应分别同一控制下和非同一控制下的吸收合并，"
    "披露并入的主要资产、负债项目及其金额。"
)

# ═══ （十一）子公司使用企业集团资产和清偿企业集团债务的重大限制（源 A173:F176，纯文本）═══
SEC_10 = "七、子公司使用企业集"
SEC_10_TEXT = [
    "说明：（1）限制内容，包括对母公司或子公司与集团内其他主体相互转移现金或其他"
    "资产的限制，以及对集团内主体之间发放股利或进行利润分配、发放或收回贷款或垫款"
    "等的限制；（2）子公司少数股东享有保护性权利，并且该保护性权利对使用集团资产"
    "或清偿集团负债的能力存在重大限制的，披露限制的性质和程度；（3）限制涉及的资产"
    "和负债在合并财务报表中的金额。",
]

# ═══ （十二）纳入合并财务报表范围的结构化主体的相关信息（源 A177:A182，纯文本）═══
SEC_11 = "七、纳入合并财务报表"
SEC_11_TEXT = [
    "说明：应披露与结构化主体相关的风险信息，向结构化主体提供财务支持或其他支持，"
    "包括帮助结构化主体取得财务支持：（1）有合同约定的，披露财务支持的合同条款包括"
    "可能导致企业承担损失的事项或情况；（2）在没有合同约定的情况下，披露所提供支持"
    "的类型、金额及原因，包括帮助该结构化主体获得财务支持的情况，其中本期对以前"
    "未纳入合并财务报表范围的结构化主体提供了财务支持或其他支持并且该支持导致控制"
    "了该结构化主体的，披露决定提供支持的相关因素；（3）存在提供支持意图的，"
    "披露该意图，包括帮助该结构化主体获得财务支持的意图。",
]

# ═══ （十三）母公司在子公司的所有者权益份额发生变化的情况（源 A184:E199）═══
SEC_12 = "七、母公司在子公司的"
T12 = "母公司在子公司的所有者权益份额发生变化的情况"
# 🔴 动态列（按子公司横向展开）：key 取运行时 `OWNERSHIP_CHANGE_SLOT` 的
# `{slot}_{seq}` 形态，禁写死 `company1..3`（源模板默认名只作占位，审计师改名
# 只动显示不动 key）。本表无子列 ⇒ 每实体 1 列。
T12_COLUMNS = flat_columns(
    [("label", "项  目", None)]
    + [
        (f"{OWNERSHIP_CHANGE_SLOT}_{seq}", name, AMOUNT)
        for seq, name in enumerate(OWNERSHIP_CHANGE_DEFAULT_NAMES, start=1)
    ]
)
T12_LABELS = [
    "购买成本/处置对价：", "现金", "非现金资产的公允价值", "发行或承担的债务的账面价值",
    "发行的权益性证券的面值", "或有对价", "购买成本/处置对价合计",
    "减：按取得/处置的股权比例计算的子公司净资产份额", "差额",
    "其中：调整资本公积", "调整盈余公积", "调整未分配利润",
]
T12_G = (
    "（2）交易对于少数股东权益及归属于母公司所有者权益的影响（源 A187:E199）。"
    "（1）在子公司所有者权益份额发生变化的情况说明见 text_sections（源 A184:A185，"
    "R185 为示例文字，正式披露请改写为项目实际内容）。数据来源：处置子公司测试表 G7-10。"
)
SEC_12_TEXT = [
    "（1）在子公司所有者权益份额发生变化的情况说明：说明未丧失控制权的股权变动"
    "交易背景、股权比例变化、交易对价，以及对少数股东权益、资本公积的影响。",
]

# ═══ （十四？）子公司向母公司转移资金的能力受到严格限制的情况（纯文本，
#     源 xlsx 该 sheet 无独立对应区块——与（十一）重大限制条款为同族通用条款，
#     md 重建拆成了两个 level-2 节；不杜撰表格，只补通用说明段）═══
SEC_13 = "七、子公司向母公司转"
SEC_13_TEXT = [
    "说明子公司向母公司转移资金（如现金分红、贷款或垫款偿还）的能力是否受到严格"
    "限制，包括限制的性质、程度及触发条件；不存在限制的应说明「不适用」。",
]


def _plan() -> dict[str, tuple[str, list[dict[str, Any]], list[str], list[str] | None]]:
    """按章节号分组：{section_number: (label, plan, expected_table_names, text_sections)}"""
    return {
        SEC_01: ("本期纳入合并报表范围的子公司基本情况", [
            rule(T01, T01_COLUMNS, _numbered(10), T01_G),
        ], [T01], None),
        SEC_02: ("母公司拥有被投资单位表决权不足半数但能形成控制的原因", [
            rule(T02, T02_COLUMNS, _numbered(10), T02_G, aliases=["序号"]),
        ], [T02], None),
        SEC_03: ("母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能形成控制的原因", [
            rule(T03, T03_COLUMNS, T03_ROWS, T03_G, aliases=["序号"]),
        ], [T03], None),
        SEC_04: ("重要非全资子公司情况", [
            rule(T04A, T04A_COLUMNS, _numbered(5), T04A_G),
            rule(T04B, T04B_COLUMNS, [data_row(x) for x in _T04B_METRICS], T04B_G),
        ], [T04A, T04B], None),
        SEC_05: ("本期不再纳入合并范围的原子公司", [
            rule(T05A, T05A_COLUMNS, _numbered(5), T05A_G),
            rule(T05B, T05B_COLUMNS, [data_row(x) for x in T05B_LABELS], T05B_G),
            rule(
                T05C, T05C_COLUMNS, [data_row(x) for x in T05C_LABELS], T05C_G,
                aliases=["本期出售的子公司处置日的经营成果"],
            ),
        ], [T05A, T05B, T05C], None),
        SEC_06: ("本期新纳入合并范围的主体", [
            rule(T06, T06_COLUMNS, _numbered(10), T06_G, aliases=["公司名称"]),
        ], [T06], None),
        SEC_07: ("本期发生的同一控制下企业合并情况", [
            rule(T07, T07_COLUMNS, _blanks(3), T07_G, aliases=["公司名称"]),
        ], [T07], None),
        SEC_08: ("本期发生的非同一控制下企业合并情况", [
            rule(T08, T08_COLUMNS, _blanks(3), T08_G),
        ], [T08], None),
        SEC_09: ("本期发生的吸收合并", [
            rule(T09, T09_COLUMNS, T09_ROWS, T09_G, aliases=["吸收合并的类型"], insert=True),
        ], [T09], None),
        SEC_10: ("子公司使用企业集团资产和清偿企业集团债务的重大限制", [], [], SEC_10_TEXT),
        SEC_11: ("纳入合并财务报表范围的结构化主体的相关信息", [], [], SEC_11_TEXT),
        SEC_12: ("母公司在子公司的所有者权益份额发生变化的情况", [
            rule(T12, T12_COLUMNS, [data_row(x) for x in T12_LABELS], T12_G),
        ], [T12], SEC_12_TEXT),
        SEC_13: ("子公司向母公司转移资金的能力受到严格限制的情况", [], [], SEC_13_TEXT),
    }


def _runner(key: str, dry_run: bool, check: bool):
    plan_map = _plan()
    label, plan, expected, req_text = plan_map[key]
    return run_section(
        SOE_PATH,
        key,
        plan,
        expected,
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        require_text_sections=req_text,
    )


_LABELS = {k: f"note_template_soe.json §{k} {v[0]}" for k, v in _plan().items()}

main = build_cli(
    "附注 G7「合并范围的变化」13 个节结构对齐（幂等，仅国企）",
    _runner,
    _LABELS,
)

if __name__ == "__main__":
    raise SystemExit(main())
