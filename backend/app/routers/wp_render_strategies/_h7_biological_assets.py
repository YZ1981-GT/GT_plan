"""H7 生产性生物资产 — 专属渲染策略.

科目1621生产性生物资产（借方/资产类）+ 累计折旧（贷方/资产备抵类）
行业适用性守卫：仅 agriculture/forestry/livestock/fishery 行业适用
返回 allResponses + projectContext + TB数据(1621) + sheet_list
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1621生产性生物资产(借方)
_H7_ACCOUNT_PREFIXES = {
    "1621": ("cost_unadjusted", "cost_audited"),  # 生产性生物资产原值
}

# 适用行业：农业/林业/畜牧业/渔业
_APPLICABLE_INDUSTRIES = {"agriculture", "forestry", "livestock", "fishery"}

H7_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h7-biological-assets"},
    {"sheet_name": "生物资产实质性程序表H7A", "component_type": "h7-biological-assets"},
    {"sheet_name": "审定表H7-1", "component_type": "h7-biological-assets"},
    {"sheet_name": "明细表H7-2", "component_type": "h7-biological-assets"},
    {"sheet_name": "调整分录汇总H7-3", "component_type": "h7-biological-assets"},
    {"sheet_name": "会计政策检查表H7-4", "component_type": "h7-biological-assets"},
    {"sheet_name": "分析表H7-5", "component_type": "h7-biological-assets"},
    {"sheet_name": "增加检查表H7-6", "component_type": "h7-biological-assets"},
    {"sheet_name": "减少检查表H7-7", "component_type": "h7-biological-assets"},
    {"sheet_name": "监盘计划H7-8", "component_type": "h7-biological-assets"},
    {"sheet_name": "盘点检查表H7-9", "component_type": "h7-biological-assets"},
    {"sheet_name": "监盘小结H7-10", "component_type": "h7-biological-assets"},
    {"sheet_name": "折旧测算表H7-11", "component_type": "h7-biological-assets"},
    {"sheet_name": "折旧分配分析表H7-12", "component_type": "h7-biological-assets"},
    {"sheet_name": "公允价值复核表H7-13", "component_type": "h7-biological-assets"},
    {"sheet_name": "互转审核表H7-14", "component_type": "h7-biological-assets"},
    {"sheet_name": "减值测算表H7-15", "component_type": "h7-biological-assets"},
    {"sheet_name": "可收回金额测试表H7-16", "component_type": "h7-biological-assets"},
    {"sheet_name": "关联交易检查表H7-17", "component_type": "h7-biological-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h7-biological-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h7-biological-assets"},
]


async def _check_industry_applicability(ctx: RenderContext) -> tuple[bool, str]:
    """检查项目行业适用性（agriculture/forestry/livestock/fishery）."""
    try:
        result = await ctx.db.execute(
            sa.text("SELECT business_category FROM projects WHERE id = :pid"),
            {"pid": str(ctx.project_id)},
        )
        row = result.fetchone()
        if row:
            industry = (row.business_category or "").strip().lower()
            if industry in _APPLICABLE_INDUSTRIES:
                return True, industry
            return False, industry
    except Exception as e:  # noqa: BLE001
        logger.warning("H7 industry check failed: %s", e)
    return False, ""


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1621的期初/期末余额及未审数."""
    tb: dict[str, float] = {}
    try:
        active_filter = get_active_filter(ctx.project_id, ctx.year)
        stmt = (
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            )
            .where(
                active_filter,
                TrialBalance.standard_account_code.in_(list(_H7_ACCOUNT_PREFIXES.keys())),
            )
        )
        result = await ctx.db.execute(stmt)
        for row in result.fetchall():
            code = row.standard_account_code
            if code in _H7_ACCOUNT_PREFIXES:
                unadj_key, aud_key = _H7_ACCOUNT_PREFIXES[code]
                tb[unadj_key] = float(row.unadjusted_amount or 0)
                tb[aud_key] = float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("H7 TB fetch failed: %s", e)
    return tb


async def render_h7_biological_assets(ctx: RenderContext) -> dict:
    """H7 生产性生物资产 RENDERER_DISPATCH 入口."""
    # 行业校验
    is_applicable, industry = await _check_industry_applicability(ctx)

    # TB 取数
    tb_data = await _fetch_tb_data(ctx)

    # 构建 html_data
    html_data = {
        "component_type": "h7-biological-assets",
        "industry": industry,
        "is_applicable": is_applicable,
        "measurement_model": "cost",  # 默认成本模式（前端从 checklist_responses 恢复）
        "tb_data": tb_data,
        "sheet_list": H7_SHEETS,
    }

    # ─── 灰度：H/I 四表取数增强（仅行业适用时） ─────────────────────────────
    if is_applicable:
        from app.core.config import settings
        if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
            try:
                import asyncio
                from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill
                segment_prefill = await asyncio.wait_for(
                    build_d_adjudication_prefill(ctx, account_prefix="1621", mode="balance"),
                    timeout=5.0,
                )
                html_data["adjudication_segment_prefill"] = {
                    "segments": [{"segment": "cost", "account_prefix": "1621", "mode": "balance", "items": segment_prefill}],
                    "enabled": True,
                }
                html_data["hi_extraction_enabled"] = True
                # Tier A transient seed（TB核对行）
                if "responses_snapshot" not in html_data:
                    html_data["responses_snapshot"] = {}
                from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
                from app.services.d_cycle_extraction.presets import resolve_effective
                from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
                await asyncio.wait_for(
                    seed_tier_a_reconciliation(
                        ctx, "H7",
                        html_data["responses_snapshot"],
                        resolve_effective=resolve_effective,
                        evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                    ),
                    timeout=5.0,
                )
            except Exception as e:
                logger.warning("HI extraction prefill failed (%s): %s", "H7", e)

    return {
        "sheets": [{"sheet_name": ctx.sheet_name or "底稿目录", "html_data": html_data}],
    }


# Alias for RENDERER_DISPATCH registration pattern
render = render_h7_biological_assets
