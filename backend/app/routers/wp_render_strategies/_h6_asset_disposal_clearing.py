"""H6 固定资产清理 — 专属渲染策略.

component_type = "h6-asset-disposal-clearing"

科目定位（语义驱动）：
  固定资产清理 = 1606（借方/资产类，过渡科目）
  含于报表行 BS-028（公式 soe: TB('1601')-TB('1602')+TB('1606')）

返回 allResponses + tb_values + transit_status + sheets元数据 + tb_source_codes
过渡科目规则：期末余额应为0（清理完毕结转H10）
联动：H1处置(subscribe) + H10损益(publish)

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.h6_account_scope import H6_ACCOUNT_SPEC, H6_SLOT_KEY_PREFIX
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


async def _fetch_tb_data(ctx: RenderContext) -> tuple[dict, SemanticAccountResult]:
    """按语义槽取固定资产清理数据（单层过渡科目）。"""
    accounts = await resolve_semantic_accounts(ctx, H6_ACCOUNT_SPEC)

    tb: dict[str, float] = {}
    gross_slot = accounts.slots.get("gross")
    if not gross_slot or not gross_slot.found:
        return tb, accounts

    codes = gross_slot.codes

    # tb_balance 叶子聚合
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
        leaves = select_leaves(to_leaf_rows(tb_rows))
        agg = aggregate_leaves(leaves, codes)
        tb["opening_balance"] = agg["opening"]
        tb["closing_balance"] = agg["closing"]
        tb["debit_amount"] = agg["debit"]
        tb["credit_amount"] = agg["credit"]
    except Exception as e:  # noqa: BLE001
        logger.warning("H6 TB balance fetch failed: %s", e)

    # trial_balance 精确匹配
    standard_codes = gross_slot.standard_codes
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
            for row in result.fetchall():
                tb["unadjusted_amount"] = tb.get("unadjusted_amount", 0.0) + float(row.unadjusted_amount or 0)
                tb["audited_amount"] = tb.get("audited_amount", 0.0) + float(row.audited_amount or 0)
        except Exception as e:  # noqa: BLE001
            logger.warning("H6 trial_balance fetch failed: %s", e)

    tb["_parent_check"] = build_parent_check(
        accounts, tb_rows, [], H6_SLOT_KEY_PREFIX.keys()
    )
    return tb, accounts


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

    tb_values, accounts = await _fetch_tb_data(ctx)
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

    resolved_codes = accounts.codes_of("gross") or ["1606"]

    payload = {
        "component_type": "h6-asset-disposal-clearing",
        "account_codes": resolved_codes,
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "transit_status": transit_status,
        "project_context": project_context,
        "prefix": "H6",
        "sheets": H6_SHEETS,
        "meta": {"sheet_count": 8, "wp_code": "H6"},
    }

    # ─── 灰度：H/I 四表取数增强 ───────────────────────────────────────────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill

            segments = []
            gross_slot = accounts.slots.get("gross")
            if gross_slot and gross_slot.found:
                for code in gross_slot.codes:
                    seg_items = await asyncio.wait_for(
                        build_d_adjudication_prefill(ctx, account_prefix=code, mode="balance"),
                        timeout=5.0,
                    )
                    if seg_items:
                        segments.append({"segment": "gross", "account_prefix": code, "mode": "balance", "items": seg_items})

            if segments:
                payload["adjudication_segment_prefill"] = {"segments": segments, "enabled": True}
                payload["hi_extraction_enabled"] = True
            # Tier A transient seed
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "H6",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "H6", e)

    return payload
