#!/usr/bin/env python
"""附注短期借款（L1）章节结构对齐源模板（幂等修订）。

**问题**：`五、33` / `八、33` 的「短期借款」两张表自 seed 生成起从未对齐过
（`columns` 全部缺失、guidance 全部缺失）：

- listed 表1「短期借款分类」``columns=0``、无 guidance
- listed 表2 表名是「借款单位」（应为「（2）逾期借款情况」）``columns=0``、无 guidance
- soe 表1「短期借款分类」``columns=0``、无 guidance
- soe 表2「已逾期未偿还的短期借款情况」``columns=0``、无 guidance，
  且 headers 是 5 列（多抄了 listed 的「逾期时间」「逾期利率」两列），
  源 xlsx 国企只有 3 列

**权威源**（运行时权威，逐格 openpyxl 实证）：
``backend/wp_templates/L/L1 短期借款.xlsx``

===== 上市 `附注披露信息核对（上市公司）` =====
表1「（1）短期借款分类」：3 列 `项  目 / 期末余额 / 上年年末余额`
  行 R08~R12（信用借款/质押借款/抵押借款/保证借款/合计）
表2「（2）逾期借款情况」：5 列 `借款单位 / 期末余额 / 借款利率 / 逾期时间 / 逾期利率`

===== 国企 `附注披露信息核对（国企）` =====
表1「（1）短期借款分类」：3 列 `借款类别 / 期末余额 / 年初余额`
  （注：源 xlsx 用"年初余额"，模板现为"期初余额"——允许的国企常用口径，不改）
表2「（2）已逾期未偿还的短期借款情况」：**3 列** `债权单位 / 期末余额 / 借款利率`

Usage::

    python backend/scripts/fix/fix_note_l1_short_term_loans_structure.py --dry-run
    python backend/scripts/fix/fix_note_l1_short_term_loans_structure.py
    python backend/scripts/fix/fix_note_l1_short_term_loans_structure.py --check

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    PERCENT,
    TEXT,
    flat_columns,
    rule,
    run_section,
    build_cli,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、33"
SOE_SECTION = "八、33"

SCRIPT_NAME = "fix_note_l1_short_term_loans_structure.py"

# ─────────────────── 上市 表1：（1）短期借款分类 ───────────────────

LISTED_T1_NAME = "短期借款分类"
LISTED_T1_COLS = flat_columns([
    ("label", "项  目", None),
    ("end_amount", "期末余额", AMOUNT),
    ("prior_amount", "上年年末余额", AMOUNT),
])
LISTED_T1_GUIDANCE = "（用于抵押、质押的财产应予披露。）"

# ─────────────────── 上市 表2：（2）逾期借款情况 ───────────────────

LISTED_T2_NAME = "（2）逾期借款情况"
LISTED_T2_COLS = flat_columns([
    ("label", "借款单位", None),
    ("end_amount", "期末余额", AMOUNT),
    ("rate", "借款利率", PERCENT),
    ("overdue_period", "逾期时间", TEXT),
    ("overdue_rate", "逾期利率", PERCENT),
])
LISTED_T2_GUIDANCE = (
    "汇总披露逾期借款（包括从长期借款转入的）的期末余额。"
    "对于重要的逾期借款，按借款单位列示借款期末余额、借款利率、逾期时间及逾期利率。"
)

# ─────────────────── 国企 表1：（1）短期借款分类 ───────────────────

SOE_T1_NAME = "短期借款分类"
SOE_T1_COLS = flat_columns([
    ("label", "借款类别", None),
    ("end_amount", "期末余额", AMOUNT),
    ("begin_amount", "期初余额", AMOUNT),
])
SOE_T1_GUIDANCE = "按借款类别列示（质押借款/抵押借款/保证借款/信用借款）。"

# ─────────────────── 国企 表2：（2）已逾期未偿还的短期借款情况 ───────────────────

SOE_T2_NAME = "已逾期未偿还的短期借款情况"
SOE_T2_COLS = flat_columns([
    ("label", "债权单位", None),
    ("end_amount", "期末余额", AMOUNT),
    ("rate", "借款利率", PERCENT),
])
SOE_T2_GUIDANCE = (
    "已到期短期借款或获得展期的，应说明展期条件、新的到期日。"
    "资产负债表日后已偿还金额应予说明。"
)

# ─────────────────── 章节定义 ───────────────────


def _listed_plan() -> list[dict]:
    return [
        rule(
            LISTED_T1_NAME,
            LISTED_T1_COLS,
            None,  # rows 不动
            LISTED_T1_GUIDANCE,
        ),
        rule(
            LISTED_T2_NAME,
            LISTED_T2_COLS,
            None,  # rows 不动
            LISTED_T2_GUIDANCE,
            aliases=["借款单位"],  # 旧表名定位
        ),
    ]


def _soe_plan() -> list[dict]:
    return [
        rule(
            SOE_T1_NAME,
            SOE_T1_COLS,
            None,  # rows 不动
            SOE_T1_GUIDANCE,
        ),
        rule(
            SOE_T2_NAME,
            SOE_T2_COLS,
            None,  # rows 不动；headers 修正为 3 列由 columns 驱动
            SOE_T2_GUIDANCE,
        ),
    ]


LISTED_EXPECTED = [LISTED_T1_NAME, LISTED_T2_NAME]
SOE_EXPECTED = [SOE_T1_NAME, SOE_T2_NAME]


def _run(key: str, dry_run: bool, check: bool):
    if key == "listed":
        return run_section(
            LISTED_PATH,
            LISTED_SECTION,
            _listed_plan(),
            LISTED_EXPECTED,
            aligned_by=SCRIPT_NAME,
            dry_run=dry_run,
            check=check,
        )
    else:
        return run_section(
            SOE_PATH,
            SOE_SECTION,
            _soe_plan(),
            SOE_EXPECTED,
            aligned_by=SCRIPT_NAME,
            dry_run=dry_run,
            check=check,
        )


LABELS = {
    "listed": f"上市 §{LISTED_SECTION} 短期借款",
    "soe": f"国企 §{SOE_SECTION} 短期借款",
}

main = build_cli(
    "附注短期借款（L1）章节结构对齐源模板（幂等修订）",
    _run,
    LABELS,
)

_aligned_by = "fix_note_l1_short_term_loans_structure.py"

if __name__ == "__main__":
    sys.exit(main())
