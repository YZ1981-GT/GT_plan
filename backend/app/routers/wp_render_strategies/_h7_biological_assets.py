"""H7 生产性生物资产 — 专属渲染策略.

科目定位（语义驱动）：
  原值 = 1621 生产性生物资产
  累计折旧 = 1622 生产性生物资产累计折旧
  减值准备 = （无独立编码）
  报表行 BS-030 = TB('1621')

行业适用性守卫：仅 agriculture/forestry/livestock/fishery 行业适用
返回 allResponses + projectContext + TB数据(三层) + sheet_list + tb_source_codes

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h7_account_scope import H7_ACCOUNT_SPEC, H7_SLOT_KEY_PREFIX
from app.services.four_table.semantic_account_resolver import (
    SemanticAccountResult,
    resolve_semantic_accounts,
)
from app.services.four_table.leaf_aggregation import (
    aggregate_leaves,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.parent_check import build_parent_check

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 适用行业：农业/林业/畜牧业/渔业
_APPLICABLE_INDUSTRIES = {"agriculture", "forestry", "livestock", "fishery"}

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


async def _fetch_tb_data(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """按语义槽取生产性生物资产三层数据。"""
    accounts = await resolve_semantic_accounts(ctx, H7_ACCOUNT_SPEC)

    tb_rows: list = []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(active_filter)
        )
        tb_rows = list(result.fetchall())
    except Exception as e:  # noqa: BLE001
        logger.warning("H7 TB balance fetch failed: %s", e)

    trial_rows: list = []
    standard_codes = sorted(
        {c for slot in accounts.slots.values() for c in slot.standard_codes if c}
    )
    if standard_codes:
        try:
            result = await ctx.db.execute(
                sa.text(
                    "SELECT standard_account_code, unadjusted_amount, audited_amount "
                    "FROM trial_balance "
                    "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                    "  AND standard_account_code = ANY(:codes)"
                ),
                {"pid": str(ctx.project_id), "year": ctx.year, "codes": standard_codes},
            )
            trial_rows = list(result.fetchall())
        except Exception as e:  # noqa: BLE001
            logger.warning("H7 trial_balance fetch failed: %s", e)

    tb = _build_h7_tb_values(accounts, tb_rows, trial_rows)
    tb["_parent_check"] = build_parent_check(
        accounts, tb_rows, trial_rows, H7_SLOT_KEY_PREFIX.keys()
    )
    return tb, accounts


def _build_h7_tb_values(accounts: SemanticAccountResult, tb_rows, trial_rows) -> dict[str, float]:
    """按语义槽聚合生产性生物资产各层金额。纯函数。"""
    leaves = select_leaves(to_leaf_rows(tb_rows))
    out: dict[str, float] = {}

    for slot_key, prefix in H7_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        agg = aggregate_leaves(leaves, slot.codes)
        out[f"{prefix}_unadjusted_opening"] = agg["opening"]
        out[f"{prefix}_unadjusted_closing"] = agg["closing"]
        out[f"{prefix}_unadjusted_debit"] = agg["debit"]
        out[f"{prefix}_unadjusted_credit"] = agg["credit"]

    by_code: dict[str, tuple[float, float]] = {}
    for row in trial_rows or []:
        get = row.get if isinstance(row, dict) else (lambda k, _r=row: getattr(_r, k, None))
        code = str(get("standard_account_code") or "").strip()
        if not code:
            continue
        prev = by_code.get(code, (0.0, 0.0))
        by_code[code] = (
            prev[0] + float(get("unadjusted_amount") or 0),
            prev[1] + float(get("audited_amount") or 0),
        )

    for slot_key, prefix in H7_SLOT_KEY_PREFIX.items():
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        wanted = set(slot.standard_codes)
        if not wanted:
            continue
        unadj = sum(v[0] for c, v in by_code.items() if c in wanted)
        audited = sum(v[1] for c, v in by_code.items() if c in wanted)
        out[f"{prefix}_unadjusted"] = unadj
        out[f"{prefix}_audited"] = audited

    return out


async def render_h7_biological_assets(ctx: RenderContext) -> dict:
    """H7 生产性生物资产 RENDERER_DISPATCH 入口."""
    # 行业校验
    is_applicable, industry = await _check_industry_applicability(ctx)

    # TB 取数（语义定位）
    tb_data, accounts = await _fetch_tb_data(ctx)
    resolved_codes = sorted({c for slot in accounts.slots.values() if slot.found for c in slot.codes})

    # 构建 html_data
    html_data = {
        "component_type": "h7-biological-assets",
        "industry": industry,
        "is_applicable": is_applicable,
        "measurement_model": "cost",
        "account_codes": resolved_codes or ["1621"],
        "tb_data": tb_data,
        "tb_source_codes": accounts.as_dict(),
        "sheet_list": H7_SHEETS,
    }

    # ─── 灰度：H/I 四表取数增强（仅行业适用时） ─────────────────────────────
    if is_applicable:
        from app.core.config import settings
        if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
            try:
                import asyncio
                from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill

                segments = []
                for slot_key, prefix in H7_SLOT_KEY_PREFIX.items():
                    slot = accounts.slots.get(slot_key)
                    if not slot or not slot.found:
                        continue
                    for code in slot.codes:
                        seg_items = await asyncio.wait_for(
                            build_d_adjudication_prefill(ctx, account_prefix=code, mode="balance"),
                            timeout=5.0,
                        )
                        if seg_items:
                            segments.append({"segment": slot_key, "account_prefix": code, "mode": "balance", "items": seg_items})

                if segments:
                    html_data["adjudication_segment_prefill"] = {"segments": segments, "enabled": True}
                    html_data["hi_extraction_enabled"] = True
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
