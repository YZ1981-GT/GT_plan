"""K7 递延收益 — 专属渲染策略.

componentType: k7-deferred-income
科目 2401 递延收益（贷方/负债类）。

返回 allResponses + projectContext + TB数据(2401)
供前端 K7-1 审定表试算表列（只读）seed。

**负债口径**：期末 = 期初 + 收到(增加) - 分摊(减少)（正数=期末贷方余额）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：2401递延收益(贷方/负债类)
_K7_ACCOUNT_PREFIXES = {
    "2401": ("deferred_income_2401_unadjusted", "deferred_income_2401_audited"),
}

K7_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k7-deferred-income"},
    {"sheet_name": "递延收益实质性程序表K7A", "component_type": "k7-deferred-income"},
    {"sheet_name": "审定表K7-1", "component_type": "k7-deferred-income"},
    {"sheet_name": "明细表K7-2", "component_type": "k7-deferred-income"},
    {"sheet_name": "调整分录汇总K7-3", "component_type": "k7-deferred-income"},
    {"sheet_name": "政府补助分摊测算表K7-4", "component_type": "k7-deferred-income"},
    {"sheet_name": "递延收益检查表K7-5", "component_type": "k7-deferred-income"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k7-deferred-income"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k7-deferred-income"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目2401的期初/期末余额及借贷发生额（负债口径：正数=贷方余额）."""
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
            for prefix, (unadj_key, audited_key) in _K7_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K7 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数/审定数（正数口径v2）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '2401%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _K7_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K7 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category
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
    except Exception as e:  # noqa: BLE001
        logger.warning("K7 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K7递延收益渲染策略：allResponses + projectContext + TB数据（负债口径）."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K7-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K7 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "k7-deferred-income",
        "account_codes": ["2401"],
        "account_direction": "credit",  # 负债类！贷方增加
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "K7",
        "sheets": K7_SHEETS,
    }
