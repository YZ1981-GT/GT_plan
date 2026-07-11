"""K12 营业外收入 — 专属渲染策略.

component_type = "k12-non-operating-income"

科目6301营业外收入（**损益类/贷方科目**）— K循环损益类最简底稿
**损益类取数逻辑**：从tb_ledger取发生额（credit_amount/debit_amount），NOT 期末余额！
净发生额 = 贷方发生(收入增加) - 借方发生(收入红冲/冲回)

6301营业外收入为贷方科目：贷方=收入增加。
与日常活动无关的利得：政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得等。

与K8(6601)/K9(6602)/K11(6701)同款损益类处理逻辑（方向相反：贷方科目）。

Requirements: 1.6, 5.1
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目：6301营业外收入（损益类/贷方=收入增加，借方=收入冲回/红冲）
_K12_ACCOUNT_PREFIX = "6301"

K12_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k12-non-operating-income"},
    {"sheet_name": "营业外收入实质性程序表K12A", "component_type": "k12-non-operating-income"},
    {"sheet_name": "审定表K12-1", "component_type": "k12-non-operating-income"},
    {"sheet_name": "明细表K12-2", "component_type": "k12-non-operating-income"},
    {"sheet_name": "调整分录汇总K12-3", "component_type": "k12-non-operating-income"},
    {"sheet_name": "营业外收入检查表K12-4", "component_type": "k12-non-operating-income"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k12-non-operating-income"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k12-non-operating-income"},
]


async def _fetch_tb_income_statement(ctx: RenderContext) -> dict:
    """损益类6301：从tb_ledger取发生额（非期末余额！）.

    6301营业外收入为贷方科目：
    - 贷方发生 = 收入增加（政府补助/盘盈/罚款收入等）
    - 借方发生 = 收入冲回/红冲
    - 净发生额 = 贷方 - 借方（正数=净收入）
    - 审定数 = 净发生额

    **关键区别**：K12用tb_ledger取数（非tb_balance），且方向为贷方科目(贷-借)。
    与K8/K9/K11（借方科目，借-贷）方向相反。
    """
    tb: dict[str, float] = {}

    # 从 tb_ledger 取贷方发生额/借方发生额汇总
    try:
        active_filter = await get_active_filter(
            ctx.db, TbLedger.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                sa.func.sum(TbLedger.debit_amount).label("total_debit"),
                sa.func.sum(TbLedger.credit_amount).label("total_credit"),
            ).where(
                active_filter,
                TbLedger.account_code.startswith(_K12_ACCOUNT_PREFIX),
            )
        )
        row = result.fetchone()
        if row and (row.total_debit is not None or row.total_credit is not None):
            debit = float(row.total_debit or 0)
            credit = float(row.total_credit or 0)
            tb = {
                "unadjusted_debit": debit,
                "unadjusted_credit": credit,
                # 6301贷方科目：净发生额=贷方-借方（收入类！）
                "audited_amount": credit - debit,
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K12 TB income statement fetch (tb_ledger) failed: %s", e)

    # 补充：从 trial_balance 取未审数/审定数（如存在）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT SUM(unadjusted_amount) AS unadjusted, SUM(audited_amount) AS audited
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '6301%'
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
        logger.warning("K12 trial_balance fetch failed: %s", e)

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
        logger.warning("K12 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K12营业外收入渲染策略：损益类取发生额（贷方科目！贷-借）.

    核心特殊：
    1. **损益类取发生额**非余额（从tb_ledger取数！）
    2. **贷方科目**：净发生额=贷方-借方（与K8/K9/K11借方科目方向相反）
    3. 营业外收入分类核对（vs其他收益6117/K10）
    4. K循环损益类最简底稿（9 sheets）
    """
    # 1. 加载 checklist_responses 快照
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K12-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K12 render responses load failed: %s", e)

    # 2. 获取TB数据（损益类！取发生额，从tb_ledger）
    tb_values = await _fetch_tb_income_statement(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "k12-non-operating-income",
        "account_codes": ["6301"],
        "income_statement": True,  # 标识损益类
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "K12",
        "sheets": K12_SHEETS,
        "meta": {
            "sheet_count": 8,
            "wp_code": "K12",
            "special_rules": {
                "income_statement": True,
                "account_direction": "credit",  # 贷方科目！（vs K8/K11借方）
                "net_formula": "贷方发生-借方发生",
                "source_table": "tb_ledger",  # 从tb_ledger取数（非tb_balance）
                "non_operating_classification": True,
                "vs_other_gains": "6117(K10)",  # 与日常活动相关的计入其他收益
            },
        },
    }
