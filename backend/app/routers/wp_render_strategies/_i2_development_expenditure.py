"""I2 开发支出 — 专属渲染策略.

component_type = "i2-development-expenditure"

科目1717开发支出（借方/资产类）
返回 allResponses + tb_values(1717) + projectContext + sheets元数据

资产类公式：期末=期初+借方-贷方（科目1717）
三角勾稽：期末=期初+增加(资本化)-减少(转无形/转费用)
核心特殊：CAS6五条件资本化判断 + I6↔I2双向联动 + I1转入联动

Requirements: 1.1-1.10, 2.1-2.7
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1717开发支出(借方/资产类)
_I2_ACCOUNT_PREFIXES = {
    "1717": ("dev_unadjusted", "dev_audited"),
}

I2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i2-development-expenditure"},
    {"sheet_name": "开发支出实质性程序表I2A", "component_type": "i2-development-expenditure"},
    {"sheet_name": "审定表I2-1", "component_type": "i2-development-expenditure"},
    {"sheet_name": "明细表I2-2", "component_type": "i2-development-expenditure"},
    {"sheet_name": "调整分录汇总I2-3", "component_type": "i2-development-expenditure"},
    {"sheet_name": "会计政策检查I2-4", "component_type": "i2-development-expenditure"},
    {"sheet_name": "实质性分析I2-5", "component_type": "i2-development-expenditure"},
    {"sheet_name": "资本化时点判断I2-6", "component_type": "i2-development-expenditure"},
    {"sheet_name": "研发项目构成明细表I2-7", "component_type": "i2-development-expenditure"},
    {"sheet_name": "研发材料投入检查表I2-8", "component_type": "i2-development-expenditure"},
    {"sheet_name": "研发人员认定检查表I2-9", "component_type": "i2-development-expenditure"},
    {"sheet_name": "研发人员工时检查表I2-10", "component_type": "i2-development-expenditure"},
    {"sheet_name": "委外研发检查表I2-11", "component_type": "i2-development-expenditure"},
    {"sheet_name": "针对性检查表I2-12", "component_type": "i2-development-expenditure"},
    {"sheet_name": "截止性测试（账到单据）I2-13", "component_type": "i2-development-expenditure"},
    {"sheet_name": "截止性测试（单据到账）I2-14", "component_type": "i2-development-expenditure"},
    {"sheet_name": "减值准备测试表I2-15", "component_type": "i2-development-expenditure"},
    {"sheet_name": "可收回金额测试I2-16", "component_type": "i2-development-expenditure"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i2-development-expenditure"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i2-development-expenditure"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1717的期初/期末余额及未审数/审定数.

    1717开发支出：借方/资产类，期末=期初+借-贷
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
                TbBalance.account_code.startswith("1717"),
            )
        )
        for row in result.fetchall():
            tb["dev_unadjusted_opening"] = tb.get("dev_unadjusted_opening", 0.0) + float(row.opening_balance or 0)
            tb["dev_unadjusted_closing"] = tb.get("dev_unadjusted_closing", 0.0) + float(row.closing_balance or 0)
            tb["dev_unadjusted_debit"] = tb.get("dev_unadjusted_debit", 0.0) + float(row.debit_amount or 0)
            tb["dev_unadjusted_credit"] = tb.get("dev_unadjusted_credit", 0.0) + float(row.credit_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("I2 TB balance fetch failed: %s", e)

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
                TrialBalance.standard_account_code.like("1717%"),
            )
        )
        for row in result.fetchall():
            tb["dev_unadjusted"] = tb.get("dev_unadjusted", 0.0) + float(row.unadjusted_amount or 0)
            tb["dev_audited"] = tb.get("dev_audited", 0.0) + float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("I2 trial_balance fetch failed: %s", e)

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
        logger.warning("I2 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I2开发支出渲染策略：allResponses + projectContext + TB数据(1717).

    支持selfLoad模式：前端selfLoad时调用render-config获取tb_values种子数据。
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "I2-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I2 render responses load failed: %s", e)

    # 2. 获取TB数据（1717开发支出）
    tb_values = await _fetch_tb_data(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "i2-development-expenditure",
        "account_codes": ["1717"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I2",
        "sheets": I2_SHEETS,
        "meta": {"sheet_count": 20, "wp_code": "I2"},
    }
