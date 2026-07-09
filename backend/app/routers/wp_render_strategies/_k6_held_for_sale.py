"""K6 持有待售资产和负债 — 专属渲染策略.

componentType: k6-held-for-sale
科目 1481 持有待售资产（借方/资产类） + 2605 持有待售负债（贷方/负债类）。

返回 allResponses + projectContext + TB数据(1481+2605)
供前端 K6-1 审定表试算表列（只读）seed。

**混合口径**：
- 持有待售资产（借方/资产类）：期末 = 期初 + 增加 - 减少 - 减值
- 持有待售负债（贷方/负债类）：期末 = 期初 + 增加 - 减少
**CAS42**：五条件分类 + 减值孰低法。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1481持有待售资产(借方/资产类) + 2605持有待售负债(贷方/负债类)
_K6_ACCOUNT_PREFIXES = {
    "1481": ("hfs_asset_1481_unadjusted", "hfs_asset_1481_audited"),
    "2605": ("hfs_liability_2605_unadjusted", "hfs_liability_2605_audited"),
}

K6_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k6-held-for-sale"},
    {"sheet_name": "持有待售实质性程序表K6A", "component_type": "k6-held-for-sale"},
    {"sheet_name": "审定表K6-1", "component_type": "k6-held-for-sale"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k6-held-for-sale"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k6-held-for-sale"},
    {"sheet_name": "明细表K6-2", "component_type": "k6-held-for-sale"},
    {"sheet_name": "调整分录汇总K6-3", "component_type": "k6-held-for-sale"},
    {"sheet_name": "初始确认检查表K6-4", "component_type": "k6-held-for-sale"},
    {"sheet_name": "减值准备测试表K6-5", "component_type": "k6-held-for-sale"},
    {"sheet_name": "处置组减值测试表K6-6", "component_type": "k6-held-for-sale"},
    {"sheet_name": "检查表(不再满足持有待售)K6-7", "component_type": "k6-held-for-sale"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1481+2605的期初/期末余额及借贷发生额.

    1481 持有待售资产（借方/资产类）- 正数=借方余额
    2605 持有待售负债（贷方/负债类）- 正数=贷方余额
    """
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
            for prefix, (unadj_key, audited_key) in _K6_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K6 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数/审定数（两科目）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1481%' OR standard_account_code LIKE '2605%')
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _K6_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("K6 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/行业）."""
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
        logger.warning("K6 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K6持有待售资产和负债渲染策略：allResponses + projectContext + TB数据（资产+负债双科目）."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K6-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K6 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "k6-held-for-sale",
        "account_codes": ["1481", "2605"],
        "account_directions": {
            "1481": "debit",   # 资产类！借方增加
            "2605": "credit",  # 负债类！贷方增加
        },
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "K6",
        "sheets": K6_SHEETS,
    }
