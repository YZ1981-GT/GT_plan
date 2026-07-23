"""K3 其他应付款 — 专属渲染策略.

componentType: k3-other-payables
科目 2241 其他应付款（贷方/负债类）。

返回 allResponses + projectContext + TB数据(2241)
供前端 K3-1 审定表试算表列（只读）seed。

**负债口径**：期末 = 期初 + 贷方 - 借方（正数=期末贷方余额）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：2241其他应付款(贷方/负债类)
_K3_ACCOUNT_PREFIXES = {
    "2241": ("payable_unadjusted", "payable_audited"),
}

K3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k3-other-payables"},
    {"sheet_name": "其他应付款实质性程序表K3A", "component_type": "k3-other-payables"},
    {"sheet_name": "审定表K3-1", "component_type": "k3-other-payables"},
    {"sheet_name": "明细表K3-2", "component_type": "k3-other-payables"},
    {"sheet_name": "调整分录汇总K3-3", "component_type": "k3-other-payables"},
    {"sheet_name": "大额其他应付款情况分析表K3-4", "component_type": "k3-other-payables"},
    {"sheet_name": "长期挂账检查表K3-5", "component_type": "k3-other-payables"},
    {"sheet_name": "关联方及交易检查表K3-6", "component_type": "k3-other-payables"},
    {"sheet_name": "其他应付款检查表K3-7", "component_type": "k3-other-payables"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k3-other-payables"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k3-other-payables"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目2241的期初/期末余额及借贷发生额（负债口径：正数=贷方余额）."""
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
            for prefix, (unadj_key, audited_key) in _K3_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K3 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数/审定数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '2241%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _K3_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K3 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/资产负债表日/关联方清单）."""
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
            # bs_date: 资产负债表日（用于截止测试窗口判断）
            year_str = str(row.audit_year) if row.audit_year else ""
            project_ctx["bs_date"] = f"{year_str}-12-31" if year_str else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("K3 project context load failed: %s", e)

    # 加载关联方清单（供K3-6关联方完整性核对）
    try:
        rp_result = await ctx.db.execute(
            sa.text("""
                SELECT name, relation_type, is_controlled_by_same_party
                FROM related_party_registry
                WHERE project_id = :pid AND is_deleted = false
                ORDER BY name
            """),
            {"pid": str(ctx.project_id)},
        )
        related_parties = []
        for rp_row in rp_result.fetchall():
            related_parties.append({
                "name": rp_row.name or "",
                "relation_type": rp_row.relation_type or "",
                "is_controlled_by_same_party": bool(rp_row.is_controlled_by_same_party),
            })
        project_ctx["related_parties"] = related_parties
    except Exception as e:  # noqa: BLE001
        logger.warning("K3 related_party_registry load failed (table may not exist): %s", e)
        project_ctx["related_parties"] = []

    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K3其他应付款渲染策略：allResponses + projectContext + TB数据（负债口径）."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K3 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "k3-other-payables",
        "account_codes": ["2241"],
        "account_direction": "credit",  # 负债类！贷方增加
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "tb_amount": tb_values.get("payable_unadjusted", 0),  # 供前端K3-1 TB预填seed
        "prefix": "K3",
        "sheets": K3_SHEETS,
    }
