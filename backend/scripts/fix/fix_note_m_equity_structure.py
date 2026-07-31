#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M 循环权益类「变动表」附注章节结构对齐（幂等）。

覆盖结构同构的标准变动表（项目 | 期初余额 | 本期增加 | 本期减少 | 期末余额）：

| 章节   | 科目       | 备注                                  |
|--------|------------|---------------------------------------|
| 五、55 | 资本公积   |                                       |
| 八、60 | 资本公积   |                                       |
| 五、59 | 盈余公积   |                                       |
| 八、62 | 盈余公积   |                                       |
| 五、58 | 专项储备   |                                       |
| 八、61 | 专项储备   | 国企侧多「备注」列（6 列）             |

现状：6 张表名 / 表头 / 行骨架均正确（源模板单行表头），**仅缺 columns 与 guidance**
→ seed 路径会走 `_infer_groups_from_headers` 前缀推断（「本期增加」「本期减少」共享
「本期」前缀 → 凭空造「本期」父表头）。本脚本只补 columns(flat) + guidance，**不动 rows**
（行骨架 seed 已对；`_source=workpaper` 下由底稿推送覆盖）。

Usage::

    python backend/scripts/fix/fix_note_m_equity_structure.py --dry-run
    python backend/scripts/fix/fix_note_m_equity_structure.py
    python backend/scripts/fix/fix_note_m_equity_structure.py --check
    python backend/scripts/fix/fix_note_m_equity_structure.py --only m4-listed

spec: .kiro/specs/disclosure-sync-path-buildout/ Task 5（M 循环批 4）
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_KIT_PATH = Path(__file__).resolve().parent / "_note_structure_kit.py"
_spec = importlib.util.spec_from_file_location("_note_structure_kit", _KIT_PATH)
assert _spec and _spec.loader
kit = importlib.util.module_from_spec(_spec)
sys.modules["_note_structure_kit"] = kit
_spec.loader.exec_module(kit)

AMOUNT = kit.AMOUNT
TEXT = kit.TEXT

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LISTED = DATA_DIR / "note_template_listed.json"
SOE = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "fix_note_m_equity_structure"


def _change_cols(with_remark: bool) -> list[dict[str, Any]]:
    pairs = [
        ("label", "项目", None),
        ("begin_amount", "期初余额", AMOUNT),
        ("increase", "本期增加", AMOUNT),
        ("decrease", "本期减少", AMOUNT),
        ("end_amount", "期末余额", AMOUNT),
    ]
    if with_remark:
        pairs.append(("remark", "备注", TEXT))
    return kit.flat_columns(pairs)


GUIDANCE = {
    "资本公积": "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少；合计 = 各项之和。"
    "须逐项说明资本公积增加、减少的原因、依据及金额；转增股本须说明法律程序及决议。"
    "数据来源审定表 / 明细表。",
    "盈余公积": "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少；合计 = 各项之和。"
    "须说明盈余公积变动情况与原因；用于转增股本 / 弥补亏损 / 分派股利的须说明决议。",
    "专项储备": "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少；合计 = 各项之和。"
    "须说明专项储备（安全生产费 / 维简费等）的变动情况与变动原因。",
}


def _plan(table_name: str, with_remark: bool):
    def planner() -> tuple[list[dict[str, Any]], list[str], list[str], list[str] | None]:
        cols = _change_cols(with_remark)
        # rows=None：保持模板既有行骨架不动，只补 columns + guidance
        plan = [kit.rule(table_name, cols, None, GUIDANCE[table_name])]
        return plan, [table_name], [], None
    return planner


SECTIONS: dict[str, tuple[Path, str, Any]] = {
    "m4-listed": (LISTED, "五、55", _plan("资本公积", False)),
    "m4-soe": (SOE, "八、60", _plan("资本公积", False)),
    "m5-listed": (LISTED, "五、59", _plan("盈余公积", False)),
    "m5-soe": (SOE, "八、62", _plan("盈余公积", False)),
    "m7-listed": (LISTED, "五、58", _plan("专项储备", False)),
    "m7-soe": (SOE, "八、61", _plan("专项储备", True)),
}

LABELS = {
    "m4-listed": "五、55 资本公积（上市）",
    "m4-soe": "八、60 资本公积（国企）",
    "m5-listed": "五、59 盈余公积（上市）",
    "m5-soe": "八、62 盈余公积（国企）",
    "m7-listed": "五、58 专项储备（上市）",
    "m7-soe": "八、61 专项储备（国企，含备注列）",
}


def run(key: str, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    path, section_number, planner = SECTIONS[key]
    plan, expected, drops, text_sections = planner()
    return kit.run_section(
        path,
        section_number,
        plan,
        expected,
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        drops=drops,
        text_sections=text_sections,
    )


main = kit.build_cli(__doc__ or "M 循环权益变动表附注章节结构对齐", run, LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
