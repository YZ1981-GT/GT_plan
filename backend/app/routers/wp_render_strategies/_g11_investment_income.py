"""G11 投资收益 — 专属渲染策略."""
from __future__ import annotations
import logging
import sqlalchemy as sa
from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from ._context import RenderContext

logger = logging.getLogger(__name__)

_G11_ACCOUNT_PREFIX = "6111"
_ADJUDICATED_ITEM_ID = "G11-1-adjudicated-amount"

G11_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "g11-investment-income"},
    {"sheet_name": "投资收益实质性程序表G11A", "component_type": "g11-investment-income"},
    {"sheet_name": "审定表G11-1", "component_type": "g11-investment-income"},
    {"sheet_name": "明细分析表G11-2", "component_type": "g11-investment-income"},
    {"sheet_name": "调整分录汇总G11-3", "component_type": "g11-investment-income"},
    {"sheet_name": "收益率分析表G11-4", "component_type": "g11-investment-income"},
    {"sheet_name": "凭证检查表G11-5", "component_type": "g11-investment-income"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "g11-investment-income"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "g11-investment-income"},
]


async def _fetch_tb_pl_amount(ctx: RenderContext) -> dict:
    """损益类 6111：本期发生额 = 贷方 - 借方。"""
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
            if code == _G11_ACCOUNT_PREFIX or code.startswith(_G11_ACCOUNT_PREFIX):
                debit += float(row.debit_amount or 0)
                credit += float(row.credit_amount or 0)
                matched = True
        if matched:
            tb = {"current_amount": credit - debit, "debit_amount": debit, "credit_amount": credit}
    except Exception as e:  # noqa: BLE001
        logger.warning("G11 TB fetch failed: %s", e)
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
            {"wp_id": str(ctx.wp_id), "pfx": "G11-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:
        logger.warning("G11 render failed: %s", e)
    tb_values = await _fetch_tb_pl_amount(ctx)
    return {
        "component_type": "g11-investment-income",
        "account_code": _G11_ACCOUNT_PREFIX,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "prefix": "G11",
        "sheets": G11_SHEETS,
    }
