"""N5 所得税费用 — 专属渲染策略.

component_type = "n5-income-tax-expense"

N5 前端组件 GtN5IncomeTaxExpense 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/当期计算/纳税调整/税收优惠/研发加计/递延核对等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot + TB数据），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 N5 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目6801所得税费用（**损益类科目**）：取本期发生额（从tb_ledger），而非期末余额
N税费循环最复杂底稿（15 sheet/~95+公式，含82行当期计算表+107行纳税调整大表）。
数据持久化在 checklist_responses 表，item_id 前缀为 "N5-*"。
N3A原底稿标记skip走OnlyOffice fallback。

Requirements: 1.1, 1.6, 1.7, 1.8, 1.9, 1.11
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

_N5_ACCOUNT_CODE = "6801"
_ADJUDICATED_ITEM_ID = "N5-1-adjudicated-amount"

N5_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "所得税审计程序表N5A", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "所得税费用审定表N5-1", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "所得税费用明细表N5-2", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "调整分录汇总N5-3", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "当期所得税费用计算表N5-4", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "纳税调整明细表N5-5", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "税收优惠明细表N5-6", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "加计扣除研发费用情况明细表N5-6-1", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "高新技术企业认定条件检查表N5-6-2", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "财产损失明细表N5-7", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "递延所得税费用核对表N5-8", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "附注披露信息（上市）", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "n5-income-tax-expense"},
    {"sheet_name": "N3A原底稿", "component_type": "n5-income-tax-expense"},
]


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
    except (ValueError, TypeError):
        return 0.0


# ─── TB 取数（损益类！本期发生额，从 tb_ledger）──────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict[str, Any]:
    """从 tb_ledger 取科目6801所得税费用本期发生额（损益类借方）.

    损益类科目取发生额（与N4/H10/I6/L8同款），不取期末余额。
    """
    result: dict[str, Any] = {
        "account_code": _N5_ACCOUNT_CODE,
        "account_name": "所得税费用",
        "direction": "debit",
        "debit_occur": 0,
        "credit_occur": 0,
        "period_amount": 0,
    }
    try:
        active_filter = get_active_filter(ctx.project_id)
        stmt = (
            sa.select(
                sa.func.coalesce(sa.func.sum(TbLedger.debit_amount), 0).label("debit_occur"),
                sa.func.coalesce(sa.func.sum(TbLedger.credit_amount), 0).label("credit_occur"),
            )
            .where(
                TbLedger.project_id == str(ctx.project_id),
                TbLedger.account_code.startswith(_N5_ACCOUNT_CODE),
                active_filter,
            )
        )
        row = (await ctx.db.execute(stmt)).fetchone()
        if row:
            debit = _parse_num(row.debit_occur)
            credit = _parse_num(row.credit_occur)
            result["debit_occur"] = debit
            result["credit_occur"] = credit
            # 损益类借方科目：本期发生额=借方发生额-贷方发生额
            result["period_amount"] = debit - credit
    except Exception as e:  # noqa: BLE001
        logger.warning("N5 render: TB 取数失败: %s", e)
    return result


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """N5 所得税费用专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据。
    前端 GtN5IncomeTaxExpense 为自加载组件（各子组件独立拉取 checklist_responses）。
    """
    # ─── 读取 checklist_responses 快照 ─────────────────────────────────
    responses_snapshot: dict[str, Any] = {}
    adjudicated_amount: float | None = None
    try:
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT item_id, conclusion, remark "
                    "FROM checklist_responses "
                    "WHERE wp_id = :wid"
                ),
                {"wid": str(ctx.wp_id)},
            )
        ).fetchall()
        for r in rows:
            responses_snapshot[r.item_id] = {
                "item_id": r.item_id,
                "conclusion": r.conclusion,
                "remark": r.remark,
            }
        # 提取审定数
        if _ADJUDICATED_ITEM_ID in responses_snapshot:
            raw_adj = responses_snapshot[_ADJUDICATED_ITEM_ID].get("conclusion")
            if raw_adj is not None:
                adjudicated_amount = _parse_num(raw_adj)
    except Exception as e:  # noqa: BLE001
        logger.warning("N5 render: checklist_responses 查询失败: %s", e)

    # ─── 项目上下文 ────────────────────────────────────────────────────
    project_context: dict[str, str] = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    try:
        proj_row = (
            await ctx.db.execute(
                sa.text(
                    "SELECT client_name, audit_year, business_category "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = (
                proj_row.business_category or ctx.business_category or ""
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("N5 render: project context 查询失败: %s", e)

    # ─── TB 取数（科目6801所得税费用，损益类，本期发生额！）────────────────
    tb = await _fetch_tb_data(ctx)

    return {
        "account_code": _N5_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 发生额数据（科目6801，借方/损益类）
        "trial_balance": tb,
        # 损益类公式方向元数据
        "formula_direction": {
            "account_code": "6801",
            "account_name": "所得税费用",
            "direction": "debit",  # 借方/损益类！
            "period_amount_formula": "debit_occur - credit_occur",
            "note": (
                "损益类借方科目：所得税费用增加在借方（确认时借记6801），"
                "取本期发生额（从tb_ledger），而非期末余额。"
                "与N4税金及附加、H10资产处置损益、I6研发费用同款。"
                "所得税费用=当期所得税费用+递延所得税费用。"
            ),
        },
        # N5 特有元数据
        "n5_metadata": {
            "engine": "income_tax_expense",
            "formula": "income_tax_expense = current_tax + deferred_tax",
            "sub_formulas": {
                "taxable_income": "accounting_profit + add_back - deduction",
                "current_tax": "taxable_income × tax_rate",
                "deferred_tax": "liability_increase - asset_increase",
                "rd_super_deduction": "rd_expense × super_rate",
            },
            "cross_wp_links": ["N1", "N3", "N4", "I6", "I2", "A"],
            "skip_sheets": ["N3A"],
        },
        # sheet 列表元数据
        "sheets": N5_SHEETS,
        "component_type": "n5-income-tax-expense",
    }
