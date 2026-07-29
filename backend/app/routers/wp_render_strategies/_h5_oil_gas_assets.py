"""H5 油气资产 — 专属渲染策略.

科目1631油气资产（借方/资产类）+ 1632累计折耗（贷方/资产备抵类）
行业适用性守卫：仅 oil_gas / mining 行业适用
返回 allResponses + projectContext + TB数据(1631+1632) + sheet_list
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1631油气资产(借方) + 1632累计折耗(贷方/备抵)
_H5_ACCOUNT_PREFIXES = {
    "1631": ("cost_unadjusted", "cost_audited"),       # 油气资产原值
    "1632": ("dep_unadjusted", "dep_audited"),         # 累计折耗
}

# 适用行业
_APPLICABLE_INDUSTRIES = {"oil_gas", "mining"}

H5_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "油气资产实质性程序表H5A", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "审定表H5-1", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "明细表H5-2", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "调整分录汇总H5-3", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "闲置检查表H5-4", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "会计政策检查表H5-5", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "分析表H5-6", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "增加检查表H5-7", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "减少检查表H5-8", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "监盘计划H5-9", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "盘点检查表H5-10", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "监盘小结H5-11", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "折耗测算表H5-12", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "折耗分配分析表H5-13", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "减值测算表H5-14", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "可收回金额测试表H5-15", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "权属检查表H5-16", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "关联交易检查表H5-17", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "经营租出检查表H5-18", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "融资租出检查表H5-19", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h5-oil-gas-assets"},
    {"sheet_name": "调整分录汇总H5-3A", "component_type": "h5-oil-gas-assets"},
]


async def _check_industry_applicability(ctx: RenderContext) -> tuple[bool, str]:
    """检查项目行业适用性（oil_gas/mining）."""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT business_category FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        row = result.fetchone()
        if row:
            industry = (row.business_category or "").strip().lower()
            if industry in _APPLICABLE_INDUSTRIES:
                return True, industry
            return False, industry
    except Exception as e:  # noqa: BLE001
        logger.warning("H5 industry check failed: %s", e)
    return False, ""


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1631+1632的期初/期末余额及未审数.

    🔴 叶子过滤防父子双算：只汇总叶子科目（某code不是任何其它code前缀）。
    """
    tb: dict[str, float] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 先拉全部 1631%/1632% 行
        all_h5_filter = sa.or_(
            TbBalance.account_code.like("1631%"),
            TbBalance.account_code.like("1632%"),
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(sa.and_(active_filter, all_h5_filter))
        )
        rows_data = result.fetchall()

        # 叶子判定：某 code 不是任何其它 code 的前缀
        all_codes = {(r.account_code or "").strip() for r in rows_data}

        def _is_leaf(code: str) -> bool:
            for other in all_codes:
                if other != code and other.startswith(code):
                    return False
            return True

        for row in rows_data:
            code = (row.account_code or "").strip()
            if not _is_leaf(code):
                continue
            for prefix, (unadj_key, audited_key) in _H5_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H5 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1631%%' OR standard_account_code LIKE '1632%%')
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H5_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H5 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/行业/适用准则）."""
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
        logger.warning("H5 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """H5油气资产渲染策略：行业校验 + allResponses + projectContext + TB数据.

    行业适用性前后端双重校验（ADR-2）：
    - oil_gas / mining → 正常渲染
    - 其他行业 → 返回 industry_error 信息供前端显示 el-empty
    """
    # ─── 1. 行业适用性守卫 ──────────────────────────────────────────────────
    is_applicable, industry = await _check_industry_applicability(ctx)
    if not is_applicable:
        return {
            "component_type": "h5-oil-gas-assets",
            "industry_error": True,
            "industry_detected": industry,
            "message": "本底稿仅适用于石油天然气/采矿行业项目",
            "applicable_industries": list(_APPLICABLE_INDUSTRIES),
        }

    # ─── 2. 加载 checklist_responses（H5-前缀） ────────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 3000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H5-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H5 render responses load failed: %s", e)

    # ─── 3. TB 数据（1631 + 1632） ─────────────────────────────────────────
    tb_values = await _fetch_tb_data(ctx)

    # ─── 4. 项目上下文 ──────────────────────────────────────────────────────
    project_context = await _load_project_context(ctx)

    payload = {
        "component_type": "h5-oil-gas-assets",
        "account_codes": ["1631", "1632"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "H5",
        "sheets": H5_SHEETS,
        "industry": industry,
    }

    # ─── 灰度：H/I 四表取数增强（仅行业适用时，AFTER industry guard） ──────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill
            segments = []
            cost_items = await asyncio.wait_for(
                build_d_adjudication_prefill(ctx, account_prefix="1631", mode="balance"),
                timeout=5.0,
            )
            if cost_items:
                segments.append({"segment": "cost", "account_prefix": "1631", "mode": "balance", "items": cost_items})
            dep_items = await asyncio.wait_for(
                build_d_adjudication_prefill(ctx, account_prefix="1632", mode="balance"),
                timeout=5.0,
            )
            if dep_items:
                segments.append({"segment": "depletion", "account_prefix": "1632", "mode": "balance", "items": dep_items})
            if segments:
                payload["adjudication_segment_prefill"] = {"segments": segments, "enabled": True}
                payload["hi_extraction_enabled"] = True
            # Tier A transient seed（TB核对行）
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "H5",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "H5", e)

    return payload
