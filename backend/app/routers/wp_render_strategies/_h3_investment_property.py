"""H3 投资性房地产 — 专属渲染策略.

科目1503投资性房地产（借方/资产类）+ 成本模式下1504累计折旧（贷方/资产备抵类）
返回 allResponses + projectContext + TB数据(1503+1504) + measurement_model
双计量模式(成本/公允价值)控制前端显隐
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目前缀：1503投资性房地产(借方) + 1504投资性房地产累计折旧(贷方/备抵，仅成本模式)
_H3_ACCOUNT_PREFIXES = {
    "1503": ("ip_unadjusted", "ip_audited"),        # 投资性房地产原值
    "1504": ("dep_unadjusted", "dep_audited"),      # 累计折旧（成本模式）
}

H3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h3-investment-property"},
    {"sheet_name": "投资性房地产实质性程序表H3A", "component_type": "h3-investment-property"},
    {"sheet_name": "审定表H3-1", "component_type": "h3-investment-property"},
    {"sheet_name": "明细表H3-2", "component_type": "h3-investment-property"},
    {"sheet_name": "调整分录汇总H3-3", "component_type": "h3-investment-property"},
    {"sheet_name": "会计政策检查表H3-4", "component_type": "h3-investment-property"},
    {"sheet_name": "增减检查表H3-5", "component_type": "h3-investment-property"},
    {"sheet_name": "互转审核表H3-6", "component_type": "h3-investment-property"},
    {"sheet_name": "折旧测算表H3-7", "component_type": "h3-investment-property"},
    {"sheet_name": "公允价值复核表H3-8", "component_type": "h3-investment-property"},
    {"sheet_name": "盘点检查表H3-9", "component_type": "h3-investment-property"},
    {"sheet_name": "减值测算表H3-10", "component_type": "h3-investment-property"},
    {"sheet_name": "可收回金额测试表H3-11", "component_type": "h3-investment-property"},
    {"sheet_name": "产权核对表H3-12", "component_type": "h3-investment-property"},
    {"sheet_name": "关联交易检查表H3-13", "component_type": "h3-investment-property"},
    {"sheet_name": "租金收入测算表H3-14", "component_type": "h3-investment-property"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h3-investment-property"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h3-investment-property"},
]


async def _fetch_tb_data(ctx: RenderContext) -> dict:
    """取科目1503+1504的期初/期末余额及未审数（仅汇总叶子科目防双算）."""
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
        all_rows = result.fetchall()

        # 只取叶子科目防止父子双算（叶子=该code不是任何其它code的前缀）
        all_codes = {(r.account_code or "").strip() for r in all_rows}
        relevant_rows = []
        for row in all_rows:
            code = (row.account_code or "").strip()
            is_relevant = any(code == pfx or code.startswith(pfx) for pfx in _H3_ACCOUNT_PREFIXES)
            if not is_relevant:
                continue
            # 叶子判定：没有其它 code 以本 code 为前缀
            is_leaf = not any(c != code and c.startswith(code) for c in all_codes)
            if is_leaf:
                relevant_rows.append(row)

        for row in relevant_rows:
            code = (row.account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H3_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[f"{unadj_key}_opening"] = tb.get(f"{unadj_key}_opening", 0.0) + float(row.opening_balance or 0)
                    tb[f"{unadj_key}_closing"] = tb.get(f"{unadj_key}_closing", 0.0) + float(row.closing_balance or 0)
                    tb[f"{unadj_key}_debit"] = tb.get(f"{unadj_key}_debit", 0.0) + float(row.debit_amount or 0)
                    tb[f"{unadj_key}_credit"] = tb.get(f"{unadj_key}_credit", 0.0) + float(row.credit_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 TB balance fetch failed: %s", e)

    # 从trial_balance取未审数
    try:
        active_filter_tb = await get_active_filter(
            ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year
        ) if hasattr(TrialBalance, '__table__') else None
        result = await ctx.db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1503%' OR standard_account_code LIKE '1504%')
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            for prefix, (unadj_key, audited_key) in _H3_ACCOUNT_PREFIXES.items():
                if code == prefix or code.startswith(prefix):
                    tb[unadj_key] = tb.get(unadj_key, 0.0) + float(row.unadjusted_amount or 0)
                    tb[audited_key] = tb.get(audited_key, 0.0) + float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 trial_balance fetch failed: %s", e)

    # 从trial_balance取6051其他业务收入审定发生额（供前端租金勾稽）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT SUM(audited_amount) AS total
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '6051%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        row = result.fetchone()
        tb["tb_6051_audited"] = float(row.total) if row and row.total else None
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 tb_6051 fetch failed: %s", e)
        tb["tb_6051_audited"] = None

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/适用准则）."""
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
        logger.warning("H3 project context load failed: %s", e)
    return project_ctx


async def _load_measurement_model(ctx: RenderContext) -> str:
    """加载计量模式（cost/fair_value）——从 checklist_responses 中读取."""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT conclusion FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = 'H3-measurement-model' LIMIT 1"
            ),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row and row.conclusion in ("cost", "fair_value"):
            return row.conclusion
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 measurement_model load failed: %s", e)
    return "cost"  # 默认成本模式


async def render(ctx: RenderContext) -> dict | None:
    """H3投资性房地产渲染策略：allResponses + projectContext + TB数据 + measurement_model."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 3000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "H3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("H3 render responses load failed: %s", e)

    tb_values = await _fetch_tb_data(ctx)
    project_context = await _load_project_context(ctx)
    measurement_model = await _load_measurement_model(ctx)

    # 将 tb_6051_audited 从 tb_values 提升到 project_context（前端消费语义更清晰）
    project_context["tb_6051_audited"] = tb_values.pop("tb_6051_audited", None)

    return {
        "component_type": "h3-investment-property",
        "account_codes": ["1503", "1504"],
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "measurement_model": measurement_model,
        "prefix": "H3",
        "sheets": H3_SHEETS,
    }
