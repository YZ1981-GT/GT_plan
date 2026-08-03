"""K7 递延收益 — 专属渲染策略.

componentType: k7-deferred-income

科目定位**不硬编码前缀**，走报表映射规则链路（共享件
`app/services/four_table/report_line_accounts.py` + 声明真源
`app/services/four_table/k_cycle_specs.py`）::

    报表行 BS-069（上市）/ BS-095（国企）「递延收益」
      四准则一致：TB('2401','期末余额')
          │ 标准码 → account_mapping 反解
          ▼
    客户原始码：2401 递延收益

K7 的科目码本来就是对的 —— 本次修的是**取数口径**的两个静默缺陷
（与 K3 同款）：

1. 🔴 **父子双计** —— 原 `_fetch_tb_data` 遍历全部 `tb_balance` 行按
   `code == prefix or code.startswith(prefix)` 累加，父行与全部子行同时计入
   ≈ 真值 2 倍；`trial_balance` 侧的 `LIKE '2401%'` 同理。
2. 🔴 **缺点号边界** —— 原自造 `_is_leaf` 用 `c.startswith(code)`，
   `2401` 会误命中 `24010`。

**负债口径**：期末 = 期初 + 收到(贷方增加) − 分摊(借方减少)。
`tb_balance` 两种符号约定并存 → 对**聚合结果**取绝对值，不在行级翻转方向。

**政府补助**：递延收益的主要来源，分摊进「其他收益」（K10 循环 6117）——
两个循环的勾稽由 K7-4 分摊测算表承载。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.1, 1.2, 2.1~2.5, 4.1 / Property 1, 2, 8
"""

from __future__ import annotations

import logging

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    parent_totals,
    select_leaves,
)
from app.services.four_table.report_line_accounts import (
    ReportLineAccounts,
    fetch_applicable_standards,
    resolve_report_line_accounts,
)
from app.services.four_table.tb_fetch import (
    fetch_tb_balance_all,
    fetch_trial_balance_amounts,
    load_project_context,
    load_responses_snapshot,
    sum_amounts,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

_LABEL = "K7 递延收益"
K7_SPEC = K_CYCLE_SPECS["K7"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测 `wb.sheetnames`）。
#: 🔴 K7 国企侧确实是「**国有企业**」（K 循环里唯一一个），不要"顺手改成国企"。
K7_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K7_DISCLOSURE_SHEET_SOE = "附注披露信息（国有企业）"

K7_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k7-deferred-income"},
    {"sheet_name": "实质性程序表K7A", "component_type": "k7-deferred-income"},
    {"sheet_name": "审定表K7-1", "component_type": "k7-deferred-income"},
    {"sheet_name": K7_DISCLOSURE_SHEET_LISTED, "component_type": "k7-deferred-income"},
    {"sheet_name": K7_DISCLOSURE_SHEET_SOE, "component_type": "k7-deferred-income"},
    {"sheet_name": "明细表K7-2", "component_type": "k7-deferred-income"},
    {"sheet_name": "调整分录汇总K7-3", "component_type": "k7-deferred-income"},
    {"sheet_name": "测算表K7-4", "component_type": "k7-deferred-income"},
    {"sheet_name": "递延收益检查表K7-5", "component_type": "k7-deferred-income"},
    {"sheet_name": "会计提示", "component_type": "k7-deferred-income"},
]

#: `tb_values` 键前缀（**保持不变** —— 前端 `useK7FormData` 在读
#: `deferred_income_2401_unadjusted` / `_audited`；K7 科目码本来就对）
_KEY = "deferred_income_2401"


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def build_tb_values(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
    tb_amounts: dict[str, dict[str, float]],
) -> dict[str, float]:
    """组装前端 `tb_values`（负债口径：对聚合结果取绝对值）。"""
    agg = aggregate_leaves(leaves, accounts.gross, absolute=True)
    unadj, audited = sum_amounts(tb_amounts, accounts.gross_standard)
    return {
        f"{_KEY}_opening": agg["opening"],
        f"{_KEY}_closing": agg["closing"],
        f"{_KEY}_debit": agg["debit"],
        f"{_KEY}_credit": agg["credit"],
        f"{_KEY}_unadjusted": abs(unadj),
        f"{_KEY}_audited": abs(audited),
    }


def build_adjudication_prefill(
    leaves: list[LeafRow], accounts: ReportLineAccounts
) -> list[dict]:
    """按**叶子科目**建 K7-1 审定表行候选（负债口径取余额绝对值）。

    返回 ``[{name, code, opening_balance, closing_balance}]``，按期末绝对值降序。
    **宁缺勿造**：科目名为空或期初期末双零的叶子跳过；无命中返 ``[]``。
    """
    rows: list[dict] = []
    for r in filter_by_prefixes(leaves, accounts.gross):
        name = (r.account_name or "").strip()
        if not name:
            continue
        if abs(r.opening) < 0.005 and abs(r.closing) < 0.005:
            continue
        rows.append(
            {
                "name": name,
                "code": r.account_code,
                "opening_balance": abs(r.opening),
                "closing_balance": abs(r.closing),
            }
        )
    rows.sort(key=lambda x: x["closing_balance"], reverse=True)
    return rows


def build_parent_check(
    all_rows: list[LeafRow], leaves: list[LeafRow], accounts: ReportLineAccounts
) -> dict:
    """自检不变量：叶子和 == 父科目行金额（Property 1）。"""
    prefix = (accounts.gross[0] if accounts.gross else "").strip()
    if not prefix:
        return {"prefix": "", "leaf_sum": 0.0, "parent": 0.0, "diff": 0.0}
    leaf_sum = aggregate_leaves(leaves, [prefix])["closing"]
    parent = parent_totals(all_rows, prefix)["closing"]
    return {
        "prefix": prefix,
        "leaf_sum": leaf_sum,
        "parent": parent,
        "diff": leaf_sum - parent,
    }


# ─────────────────────────────────────────────────────────────────────────────
# render
# ─────────────────────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    """K7 递延收益渲染策略：allResponses + projectContext + TB数据 + 取数溯源."""

    responses_snapshot = await load_responses_snapshot(ctx, "K7", limit=2000, label=_LABEL)

    standards = await fetch_applicable_standards(ctx)
    accounts = await resolve_report_line_accounts(ctx, K7_SPEC.spec_for(standards))

    all_rows = await fetch_tb_balance_all(ctx, label=_LABEL)
    leaves = select_leaves(all_rows)
    tb_amounts = await fetch_trial_balance_amounts(
        ctx, list(accounts.gross_standard), label=_LABEL
    )

    tb_values = build_tb_values(leaves, accounts, tb_amounts)
    adjudication_prefill = build_adjudication_prefill(leaves, accounts)
    project_context = await load_project_context(ctx, label=_LABEL)

    source_codes = accounts.as_dict()
    source_codes["nature"] = "balance"
    source_codes["empty_reason"] = None
    source_codes["account_name"] = K7_SPEC.account_name

    return {
        "component_type": "k7-deferred-income",
        "account_codes": list(accounts.gross_standard),
        "account_direction": "credit",  # 负债类！贷方增加
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": source_codes,
        "parent_check": build_parent_check(all_rows, leaves, accounts),
        "project_context": project_context,
        "adjudication_prefill": adjudication_prefill,
        "prefix": "K7",
        "sheets": K7_SHEETS,
    }
