"""I1 无形资产、累计摊销及减值准备 — 专属渲染策略.

component_type = "i1-intangible-assets"

科目1701无形资产（借方/资产类）+ 1702累计摊销（贷方/资产备抵类）+ 1703无形资产减值准备（贷方/资产备抵类）
返回 allResponses + tb_values(1701+1702+1703) + projectContext + sheets元数据

资产类公式：期末=期初+借方-贷方（科目1701）
备抵类公式：期末=期初+贷方-借方（科目1702/1703）
三角勾稽：期末=期初+增加-减少
净值=原值-摊销-减值

联动：TB回写(1701+1702+1703) + I2资本化转入 + 摊销分配(K8/K9/I6) + 附注EventBus

Requirements: 1.1-1.10, 2.1-2.11
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1701无形资产(借方/资产) + 1702累计摊销(贷方/备抵) + 1703减值准备(贷方/备抵)
_I1_ACCOUNT_PREFIXES = {
    "1701": ("cost_unadjusted", "cost_audited"),         # 无形资产原值
    "1702": ("amort_unadjusted", "amort_audited"),       # 累计摊销
    "1703": ("impair_unadjusted", "impair_audited"),     # 无形资产减值准备
}

I1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产实质性程序表I1A", "component_type": "i1-intangible-assets"},
    {"sheet_name": "审定表I1", "component_type": "i1-intangible-assets"},
    {"sheet_name": "明细表I1-2", "component_type": "i1-intangible-assets"},
    {"sheet_name": "调整分录汇总I1-3", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产摊销减值政策检查表I1-4", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产增加检查表I1-5", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产减少明细表I1-6", "component_type": "i1-intangible-assets"},
    {"sheet_name": "使用寿命检查表I1-7", "component_type": "i1-intangible-assets"},
    {"sheet_name": "无形资产权属检查表I1-8", "component_type": "i1-intangible-assets"},
    {"sheet_name": "摊销分配分析表I1-9", "component_type": "i1-intangible-assets"},
    {"sheet_name": "摊销测算表（不含减值）I1-10", "component_type": "i1-intangible-assets"},
    {"sheet_name": "摊销测算表（含减值）I1-11", "component_type": "i1-intangible-assets"},
    {"sheet_name": "减值准备测试表I1-12", "component_type": "i1-intangible-assets"},
    {"sheet_name": "可收回金额测试I1-13", "component_type": "i1-intangible-assets"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i1-intangible-assets"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i1-intangible-assets"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1701+1702+1703的期初/期末余额及未审数/审定数.

    1701无形资产：借方/资产类，期末=期初+借-贷
    1702累计摊销：贷方/备抵类，期末=期初+贷-借
    1703减值准备：贷方/备抵类，期末=期初+贷-借
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
                sa.or_(
                    TbBalance.account_code.startswith("1701"),
                    TbBalance.account_code.startswith("1702"),
                    TbBalance.account_code.startswith("1703"),
                ),
            )
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix, (unadj_key, _audited_key) in _I1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("I1 TB balance fetch failed: %s", e)

    # 从 trial_balance 取未审数+审定数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1701%'
                       OR standard_account_code LIKE '1702%'
                       OR standard_account_code LIKE '1703%')
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _I1_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("I1 trial_balance fetch failed: %s", e)

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
        logger.warning("I1 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I1无形资产渲染策略：allResponses + projectContext + TB数据(1701+1702+1703).

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
            {"wp_id": str(ctx.wp_id), "pfx": "I1-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I1 render responses load failed: %s", e)

    # 2. 获取TB数据（1701无形资产 + 1702累计摊销 + 1703减值准备）
    tb_values = await _fetch_tb_data(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "i1-intangible-assets",
        "account_codes": ["1701", "1702", "1703"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I1",
        "sheets": I1_SHEETS,
        "meta": {"sheet_count": 17, "wp_code": "I1"},
    }
