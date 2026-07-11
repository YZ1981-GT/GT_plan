"""H2 在建工程 — 专属渲染策略.

科目1604在建工程（借方/资产类）
返回 allResponses + projectContext + TB数据(1604)
三角勾稽含转固扣减：期末=期初+增加-减少-转固
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1604在建工程（借方/资产类）
_H2_ACCOUNT_PREFIXES = {
    "1604": ("cip_unadjusted", "cip_audited"),  # 在建工程
}

H2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "在建工程实质性程序表H2A", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "审定表H2-1", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "明细表H2-2", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "调整分录汇总H2-3", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "分析表H2-4", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "转固时点检查表H2-5", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "在建工程审核记录H2-6", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "工程造价比较表H2-7", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "增加检查表H2-8", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "减少检查表H2-9", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "利息资本化测算表（无专门借款）H2-10", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "利息资本化测算表（有专门借款）H2-11", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "监盘计划H2-12", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "盘点检查表H2-13", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "监盘小结H2-14", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "减值测算表H2-15", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "可收回金额测试表H2-16", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "关联交易检查表H2-17", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h2-construction-in-progress"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h2-construction-in-progress"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1604的期初/期末余额及未审数."""
    tb: dict[str, float] = {}
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
            ).where(active_filter)
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H2_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '1604%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H2_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category, p.applicable_standard_v2 AS applicable_standards
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            project_ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            project_ctx["business_category"] = row.business_category or ""
            project_ctx["applicable_standards"] = row.applicable_standards or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """H2在建工程渲染策略：allResponses + projectContext + TB数据."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H2-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H2 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "h2-construction-in-progress",
        "account_codes": ["1604"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "H2",
        "sheets": H2_SHEETS,
    }
