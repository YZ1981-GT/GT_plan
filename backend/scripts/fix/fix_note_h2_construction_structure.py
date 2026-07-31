#!/usr/bin/env python
"""附注「在建工程」章节结构对齐源模板（幂等修订）。

**目标**：附注模板在建工程章节（上市 §五、23 / 国企 §八、23）由 md 重建产物
修正为源模板结构 —— 重建被压扁的两级表头、改名表头首格泄漏值「项  目」→「工程物资」、
删 `header_label` 假数据行、补 `columns`/`guidance`。

历史问题（2026-07-31 实测 + 源 xlsx 精读 `backend/wp_templates/H/H2 在建工程.xlsx`）：

1. **两级表头被压扁**：
   - 上市「在建工程明细」源为 `期末余额{账面余额/减值准备/账面净值}·上年年末余额{…}`（7 列两级），
     模板压成 3 列（项目/期末余额/上年年末余额）。
   - 国企「在建工程」汇总表 + 「（1）在建工程情况」源为 `期末余额{账面余额/减值准备/账面价值}·
     期初余额{…}`（7 列两级），模板压成 3 列。
2. **垃圾表名**：上市第 6 张表在模板中名为表头首格「项  目」，源模板实为「工程物资」
   （行：专用材料/专用设备/工器具/工程物资减值准备/合计）。
3. **假数据行**：上市「在建工程明细」、国企「在建工程」汇总/「（1）在建工程情况」的 `rows[0]`
   为 `row_type: header_label`（压扁的第二行表头残留）。
4. **columns/guidance 全缺**：上市 6 表 + 国企 4 表 `columns=0`（未表态）且无 `guidance`。

裁决要点：

- 两级表头唯一机制 = `ColumnDef.group` → `_column_groups`；列 `key` 逐字镜像前端同步载荷
  `h2DisclosureSyncPayload.ts`（键早已是 `end_book/end_impairment/end_net/prior_*` |
  `end_book/end_impairment/end_carrying/begin_*`，前端只是把两级 label 扁平成「期末余额-账面余额」，
  本脚本改为 `group=期末余额 + label=账面余额`；Task 4 同步改前端 label）。
- 国企末子列为「账面价值」（key `*_carrying`）、期别为「期初余额」（prefix `begin`）；
  上市末子列为「账面净值」（key `*_net`）、期别为「上年年末余额」（prefix `prior`）。
- 单级表列 key 以既有 `buildH2SyncPayload` 为真源（columns-coverage 已验证），禁反向改。
- 汇总/明细行保留 `account_codes`/`report_row_code`（`report_row_code` 陈旧属平台级 data-hygiene，
  本 spec 不动，仅剥离 header_label 假行）。

Usage::

    python backend/scripts/fix/fix_note_h2_construction_structure.py --dry-run
    python backend/scripts/fix/fix_note_h2_construction_structure.py
    python backend/scripts/fix/fix_note_h2_construction_structure.py --check

spec: .kiro/specs/h2-construction-in-progress-disclosure-alignment/ (Task 2)
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
    total_row,
    two_period_columns,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、23"
SOE_SECTION = "八、23"
ALIGNED_BY = "h2-construction-in-progress-disclosure-alignment"

# ── 表名（与 h2NoteSectionMap.ts H2_*_SUBTABLE 及模板 tables[].name 逐字一致）──
T_SUMMARY = "在建工程"
T_L_DETAIL = "在建工程明细"
T_L_MOVE = "重要在建工程项目变动情况"
T_L_CONT = "重要在建工程项目变动情况（续）："
T_L_IMPAIR = "在建工程减值准备情况"
T_L_MATERIALS = "工程物资"
T_L_MATERIALS_OBSOLETE = "项  目"  # 表头首格泄漏名

T_S_DETAIL = "（1）在建工程情况"
T_S_MOVE = "（2）重要在建工程项目本期变动情况"
T_S_IMPAIR = "（3）本期计提在建工程减值准备情况"


# ── 两级列（key 与 h2DisclosureSyncPayload 一致）────────────────────────────
def _listed_detail_cols() -> list[dict[str, Any]]:
    return two_period_columns(
        ("label", "项目"),
        ("期末余额", "上年年末余额"),
        [("book", "账面余额", AMOUNT), ("impairment", "减值准备", AMOUNT), ("net", "账面净值", AMOUNT)],
        prefixes=("end", "prior"),
    )


def _soe_two_level_cols() -> list[dict[str, Any]]:
    return two_period_columns(
        ("label", "项目"),
        ("期末余额", "期初余额"),
        [("book", "账面余额", AMOUNT), ("impairment", "减值准备", AMOUNT), ("carrying", "账面价值", AMOUNT)],
        prefixes=("end", "begin"),
    )


# ── guidance（源模板红字 / 15 号文 / 勾稽提示，不自造披露口径）────────────────
_G_SUMMARY_LISTED = (
    "汇总表：在建工程 + 工程物资 = 合计。勾稽：在建工程行期末余额 = 「在建工程明细」表"
    "账面净值合计；工程物资行 = 「工程物资」表合计；本表合计期末余额 = 资产负债表"
    "「在建工程」项目。底稿可从 H2-1 审定表 / H4 工程物资同步。"
)
_G_DETAIL_LISTED = (
    "两级表头：期末余额 / 上年年末余额 各含 账面余额 / 减值准备 / 账面净值。"
    "勾稽：账面净值 = 账面余额 − 减值准备（每期独立）；各明细行之和 = 合计行。"
    "行按被审计单位实际在建工程项目增删；底稿从 H2-2 明细表同步。"
)
_G_MOVE_LISTED = (
    "重要在建工程项目本期变动：期末余额 = 期初余额 + 本期增加 − 转入固定资产 − 其他减少"
    "（源模板 E=A+B−C−D）。「其中：本期利息资本化金额」为「利息资本化累计金额」的其中项；"
    "本期利息资本化率% 为比例列。"
)
_G_CONT_LISTED = (
    "承「重要在建工程项目变动情况」表：预算数 / 工程累计投入占预算比例% / 工程进度 / 资金来源。"
    "资金来源应区分募股资金、金融机构贷款、自有资金等。（注：工程进度不一定是投入进度。）"
)
_G_IMPAIR_LISTED = (
    "在建工程减值准备变动：期末余额 = 期初余额 + 本期计提 − 本期减少。"
    "【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法、关键参数及其确定依据（15号文）；"
    "本年执行减值测试的，即使未计提减值也应披露。】"
)
_G_MATERIALS_LISTED = (
    "工程物资明细：专用材料 / 专用设备 / 工器具 等，减：工程物资减值准备 = 合计。"
    "勾稽：本表合计 = 汇总表「工程物资」行期末/上年年末余额。"
)
_G_SUMMARY_SOE = (
    "汇总表（两级表头：期末余额 / 期初余额 各含 账面余额 / 减值准备 / 账面价值）："
    "在建工程 + 工程物资 = 合计。勾稽：账面价值 = 账面余额 − 减值准备；"
    "本表合计期末账面价值 = 资产负债表「在建工程」项目。"
)
_G_DETAIL_SOE = (
    "两级表头：期末余额 / 期初余额 各含 账面余额 / 减值准备 / 账面价值。"
    "勾稽：账面价值 = 账面余额 − 减值准备（每期独立）；各明细行之和 = 合计行。"
)
_G_MOVE_SOE = (
    "重要在建工程项目本期变动：期末余额 = 期初余额 + 本期增加 − 本期转入固定资产金额 − "
    "本期其他减少金额。含预算数 / 工程累计投入占预算比例(%) / 工程进度 / 利息资本化累计金额"
    "（其中本期）/ 本期利息资本化率(%) / 资金来源。"
)
_G_IMPAIR_SOE = (
    "本期计提在建工程减值准备：按项目列示本期计提金额及计提原因。"
    "【长期资产减值测试应披露可收回金额的确定方法及关键参数（15号文）。】"
)


def _listed_plan() -> list[dict[str, Any]]:
    return [
        rule(T_SUMMARY, flat_columns([
            ("label", "项目", None),
            ("end_balance", "期末余额", AMOUNT),
            ("prior_balance", "上年年末余额", AMOUNT),
        ]), None, _G_SUMMARY_LISTED),
        # detail：两级 7 列 + 剥离 header_label 假行（seed 保留合计，明细行运行时动态）
        rule(T_L_DETAIL, _listed_detail_cols(), [total_row()], _G_DETAIL_LISTED),
        rule(T_L_MOVE, flat_columns([
            ("label", "工程名称", None),
            ("begin_balance", "期初余额", AMOUNT),
            ("increase", "本期增加", AMOUNT),
            ("transfer_to_fa", "转入固定资产", AMOUNT),
            ("other_decrease", "其他减少", AMOUNT),
            ("interest_cap_accum", "利息资本化累计金额", AMOUNT),
            ("interest_cap_current", "其中：本期利息资本化金额", AMOUNT),
            ("interest_cap_rate", "本期利息资本化率%", None),
            ("end_balance", "期末余额", AMOUNT),
        ]), None, _G_MOVE_LISTED),
        rule(T_L_CONT, flat_columns([
            ("label", "工程名称", None),
            ("budget", "预算数", AMOUNT),
            ("cum_input_pct", "工程累计投入占预算比例%", None),
            ("progress", "工程进度", None),
            ("fund_source", "资金来源", None),
        ]), None, _G_CONT_LISTED),
        rule(T_L_IMPAIR, flat_columns([
            ("label", "项目", None),
            ("begin_balance", "期初余额", AMOUNT),
            ("provision", "本期计提", AMOUNT),
            ("decrease", "本期减少", AMOUNT),
            ("end_balance", "期末余额", AMOUNT),
        ]), None, _G_IMPAIR_LISTED),
        # materials：改名「项  目」→「工程物资」，保留固定行
        rule(T_L_MATERIALS, flat_columns([
            ("label", "项目", None),
            ("end_balance", "期末余额", AMOUNT),
            ("prior_balance", "上年年末余额", AMOUNT),
        ]), None, _G_MATERIALS_LISTED, aliases=[T_L_MATERIALS_OBSOLETE]),
    ]


# 国企汇总表行（剥离 header_label，保留 account_codes / report_row_code）
_SOE_SUMMARY_ROWS: list[dict[str, Any]] = [
    {"label": "在建工程", "account_codes": ["1604"], "report_row_code": "BS-015", "row_type": "data"},
    {"label": "工程物资", "account_codes": ["1605"], "row_type": "data"},
    total_row(),
]


def _soe_plan() -> list[dict[str, Any]]:
    return [
        rule(T_SUMMARY, _soe_two_level_cols(), _SOE_SUMMARY_ROWS, _G_SUMMARY_SOE),
        rule(T_S_DETAIL, _soe_two_level_cols(), [total_row()], _G_DETAIL_SOE),
        rule(T_S_MOVE, flat_columns([
            ("label", "项目名称", None),
            ("budget", "预算数", AMOUNT),
            ("begin_balance", "期初余额", AMOUNT),
            ("increase", "本期增加", AMOUNT),
            ("transfer_to_fa", "本期转入固定资产金额", AMOUNT),
            ("other_decrease", "本期其他减少金额", AMOUNT),
            ("end_balance", "期末余额", AMOUNT),
            ("cum_input_pct", "工程累计投入占预算比例(%)", None),
            ("progress", "工程进度", None),
            ("interest_cap_accum", "利息资本化累计金额", AMOUNT),
            ("interest_cap_current", "其中：本期利息资本化金额", AMOUNT),
            ("interest_cap_rate", "本期利息资本化率(%)", None),
            ("fund_source", "资金来源", None),
        ]), None, _G_MOVE_SOE),
        rule(T_S_IMPAIR, flat_columns([
            ("label", "项目", None),
            ("provision_amount", "本期计提金额", AMOUNT),
            ("reason", "计提原因", None),
        ]), None, _G_IMPAIR_SOE),
    ]


EXPECTED = {
    "listed": [T_SUMMARY, T_L_DETAIL, T_L_MOVE, T_L_CONT, T_L_IMPAIR, T_L_MATERIALS],
    "soe": [T_SUMMARY, T_S_DETAIL, T_S_MOVE, T_S_IMPAIR],
}

_TARGETS = {
    "listed": (LISTED_PATH, LISTED_SECTION, _listed_plan),
    "soe": (SOE_PATH, SOE_SECTION, _soe_plan),
}
_LABELS = {
    "listed": "note_template_listed.json §五、23 在建工程（上市）",
    "soe": "note_template_soe.json §八、23 在建工程（国企）",
}
def _runner(key: str, dry_run: bool, check: bool):
    # 「项  目」→「工程物资」走 rule aliases 改名（保留固定行），不能进 drops
    # （drop_tables 在 apply_plan 之前执行，会把待改名的表连同行一起删掉）。
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


main = build_cli("附注在建工程章节结构对齐源模板（幂等）", _runner, _LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
