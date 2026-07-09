"""H1 固定资产 — 专属渲染策略.

科目1601固定资产（借方/资产类）+ 1602累计折旧（贷方/资产备抵类）
返回 allResponses + projectContext + TB数据(1601+1602)
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1601固定资产(借方) + 1602累计折旧(贷方/备抵)
_H1_ACCOUNT_PREFIXES = {
    "1601": ("cost_unadjusted", "cost_audited"),       # 固定资产原值
    "1602": ("dep_unadjusted", "dep_audited"),         # 累计折旧
}

H1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h1-fixed-assets"},
    {"sheet_name": "固定资产实质性程序表H1A", "component_type": "h1-fixed-assets"},
    {"sheet_name": "审定表H1-1", "component_type": "h1-fixed-assets"},
    {"sheet_name": "明细表H1-2", "component_type": "h1-fixed-assets"},
    {"sheet_name": "调整分录汇总H1-3", "component_type": "h1-fixed-assets"},
    {"sheet_name": "闲置检查表H1-4", "component_type": "h1-fixed-assets"},
    {"sheet_name": "会计政策估计检查表H1-5", "component_type": "h1-fixed-assets"},
    {"sheet_name": "分析表H1-6", "component_type": "h1-fixed-assets"},
    {"sheet_name": "增加检查表H1-7", "component_type": "h1-fixed-assets"},
    {"sheet_name": "减少检查表H1-8", "component_type": "h1-fixed-assets"},
    {"sheet_name": "监盘计划H1-9", "component_type": "h1-fixed-assets"},
    {"sheet_name": "盘点检查表H1-10", "component_type": "h1-fixed-assets"},
    {"sheet_name": "监盘小结H1-11", "component_type": "h1-fixed-assets"},
    {"sheet_name": "折旧测算表H1-12", "component_type": "h1-fixed-assets"},
    {"sheet_name": "折旧分配分析表H1-13", "component_type": "h1-fixed-assets"},
    {"sheet_name": "减值测算表H1-14", "component_type": "h1-fixed-assets"},
    {"sheet_name": "可收回金额测试表H1-15", "component_type": "h1-fixed-assets"},
    {"sheet_name": "房屋建筑物权属检查表H1-16", "component_type": "h1-fixed-assets"},
    {"sheet_name": "运输设备权属检查表H1-17", "component_type": "h1-fixed-assets"},
    {"sheet_name": "关联交易检查表H1-18", "component_type": "h1-fixed-assets"},
    {"sheet_name": "经营租出固定资产检查表H1-19", "component_type": "h1-fixed-assets"},
    {"sheet_name": "融资租出固定资产检查表H1-20", "component_type": "h1-fixed-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h1-fixed-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h1-fixed-assets"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1601+1602的期初/期末余额及未审数."""
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
            for prefix, (unadj_key, audited_key) in _H1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1601%' OR standard_account_code LIKE '1602%')
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category, p.applicable_standards
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
        logger.warning("H1 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """H1固定资产渲染策略：allResponses + projectContext + TB数据."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H1-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H1 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "h1-fixed-assets",
        "account_codes": ["1601", "1602"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "H1",
        "sheets": H1_SHEETS,
    }
