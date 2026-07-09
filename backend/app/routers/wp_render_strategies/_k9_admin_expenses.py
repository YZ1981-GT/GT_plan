"""K9 管理费用 — 专属渲染策略.

component_type = "k9-admin-expenses"

科目6602管理费用（**损益类/借方科目**）— K循环损益类底稿
**损益类取数逻辑**：从tb_balance取发生额（debit_amount/credit_amount），NOT 期末余额！
净发生额 = 借方发生(费用增加) - 贷方发生(费用冲回/结转)

与K8(6601销售费用)/I6(6602研发费用)/H10(6115资产处置损益)同款损益类处理逻辑。

联动：TB回写(**发生额**6602) + 截止双向 + 实质性分析 + 附注EventBus

Requirements: 1.6, 7.1-7.2
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目：6602管理费用（损益类/借方=费用增加，贷方=费用冲回）
_K9_ACCOUNT_PREFIX = "6602"

K9_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k9-admin-expenses"},
    {"sheet_name": "管理费用实质性程序表K9A", "component_type": "k9-admin-expenses"},
    {"sheet_name": "审定表K9-1", "component_type": "k9-admin-expenses"},
    {"sheet_name": "明细表K9-2", "component_type": "k9-admin-expenses"},
    {"sheet_name": "调整分录汇总K9-3", "component_type": "k9-admin-expenses"},
    {"sheet_name": "实质性分析K9-4", "component_type": "k9-admin-expenses"},
    {"sheet_name": "合同检查表K9-5", "component_type": "k9-admin-expenses"},
    {"sheet_name": "截止性测试(记账凭证至原始凭证)K9-6", "component_type": "k9-admin-expenses"},
    {"sheet_name": "截止性测试(原始凭证至记账凭证)K9-7", "component_type": "k9-admin-expenses"},
    {"sheet_name": "管理费用检查表K9-8", "component_type": "k9-admin-expenses"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k9-admin-expenses"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k9-admin-expenses"},
]


async def _fetch_tb_income_statement(ctx: RenderContext) -> dict:
    """损益类6602：从tb_balance取发生额（非期末余额！）.

    6602管理费用为借方科目：
    - 借方发生 = 费用增加
    - 贷方发生 = 费用冲回/结转
    - 净发生额 = 借方 - 贷方（正数=净费用）
    - 审定数 = 净发生额

    与K8(6601)/I6(6602)/H10(6115)同款损益类处理。
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
                TbBalance.account_code.startswith(_K9_ACCOUNT_PREFIX),
            )
        )
        row = result.fetchone()
        if row and (row.total_debit is not None or row.total_credit is not None):
            debit = float(row.total_debit or 0)
            credit = float(row.total_credit or 0)
            tb = {
                "unadjusted_debit": debit,
                "unadjusted_credit": credit,
                # 6602借方科目：净发生额=借方-贷方
                "audited_amount": debit - credit,
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K9 TB income statement fetch failed: %s", e)

    # 补充：从 trial_balance 取未审数/审定数（如存在）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT SUM(unadjusted_amount) AS unadjusted, SUM(audited_amount) AS audited
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '6602%'
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
        logger.warning("K9 trial_balance fetch failed: %s", e)

    return tb


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category, p.applicable_standards
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
        logger.warning("K9 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K9管理费用渲染策略：损益类取发生额 + 实质性分析 + 截止双向.

    核心特殊：
    1. **损益类取发生额**非余额（与K8/I6/H10同款）
    2. 实质性分析引擎（同比/环比/占收入比/异常波动识别）
    3. 截止性测试双向（记账凭证→原始凭证 + 原始凭证→记账凭证）
    4. 合同检查（中介服务/咨询/租赁）
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K9-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K9 render responses load failed: %s", e)

    # 2. 获取TB数据（损益类！取发生额）
    tb_values = await _fetch_tb_income_statement(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "k9-admin-expenses",
        "account_codes": ["6602"],
        "income_statement": True,  # 标识损益类
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "K9",
        "sheets": K9_SHEETS,
        "meta": {
            "sheet_count": 12,
            "wp_code": "K9",
            "special_rules": {
                "income_statement": True,
                "account_direction": "debit",
                "net_formula": "借方发生-贷方发生",
                "source_table": "tb_ledger/tb_balance发生额列",
                "substantive_analysis": True,
                "cutoff_test_bidirectional": True,
                "contract_check": True,
            },
        },
    }
