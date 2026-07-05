"""G14 信用减值损失 — 专属渲染策略.

componentType: g14-credit-impairment-loss
科目 6702 信用减值损失（借方/损益类）。
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

_G14_ACCOUNT_PREFIX = "6702"
_ADJUDICATED_ITEM_ID = "G14-1-adjudicated-amount"


async def _fetch_tb_pl_amount(ctx: RenderContext) -> dict:
    """损益类 6702：本期发生额 = 借方 - 贷方。"""
    tb: dict[str, float] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(active_filter)
        )
        debit = 0.0
        credit = 0.0
        matched = False
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            if code == _G14_ACCOUNT_PREFIX or code.startswith(_G14_ACCOUNT_PREFIX):
                debit += float(row.debit_amount or 0)
                credit += float(row.credit_amount or 0)
                matched = True
        if matched:
            tb = {"current_amount": debit - credit, "debit_amount": debit, "credit_amount": credit}
    except Exception as e:  # noqa: BLE001
        logger.warning("G14 TB fetch failed: %s", e)
    return tb


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "G14%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        adjudicated_amount = responses_snapshot.get(_ADJUDICATED_ITEM_ID, {}).get("conclusion", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("G14 render failed: %s", e)

    tb_values = await _fetch_tb_pl_amount(ctx)

    return {
        "component_type": "g14-credit-impairment-loss",
        "account_code": _G14_ACCOUNT_PREFIX,
        "prefix": "G14",
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "adjudicated_amount": adjudicated_amount,
    }
