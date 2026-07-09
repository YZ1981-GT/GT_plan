"""N4 税金及附加 — 专属渲染策略（损益类！取本期发生额）.

component_type = "n4-taxes-and-surcharges"
科目 6403 税金及附加 — 损益类借方科目，从 tb_ledger 取本期发生额（借方发生-贷方发生）。

**损益类取数逻辑**：从tb_ledger取发生额（debit_amount/credit_amount），NOT 期末余额！
净发生额 = 借方发生(费用增加) - 贷方发生(费用冲回/红冲)

6403税金及附加为借方科目：借方=费用增加（确认时借记6403）。
与H10资产处置损益、I6研发费用、N5所得税费用同款损益类借方取数逻辑（借-贷）。
与K10(6117贷方科目,贷-借)方向相反。

N税费循环损益类底稿（9 sheet/~110+公式，其中O2A原底稿标记skip）。
数据持久化在 checklist_responses 表，item_id 前缀为 "N4-*"。
O2A原底稿标记skip走OnlyOffice fallback。

Requirements: 1.6, 7.2
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目：6403税金及附加（损益类/借方=费用增加，贷方=费用冲回/红冲）
_N4_ACCOUNT_CODE = "6403"

N4_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "税金及附加审计程序表N4A", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "税金及附加审定表N4-1", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "税金及附加明细表N4-2", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "调整分录汇总N4-3", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "n4-taxes-and-surcharges"},
    {"sheet_name": "O2A原底稿", "component_type": "skip"},
]


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
    except (ValueError, TypeError):
        return 0.0


# ─── TB 取数（损益类！本期发生额，从 tb_ledger）──────────────────────────────


async def _fetch_tb_period_amount(ctx: RenderContext) -> dict[str, Any]:
    """从 tb_ledger 取科目6403税金及附加本期发生额（损益类借方）.

    损益类科目取发生额（与N5/H10/I6/L8同款），不取期末余额。

    6403税金及附加为借方科目：
    - 借方发生 = 费用增加（确认时借记6403）
    - 贷方发生 = 费用冲回/红冲
    - 净发生额 = 借方 - 贷方（正数=净费用）
    - 审定数 = 净发生额（本期发生额）

    **关键区别**：N4用tb_ledger取数（非tb_balance），方向为借方科目(借-贷)。
    与N5(6801)、H10、I6方向一致（借-贷），与K10(6117贷方科目,贷-借)方向相反。
    """
    result: dict[str, Any] = {
        "account_code": _N4_ACCOUNT_CODE,
        "account_name": "税金及附加",
        "direction": "debit",
        "unadjusted_debit": 0.0,
        "unadjusted_credit": 0.0,
        "audited_amount": 0.0,
        "prior_amount": 0.0,
    }

    # 从 tb_ledger 取借方发生额/贷方发生额汇总
    try:
        active_filter = await get_active_filter(
            ctx.db, TbLedger.__table__, ctx.project_id, ctx.year or 0
        )
        stmt = sa.select(
            sa.func.coalesce(sa.func.sum(TbLedger.debit_amount), 0).label("total_debit"),
            sa.func.coalesce(sa.func.sum(TbLedger.credit_amount), 0).label("total_credit"),
        ).where(
            active_filter,
            TbLedger.account_code.startswith(_N4_ACCOUNT_CODE),
        )
        row = (await ctx.db.execute(stmt)).fetchone()
        if row:
            debit = _parse_num(row.total_debit)
            credit = _parse_num(row.total_credit)
            result["unadjusted_debit"] = debit
            result["unadjusted_credit"] = credit
            # 6403借方科目：净发生额=借方-贷方（费用类！）
            result["audited_amount"] = debit - credit
    except Exception as e:  # noqa: BLE001
        logger.warning("N4 render: tb_ledger 损益类取数失败: %s", e)

    # 补充：从 trial_balance 取上期数（如存在）
    try:
        prior_year = (ctx.year or 0) - 1
        if prior_year > 0:
            prior_result = await ctx.db.execute(
                sa.text("""
                    SELECT SUM(audited_amount) AS prior_audited
                    FROM trial_balance
                    WHERE project_id = :pid AND year = :year AND is_deleted = false
                      AND standard_account_code LIKE :code_prefix
                """),
                {
                    "pid": str(ctx.project_id),
                    "year": prior_year,
                    "code_prefix": f"{_N4_ACCOUNT_CODE}%",
                },
            )
            prior_row = prior_result.fetchone()
            if prior_row and prior_row.prior_audited is not None:
                result["prior_amount"] = _parse_num(prior_row.prior_audited)
    except Exception as e:  # noqa: BLE001
        logger.warning("N4 render: trial_balance 上期数查询失败: %s", e)

    return result


async def _load_checklist_responses(ctx: RenderContext) -> dict[str, dict]:
    """加载 checklist_responses 快照（N4- 前缀项）."""
    responses: dict[str, dict] = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark, wp_ref "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "N4-%"},
        )
        for row in result.fetchall():
            responses[row.item_id] = {
                "item_id": row.item_id,
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
                "wp_ref": row.wp_ref or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("N4 render: checklist_responses 查询失败 wp_id=%s: %s", ctx.wp_id, e)
    return responses


async def _load_project_context(ctx: RenderContext) -> dict[str, str]:
    """加载项目上下文."""
    project_ctx: dict[str, str] = {}
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
        logger.warning("N4 render: project context 加载失败: %s", e)
    return project_ctx


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any] | None:
    """N4 税金及附加专属渲染策略：损益类取发生额（借方科目！借-贷）.

    核心特殊：
    1. **损益类取发生额**非余额（从tb_ledger取数！）
    2. **借方科目**：净发生额=借方-贷方（费用类！与N5/H10/I6同款）
    3. 各税种费用确认与N2应交税费计提对应（cross_wp_ref联动）
    4. N税费循环损益类底稿（8 sheets + 1 skip）

    返回轻量 html_data 给前端 GtN4TaxesAndSurcharges 组件 selfLoad 使用。
    实际数据拉取由前端子组件通过 checklist-responses API 完成。
    """
    # 1. 获取TB数据（损益类！取发生额，从tb_ledger）
    tb_values = await _fetch_tb_period_amount(ctx)

    # 2. 加载 checklist_responses 快照（N4- 前缀项）
    checklist_responses = await _load_checklist_responses(ctx)

    # 3. 加载项目上下文
    project_context = await _load_project_context(ctx)

    return {
        "component_type": "n4-taxes-and-surcharges",
        "account_code": _N4_ACCOUNT_CODE,
        "account_direction": "debit",
        "account_category": "expense",
        "data_source": "tb_ledger_period_amount",
        "tb_values": tb_values,
        "checklist_responses": checklist_responses,
        "project_context": project_context,
        "sheets": N4_SHEETS,
        "meta": {
            "sheet_count": 8,
            "wp_code": "N4",
            "special_rules": {
                "income_statement": True,
                "account_direction": "debit",
                "net_formula": "借方发生-贷方发生",
                "source_table": "tb_ledger",
                "n2_cross_verify": True,
                "a_income_statement_link": True,
            },
        },
    }
