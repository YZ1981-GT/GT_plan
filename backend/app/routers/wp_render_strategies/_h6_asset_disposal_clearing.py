"""H6 固定资产清理 — 专属渲染策略.

component_type = "h6-asset-disposal-clearing"

科目1606固定资产清理（借方/资产类，过渡科目）
返回 allResponses + tb_values(1606) + transit_status(期末=0?) + sheets元数据
资产类公式：期末=期初+借方-贷方；审定=未审+AJE+RJE
过渡科目规则：期末余额应为0（清理完毕结转H10）
联动：H1处置(subscribe disposal:initiated) + H10损益(publish disposal:completed)

Requirements: 1.6, 6.3
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1606固定资产清理（借方/资产类，过渡科目）
_H6_ACCOUNT_PREFIX = "1606"

H6_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h6-asset-disposal-clearing"},
    {"sheet_name": "固定资产清理实质性程序表H6A", "component_type": "h6-asset-disposal-clearing"},
    {"sheet_name": "审定表H6-1", "component_type": "h6-asset-disposal-clearing"},
    {"sheet_name": "明细表H6-2", "component_type": "h6-asset-disposal-clearing"},
    {"sheet_name": "调整分录汇总H6-3", "component_type": "h6-asset-disposal-clearing"},
    {"sheet_name": "检查表H6-4", "component_type": "h6-asset-disposal-clearing"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h6-asset-disposal-clearing"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h6-asset-disposal-clearing"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1606的期初/期末余额及未审数/审定数.

    资产类借方科目：期末=期初+借方-贷方
    过渡科目期末应为0。
    """
    tb: dict[str, float] = {}

    # 从 tb_balance 取余额数据（使用 get_active_filter）
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(
                active_filter,
                sa.or_(
                    TbBalance.account_code == _H6_ACCOUNT_PREFIX,
                    TbBalance.account_code.startswith(_H6_ACCOUNT_PREFIX),
                ),
            )
        )
        for row in result.fetchall():
            tb["opening_balance"] = tb.get("opening_balance", 0.0) + float(row.opening_balance or 0)
            tb["closing_balance"] = tb.get("closing_balance", 0.0) + float(row.closing_balance or 0)
            tb["debit_amount"] = tb.get("debit_amount", 0.0) + float(row.debit_amount or 0)
            tb["credit_amount"] = tb.get("credit_amount", 0.0) + float(row.credit_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("H6 TB balance fetch failed: %s", e)

    # 从 trial_balance 取未审数+审定数（使用 get_active_filter 对齐平台口径）
    try:
        tb_active_filter = await get_active_filter(
            ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            ).where(
                tb_active_filter,
                TrialBalance.standard_account_code.like("1606%"),
            )
        )
        for row in result.fetchall():
            tb["unadjusted_amount"] = tb.get("unadjusted_amount", 0.0) + float(row.unadjusted_amount or 0)
            tb["audited_amount"] = tb.get("audited_amount", 0.0) + float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("H6 trial_balance fetch failed: %s", e)

    return tb


def _compute_transit_status(tb_values: dict) -> dict:
    """过渡科目校验：期末余额是否为0.

    Requirements 6.3: 后端在期末报告生成时校验1606余额，不为0时添加审计提醒。
    """
    # 优先使用审定数，其次使用期末余额
    balance = tb_values.get("audited_amount", tb_values.get("closing_balance", 0.0))
    is_zero = abs(balance) < 0.005  # 容差0.005元（避免浮点精度问题）
    return {
        "is_zero": is_zero,
        "balance": balance,
        "message": "✓ 所有清理已结转" if is_zero else f"⚠ 存在未结转项目，余额：{balance:.2f}元",
    }


async def render(ctx: RenderContext) -> dict | None:
    """H6固定资产清理渲染策略：allResponses + tb_values + transit_status + project_context + sheets."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H6-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H6 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    transit_status = _compute_transit_status(tb_values)

    # 加载 project_context（template_type + report_scope 供前端附注变体判定）
    project_context: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.template_type, p.report_scope
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_context["client_name"] = row.client_name or ""
            project_context["audit_year"] = str(row.audit_year) if row.audit_year else ""
            project_context["template_type"] = (
                str(row.template_type.value) if hasattr(row.template_type, "value")
                else (str(row.template_type) if row.template_type else "")
            )
            project_context["report_scope"] = (
                str(row.report_scope.value) if hasattr(row.report_scope, "value")
                else (str(row.report_scope) if row.report_scope else "")
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("H6 project context load failed: %s", e)

    return {
        "component_type": "h6-asset-disposal-clearing",
        "account_codes": ["1606"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "transit_status": transit_status,
        "project_context": project_context,
        "prefix": "H6",
        "sheets": H6_SHEETS,
        "meta": {"sheet_count": 8, "wp_code": "H6"},
    }
