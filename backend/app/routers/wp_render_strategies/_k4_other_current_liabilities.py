"""K4 其他流动负债 — 专属渲染策略.

componentType: k4-other-current-liabilities

科目定位走报表映射规则链路（共享件
`app/services/four_table/report_line_accounts.py` + 声明真源
`app/services/four_table/k_cycle_specs.py`）::

    报表行 BS-058（上市）/ BS-081（国企）「其他流动负债」

🔴 **本循环四表侧无法自动取数 —— 宁缺勿造（DB 只读实证）**

原实现硬编码 `2245`，`report_config` 的公式写 `TB('2301','期末余额')`，
但**两个码在三张表里都零命中**::

    account_chart  : 按码查 2245 / 2301 → 0 条；按名查「其他流动负债」→ 0 条
    tb_balance     : 2245% / 2301% → 0 行（active 数据集）
    trial_balance  : 2245 / 2301   → 0 条

标准科目表（CAS 2006 及其本地化改编两个变体）里**就没有「其他流动负债」这个科目** ——
它在实务中是**报表行**，由多个明细科目按性质归集（一年内到期的非流动负债、
短期应付债券、预计负债流动部分等），归集规则因企业而异。

故按平台铁律**宁缺勿造**：不回退到任何不存在的码，返回空取数结果 +
`tb_source_codes.empty_reason` 留证，审定表走手工录入（前端据此禁用取数类按钮
而非发无效请求）。

**逃生通道**：若某项目确实把其他流动负债挂在某个具体科目上，可在 `report_config`
写项目级覆盖（`applicable_standard = 'project:{project_id}'`）——
`resolve_report_line_accounts` 的优先级链会先命中它，本模块**无需改代码**即生效。
这也是本文件仍走完整解析链路（而不是直接 `return {}`）的原因。

**负债口径**：期末 = 期初 + 贷方(增加) − 借方(减少)。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.4, 4.1, 6.5 / Property 4
"""

from __future__ import annotations

import logging

from app.services.four_table.k_cycle_specs import (
    EMPTY_REASON_NO_ACCOUNT,
    K_CYCLE_SPECS,
)
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    select_leaves,
)
from app.services.four_table.report_line_accounts import (
    ReportLineAccounts,
    fetch_applicable_standards,
    resolve_report_line_accounts,
)
from app.services.four_table.tb_fetch import (
    fetch_tb_balance_leaves,
    fetch_trial_balance_amounts,
    load_project_context,
    load_responses_snapshot,
    sum_amounts,
)

from ._context import RenderContext
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.k_cycle_specs import semantic_spec_of

logger = logging.getLogger(__name__)

_LABEL = "K4 其他流动负债"
K4_SPEC = K_CYCLE_SPECS["K4"]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测 `wb.sheetnames`）。
K4_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K4_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K4_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "实质性程序表 K4A", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "审定表 K4-1", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": K4_DISCLOSURE_SHEET_LISTED, "component_type": "k4-other-current-liabilities"},
    {"sheet_name": K4_DISCLOSURE_SHEET_SOE, "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "明细表 K4-2", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "调整分录汇总 K4-3", "component_type": "k4-other-current-liabilities"},
    {"sheet_name": "其他流动负债检查表 K4-4", "component_type": "k4-other-current-liabilities"},
]

#: `tb_values` 键（**保持不变** —— 前端在读 `liability_unadjusted` / `liability_audited`；
#: 键名本就不含科目码，无需改）
_KEY = "liability"


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def build_tb_values(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
    tb_amounts: dict[str, dict[str, float]],
) -> dict[str, float]:
    """组装前端 `tb_values`（负债口径取绝对值）。

    无科目时**全部返 0** —— 这是宁缺勿造的可观测形态：前端看到 0 且
    `empty_reason` 非空，就知道「不是坏了，是四表侧确实取不到」。
    """
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
    """按叶子科目建 K4-1 审定表行候选。无科目 → ``[]``（宁缺勿造）。"""
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


def build_source_codes(accounts: ReportLineAccounts, account_name: str) -> dict:
    """取数溯源结构；无科目时填 `empty_reason` 供前端展示说明。"""
    out = accounts.as_dict()
    out["nature"] = "balance"
    out["account_name"] = account_name
    out["empty_reason"] = None if accounts.gross else EMPTY_REASON_NO_ACCOUNT
    return out


# ─────────────────────────────────────────────────────────────────────────────
# render
# ─────────────────────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    """K4 其他流动负债渲染策略：allResponses + projectContext + 取数溯源（通常为空）."""

    # 科目定位（语义驱动，additive）
    _sem_spec = semantic_spec_of("K4")
    try:
        _sem_accounts = await resolve_semantic_accounts(ctx, _sem_spec) if _sem_spec else None
    except Exception:  # noqa: BLE001
        _sem_accounts = None

    responses_snapshot = await load_responses_snapshot(ctx, "K4", limit=2000, label=_LABEL)

    standards = await fetch_applicable_standards(ctx)
    accounts = await resolve_report_line_accounts(ctx, K4_SPEC.spec_for(standards))

    # 解析不出科目时不查四表（省一次全表扫），直接给空结果
    if accounts.gross:
        leaves = await fetch_tb_balance_leaves(ctx, label=_LABEL)
        tb_amounts = await fetch_trial_balance_amounts(
            ctx, list(accounts.gross_standard), label=_LABEL
        )
    else:
        logger.info("%s: 报表映射未解析出科目，按宁缺勿造返回空取数结果", _LABEL)
        leaves = []
        tb_amounts = {}

    tb_values = build_tb_values(leaves, accounts, tb_amounts)
    adjudication_prefill = build_adjudication_prefill(leaves, accounts)
    project_context = await load_project_context(ctx, label=_LABEL)

    return {
        "component_type": "k4-other-current-liabilities",
        "account_codes": list(accounts.gross_standard),
        "account_direction": "credit",  # 负债类！贷方增加
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": build_source_codes(accounts, K4_SPEC.account_name),
        "project_context": project_context,
        "adjudication_prefill": adjudication_prefill,
        "prefix": "K4",
        "sheets": K4_SHEETS,
    }
