#!/usr/bin/env python
"""附注 D 类剩余四循环披露章节结构对齐源模板（幂等修订）。

覆盖章节（D1 / D2 已由前序 spec 收口，D4 另立）：

| 循环 | 上市 | 国企 | 源 xlsx |
|------|------|------|---------|
| D3 预收款项 | 五、38 | 八、38 | ``D3 预收账款.xlsx`` |
| D5 应收款项融资 | 五、6 | 八、6 | ``D5 应收款项融资.xlsx`` |
| D6 合同资产 | 五、10 | 八、11 | ``D6 合同资产.xlsx`` |
| D7 合同负债 | 五、39 | 八、39 | ``D7 合同负债.xlsx`` |

`diagnose_disclosure_sheet_vs_template.py` 跑出的欠账（2026-07-30）：

- **8 个章节 27 张表全部 `columns` 未表态 + 全部无 `guidance`**
  → seed 路径被 `_infer_groups_from_headers` 按前缀反猜父表头；TAB 无编制提示
- D5 上市「背书或贴现」两列共前缀「期末」→ 未表态时**必然**被猜出凭空「期末」父表头
- D5 上市「减值准备情况」模板只剩 1 列（标签列被 md 重建脚本吃掉）
- D6 上市 9 张表里 5 张是垃圾：`续：` / 空名 / `项  目`（表头首格泄漏）/
  `按单项计提减值准备：`（尾冒号）；两版主表的两级表头被压扁成 3 列
- D7 国企第 2 表名是占位 `合同负债（表2）`

**权威源**：``backend/wp_templates/D/*.xlsx``（运行时权威目录）的两个披露 sheet，
openpyxl 逐格 + 合并区读出（`基础数据/` 目录在本仓库不存在，不作裁决）。

裁决要点：

- 🔴 平台附注只支持**两级**表头。D6 上市「（2）合同资产减值准备计提情况」源模板是
  **三级**（期末余额 > 账面余额·减值准备 > 金额·比例）→ 按 D1 国企分类表既定范式，
  顶层期间提到**表名**里（`（期末余额）` / `（续：上年年末余额）`），只留下两级。
  这同时消掉「同一分组内两个『金额』列名重复」的冲突。
- **同表并列双期 → `group`；期间已在表名中 → `flat`**（单组跨全部数据列不携带信息）。
- 源模板方括号（D5 `[本期转销]` `[其他]`）是「可选项」编辑标记，非内容 → 行名去括号，
  可选语义写进 `guidance`。
- 源模板「……组合」「可无限量添加行」是占位说明 → 落成**空白录入行**，不落行名。

Usage::

    python backend/scripts/fix/fix_note_d_cycle_rest_structure.py --dry-run
    python backend/scripts/fix/fix_note_d_cycle_rest_structure.py
    python backend/scripts/fix/fix_note_d_cycle_rest_structure.py --check
    python backend/scripts/fix/fix_note_d_cycle_rest_structure.py --only d6-listed

spec: .kiro/specs/d-cycle-remaining-disclosure-alignment/ Task 1
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    PERCENT,
    TEXT,
    blanks_then_total,
    build_cli,
    data_row,
    flat_columns,
    grouped_columns,
    labels_then_total,
    rule,
    run_section,
    subtotal_row,
    total_row,
    two_period_columns,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "d-cycle-remaining-disclosure-alignment"

TEMPLATE_PATH = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}

# 三列同构的「账面余额 / 减值准备 / 账面价值」子列（D6 主表两版共用）
_BOOK_SUBS = [
    ("book_balance", "账面余额", AMOUNT),
    ("impairment", "减值准备", AMOUNT),
    ("book_value", "账面价值", AMOUNT),
]


# ─────────────────────────── D3 预收款项 ───────────────────────────

def _d3_listed_plan() -> list[dict[str, Any]]:
    return [
        rule(
            "预收款项",
            flat_columns([
                ("label", "项 目", None),
                ("end_amount", "期末余额", AMOUNT),
                ("prior_amount", "上年年末余额", AMOUNT),
            ]),
            blanks_then_total(6, "合 计"),
            "项目行取自审定表 D3-1（源模板 A7:A12 为审定表引用，可增删行）；"
            "合计 = 各项目之和。",
        ),
        rule(
            "账龄超过1年的重要预收款项",
            flat_columns([
                ("label", "项目", None),
                ("end_amount", "期末余额", AMOUNT),
                ("reason", "未偿还或未结转的原因", TEXT),
            ]),
            blanks_then_total(3, "合 计"),
            "取自「账龄1年以上的预收账款检查表 D3-5」；须逐项说明未偿还或未结转的原因。",
        ),
        rule(
            "本期预收账款账面价值的重大变动",
            flat_columns([
                ("label", "项目", None),
                ("change_amount", "变动金额", AMOUNT),
                ("reason", "变动原因", TEXT),
            ]),
            blanks_then_total(3, "合 计"),
            "取自「账龄1年以上的预收账款检查表 D3-5」；仅列示重大变动项目并说明原因。",
        ),
    ]


def _d3_soe_plan() -> list[dict[str, Any]]:
    return [
        rule(
            "预收款项",
            flat_columns([
                ("label", "账  龄", None),
                ("end_amount", "期末余额", AMOUNT),
                ("prior_amount", "期初余额", AMOUNT),
            ]),
            labels_then_total(["1年以内（含1年）", "1年以上"], "合  计"),
            "国企版按账龄两档列示（源模板 A7:A8）；1年以上 = 审定表 D3-1 合计 − 1年以内。",
        ),
        rule(
            "账龄超过1年的重要预收账款",
            flat_columns([
                ("label", "债权单位名称", None),
                ("end_amount", "期末余额", AMOUNT),
                ("reason", "未偿还原因", TEXT),
            ]),
            blanks_then_total(3, "合计"),
            "取自「账龄1年以上的预收账款检查表 D3-5」；逐户列示并说明未偿还原因。",
            aliases=["账龄超过1年的重要预收款项"],
        ),
    ]


# ───────────────────────── D5 应收款项融资 ─────────────────────────

_D5_LISTED_GUIDANCE_MAIN = (
    "提示：「应收款项融资」反映资产负债表日以公允价值计量且其变动计入其他综合收益的"
    "应收票据和应收账款等；披露应参考应收账款和应收票据的相关披露内容。"
    "勾稽：应收票据票面金额或应收账款余额 − 公允价值变动 = 期末公允价值。"
)


def _d5_listed_plan() -> list[dict[str, Any]]:
    return [
        rule(
            "应收款项融资",
            flat_columns([
                ("label", "项  目", None),
                ("end_amount", "期末余额", AMOUNT),
                ("prior_amount", "上年年末余额", AMOUNT),
            ]),
            [
                data_row("应收票据"),
                data_row("应收账款"),
                subtotal_row("小  计"),
                data_row("减：其他综合收益-公允价值变动"),
                total_row("期末公允价值"),
            ],
            _D5_LISTED_GUIDANCE_MAIN,
        ),
        rule(
            "本期计提、收回或转回的减值准备情况",
            flat_columns([
                ("label", "项目", None),
                ("amount", "减值准备金额", AMOUNT),
            ]),
            [
                data_row("上年年末余额"),
                data_row("本期计提"),
                data_row("本期收回或转回"),
                data_row("本期核销"),
                data_row("本期转销"),
                data_row("其他"),
                total_row("期末余额"),
            ],
            "提示：若涉及应收账款，本期计提、收回或转回的减值准备情况参考应收账款（2）（3）披露。"
            "源模板中「本期转销」「其他」为可选行（方括号标示），无发生额可删。"
            "勾稽：期末余额 = 上年年末余额 + 本期计提 − 本期收回或转回 − 本期核销 − 本期转销 − 其他。",
        ),
        rule(
            "期末本公司已质押的应收票据",
            flat_columns([
                ("label", "种  类", None),
                ("pledged_amount", "期末已质押金额", AMOUNT),
            ]),
            labels_then_total(["银行承兑票据", "商业承兑票据"], "合  计"),
            "可添加行项目。质押票据金额应与 D5 底稿质押检查一致。",
        ),
        rule(
            "期末本公司已背书或贴现但尚未到期的应收票据",
            flat_columns([
                ("label", "种  类", None),
                ("derecognized", "期末终止确认金额", AMOUNT),
                ("not_derecognized", "期末未终止确认金额", AMOUNT),
            ]),
            labels_then_total(["银行承兑票据", "商业承兑票据"], "合  计"),
            "按《企业会计准则第23号——金融资产转移》判断是否终止确认，并列示终止确认金额"
            "及与终止确认相关的利得和损失。证监会《2014年上市公司年报会计监管报告》要求"
            "对已背书或贴现且尚未到期的银行承兑汇票终止确认后，补充披露被追索时可能存在的支付风险。",
        ),
    ]


def _d5_soe_plan() -> list[dict[str, Any]]:
    return [
        rule(
            "应收款项融资",
            flat_columns([
                ("label", "项  目", None),
                ("end_amount", "期末余额", AMOUNT),
                ("prior_amount", "期初余额", AMOUNT),
            ]),
            labels_then_total(["应收票据", "应收账款"], "合  计"),
            "提示：1、应收账款的减值准备计提与核销情况参考附注八、5、（3）（4）披露；"
            "2、应收票据的期末质押、背书或贴现且资产负债表日尚未到期、出票人未履约、"
            "坏账准备计提情况参考附注八、4、（2）（3）（4）（5）（6）披露。",
            aliases=["应收款项融资"],
        ),
    ]


# ─────────────────────────── D7 合同负债 ───────────────────────────

_D7_NET_GUIDANCE = (
    "提示：同一合同下的合同资产和合同负债应当以净额在资产负债表列示。净额为贷方余额的，"
    "应当根据其流动性在「合同负债」或「其他非流动负债」项目中列示，其中预计自资产负债表日起"
    "一年内到期的应在「合同负债」项目列示，不应在「一年内到期的非流动负债」项目列示。"
)


def _d7_listed_plan() -> list[dict[str, Any]]:
    return [
        rule(
            "合同负债",
            flat_columns([
                ("label", "项  目", None),
                ("end_amount", "期末余额", AMOUNT),
                ("prior_amount", "上年年末余额", AMOUNT),
            ]),
            [
                *[data_row() for _ in range(6)],
                data_row("减：计入其他非流动负债的合同负债"),
                total_row("合  计"),
            ],
            _D7_NET_GUIDANCE + " 项目行取自审定表 D7-1。",
        ),
        rule(
            "账龄超过1年的重要合同负债",
            flat_columns([
                ("label", "项  目", None),
                ("end_amount", "期末余额", AMOUNT),
                ("reason", "未偿还或未结转的原因", TEXT),
            ]),
            blanks_then_total(4, "合  计"),
            "逐项列示账龄超过 1 年的重要合同负债并说明未偿还或未结转的原因。",
        ),
        rule(
            "本期合同负债账面价值的重大变动",
            flat_columns([
                ("label", "项  目", None),
                ("change_amount", "变动金额", AMOUNT),
                ("reason", "变动原因", TEXT),
            ]),
            blanks_then_total(4, "合  计"),
            "重大变动情形包括：①企业合并导致的变动；②对收入进行累积追加调整导致的变动；"
            "③履行履约义务（即从合同负债转为收入）的时间安排发生变化。",
        ),
    ]


def _d7_soe_plan() -> list[dict[str, Any]]:
    return [
        rule(
            "合同负债",
            flat_columns([
                ("label", "项  目", None),
                ("end_amount", "期末余额", AMOUNT),
                ("prior_amount", "期初余额", AMOUNT),
            ]),
            blanks_then_total(6, "合  计"),
            "项目行取自审定表 D7-1。" + _D7_NET_GUIDANCE,
        ),
        rule(
            "本期合同负债账面价值的重大变动",
            flat_columns([
                ("label", "项  目", None),
                ("change_amount", "变动金额", AMOUNT),
                ("reason", "变动原因", TEXT),
            ]),
            blanks_then_total(3, "合  计"),
            "重大变动情形包括：①企业合并导致的变动；②对收入进行累积追加调整导致的变动；"
            "③履行履约义务的时间安排发生变化。",
            aliases=["合同负债（表2）"],
        ),
    ]


# ─────────────────────────── D6 合同资产 ───────────────────────────

_D6_NET_GUIDANCE = (
    "提示：同一合同下的合同资产和合同负债应当以净额在资产负债表列示。净额为借方余额的，"
    "应当根据其流动性在「合同资产」或「其他非流动资产」项目中列示，其中预计自资产负债表日起"
    "一年内变现的应在「合同资产」项目列示，不应在「一年内到期的非流动资产」项目列示。"
)

_D6_MAJOR_CHANGE_GUIDANCE = (
    "重大变动情形包括：①企业合并导致的变动；②对收入进行累积追加调整导致的相关合同资产和"
    "合同负债的变动（可能源于估计履约进度、估计交易价格的变化或合同变更）；"
    "③对合同对价的权利成为无条件权利（即合同资产重分类为应收款项）的时间安排发生变化。"
)

# 组合计提明细的双期子列（源 B69:D69「期末余额」/ E69:G69「上年年末余额」）
_D6_GROUP_SUBS = [
    ("balance", "合同资产", AMOUNT),
    ("provision", "坏账准备", AMOUNT),
    ("loss_rate", "预期信用损失率(%)", PERCENT),
]

# 按单项计提明细（期间在表名中 → flat）
_D6_SINGLE_PAIRS = [
    ("label", "名 称", None),
    ("balance", "账面余额", AMOUNT),
    ("provision", "坏账准备", AMOUNT),
    ("loss_rate", "预期信用损失率(%)", PERCENT),
    ("reason", "计提理由", TEXT),
]


def _d6_impairment_columns() -> list[dict[str, Any]]:
    """减值准备计提情况（单期）：源模板三级 → 顶层期间提到表名，只留下两级。

    源 B44:C44「账面余额」{金额, 比例(%)} / D44:E44「减值准备」{金额, 预期信用损失率(%)} /
    F44:F45「账面价值」（rowspan=2 独立列）。
    """
    return grouped_columns(
        ("label", "类别"),
        [
            ("balance_amount", "金额", AMOUNT, "账面余额"),
            ("balance_ratio", "比例(%)", PERCENT, "账面余额"),
            ("provision_amount", "金额", AMOUNT, "减值准备"),
            ("provision_loss_rate", "预期信用损失率(%)", PERCENT, "减值准备"),
            ("book_value", "账面价值", AMOUNT, None),
        ],
    )


def _d6_impairment_rows() -> list[dict[str, Any]]:
    """源 A46-A54：单项计提 + 其中：3 明细 / 组合计提 + 其中：3 明细 / 合 计。

    「其中：」是结构标签行，其下 2 行为空白录入行（占位说明不落行名）。
    """
    return [
        data_row("按单项计提坏账准备"),
        data_row("其中："),
        data_row(),
        data_row(),
        data_row("按组合计提坏账准备"),
        data_row("其中："),
        data_row(),
        data_row(),
        total_row("合 计"),
    ]


def _d6_listed_plan() -> list[dict[str, Any]]:
    return [
        rule(
            "合同资产",
            two_period_columns(("label", "项  目"), ("期末余额", "上年年末余额"), _BOOK_SUBS),
            [
                data_row("单项计提坏账准备"),
                data_row("按组合计提坏账准备"),
                data_row("其中：业务类型组合"),
                data_row("客户类型组合"),
                data_row(),
                subtotal_row("小  计"),
                data_row("减：列示于其他非流动资产的合同资产"),
                total_row("合  计"),
            ],
            _D6_NET_GUIDANCE
            + " 账面价值 = 账面余额 − 减值准备；数据取自审定表 D6-1。"
            "源模板另提供简化披露格式（合同资产 / 减：合同资产减值准备 / 小计 / "
            "减：列示于其他非流动资产的合同资产 / 合计），二者择一。",
        ),
        rule(
            "本期合同资产账面价值的重大变动",
            flat_columns([
                ("label", "项  目", None),
                ("change_amount", "变动金额", AMOUNT),
                ("reason", "变动原因", TEXT),
            ]),
            blanks_then_total(6, "合  计"),
            _D6_MAJOR_CHANGE_GUIDANCE,
        ),
        rule(
            "合同资产减值准备计提情况（期末余额）",
            _d6_impairment_columns(),
            _d6_impairment_rows(),
            "源模板为三级表头（期末余额 > 账面余额·减值准备 > 金额·比例），"
            "平台附注只支持两级 → 顶层期间提到表名，上年年末余额另表列示。"
            "比例(%) = 该类账面余额 ÷ 账面余额合计；预期信用损失率(%) = 减值准备 ÷ 账面余额。",
            aliases=["合同资产减值准备计提情况"],
        ),
        rule(
            "合同资产减值准备计提情况（续：上年年末余额）",
            _d6_impairment_columns(),
            _d6_impairment_rows(),
            "上年年末余额段（源模板 G43:K45），列结构与期末段同构，供比较期披露。",
            insert=True,
        ),
        rule(
            "按单项计提减值准备（期末余额）",
            flat_columns(_D6_SINGLE_PAIRS),
            blanks_then_total(2, "合  计"),
            "逐项列示单项计提减值准备的合同资产（源模板 A55-A60，可添加行）；"
            "预期信用损失率(%) = 坏账准备 ÷ 账面余额；须填写计提理由。",
            aliases=["按单项计提减值准备：", "按单项计提减值准备"],
        ),
        rule(
            "按单项计提减值准备（续：上年年末余额）",
            flat_columns(_D6_SINGLE_PAIRS),
            blanks_then_total(2, "合  计"),
            "上年年末余额段（源模板 A61「续：」A62-A66），列结构与期末段同构。",
            aliases=["续："],
        ),
        rule(
            "组合计提项目：工程施工",
            two_period_columns(
                ("label", "账  龄"), ("期末余额", "上年年末余额"), _D6_GROUP_SUBS
            ),
            [
                data_row("1年以内"),
                data_row("1至2年"),
                data_row("2至3年"),
                data_row(),
                total_row("合  计"),
            ],
            "组合名与账龄档位按项目实际情况调整（源模板 A71-A74 为示例，「……」为占位）；"
            "预期信用损失率(%) = 坏账准备 ÷ 合同资产。",
        ),
        rule(
            "组合计提项目：质量保证金",
            two_period_columns(
                ("label", "账  龄"), ("期末余额", "上年年末余额"), _D6_GROUP_SUBS
            ),
            [
                data_row("1年以内"),
                data_row("1至2年"),
                data_row("2至3年"),
                data_row(),
                total_row("合  计"),
            ],
            "组合名与账龄档位按项目实际情况调整；预期信用损失率(%) = 坏账准备 ÷ 合同资产。",
        ),
        rule(
            "本期计提、收回或转回的合同资产减值准备情况",
            flat_columns([
                ("label", "项  目", None),
                ("provision", "本期计提", AMOUNT),
                ("reversal", "本期转回", AMOUNT),
                ("write_off", "本期转销/核销", AMOUNT),
                ("reason", "原因", TEXT),
            ]),
            blanks_then_total(3, "合  计"),
            "对本期重要的减值准备计提、转回、转销/核销逐项说明原因（源模板 A85-A89）。",
            aliases=["项  目", "项目"],
        ),
    ]


# 上市侧 `text_sections`：原本只有 3 条 `【提示…】`，**缺源模板 A36-A41 的说明段**
# （国企侧 A32-A36 已齐备）→ 补齐，保留原有提示不动。
# 🔴 说明正文不得写成 `#### xxx`：后端 `_is_table_title_paragraph` 认 `#` 即标题，
# 标题本身不进任何输出 → 实质披露正文会被静默丢弃（H1 上市曾中招）。
_D6_LISTED_TEXT_SECTIONS = [
    "【提示：同一合同下的合同资产和合同负债应当以净额在资产负债表列示。净额为借方余额的，"
    "应当根据其流动性在“合同资产”或“其他非流动资产”项目中列示，其中预计自资产负债表日起"
    "一年内变现的，应当在“合同资产”项目列示，不应在“一年内到期的非流动资产”项目列示；"
    "净额为贷方余额的，应当根据其流动性在“合同负债”或“其他非流动负债”项目中列示，"
    "其中预计自资产负债表日起一年内到期的，应当在“合同负债”项目列示，"
    "不应在“一年内到期的非流动负债”项目列示。】",
    "【注意：由于现金流缺口要基于预期能收到的现金流量进行计算，因此在计量合同资产的预期信用"
    "损失时考虑的期限应截止于预期收取现金流量之日，即需要考虑合同资产转为应收款项后可能发生的"
    "信用违约事件造成的损失。合同资产不是金融资产，与应收账款账龄不存在连续计算的问题。"
    "组合计提时，合同资产与信用期内应收账款的预期损失可能接近；单项计提时，"
    "同一客户的合同资产与应收账款预期损失通常相同。】",
    "【或：披露格式如下】",
    "1、履行履约义务的时间与通常的付款时间之间的关系，以及此类因素对合同资产"
    "（如果对合同负债产生影响在合同负债科目下说明）账面价值的影响的定量或定性信息。",
    "2、合同资产的账面价值在本期内发生的重大变动的情形包括：",
    "①企业合并导致的变动；",
    "②对收入进行累积追加调整导致的相关合同资产和合同负债的变动，此类调整可能源于估计履约进度的"
    "变化、估计交易价格的变化（包括对于可变对价是否受到限制的评估发生变化）或者合同变更；",
    "③对合同对价的权利成为无条件权利（即，合同资产重分类为应收款项）的时间安排发生变化。",
]


def _d6_soe_plan() -> list[dict[str, Any]]:
    return [
        rule(
            "合同资产情况",
            two_period_columns(("label", "项  目"), ("期末数", "期初数"), _BOOK_SUBS),
            [
                data_row("单项计提坏账准备"),
                data_row("按组合计提坏账准备"),
                data_row("其中：业务类型组合"),
                data_row("客户类型组合"),
                data_row(),
                total_row("合  计"),
            ],
            "账面价值 = 账面余额 − 减值准备；数据取自审定表 D6-1。组合明细行可按实际组合增删。",
        ),
        rule(
            "合同资产减值准备",
            grouped_columns(
                ("label", "项  目"),
                [
                    ("prior_balance", "期初数", AMOUNT, None),
                    ("provision", "计提", AMOUNT, "本期变动金额"),
                    ("reversal", "转回", AMOUNT, "本期变动金额"),
                    ("write_off", "转销/核销", AMOUNT, "本期变动金额"),
                    ("end_balance", "期末数", AMOUNT, None),
                    ("reason", "原因", TEXT, None),
                ],
            ),
            blanks_then_total(3, "合  计"),
            "勾稽：期末数 = 期初数 + 计提 − 转回 − 转销/核销（源模板 F21 公式）；"
            "重要变动须填写原因。",
        ),
        rule(
            "本期合同资产账面价值的重大变动",
            flat_columns([
                ("label", "项  目", None),
                ("change_amount", "变动金额", AMOUNT),
                ("reason", "变动原因", TEXT),
            ]),
            blanks_then_total(4, "合  计"),
            "源模板标注「国资委格式未要求披露」，按需填列。" + _D6_MAJOR_CHANGE_GUIDANCE,
        ),
    ]


# ─────────────────────────── 章节装配 ───────────────────────────

def _expected(plan: list[dict[str, Any]]) -> list[str]:
    return [str(r["new_name"]) for r in plan]


SECTIONS: dict[str, dict[str, Any]] = {
    "d3-listed": {
        "variant": "listed", "section": "五、38", "label": "D3 预收款项 五、38（上市）",
        "plan": _d3_listed_plan(), "drops": [],
    },
    "d3-soe": {
        "variant": "soe", "section": "八、38", "label": "D3 预收款项 八、38（国企）",
        "plan": _d3_soe_plan(), "drops": [],
    },
    "d5-listed": {
        "variant": "listed", "section": "五、6", "label": "D5 应收款项融资 五、6（上市）",
        "plan": _d5_listed_plan(), "drops": [],
    },
    "d5-soe": {
        "variant": "soe", "section": "八、6", "label": "D5 应收款项融资 八、6（国企）",
        "plan": _d5_soe_plan(), "drops": [],
    },
    "d6-listed": {
        "variant": "listed", "section": "五、10", "label": "D6 合同资产 五、10（上市）",
        "plan": _d6_listed_plan(),
        # 空名表是组合明细表被 md 重建脚本切碎的残片（headers 只剩两个期间名）
        "drops": [""],
        "text_sections": _D6_LISTED_TEXT_SECTIONS,
    },
    "d6-soe": {
        "variant": "soe", "section": "八、11", "label": "D6 合同资产 八、11（国企）",
        "plan": _d6_soe_plan(), "drops": [],
    },
    "d7-listed": {
        "variant": "listed", "section": "五、39", "label": "D7 合同负债 五、39（上市）",
        "plan": _d7_listed_plan(), "drops": [],
    },
    "d7-soe": {
        "variant": "soe", "section": "八、39", "label": "D7 合同负债 八、39（国企）",
        "plan": _d7_soe_plan(), "drops": [],
    },
}

for _spec in SECTIONS.values():
    _spec["expected"] = _expected(_spec["plan"])

LABELS = {k: str(v["label"]) for k, v in SECTIONS.items()}


def run_key(key: str, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    spec = SECTIONS[key]
    return run_section(
        TEMPLATE_PATH[str(spec["variant"])],
        str(spec["section"]),
        list(spec["plan"]),
        list(spec["expected"]),
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        drops=list(spec["drops"]),
        text_sections=spec.get("text_sections"),
    )


main = build_cli(
    "附注 D 类剩余循环（D3/D5/D6/D7）披露章节结构对齐（幂等）", run_key, LABELS
)


if __name__ == "__main__":
    sys.exit(main())
