"""H10 资产处置损益 — 专属渲染策略."""
from __future__ import annotations
import logging
import sqlalchemy as sa
from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from ._context import RenderContext

logger = logging.getLogger(__name__)

_H10_ACCOUNT_PREFIX = "6115"
_ADJUDICATED_ITEM_ID = "H10-1-adjudicated-amount"

H10_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "资产处置损益实质性程序表H10A", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "审定表H10-1", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "明细表H10-2", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "调整分录汇总H10-3", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "检查表H10-4", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h10-asset-disposal-income"},
]


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（对齐 H1/D2 范式：客户名/审计年度/资产负债表日/关联方/变体）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category,
                       p.applicable_standard_v2 AS applicable_standards,
                       p.template_type, p.report_scope
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            audit_year = str(row.audit_year) if row.audit_year else ""
            project_ctx["audit_year"] = audit_year
            project_ctx["business_category"] = row.business_category or ""
            project_ctx["applicable_standards"] = row.applicable_standards or ""
            project_ctx["template_type"] = (
                str(row.template_type.value) if hasattr(row.template_type, "value")
                else (str(row.template_type) if row.template_type else "")
            )
            project_ctx["report_scope"] = (
                str(row.report_scope.value) if hasattr(row.report_scope, "value")
                else (str(row.report_scope) if row.report_scope else "")
            )
            project_ctx["bs_date"] = f"{audit_year}-12-31" if audit_year else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("H10 project context load failed: %s", e)

    # 关联方（供 H10-4 关联方处置检查）
    try:
        rp_result = await ctx.db.execute(
            sa.text(
                "SELECT name, relation_type FROM related_party_registry "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        project_ctx["related_parties"] = [
            {"name": r.name, "relation_type": r.relation_type or ""}
            for r in rp_result.fetchall()
        ]
    except Exception:  # noqa: BLE001
        project_ctx["related_parties"] = []

    return project_ctx


async def _fetch_tb_pl_amount(ctx: RenderContext) -> dict:
    """损益类 6115：本期发生额 = 贷方 - 借方。"""
    tb: dict[str, float] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(active_filter)
        )
        debit = 0.0
        credit = 0.0
        matched = False
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            if code == _H10_ACCOUNT_PREFIX or code.startswith(_H10_ACCOUNT_PREFIX):
                debit += float(row.debit_amount or 0)
                credit += float(row.credit_amount or 0)
                matched = True
        if matched:
            tb = {"current_amount": credit - debit, "debit_amount": debit, "credit_amount": credit}
    except Exception as e:  # noqa: BLE001
        logger.warning("H10 TB fetch failed: %s", e)
    return tb


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H10-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:
        logger.warning("H10 render failed: %s", e)

    tb_values = await _fetch_tb_pl_amount(ctx)
    project_context = await _load_project_context(ctx)

    payload = {
        "component_type": "h10-asset-disposal-income",
        "account_code": _H10_ACCOUNT_PREFIX,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "H10",
        "sheets": H10_SHEETS,
    }

    # ─── 灰度：H/I 四表取数增强（损益类 mode=occurrence） ─────────────────
    from app.core.config import settings
    if settings.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            import asyncio
            from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill
            segment_prefill = await asyncio.wait_for(
                build_d_adjudication_prefill(ctx, account_prefix="6115", mode="occurrence"),
                timeout=5.0,
            )
            payload["adjudication_segment_prefill"] = {
                "segments": [{"segment": "cost", "account_prefix": "6115", "mode": "occurrence", "items": segment_prefill}],
                "enabled": True,
            }
            payload["hi_extraction_enabled"] = True
            # Tier A transient seed（TB核对行）
            from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
            from app.services.d_cycle_extraction.presets import resolve_effective
            from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
            await asyncio.wait_for(
                seed_tier_a_reconciliation(
                    ctx, "H10",
                    responses_snapshot,
                    resolve_effective=resolve_effective,
                    evaluate_wp_formula_expression=evaluate_wp_formula_expression,
                ),
                timeout=5.0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("HI extraction prefill failed (%s): %s", "H10", e)

    return payload
