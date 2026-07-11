"""I3 商誉 — 专属渲染策略.

component_type = "i3-goodwill"

科目1711商誉（借方/资产类）— 商誉不摊销！仅年度减值测试
返回 allResponses + tb_values(1711) + projectContext + sheets元数据

商誉核心特殊：
- 期末=期初+新并购-减值（只减不增，无摊销）
- DCF资产组(CGU)模型是核心
- 减值先冲商誉再分摊至资产组其他资产
- 减值不可转回

联动：TB回写(1711) + 附注EventBus + I3-6→I3-7 DCF联动

Requirements: 1.1-1.10, 2.1-2.8, 5.1-5.5, 6.1-6.7
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目：1711商誉（借方/资产类）— 不摊销，仅减值
_I3_ACCOUNT_PREFIXES = {
    "1711": ("goodwill_unadjusted", "goodwill_audited"),  # 商誉
}

I3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "i3-goodwill"},
    {"sheet_name": "商誉实质性程序表I3A", "component_type": "i3-goodwill"},
    {"sheet_name": "审定表I3-1", "component_type": "i3-goodwill"},
    {"sheet_name": "明细表I3-2", "component_type": "i3-goodwill"},
    {"sheet_name": "调整分录汇总I3-3", "component_type": "i3-goodwill"},
    {"sheet_name": "入账价值测算表I3-4", "component_type": "i3-goodwill"},
    {"sheet_name": "针对性检查表I3-5", "component_type": "i3-goodwill"},
    {"sheet_name": "商誉减值测试I3-6", "component_type": "i3-goodwill"},
    {"sheet_name": "可收回金额测试I3-7", "component_type": "i3-goodwill"},
    {"sheet_name": "复核公司减值测试过程及结论I3-8", "component_type": "i3-goodwill"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "i3-goodwill"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "i3-goodwill"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1711商誉的期初/期末余额及未审数/审定数.

    1711商誉：借方/资产类，期末=期初+借-贷
    商誉不摊销！仅通过减值减少。
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
                TbBalance.account_code.startswith("1711"),
            )
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix, (unadj_key, _audited_key) in _I3_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("I3 TB balance fetch failed: %s", e)

    # 从 trial_balance 取未审数+审定数
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '1711%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _I3_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("I3 trial_balance fetch failed: %s", e)

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
        logger.warning("I3 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """I3商誉渲染策略：allResponses + projectContext + TB数据(1711).

    支持selfLoad模式：前端selfLoad时调用render-config获取tb_values种子数据。
    商誉特殊：不摊销，仅年度减值测试，期末=期初+新并购-减值。
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "I3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("I3 render responses load failed: %s", e)

    # 2. 获取TB数据（1711商誉）
    tb_values = await _fetch_tb_data(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "i3-goodwill",
        "account_codes": ["1711"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "I3",
        "sheets": I3_SHEETS,
        "meta": {
            "sheet_count": 12,
            "wp_code": "I3",
            "special_rules": {
                "no_amortization": True,
                "impairment_only": True,
                "impairment_not_reversible": True,
                "allocation_rule": "先冲商誉再分摊至资产组其他资产",
            },
        },
    }
