#!/usr/bin/env python
"""附注「应收账款」披露章节（上市 五、5 / 国企 八、5）结构对齐（幂等修订）。

**背景**（2026-08-01 复核实证）：D2 的表名/行骨架/占位行已由并发会话的两个归档 spec
（`d2-ar-disclosure-template-alignment` / `d2-ar-disclosure-soe-alignment`）处理过
（`_aligned_by='d2-ar-disclosure-soe-alignment'` 已见于国企侧），**但两者都只做了
同步载荷（前端 `d2NoteSectionMap.ts`）与部分行骨架，没有把 `columns`/`guidance`
写回模板 JSON** —— 上市 17 表、国企 13 表的 `columns` 与 `guidance` 仍全缺
（`_aligned_by` 上市侧甚至是 `None`）。

后果：seed 路径（新建项目 / 重新生成附注）会被 `_infer_groups_from_headers`
按前缀反猜出凭空父表头；附注 TAB 页签无编制提示。

本脚本**只补 `columns`（含 `_column_groups`）与 `guidance`，不动 `rows`/表名**
（`rows=None` 委托 `apply_plan` 保留既有骨架，避免与并发会话的行数据打架）；
唯一例外是国企侧 4 处历史遗留占位行（「可无限量添加行」/`header_label` 假行），
按铁律必须删除（语义已移入 guidance）。

**列定义权威源** = 前端 `composables/d2NoteSectionMap.ts` 已声明的 16 个 `ColumnDef`
常量（`AGING_COLUMNS_*` / `CLASS_COLUMNS_*` / `INDIVIDUAL_COLUMNS_*` /
`PORTFOLIO_COLUMNS_*` / `MOVEMENT_COLUMNS_*` / `REVERSAL_COLUMNS_*` /
`WRITEOFF_*_COLUMNS*` / `TOP5_COLUMNS_*` / `DERECOGNIZED_COLUMNS_*` /
`CONTINUED_INVOLVEMENT_COLUMNS*`）——它们已经过并发 spec 的实测校验（浏览器实测
落库、列头/两级表头正确），本脚本原样镜像到 Python，不重新裁决。

guidance 文案取源模板红字 / F5-* 校验预设（`note_check_preset_formulas.json`，
D2 沿用共享 F5 编号池）。

用法（cwd=backend）::

    python scripts/fix/fix_note_d2_ar_structure.py --dry-run
    python scripts/fix/fix_note_d2_ar_structure.py
    python scripts/fix/fix_note_d2_ar_structure.py --check

spec: .kiro/specs/d-cycle-extraction-chain-completion/ Task 2.2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    PERCENT,
    TEXT,
    apply_plan,
    derive_column_groups,
    find_bare_table_name_paragraphs,
    find_section,
    flat_columns,
    grouped_columns,
    rule,
    stamp,
    titleize_text_sections,
    validate_section,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "d-cycle-extraction-chain-completion"

TEMPLATE_PATH = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}
SECTION_NUMBER = {"listed": "五、5", "soe": "八、5"}


# ─────────────────────────── guidance 文案 ───────────────────────────
# 只取源模板红字 / 附注括注 / 以「勾稽：」前缀标注的 F5-* 校验预设。

_G_AGING = (
    "按账龄披露应收账款。勾稽：账龄各档之和 = 合计行（F5-19、F5-24，每个数值列独立）；"
    "「其他」列（坏账准备/净额）恒为账面余额 − 坏账准备（F5-11）；"
    "预期信用损失率(%) = 坏账准备 ÷ 账面余额 × 100（F5-12、F5-13）。"
    "（可根据企业具体会计政策，相应修改账龄组合的划分）"
)

_G_CLASS = (
    "按坏账计提方法分类披露应收账款。勾稽：比例(%) = 该行账面余额 ÷ 合计行账面余额 × 100"
    "（F5-27、F5-29）；预期信用损失率(%) = 坏账准备 ÷ 账面余额 × 100（F5-12）；"
    "账面余额 − 坏账准备 = 账面价值（F5-11）；各明细行之和 = 合计行（F5-24、F5-26）；"
    "按单项计提行 = 单项计提明细小计、按组合计提行 = 各组合分表小计之和（F5-3、F5-4）。"
    "注：填写组合名称。账面余额中的比例按期末该类应收账款除以应收账款合计数计算，"
    "坏账准备比例按该类应收账款期末已计提坏账准备除以期末该类应收账款余额计算。"
)

_G_INDIVIDUAL = (
    "期末单项计提坏账准备的应收账款逐项列示，可无限量添加行项目。"
    "勾稽：预期信用损失率(%) = 坏账准备 ÷ 账面余额 × 100（F5-13、F5-29）；"
    "各明细行之和 = 合计行（F5-21、F5-24）。"
    "完整性：账面余额 ≠ 0 时，名称（债务人名称）、坏账准备、计提依据（理由）列"
    "均不应为空（F5-33、F5-34）。"
)

_G_PORTFOLIO = (
    "组合计提项目分表（按客户类型/账龄等组合方式，逐组合各一张表）。"
    "勾稽：各账龄档之和 = 合计行（F5-17、F5-18，每个数值列独立）；"
    "本表合计 = 按坏账计提方法分类表「按组合计提」行对应组合的小计（F5-3、F5-4）；"
    "预期信用损失率(%)/比例(%) = 坏账准备 ÷ 应收账款 × 100（F5-13、F5-29）。"
    "注：填写具体组合名称。"
)

_G_OTHER_PORTFOLIO = (
    "采用余额百分比或其他组合方法计提坏账准备的应收账款（不适用的删除）。"
    "勾稽：各组合名称行之和 = 合计行（F5-22）；计提比例(%) = 坏账准备 ÷ 账面余额 × 100"
    "（F5-28）；本表合计 = 按坏账计提方法分类表「按组合计提」行对应组合的小计（F5-3、F5-4）。"
)

_G_MOVEMENT = (
    "本期计提、收回或转回的坏账准备情况。"
    "勾稽：期末数 = 期初数 + 本期计提 − 本期收回或转回 − 本期核销 − 本期转销 − 其他"
    "（源模板 B86 公式；国企侧为 期末数=期初数+计提-收回或转回-转销或核销，F5-6）；"
    "期末数 = 分类表坏账准备期末合计（F5-8）；期初数 = 分类表坏账准备期初合计（F5-8a）。"
    "「本期转销」「其他」为源模板可选行，无发生额时可删除。"
)

_G_REVERSAL = (
    "其中，本期坏账准备转回或收回金额重要的（不适用的删除）。"
    "勾稽：各明细行之和 = 合计行（F5-30、F5-19）。"
    "完整性：转回或收回金额 ≠ 0 时，单位（债务人）名称、转回原因/收回方式（原因、方式）"
    "均不应为空（F5-31、F5-32）。"
    "注：本期坏账准备收回或转回金额重要的，应披露转回原因、收回方式、"
    "确定原坏账准备计提比例的依据及其合理性。"
)

_G_WRITEOFF_AMOUNT = (
    "列示本期实际核销的应收账款总额。"
    "勾稽：本表（含逐项披露子表）各明细行之和 = 合计行（F5-21）；"
    "核销金额应与坏账准备变动表「本期核销」列一致。"
)

_G_WRITEOFF_DETAIL = (
    "其中，重要的应收账款核销情况（逐项披露）。"
    "勾稽：各明细行之和 = 合计行（F5-21）。"
    "完整性：核销金额 ≠ 0 时，单位（债务人）名称、应收账款性质、核销原因、"
    "履行的核销程序、是否由关联交易产生（是否因关联交易产生）列均不应为空（F5-33、F5-34）。"
)

_G_TOP5 = (
    "按欠款方归集的应收账款和合同资产期末余额前五名单位情况。"
    "勾稽：各单位行之和 = 合计行（F5-22）；占比 = 该单位应收账款及合同资产期末余额合计 ÷ "
    "应收账款及合同资产期末余额合计数 × 100（F5-37）。"
)

_G_DERECOGNIZED = (
    "因金融资产转移而终止确认的应收账款情况。"
    "勾稽：各明细行之和 = 合计行（F5-23）。"
)

_G_CONTINUED_INVOLVEMENT = (
    "应收账款转移且继续涉入形成的资产、负债的金额（如证券化、保理等，不适用的删除）。"
    "资产、负债分块列示，各自小计。"
)


# ─────────────────────────── 列定义（镜像前端 d2NoteSectionMap.ts） ───────────

AMT = AMOUNT
PCT = PERCENT
TXT = TEXT

AGING_COLUMNS_LISTED = flat_columns([
    ("label", "账 龄", None),
    ("end_amount", "期末余额", AMT),
    ("prior_amount", "上年年末余额", AMT),
])
AGING_COLUMNS_SOE = flat_columns([
    ("label", "账 龄", None),
    ("end_amount", "期末数", AMT),
    ("prior_amount", "期初数", AMT),
])

# 分类披露：期末余额/上年年末余额由表名承载，此处两级（账面余额{金额,比例} / 坏账准备{金额,损失率} / 账面价值）
CLASS_COLUMNS_LISTED = grouped_columns(
    ("label", "类 别"),
    [
        ("book_amount", "金额", AMT, "账面余额"),
        ("ratio", "比例(%)", PCT, "账面余额"),
        ("provision", "金额", AMT, "坏账准备"),
        ("loss_rate", "预期信用损失率(%)", PCT, "坏账准备"),
        ("carrying_value", "账面价值", AMT, None),
    ],
)
CLASS_COLUMNS_SOE = grouped_columns(
    ("label", "类 别"),
    [
        ("book_amount", "金额", AMT, "账面金额"),
        ("ratio", "比例(%)", PCT, "账面金额"),
        ("provision", "金额", AMT, "坏账准备"),
        ("loss_rate", "预期信用损失率(%)", PCT, "坏账准备"),
        ("carrying_value", "账面价值", AMT, None),
    ],
)

INDIVIDUAL_COLUMNS_LISTED = flat_columns([
    ("label", "名 称", None),
    ("book_amount", "账面余额", AMT),
    ("provision", "坏账准备", AMT),
    ("loss_rate", "预期信用损失率（%）", PCT),
    ("basis", "计提依据", TXT),
])
INDIVIDUAL_COLUMNS_SOE = flat_columns([
    ("label", "债务人名称", None),
    ("end_amount", "账面余额", AMT),
    ("provision", "坏账准备", AMT),
    ("aging", "账龄", TXT),
    ("loss_rate", "预期信用损失率（%）", PCT),
    ("basis", "计提理由", TXT),
])

PORTFOLIO_COLUMNS_LISTED = grouped_columns(
    ("label", "账龄"),
    [
        ("end_amount", "应收账款", AMT, "期末余额"),
        ("end_provision", "坏账准备", AMT, "期末余额"),
        ("end_loss_rate", "预期信用损失率(%)", PCT, "期末余额"),
        ("prior_amount", "应收账款", AMT, "上年年末余额"),
        ("prior_provision", "坏账准备", AMT, "上年年末余额"),
        ("prior_loss_rate", "预期信用损失率(%)", PCT, "上年年末余额"),
    ],
)
PORTFOLIO_COLUMNS_SOE = grouped_columns(
    ("label", "账 龄"),
    [
        ("end_amount", "应收账款", AMT, "期末数"),
        ("end_ratio", "比例（%）", PCT, "期末数"),
        ("end_provision", "坏账准备", AMT, "期末数"),
        ("prior_amount", "应收账款", AMT, "期初数"),
        ("prior_ratio", "比例（%）", PCT, "期初数"),
        ("prior_provision", "坏账准备", AMT, "期初数"),
    ],
)
OTHER_PORTFOLIO_COLUMNS_SOE = grouped_columns(
    ("label", "组合名称"),
    [
        ("end_amount", "账面余额", AMT, "期末数"),
        ("end_rate", "计提比例（%）", PCT, "期末数"),
        ("end_provision", "坏账准备", AMT, "期末数"),
        ("prior_amount", "账面余额", AMT, "期初数"),
        ("prior_rate", "计提比例（%）", PCT, "期初数"),
        ("prior_provision", "坏账准备", AMT, "期初数"),
    ],
)

MOVEMENT_COLUMNS_LISTED = flat_columns([
    ("label", "项 目", None),
    ("amount", "坏账准备金额", AMT),
])
MOVEMENT_COLUMNS_SOE = grouped_columns(
    ("label", "类 别"),
    [
        ("prior_amount", "期初数", AMT, None),
        ("provision_amount", "计提", AMT, "本期变动金额"),
        ("reversal_amount", "收回或转回", AMT, "本期变动金额"),
        ("writeoff_amount", "转销或核销", AMT, "本期变动金额"),
        ("end_amount", "期末数", AMT, None),
    ],
)

REVERSAL_COLUMNS_LISTED = flat_columns([
    ("label", "单位名称", None),
    ("reversal_reason", "转回原因", TXT),
    ("recovery_method", "收回方式", TXT),
    ("original_basis", "原确定坏账准备的依据", TXT),
    ("amount", "转回或收回金额", AMT),
])
REVERSAL_COLUMNS_SOE = flat_columns([
    ("label", "债务人名称", None),
    ("amount", "转回或收回金额", AMT),
    ("cumulative_provision", "转回或收回前累计已计提坏账准备金额", AMT),
    ("reason_method", "转回或收回原因、方式", TXT),
])

WRITEOFF_AMOUNT_COLUMNS = flat_columns([
    ("label", "项  目", None),
    ("amount", "核销金额", AMT),
])

WRITEOFF_DETAIL_COLUMNS_LISTED = flat_columns([
    ("label", "单位名称", None),
    ("nature", "应收账款性质", TXT),
    ("amount", "核销金额", AMT),
    ("reason", "核销原因", TXT),
    ("procedure", "履行的核销程序", TXT),
    ("related", "款项是否由关联交易产生", TXT),
])
WRITEOFF_DETAIL_COLUMNS_SOE = flat_columns([
    ("label", "债务人名称", None),
    ("nature", "应收账款性质", TXT),
    ("amount", "核销金额", AMT),
    ("reason", "核销原因", TXT),
    ("procedure", "履行的核销程序", TXT),
    ("related", "是否因关联交易产生", TXT),
])

TOP5_COLUMNS_LISTED = flat_columns([
    ("label", "单位名称", None),
    ("ar_amount", "应收账款期末余额", AMT),
    ("contract_asset_amount", "合同资产期末余额", AMT),
    ("total_amount", "应收账款和合同资产期末余额", AMT),
    ("ratio", "占应收账款和合同资产期末余额合计数的比例%", PCT),
    ("provision", "应收账款坏账准备和合同资产减值准备期末余额", AMT),
])
TOP5_COLUMNS_SOE = flat_columns([
    ("label", "债务人名称", None),
    ("ar_amount", "账面余额", AMT),
    ("ratio", "占应收账款合计的比例（%）", PCT),
    ("provision", "坏账准备", AMT),
])

DERECOGNIZED_COLUMNS_LISTED = flat_columns([
    ("label", "项  目", None),
    ("transfer_method", "转移方式", TXT),
    ("amount", "终止确认金额", AMT),
    ("gain_loss", "与终止确认相关的利得或损失", AMT),
])
DERECOGNIZED_COLUMNS_SOE = flat_columns([
    ("label", "债务人名称", None),
    ("amount", "终止确认金额", AMT),
    ("gain_loss", "与终止确认相关的利得或损失（损失以“-”填列）", AMT),
])

CONTINUED_INVOLVEMENT_COLUMNS_LISTED = flat_columns([
    ("label", "项  目", None),
    ("transfer_method", "资产转移方式", TXT),
    ("asset_amount", "继续涉入形成的资产金额", AMT),
    ("liability_amount", "继续涉入形成的负债金额", AMT),
])
CONTINUED_INVOLVEMENT_COLUMNS_SOE = flat_columns([
    ("label", "项  目", None),
    ("amount", "期末金额", AMT),
])


# ─────────────────────────── 计划装配 ───────────────────────────
# 🔴 全部 rows=None：不动既有行骨架（并发 spec 已实测校验过），只补 columns/guidance。

def _build_listed_plan() -> list[dict[str, Any]]:
    return [
        rule("按账龄披露", AGING_COLUMNS_LISTED, None, _G_AGING),
        rule("按坏账计提方法分类披露", CLASS_COLUMNS_LISTED, None, _G_CLASS),
        rule("按坏账计提方法分类披露（续：上年年末余额）", CLASS_COLUMNS_LISTED, None, _G_CLASS),
        rule("按单项计提坏账准备的应收账款", INDIVIDUAL_COLUMNS_LISTED, None, _G_INDIVIDUAL),
        rule("按单项计提坏账准备的应收账款（续：上年年末余额）", INDIVIDUAL_COLUMNS_LISTED, None, _G_INDIVIDUAL),
        # 组合计提分表：模板里已实例化 5 张（按项目实际组合动态生成），列定义同构
        rule("组合计提项目：应收中央企业客户", PORTFOLIO_COLUMNS_LISTED, None, _G_PORTFOLIO),
        rule("组合计提项目：应收地方国有企业客户", PORTFOLIO_COLUMNS_LISTED, None, _G_PORTFOLIO),
        rule("组合计提项目：应收海外企业客户", PORTFOLIO_COLUMNS_LISTED, None, _G_PORTFOLIO),
        rule("组合计提项目：组合4", PORTFOLIO_COLUMNS_LISTED, None, _G_PORTFOLIO),
        rule("组合计提项目：组合5", PORTFOLIO_COLUMNS_LISTED, None, _G_PORTFOLIO),
        rule("本期计提、收回或转回的坏账准备情况", MOVEMENT_COLUMNS_LISTED, None, _G_MOVEMENT),
        rule("转回或收回金额重要的坏账准备", REVERSAL_COLUMNS_LISTED, None, _G_REVERSAL),
        rule("本期实际核销的应收账款情况", WRITEOFF_AMOUNT_COLUMNS, None, _G_WRITEOFF_AMOUNT),
        rule("重要的应收账款核销情况（逐项披露）", WRITEOFF_DETAIL_COLUMNS_LISTED, None, _G_WRITEOFF_DETAIL),
        rule("按欠款方归集的应收账款和合同资产期末余额前五名单位情况", TOP5_COLUMNS_LISTED, None, _G_TOP5),
        rule("因金融资产转移而终止确认的应收账款情况", DERECOGNIZED_COLUMNS_LISTED, None, _G_DERECOGNIZED),
        # 🔴 源模板 R172 字面「…形成的资产、负债的金额」（漏「的金额」二字），
        # aliases 兼容旧名以便原地改名（不产生孤儿子表）。
        rule(
            "转移应收账款且继续涉入形成的资产、负债的金额",
            CONTINUED_INVOLVEMENT_COLUMNS_LISTED, None, _G_CONTINUED_INVOLVEMENT,
            aliases=["转移应收账款且继续涉入形成的资产、负债"],
        ),
    ]


def _build_soe_plan() -> list[dict[str, Any]]:
    return [
        rule("（1）按账龄披露应收账款", AGING_COLUMNS_SOE, None, _G_AGING),
        rule("（2）按坏账准备计提方法分类披露应收账款", CLASS_COLUMNS_SOE, None, _G_CLASS),
        rule("（2）按坏账准备计提方法分类披露应收账款（续：期初数）", CLASS_COLUMNS_SOE, None, _G_CLASS),
        # 🔴 占位行清理：header_label 假行 + 「可无限量添加行」（rows=[data_row(),total_row()] 交由脚本判定，见下方 CLEAN_PLACEHOLDER）
        rule("期末单项计提坏账准备的应收账款", INDIVIDUAL_COLUMNS_SOE, None, _G_INDIVIDUAL),
        rule("组合计提项目：应收中央企业客户", PORTFOLIO_COLUMNS_SOE, None, _G_PORTFOLIO),
        rule("组合计提项目：应收海外企业客户", PORTFOLIO_COLUMNS_SOE, None, _G_PORTFOLIO),
        rule("采用余额百分比或其他组合方法计提坏账准备的应收账款", OTHER_PORTFOLIO_COLUMNS_SOE, None, _G_OTHER_PORTFOLIO),
        rule("（3）本期计提、收回或转回的坏账准备情况", MOVEMENT_COLUMNS_SOE, None, _G_MOVEMENT),
        rule("收回或转回的坏账准备", REVERSAL_COLUMNS_SOE, None, _G_REVERSAL),
        rule("（4）本期实际核销的应收账款", WRITEOFF_DETAIL_COLUMNS_SOE, None, _G_WRITEOFF_DETAIL),
        rule("（5）按欠款方归集的期末余额前五名的应收账款", TOP5_COLUMNS_SOE, None, _G_TOP5),
        rule("（6）由金融资产转移而终止确认的应收账款", DERECOGNIZED_COLUMNS_SOE, None, _G_DERECOGNIZED),
        rule("（7）应收账款转移继续涉入形成的资产、负债的金额", CONTINUED_INVOLVEMENT_COLUMNS_SOE, None, _G_CONTINUED_INVOLVEMENT),
    ]


SECTION_PLANS: dict[str, dict[str, Any]] = {
    "listed": {
        "section": SECTION_NUMBER["listed"],
        "plan": _build_listed_plan(),
        "expected": [
            "按账龄披露", "按坏账计提方法分类披露", "按坏账计提方法分类披露（续：上年年末余额）",
            "按单项计提坏账准备的应收账款", "按单项计提坏账准备的应收账款（续：上年年末余额）",
            "组合计提项目：应收中央企业客户", "组合计提项目：应收地方国有企业客户",
            "组合计提项目：应收海外企业客户", "组合计提项目：组合4", "组合计提项目：组合5",
            "本期计提、收回或转回的坏账准备情况", "转回或收回金额重要的坏账准备",
            "本期实际核销的应收账款情况", "重要的应收账款核销情况（逐项披露）",
            "按欠款方归集的应收账款和合同资产期末余额前五名单位情况",
            "因金融资产转移而终止确认的应收账款情况", "转移应收账款且继续涉入形成的资产、负债的金额",
        ],
    },
    "soe": {
        "section": SECTION_NUMBER["soe"],
        "plan": _build_soe_plan(),
        "expected": [
            "（1）按账龄披露应收账款", "（2）按坏账准备计提方法分类披露应收账款",
            "（2）按坏账准备计提方法分类披露应收账款（续：期初数）",
            "期末单项计提坏账准备的应收账款", "组合计提项目：应收中央企业客户",
            "组合计提项目：应收海外企业客户", "采用余额百分比或其他组合方法计提坏账准备的应收账款",
            "（3）本期计提、收回或转回的坏账准备情况", "收回或转回的坏账准备",
            "（4）本期实际核销的应收账款", "（5）按欠款方归集的期末余额前五名的应收账款",
            "（6）由金融资产转移而终止确认的应收账款",
            "（7）应收账款转移继续涉入形成的资产、负债的金额",
        ],
    },
}


# ─────────────────────────── 占位行清理（国企 4 处） ───────────────────────

_PLACEHOLDER_LABELS = {"可无限量添加行", "……", "..."}


def _clean_placeholder_rows(section: dict[str, Any]) -> list[str]:
    """删除 rows 里的 header_label 假行 / 占位说明行（语义已在 guidance 里）。"""
    changes: list[str] = []
    for i, tbl in enumerate(section.get("tables") or []):
        rows = tbl.get("rows") or []
        kept = [
            r for r in rows
            if str(r.get("row_type", "")) != "header_label"
            and str(r.get("label", "")).strip() not in _PLACEHOLDER_LABELS
        ]
        if len(kept) != len(rows):
            changes.append(f"[{i}] {tbl.get('name')}.rows：{len(rows)} → {len(kept)}（删占位/假表头行）")
            tbl["rows"] = kept
    return changes


# ─────────────────────────── CLI ───────────────────────────

def run(variant: str, *, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    spec = SECTION_PLANS[variant]
    path = TEMPLATE_PATH[variant]
    doc = json.loads(path.read_text(encoding="utf-8"))
    section = find_section(doc, spec["section"])
    if section is None:
        return [], [f"未找到章节 {spec['section']}（{path.name}）"], []

    if check:
        return [], [], validate_section(section, spec["expected"])

    changes, warnings = apply_plan(section, spec["plan"])
    changes += _clean_placeholder_rows(section)
    changes += titleize_text_sections(section)
    errs = validate_section(section, spec["expected"])
    if changes and not dry_run and not errs:
        stamp(section, ALIGNED_BY)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes, warnings, errs


def main() -> int:
    ap = argparse.ArgumentParser(description="附注 D2 应收账款披露章节结构对齐（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印变更，不写文件")
    ap.add_argument("--check", action="store_true", help="只校验现状，返回非零表示欠账")
    ap.add_argument("--variant", choices=["listed", "soe"], help="只处理单个版本")
    args = ap.parse_args()

    variants = [args.variant] if args.variant else ["listed", "soe"]
    total_changes = 0
    total_errs = 0

    for variant in variants:
        changes, warnings, errs = run(variant, dry_run=args.dry_run, check=args.check)
        head = f"[{variant}] {SECTION_NUMBER[variant]} 应收账款"
        print(f"\n=== {head} ===")
        for c in changes:
            print(f"  ~ {c}")
        for w in warnings:
            print(f"  ! {w}")
        for e in errs:
            print(f"  x {e}")
        if not changes and not errs and not args.check:
            print("  = 已对齐（幂等空操作）")
        if args.check:
            print(f"  = 已对齐（幂等空操作）" if not errs else f"  x {len(errs)} 项欠账")
        total_changes += len(changes)
        total_errs += len(errs)

    if args.check:
        print(f"\n--check：{total_errs} 项欠账")
        return 1 if total_errs else 0

    print(f"\n共 {total_changes} 处变更，{total_errs} 项问题")
    return 1 if total_errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
