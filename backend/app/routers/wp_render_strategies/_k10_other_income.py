"""K10 其他收益底稿 — 专属 HTML 渲染策略（损益类！取发生额）

component_type = "k10-other-income"
科目 6117 其他收益 — 损益类贷方科目，从 tb_ledger 取本期发生额（贷方发生-借方发生）。

**损益类取数逻辑**：从tb_ledger取发生额（credit_amount/debit_amount），NOT 期末余额！
净发生额 = 贷方发生(收益增加) - 借方发生(收益红冲/冲回)

6117其他收益为贷方科目：贷方=收益增加。
与日常活动相关的政府补助→其他收益(6117)；与日常活动无关→营业外收入(6301,K12)。

与K12(6301)同款损益类贷方科目处理逻辑（方向一致：贷-借）。

Spec: .kiro/specs/k10-other-income/
Requirements: 1.6, 6.1
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目：6117其他收益（损益类/贷方=收益增加，借方=收益冲回/红冲）
_K10_ACCOUNT_PREFIX = "6117"

K10_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k10-other-income"},
    {"sheet_name": "其他收益实质性程序表K10A", "component_type": "k10-other-income"},
    {"sheet_name": "审定表K10-1", "component_type": "k10-other-income"},
    {"sheet_name": "明细表K10-2", "component_type": "k10-other-income"},
    {"sheet_name": "调整分录汇总K10-3", "component_type": "k10-other-income"},
    {"sheet_name": "政府补助核对表K10-4", "component_type": "k10-other-income"},
    {"sheet_name": "应收政府补助检查表K10-5", "component_type": "k10-other-income"},
    {"sheet_name": "其他收益检查表K10-6", "component_type": "k10-other-income"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "k10-other-income"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "k10-other-income"},
]


async def _fetch_tb_income_statement(ctx: RenderContext) -> dict:
    """损益类6117：从tb_ledger取发生额（非期末余额！）.

    6117其他收益为贷方科目：
    - 贷方发生 = 收益增加（政府补助-即征即退/财政贴息/研发补助/稳岗补贴等）
    - 借方发生 = 收益冲回/红冲
    - 净发生额 = 贷方 - 借方（正数=净收益）
    - 审定数 = 净发生额

    **关键区别**：K10用tb_ledger取数（非tb_balance），方向为贷方科目(贷-借)。
    与K12(6301)方向一致，与K13(6711借方科目，借-贷)方向相反。
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
                TbLedger.account_code.startswith(_K10_ACCOUNT_PREFIX),
            )
        )
        row = result.fetchone()
        if row and (row.total_debit is not None or row.total_credit is not None):
            debit = float(row.total_debit or 0)
            credit = float(row.total_credit or 0)
            tb = {
                "unadjusted_debit": debit,
                "unadjusted_credit": credit,
                # 6117贷方科目：净发生额=贷方-借方（收益类！）
                "audited_amount": credit - debit,
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K10 TB income statement fetch (tb_ledger) failed: %s", e)

    # 补充：从 trial_balance 取未审数/审定数（如存在）
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT SUM(unadjusted_amount) AS unadjusted, SUM(audited_amount) AS audited
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '6117%'
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
        logger.warning("K10 trial_balance fetch failed: %s", e)

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
        logger.warning("K10 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K10其他收益渲染策略：损益类取发生额（贷方科目！贷-借）.

    核心特殊：
    1. **损益类取发生额**非余额（从tb_ledger取数！）
    2. **贷方科目**：净发生额=贷方-借方（与K12(6301)方向一致）
    3. 政府补助核对（与K7递延收益分摊一致性校验）
    4. K循环损益类底稿（10 sheets）
    """
    # 1. 加载 checklist_responses 快照（K10- 前缀项）
    all_responses: dict[str, dict] = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark, wp_ref "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K10-%"},
        )
        for row in result.fetchall():
            all_responses[row.item_id] = {
                "item_id": row.item_id,
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
                "wp_ref": row.wp_ref or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K10 render responses load failed wp_id=%s: %s", ctx.wp_id, e)

    # 2. 获取TB数据（损益类！取发生额，从tb_ledger）
    tb_values = await _fetch_tb_income_statement(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "k10-other-income",
        "account_codes": ["6117"],
        "income_statement": True,  # 标识损益类
        "allResponses": all_responses,
        "tb_values": tb_values,
        "project_context": project_context,
        "prefix": "K10",
        "sheets": K10_SHEETS,
        "meta": {
            "sheet_count": 10,
            "wp_code": "K10",
            "special_rules": {
                "income_statement": True,
                "account_direction": "credit",  # 贷方科目！
                "net_formula": "贷方发生-借方发生",
                "source_table": "tb_ledger",  # 从tb_ledger取数（非tb_balance）
                "grant_reconcile": True,  # 政府补助核对（与K7递延收益联动）
                "vs_non_operating": "6301(K12)",  # 与日常活动无关计入营业外收入
            },
        },
    }
