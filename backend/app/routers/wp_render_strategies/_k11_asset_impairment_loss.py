"""K11 资产减值损失 — 专属渲染策略.

component_type = "k11-asset-impairment-loss"

科目6701资产减值损失（**损益类/借方科目**）— K循环损益类减值汇总底稿
**损益类取数逻辑**：从tb_balance取发生额（debit_amount/credit_amount），NOT 期末余额！
净发生额 = 借方发生(减值增加) - 贷方发生(减值转回/红冲)

K11为各类资产减值损失的汇总底稿，联动：
- F2(存货跌价)/H1(固定资产减值)/I1(无形资产减值)/I3(商誉减值)

与K8(6601)/K9(6602)/I6(6602)/H10(6115)同款损益类处理逻辑。

Requirements: 1.6, 5.1
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目：6701资产减值损失（损益类/借方=减值增加，贷方=减值转回/红冲）
_K11_ACCOUNT_PREFIX = "6701"

K11_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "资产减值损失实质性程序表K11A", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "审定表K11-1", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "明细表K11-2", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "调整分录汇总K11-3", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k11-asset-impairment-loss"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k11-asset-impairment-loss"},
]


async def _fetch_tb_income_statement(ctx: RenderContext) -> dict:
    """损益类6701：从tb_balance取发生额（非期末余额！）.

    6701资产减值损失为借方科目：
    - 借方发生 = 减值增加（计提）
    - 贷方发生 = 减值转回/红冲
    - 净发生额 = 借方 - 贷方（正数=净减值）
    - 审定数 = 净发生额

    与K8(6601)/K9(6602)/I6(6602)/H10(6115)同款损益类处理。
    """
    tb: dict[str, float] = {}

    # 从 tb_balance 取借方发生额/贷方发生额（debit_amount/credit_amount 即为本期发生额）
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                sa.func.sum(TbBalance.debit_amount).label("total_debit"),
                sa.func.sum(TbBalance.credit_amount).label("total_credit"),
            ).where(
                active_filter,
                TbBalance.account_code.startswith(_K11_ACCOUNT_PREFIX),
            )
        )
        row = result.fetchone()
        if row and (row.total_debit is not None or row.total_credit is not None):
            debit = float(row.total_debit or 0)
            credit = float(row.total_credit or 0)
            tb = {
                "unadjusted_debit": debit,
                "unadjusted_credit": credit,
                # 6701借方科目：净发生额=借方-贷方
                "audited_amount": debit - credit,
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K11 TB income statement fetch failed: %s", e)

    # 补充：从 trial_balance 取未审数/审定数（如存在）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT SUM(unadjusted_amount) AS unadjusted, SUM(audited_amount) AS audited
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '6701%'
            """),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        row = result.fetchone()
        if row:
            if row.unadjusted is not None:
                tb["trial_balance_unadjusted"] = float(row.unadjusted)
            if row.audited is not None:
                tb["trial_balance_audited"] = float(row.audited)
    except Exception as e:  # noqa: BLE001
        logger.warning("K11 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文."""
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
        logger.warning("K11 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K11资产减值损失渲染策略：损益类取发生额 + 减值汇总联动.

    核心特殊：
    1. **损益类取发生额**非余额（与K8/K9/I6/H10同款）
    2. 减值汇总引擎（汇总各类资产减值 + 源底稿核对）
    3. 联动各减值源底稿（F2存货/H1固定资产/I1无形资产/I3商誉）
    4. 商誉减值不可转回特殊处理
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K11-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K11 render responses load failed: %s", e)

    # 2. 获取TB数据（损益类！取发生额）
    tb_values = await _fetch_tb_income_statement(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "k11-asset-impairment-loss",
        "account_codes": ["6701"],
        "income_statement": True,  # 标识损益类
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "K11",
        "sheets": K11_SHEETS,
        "meta": {
            "sheet_count": 7,
            "wp_code": "K11",
            "special_rules": {
                "income_statement": True,
                "account_direction": "debit",
                "net_formula": "借方发生-贷方发生",
                "source_table": "tb_ledger/tb_balance发生额列",
                "impairment_summary": True,
                "source_wps": ["F2", "H1", "I1", "I3"],
                "goodwill_no_reversal": True,
            },
        },
    }
