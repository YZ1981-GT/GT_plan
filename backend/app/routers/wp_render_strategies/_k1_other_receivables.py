"""K1 其他应收款 — 专属渲染策略.

componentType: k1-other-receivables
科目 1221 其他应收款（借方/资产类）+ 坏账准备（贷方/资产备抵类）。

返回 allResponses + projectContext + TB数据(1221+坏账准备)
供前端 K1-1 审定表试算表列（只读）seed。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1221其他应收款(借方/资产类) + 1231坏账准备(贷方/备抵类)
_K1_ACCOUNT_PREFIXES = {
    "1221": ("receivable_unadjusted", "receivable_audited"),   # 其他应收款
    "1231": ("bad_debt_unadjusted", "bad_debt_audited"),       # 坏账准备
}

K1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k1-other-receivables"},
    {"sheet_name": "其他应收款实质性程序表K1A", "component_type": "k1-other-receivables"},
    {"sheet_name": "审定表K1-1", "component_type": "k1-other-receivables"},
    {"sheet_name": "明细表K1-2", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备明细表K1-3", "component_type": "k1-other-receivables"},
    {"sheet_name": "调整分录汇总K1-4", "component_type": "k1-other-receivables"},
    {"sheet_name": "大额其他应收款情况分析表K1-5", "component_type": "k1-other-receivables"},
    {"sheet_name": "信用减值损失会计政策检查K1-6", "component_type": "k1-other-receivables"},
    {"sheet_name": "三阶段划分检查表K1-7", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备测算K1-8", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备转回收回核销检查表K1-9", "component_type": "k1-other-receivables"},
    {"sheet_name": "长期未收回款项检查表K1-10", "component_type": "k1-other-receivables"},
    {"sheet_name": "关联方及交易检查表K1-11", "component_type": "k1-other-receivables"},
    {"sheet_name": "其他应收款检查表K1-12", "component_type": "k1-other-receivables"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k1-other-receivables"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k1-other-receivables"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1221+1231的期初/期末余额及借贷发生额."""
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
            for prefix, (unadj_key, audited_key) in _K1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数/审定数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1221%' OR standard_account_code LIKE '1231%')
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _K1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 trial_balance fetch failed: %s", e)

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
        logger.warning("K1 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K1其他应收款渲染策略：allResponses + projectContext + TB数据."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K1-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "k1-other-receivables",
        "account_codes": ["1221", "1231"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "K1",
        "sheets": K1_SHEETS,
    }
