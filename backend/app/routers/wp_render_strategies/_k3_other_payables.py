"""K3 其他应付款 — 专属渲染策略.

componentType: k3-other-payables

科目定位**不硬编码前缀**，走报表映射规则链路（共享件
`app/services/four_table/report_line_accounts.py` + 声明真源
`app/services/four_table/k_cycle_specs.py`）::

    报表行 BS-053（上市）/ BS-075（国企）「其他应付款」
      四准则一致：TB('2241','期末余额')
          │ 标准码 → account_mapping 反解
          ▼
    客户原始码：2241 其他应付款（活体子科目树 4 级：
                2241.13.02 代收货款 / 2241.15.04 应付利息 / 2241.98.06 暂收暂存 …）

K3 的科目码本来就是对的 —— 本次修的是**取数口径**的两个静默缺陷：

1. 🔴 **父子双计** —— 原 `_fetch_tb_data` 用
   `code == prefix or code.startswith(prefix)` 遍历全部 `tb_balance` 行累加，
   父科目行 `2241` 与其**全部**子科目行同时被计入 ≈ 真值 2 倍
   （活体项目 `005a6f2d`：父行 −499,561,349.11 + 24 个子科目行）；
   `trial_balance` 侧的 `LIKE '2241%'` 同理。
   现改叶子口径 + 最长前缀归属。
2. 🔴 **缺点号边界** —— 原自造 `_is_leaf` 用 `c.startswith(code)` 判子科目，
   `2241` 会误命中 `22410`（F1/G7 已删过同款）。现用共享件 `select_leaves`。

**负债口径**：期末 = 期初 + 贷方(增加) − 借方(减少)。
`tb_balance` 存在「无符号 + 方向列」与「已带符号」两种约定并存（活体 `2241`
在项目 `005a6f2d` 为 −499,561,349.11、在 `37814426` 为 +98,929,310.93）
→ 对**聚合结果**取绝对值，不在行级翻转方向。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.1, 1.2, 2.1~2.5, 4.1 / Property 1, 2, 8
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

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

_LABEL = "K3 其他应付款"
K3_SPEC = K_CYCLE_SPECS["K3"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测 `wb.sheetnames`）。
#: 🔴 K3 两侧都是**半角**括号，且国企侧是「国企」而非「国有企业」
#: （原 `K3_SHEETS` 写的是全角 +「国有企业」，与源模板不一致 → `?sheet=` 深链落空）。
K3_DISCLOSURE_SHEET_LISTED = "附注披露信息(上市公司)"
K3_DISCLOSURE_SHEET_SOE = "附注披露信息(国企)"

K3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k3-other-payables"},
    {"sheet_name": "实质性程序表K3A", "component_type": "k3-other-payables"},
    {"sheet_name": "审定表K3-1", "component_type": "k3-other-payables"},
    {"sheet_name": K3_DISCLOSURE_SHEET_LISTED, "component_type": "k3-other-payables"},
    {"sheet_name": K3_DISCLOSURE_SHEET_SOE, "component_type": "k3-other-payables"},
    {"sheet_name": "明细表K3-2", "component_type": "k3-other-payables"},
    {"sheet_name": "调整分录汇总K3-3", "component_type": "k3-other-payables"},
    {"sheet_name": "大额其他应付款情况分析表K3-4", "component_type": "k3-other-payables"},
    {"sheet_name": "长期挂账检查表K3-5", "component_type": "k3-other-payables"},
    {"sheet_name": "关联方及交易检查表K3-6", "component_type": "k3-other-payables"},
    {"sheet_name": "其他应付款检查表K3-7", "component_type": "k3-other-payables"},
]

#: `tb_values` 键前缀（**保持不变** —— 前端 `useK3FormData` 在读
#: `other_payable_2241_unadjusted` / `_audited`；K3 科目码本来就对，
#: 键名里的 `2241` 不是错误信息，故不改键名以免静默断链）
_KEY = "other_payable_2241"


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
        "payable_unadjusted": abs(unadj),
        "payable_audited": abs(audited),
        f"{_KEY}_unadjusted": abs(unadj),
        f"{_KEY}_audited": abs(audited),
    }


def build_adjudication_prefill(
    leaves: list[LeafRow], accounts: ReportLineAccounts
) -> list[dict]:
    """按**叶子科目**建 K3-1 审定表行候选（负债口径取余额绝对值）。

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
# DB 访问（全程 fail-open）
# ─────────────────────────────────────────────────────────────────────────────


async def _load_related_parties(ctx: RenderContext) -> list[dict]:
    """关联方清单（供 K3-6 关联方完整性核对）。表不存在时返 ``[]``。"""
    try:
        result = await ctx.db.execute(
            sa.text(
                """
                SELECT name, relation_type, is_controlled_by_same_party
                FROM related_party_registry
                WHERE project_id = :pid AND is_deleted = false
                ORDER BY name
                """
            ),
            {"pid": str(ctx.project_id)},
        )
        return [
            {
                "name": r.name or "",
                "relation_type": r.relation_type or "",
                "is_controlled_by_same_party": bool(r.is_controlled_by_same_party),
            }
            for r in result.fetchall()
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("%s: related_party_registry 加载失败（表可能不存在）: %s", _LABEL, e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# render
# ─────────────────────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    """K3 其他应付款渲染策略：allResponses + projectContext + TB数据 + 取数溯源."""

    responses_snapshot = await load_responses_snapshot(ctx, "K3", limit=2000, label=_LABEL)

    standards = await fetch_applicable_standards(ctx)
    accounts = await resolve_report_line_accounts(ctx, K3_SPEC.spec_for(standards))

    all_rows = await fetch_tb_balance_all(ctx, label=_LABEL)
    leaves = select_leaves(all_rows)
    tb_amounts = await fetch_trial_balance_amounts(
        ctx, list(accounts.gross_standard), label=_LABEL
    )

    tb_values = build_tb_values(leaves, accounts, tb_amounts)
    adjudication_prefill = build_adjudication_prefill(leaves, accounts)

    project_context = await load_project_context(ctx, label=_LABEL)
    audit_year = project_context.get("audit_year") or ""
    project_context["bs_date"] = f"{audit_year}-12-31" if audit_year else ""
    project_context["related_parties"] = await _load_related_parties(ctx)

    source_codes = accounts.as_dict()
    source_codes["nature"] = "balance"
    source_codes["empty_reason"] = None
    source_codes["account_name"] = K3_SPEC.account_name

    return {
        "component_type": "k3-other-payables",
        "account_codes": list(accounts.gross_standard),
        "account_direction": "credit",  # 负债类！贷方增加
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": source_codes,
        "parent_check": build_parent_check(all_rows, leaves, accounts),
        "project_context": project_context,
        "tb_amount": tb_values.get("payable_unadjusted", 0),  # 供前端 K3-1 TB 预填 seed
        "adjudication_prefill": adjudication_prefill,
        "prefix": "K3",
        "sheets": K3_SHEETS,
    }
