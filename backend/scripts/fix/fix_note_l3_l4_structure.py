#!/usr/bin/env python
"""附注长期借款 / 应付债券 / 一年内到期的非流动负债章节结构对齐源模板（幂等修订）。

**覆盖 6 个章节**：

1. 五、45 长期借款（listed）—— 1 表，一层表头
2. 八、49 长期借款（soe）—— 1 表，一层表头
3. 五、46 应付债券（listed）—— 5 表
4. 八、50 应付债券（soe）—— 2 表
5. 五、43 一年内到期的非流动负债（listed）—— 5 表
6. 八、44 一年内到期的非流动负债（soe）—— 1 表

**问题摘要**：

- L3 两版「长期借款」按底稿一行表头 5 列（两列同名「利率区间」）；国企模板原只有 4 列（遗漏一列「利率区间」）。
  早先写成「期末余额 / 上年年末余额」两组的两级表头，R8.4 批 9b-2 按底稿改回一层。
- 5914e315b 把 五、46 第 4 张、五、43 第 5 张改成了同节前一张的表名（同节重名），按位置改回原名。
- L4 上市第 4 张表名是参考格式占位名 `参考披露格式：` 应改为
  「（3）划分为金融负债的其他金融工具」。
- 五、43 上市第 5 张表名为表头首格泄漏 `项  目` 应改为「一年内到期的长期应付款」。
- 各表 columns / guidance 全缺。

**权威源**（运行时权威，openpyxl 实证）：
``backend/wp_templates/L/L3 长期借款.xlsx``
``backend/wp_templates/L/L4 应付债券.xlsx``
``backend/wp_templates/L/L5 长期应付款.xlsx``（五、43 源模板来自此文件）

Usage::

    python backend/scripts/fix/fix_note_l3_l4_structure.py --dry-run
    python backend/scripts/fix/fix_note_l3_l4_structure.py
    python backend/scripts/fix/fix_note_l3_l4_structure.py --check

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/
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
SOE_PATH = DATA_DIR / "note_template_soe.json"

SCRIPT_NAME = "fix_note_l3_l4_structure.py"

# ═══════════════════════════════════════════════════════════════════
# L3 长期借款
# ═══════════════════════════════════════════════════════════════════

# 🔴 一层表头（R8.4 批 9b-2，用户「长期借款两版改成一层」）：底稿 L3 两张披露 sheet 的表头都只有一行、
#    没有合并格（上市 A7:E7 / 国企 A8:E8），原先拆成「期末余额 / 上年年末余额」两组（各含 余额 + 利率区间）
#    是臆造的分组。两列「利率区间」同名照抄（加期别前缀即杜撰），靠 key 区分；key 不变（推送规则与已存数据零迁移）。
#    行与行序按底稿（质押 / 抵押 / 保证 / 信用 + 小计 − 一年内到期 = 合计）。
_L3_ROWS = [
    data_row("质押借款"),
    data_row("抵押借款"),
    data_row("保证借款"),
    data_row("信用借款"),
    subtotal_row("小计"),
    data_row("减：一年内到期的长期借款"),
    total_row("合计"),
]

# ─── 上市 五、45 长期借款 ─── 1 表，一层表头
L3_LISTED_SECTION = "五、45"
L3_LISTED_TABLE_NAME = "长期借款"

# 源 xlsx R07: 项  目 | 期末余额 | 利率区间 | 上年年末余额 | 利率区间
L3_LISTED_COLS = flat_columns([
    ("label", "项  目", None),
    ("end_amount", "期末余额", AMOUNT),
    ("end_rate_range", "利率区间", TEXT),
    ("prior_amount", "上年年末余额", AMOUNT),
    ("prior_rate_range", "利率区间", TEXT),
])

L3_LISTED_GUIDANCE = (
    "按借款种类分类列示（质押/抵押/保证/信用），同时列示利率区间。"
    "减：一年内到期的长期借款。"
)

# ─── 国企 八、49 长期借款 ─── 1 表，一层表头
L3_SOE_SECTION = "八、49"
L3_SOE_TABLE_NAME = "长期借款"

# 源 xlsx R08: 借款类别 | 期末余额 | 利率区间 | 期初余额 | 利率区间
L3_SOE_COLS = flat_columns([
    ("label", "借款类别", None),
    ("end_amount", "期末余额", AMOUNT),
    ("end_rate_range", "利率区间", TEXT),
    ("begin_amount", "期初余额", AMOUNT),
    ("begin_rate_range", "利率区间", TEXT),
])

L3_SOE_GUIDANCE = (
    "按借款类别列示（质押/抵押/保证/信用），同时列示利率区间。"
    "减：一年内到期的长期借款。"
)


# ═══════════════════════════════════════════════════════════════════
# L4 应付债券
# ═══════════════════════════════════════════════════════════════════

# ─── 上市 五、46 应付债券 ─── 5 表
L4_LISTED_SECTION = "五、46"

L4_L_T1_NAME = "应付债券"
L4_L_T1_COLS = flat_columns([
    ("label", "项目", None),
    ("end_amount", "期末余额", AMOUNT),
    ("prior_amount", "上年年末余额", AMOUNT),
])
L4_L_T1_GUIDANCE = (
    "按面值/溢折价/应计利息列示应付债券期末与上年年末余额。"
    "15 号文：应付债券披露面值、利率、期限、发行日期、还本付息方式等基本情况。"
)

L4_L_T2_NAME = "应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）"
L4_L_T2_COLS = flat_columns([
    ("label", "债券名称", None),
    ("face_value", "面值", AMOUNT),
    ("coupon_rate", "票面利率", PERCENT),
    ("issue_date", "发行日期", TEXT),
    ("term", "债券期限", TEXT),
    ("issue_amount", "发行金额", AMOUNT),
])
L4_L_T2_GUIDANCE = (
    "应付债券基本信息：逐只列示债券名称、面值、票面利率、发行日期、债券期限、发行金额。"
    "15 号文第三十八条相关条款。"
)

L4_L_T3_NAME = "应付债券（续）"
L4_L_T3_COLS = flat_columns([
    ("label", "债券名称", None),
    ("begin_balance", "期初余额", AMOUNT),
    ("issue_current", "本期发行", AMOUNT),
    ("interest_accrual", "按面值计提利息", AMOUNT),
    ("premium_amort", "溢折价摊销", AMOUNT),
    ("repay_current", "本期偿还", AMOUNT),
    ("end_balance", "期末余额", AMOUNT),
    ("is_default", "是否违约", TEXT),
])
L4_L_T3_GUIDANCE = (
    "应付债券变动明细（续表）：期末余额 = 期初余额 + 本期发行 + 按面值计提利息 + "
    "溢折价摊销 − 本期偿还。「是否违约」注明到期未能偿还的情况。"
)

L4_L_T4_NAME = "（3）划分为金融负债的其他金融工具"
L4_L_T4_OBSOLETE_NAME = "参考披露格式："
L4_L_T4_COLS = flat_columns([
    ("label", "项目", None),
    ("begin_balance", "期初余额", AMOUNT),
    ("issue_current", "本期增加", AMOUNT),
    ("interest_current", "本期计提利息", AMOUNT),
    ("repay_current", "本期减少", AMOUNT),
    ("end_balance", "期末余额", AMOUNT),
    ("dividend_yield", "票面利率（股息率）", PERCENT),
    ("issue_date", "发行日", TEXT),
    ("term", "期限", TEXT),
    ("condition", "转股/赎回条件", TEXT),
])
L4_L_T4_GUIDANCE = (
    "划分为金融负债的优先股、永续债等其他金融工具增减变动情况。"
    "逐只列示面值、票面利率（股息率）、发行日期、期限及转股/赎回条件。"
    "15 号文第三十七条：公开发行的金融工具按类别披露条款和条件。"
)

L4_L_T5_NAME = "期末发行在外的优先股、永续债等其他金融工具变动情况"
L4_L_T5_COLS = grouped_columns(
    ("label", "发行在外的金融工具"),
    [
        ("begin_count", "数量", AMOUNT, "期初余额"),
        ("begin_value", "账面价值", AMOUNT, "期初余额"),
        ("increase_count", "数量", AMOUNT, "本期增加"),
        ("increase_value", "账面价值", AMOUNT, "本期增加"),
        ("decrease_count", "数量", AMOUNT, "本期减少"),
        ("decrease_value", "账面价值", AMOUNT, "本期减少"),
        ("end_count", "数量", AMOUNT, "期末余额"),
        ("end_value", "账面价值", AMOUNT, "期末余额"),
    ],
)
# 删除 header_label 假行（压扁的第二行表头残留），保留真实数据行 + 合计行
L4_L_T5_ROWS: list[dict[str, Any]] = [
    {"label": "工具1", "row_type": "data"},
    {"label": "合计", "is_total": True, "row_type": "total"},
]
L4_L_T5_GUIDANCE = (
    "期末发行在外的优先股、永续债等其他金融工具数量及账面价值变动情况。"
    "如无发行在外的优先股/永续债，本表可删除。"
    "源模板 r063/r064 为两级表头（4 组各含数量+账面价值）。"
)

# ─── 国企 八、50 应付债券 ─── 2 表
L4_SOE_SECTION = "八、50"

L4_S_T1_NAME = "应付债券"
L4_S_T1_COLS = flat_columns([
    ("label", "项目", None),
    ("end_amount", "期末余额", AMOUNT),
    ("begin_amount", "期初余额", AMOUNT),
])
L4_S_T1_GUIDANCE = (
    "按面值/溢折价/应计利息列示应付债券期末与期初余额。"
    "15 号文：应付债券披露面值、利率、期限等基本情况。"
)

L4_S_T2_NAME = "应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）"
# 源 xlsx 为 10 列一张表
L4_S_T2_COLS = flat_columns([
    ("label", "债券名称", None),
    ("face_value", "面值", AMOUNT),
    ("issue_date", "发行日期", TEXT),
    ("term", "债券期限", TEXT),
    ("issue_amount", "发行金额", AMOUNT),
    ("begin_interest", "年初应付利息", AMOUNT),
    ("interest_accrual", "本期应计利息", AMOUNT),
    ("interest_paid", "本期已付利息", AMOUNT),
    ("end_interest", "期末应付利息", AMOUNT),
    ("end_balance", "期末余额", AMOUNT),
])
L4_S_T2_GUIDANCE = (
    "应付债券增减变动明细（国企版 10 列）：逐只列示债券名称、面值、发行日期、"
    "债券期限、发行金额、年初应付利息、本期应计利息、本期已付利息、期末应付利息、期末余额。"
)


# ═══════════════════════════════════════════════════════════════════
# 五、43 / 八、44  一年内到期的非流动负债
# ═══════════════════════════════════════════════════════════════════

# ─── 上市 五、43 ─── 5 表
L_NONCURRENT_LISTED_SECTION = "五、43"

NC_L_T1_NAME = "一年内到期的非流动负债"
NC_L_T1_COLS = flat_columns([
    ("label", "项目", None),
    ("end_amount", "期末余额", AMOUNT),
    ("prior_amount", "上年年末余额", AMOUNT),
])
NC_L_T1_GUIDANCE = "一年内到期的各项非流动负债按类别分别列示。"

NC_L_T2_NAME = "一年内到期的长期借款"
NC_L_T2_COLS = flat_columns([
    ("label", "项目", None),
    ("end_amount", "期末余额", AMOUNT),
    ("prior_amount", "上年年末余额", AMOUNT),
])
NC_L_T2_GUIDANCE = "一年内到期的各项非流动负债按类别分别列示。"

NC_L_T3_NAME = "一年内到期的应付债券"
NC_L_T3_COLS = flat_columns([
    ("label", "债券名称", None),
    ("face_value", "面值", AMOUNT),
    ("issue_date", "发行日期", TEXT),
    ("term", "债券期限", TEXT),
    ("issue_amount", "发行金额", AMOUNT),
])
NC_L_T3_GUIDANCE = "一年内到期的各项非流动负债按类别分别列示。"

NC_L_T4_NAME = "一年内到期的应付债券（续）"
NC_L_T4_COLS = flat_columns([
    ("label", "债券名称", None),
    ("begin_balance", "期初余额", AMOUNT),
    ("interest_accrual", "按面值计提利息", AMOUNT),
    ("premium_amort", "溢折价摊销", AMOUNT),
    ("repay_current", "本期偿还", AMOUNT),
    ("end_balance", "期末余额", AMOUNT),
    ("is_default", "是否违约", TEXT),
])
NC_L_T4_GUIDANCE = "一年内到期的各项非流动负债按类别分别列示。"

NC_L_T5_NAME = "一年内到期的长期应付款"
NC_L_T5_OBSOLETE_NAME = "项  目"  # 表头首格泄漏名
NC_L_T5_COLS = flat_columns([
    ("label", "项目", None),
    ("end_amount", "期末余额", AMOUNT),
    ("prior_amount", "上年年末余额", AMOUNT),
])
NC_L_T5_GUIDANCE = "一年内到期的各项非流动负债按类别分别列示。"

# ─── 国企 八、44 ─── 1 表
L_NONCURRENT_SOE_SECTION = "八、44"

NC_S_T1_NAME = "一年内到期的非流动负债"
NC_S_T1_COLS = flat_columns([
    ("label", "项目", None),
    ("end_amount", "期末余额", AMOUNT),
    ("begin_amount", "期初余额", AMOUNT),
])
NC_S_T1_GUIDANCE = "一年内到期的各项非流动负债按类别分别列示。"


# ═══════════════════════════════════════════════════════════════════
# 计划编排
# ═══════════════════════════════════════════════════════════════════

def _l3_listed_plan() -> list[dict[str, Any]]:
    return [
        rule(L3_LISTED_TABLE_NAME, L3_LISTED_COLS, _L3_ROWS, L3_LISTED_GUIDANCE),
    ]


def _l3_soe_plan() -> list[dict[str, Any]]:
    return [
        rule(L3_SOE_TABLE_NAME, L3_SOE_COLS, _L3_ROWS, L3_SOE_GUIDANCE),
    ]


# 🔴 5914e315b（2026-10-10「附注续表(续)格式识别」）把上市 五、46 第 4 张表与 五、43 第 5 张表改成了同节前一张表的名字
#    （「应付债券的增减变动（…）」×2 /「一年内到期的应付债券（续）」×2）：sub_table_data 按表名作键，同节重名整张表
#    互相覆盖；本脚本按原名找不到表，--check 自那天起一直红。表头仍是原表的（10 列 / 3 列），按位置改回原名：
#    游标只前进，前一条规则已认领第一张同名表，这里的别名只会命中第二张（R8.4 批 9b-2）。
_L4_L_T4_RENAMED_BY_CONTINUATION = L4_L_T2_NAME
_NC_L_T5_RENAMED_BY_CONTINUATION = NC_L_T4_NAME


def _l4_listed_plan() -> list[dict[str, Any]]:
    return [
        rule(L4_L_T1_NAME, L4_L_T1_COLS, None, L4_L_T1_GUIDANCE),
        rule(L4_L_T2_NAME, L4_L_T2_COLS, None, L4_L_T2_GUIDANCE),
        rule(L4_L_T3_NAME, L4_L_T3_COLS, None, L4_L_T3_GUIDANCE),
        rule(
            L4_L_T4_NAME, L4_L_T4_COLS, None, L4_L_T4_GUIDANCE,
            aliases=[L4_L_T4_OBSOLETE_NAME, _L4_L_T4_RENAMED_BY_CONTINUATION],
        ),
        rule(L4_L_T5_NAME, L4_L_T5_COLS, L4_L_T5_ROWS, L4_L_T5_GUIDANCE),
    ]


def _l4_soe_plan() -> list[dict[str, Any]]:
    return [
        rule(L4_S_T1_NAME, L4_S_T1_COLS, None, L4_S_T1_GUIDANCE),
        rule(L4_S_T2_NAME, L4_S_T2_COLS, None, L4_S_T2_GUIDANCE),
    ]


def _nc_listed_plan() -> list[dict[str, Any]]:
    return [
        rule(NC_L_T1_NAME, NC_L_T1_COLS, None, NC_L_T1_GUIDANCE),
        rule(NC_L_T2_NAME, NC_L_T2_COLS, None, NC_L_T2_GUIDANCE),
        rule(NC_L_T3_NAME, NC_L_T3_COLS, None, NC_L_T3_GUIDANCE),
        rule(NC_L_T4_NAME, NC_L_T4_COLS, None, NC_L_T4_GUIDANCE),
        rule(
            NC_L_T5_NAME, NC_L_T5_COLS, None, NC_L_T5_GUIDANCE,
            aliases=[NC_L_T5_OBSOLETE_NAME, _NC_L_T5_RENAMED_BY_CONTINUATION],
        ),
    ]


def _nc_soe_plan() -> list[dict[str, Any]]:
    return [
        rule(NC_S_T1_NAME, NC_S_T1_COLS, None, NC_S_T1_GUIDANCE),
    ]


# ═══════════════════════════════════════════════════════════════════
# Expected table names per section
# ═══════════════════════════════════════════════════════════════════

EXPECTED: dict[str, list[str]] = {
    "l3_listed": [L3_LISTED_TABLE_NAME],
    "l3_soe": [L3_SOE_TABLE_NAME],
    "l4_listed": [L4_L_T1_NAME, L4_L_T2_NAME, L4_L_T3_NAME, L4_L_T4_NAME, L4_L_T5_NAME],
    "l4_soe": [L4_S_T1_NAME, L4_S_T2_NAME],
    "nc_listed": [NC_L_T1_NAME, NC_L_T2_NAME, NC_L_T3_NAME, NC_L_T4_NAME, NC_L_T5_NAME],
    "nc_soe": [NC_S_T1_NAME],
}

_TARGETS: dict[str, tuple[Path, str, Any]] = {
    "l3_listed": (LISTED_PATH, L3_LISTED_SECTION, _l3_listed_plan),
    "l3_soe": (SOE_PATH, L3_SOE_SECTION, _l3_soe_plan),
    "l4_listed": (LISTED_PATH, L4_LISTED_SECTION, _l4_listed_plan),
    "l4_soe": (SOE_PATH, L4_SOE_SECTION, _l4_soe_plan),
    "nc_listed": (LISTED_PATH, L_NONCURRENT_LISTED_SECTION, _nc_listed_plan),
    "nc_soe": (SOE_PATH, L_NONCURRENT_SOE_SECTION, _nc_soe_plan),
}

LABELS: dict[str, str] = {
    "l3_listed": f"上市 §{L3_LISTED_SECTION} 长期借款",
    "l3_soe": f"国企 §{L3_SOE_SECTION} 长期借款",
    "l4_listed": f"上市 §{L4_LISTED_SECTION} 应付债券",
    "l4_soe": f"国企 §{L4_SOE_SECTION} 应付债券",
    "nc_listed": f"上市 §{L_NONCURRENT_LISTED_SECTION} 一年内到期的非流动负债",
    "nc_soe": f"国企 §{L_NONCURRENT_SOE_SECTION} 一年内到期的非流动负债",
}


def _run(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn = _TARGETS[key]
    return run_section(
        path,
        section_number,
        plan_fn(),
        EXPECTED[key],
        aligned_by=SCRIPT_NAME,
        dry_run=dry_run,
        check=check,
    )


main = build_cli(
    "附注长期借款/应付债券/一年内到期的非流动负债章节结构对齐源模板（幂等修订）",
    _run,
    LABELS,
)

if __name__ == "__main__":
    raise SystemExit(main())
