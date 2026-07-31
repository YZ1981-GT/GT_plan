#!/usr/bin/env python
"""附注「油气资产」章节补齐 columns / guidance（幂等修订，仅国企）。

**背景**：§八、25 的**行集与表头已与源模板逐行一致**
（`backend/wp_templates/H/H5 油气资产.xlsx` 的「附注披露信息（国有企业）」行 9 表头 5 列、
行 10~24 四层 16 行）—— 与 H2/H3 不同，H5 模板结构没有被 md 重建破坏。
唯一欠账是 `columns=0`（未表态 → seed 路径走 `_infer_groups_from_headers` 前缀推断，
会把 `本期增加额`/`本期减少额` 反猜出凭空「本期」父表头）+ 无 `guidance`。

故本脚本**只补 columns/guidance，`rows=None` 不动行集**。

**上市侧不处理**（实证，非欠账）：`note_template_variant_matrix.json` 的
`you_qi_zi_chan.listed_standalone = null`，且 `note_template_listed.json` 中油气资产
章节数实测 **0** —— 上市准则下油气资产不单独设附注章节。源 xlsx 虽有「附注披露信息
（上市公司）」sheet（4 层列转置），但无落点，**不得凭空新建章节**（宁缺勿造）。

Usage::

    python backend/scripts/fix/fix_note_h5_oil_gas_structure.py --dry-run
    python backend/scripts/fix/fix_note_h5_oil_gas_structure.py
    python backend/scripts/fix/fix_note_h5_oil_gas_structure.py --check

spec: .kiro/specs/h5-oil-gas-disclosure-alignment/ (Task 2)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    build_cli,
    flat_columns,
    rule,
    run_section,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
SOE_PATH = _BACKEND / "data" / "note_template_soe.json"
SOE_SECTION = "八、25"
ALIGNED_BY = "h5-oil-gas-disclosure-alignment"

T_MAIN = "油气资产"

# 与前端 h5NoteSectionMap.H5_SOE_COLUMNS 的 key 逐字一致（seed 路径 ↔ 推送路径同键）
_COLUMNS = flat_columns([
    ("label", "项目", None),
    ("begin", "期初余额", AMOUNT),
    ("increase", "本期增加额", AMOUNT),
    ("decrease", "本期减少额", AMOUNT),
    ("end", "期末余额", AMOUNT),
])

_GUIDANCE = (
    "油气资产分类表（源模板 R9–R24）：四层结构 —— 一、原价合计 / 二、累计折耗合计 / "
    "三、油气资产减值准备累计金额合计 / 四、油气资产账面价值合计，"
    "各层下以「其中：」列示 探明矿区权益 / 未探明矿区权益 / 井及相关设施"
    "（累计折耗层源模板只列 探明矿区权益 与 井及相关设施 两类）。"
    "源模板列示约定：「四、油气资产账面价值合计」层的「本期增加额」「本期减少额」填「—」"
    "（该层为推导层，不作变动分析）。"
    "勾稽：各层 期末余额 = 期初余额 + 本期增加额 − 本期减少额；"
    "四、账面价值合计 = 一、原价合计 − 二、累计折耗合计 − 三、减值准备累计金额合计（逐期成立）；"
    "各层合计行 = 该层「其中：」各类别之和。"
    "另需披露当期在国内和国外发生的取得矿区权益、油气勘探和油气开发各项支出的总额。"
    "数据来源：审定表 H5-1 / 明细表 H5-2 / 折耗测算表 H5-12 / 减值测算表 H5-14。"
)


def _soe_plan() -> list[dict[str, Any]]:
    # rows=None：模板行集已与源模板一致，不动（只补 columns/guidance）
    return [rule(T_MAIN, _COLUMNS, None, _GUIDANCE)]


EXPECTED = {"soe": [T_MAIN]}
_TARGETS = {"soe": (SOE_PATH, SOE_SECTION, _soe_plan)}
_LABELS = {"soe": "note_template_soe.json §八、25 油气资产（国企）"}


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


main = build_cli("附注油气资产章节补齐 columns/guidance（幂等）", _runner, _LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
