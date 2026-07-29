"""I5 其他非流动资产 — 专属渲染策略.

component_type = "i5-other-noncurrent-assets"

科目1911其他非流动资产（借方/资产类）— 最简标准底稿
返回 allResponses + tb_values(1911) + projectContext + sheets元数据

I5核心特点：
- 最简单标准底稿（9 sheets），无特殊逻辑
- 标准资产类三角勾稽：期末=期初+增加-减少
- 审定=未审+AJE+RJE

联动：TB回写(1911) + 附注EventBus + substantive:adjudicated

Requirements: 1.1-1.10, 2.1-2.7
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目：1911其他非流动资产（借方/资产类）
_I5_ACCOUNT_PREFIXES = {
    "1911": ("other_noncurrent_assets_1911_unadjusted", "other_noncurrent_assets_1911_audited"),
}

I5_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "其他非流动资产实质性程序表I5A", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "审定表I5-1", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "明细表I5-2", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "调整分录汇总I5-3", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "针对性检查表I5-4", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i5-other-noncurrent-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i5-other-noncurrent-assets"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1911其他非流动资产的期初/期末余额及未审数/审定数.

    1911其他非流动资产：借方/资产类，期末=期初+借-贷
    标准资产类三角勾稽：期末=期初+增加-减少
    """
    tb: dict[str, float] = {}

    # 从 tb_balance 取期初/期末/借/贷
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
                TbBalance.account_code.startswith("1911"),
            )
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix, (unadj_key, _audited_key) in _I5_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("I5 TB balance fetch failed: %s", e)

    # 从 trial_balance 取未审数+审定数（ORM + get_active_filter 口径统一）
    try:
        tb_filter = await get_active_filter(
            ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            ).where(
                tb_filter,
                TrialBalance.standard_account_code.like("1911%"),
            )
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _I5_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("I5 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则/行业类别）."""
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
        logger.warning("I5 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I5其他非流动资产渲染策略：allResponses + projectContext + TB数据(1911).

    支持selfLoad模式：前端selfLoad时调用render-config获取tb_values种子数据。
    最简标准底稿：标准资产类三角勾稽，期末=期初+增加-减少。
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "I5-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I5 render responses load failed: %s", e)

    # 2. 获取TB数据（1911其他非流动资产）
    tb_values = await _fetch_tb_data(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    payload = {
        "component_type": "i5-other-noncurrent-assets",
        "account_codes": ["1911"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I5",
        "sheets": I5_SHEETS,
        "meta": {
            "sheet_count": 9,
            "wp_code": "I5",
            "special_rules": {
                "simplest_standard": True,
                "triangle_reconciliation": "期末=期初+增加-减少",
                "no_amortization": True,
                "no_impairment_model": True,
            },
        },
    }

    # ─── 灰度：H/I 四表取数增强 ───────────────────────────────────────────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill
            segment_prefill = await asyncio.wait_for(
                build_d_adjudication_prefill(ctx, account_prefix="1911", mode="balance"),
                timeout=5.0,
            )
            payload["adjudication_segment_prefill"] = {
                "segments": [{"segment": "cost", "account_prefix": "1911", "mode": "balance", "items": segment_prefill}],
                "enabled": True,
            }
            payload["hi_extraction_enabled"] = True
            # Tier A transient seed（TB核对行）
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "I5",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("HI extraction prefill failed (%s): %s", "I5", e)

    return payload
