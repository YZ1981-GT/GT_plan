"""H10 资产处置损益 — 专属渲染策略."""
from __future__ import annotations
import logging
import sqlalchemy as sa
from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from ._context import RenderContext

logger = logging.getLogger(__name__)

_H10_ACCOUNT_PREFIX = "6115"
_ADJUDICATED_ITEM_ID = "H10-1-adjudicated-amount"

H10_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "资产处置损益实质性程序表H10A", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "审定表H10-1", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "明细表H10-2", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "调整分录汇总H10-3", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "检查表H10-4", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "h10-asset-disposal-income"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "h10-asset-disposal-income"},
]


async def _fetch_tb_pl_amount(ctx: RenderContext) -> dict:
    """损益类 6115：本期发生额 = 贷方 - 借方。"""
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
            if code == _H10_ACCOUNT_PREFIX or code.startswith(_H10_ACCOUNT_PREFIX):
                debit += float(row.debit_amount or 0)
                credit += float(row.credit_amount or 0)
                matched = True
        if matched:
            tb = {"current_amount": credit - debit, "debit_amount": debit, "credit_amount": credit}
    except Exception as e:  # noqa: BLE001
        logger.warning("H10 TB fetch failed: %s", e)
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
            {"wp_id": str(ctx.wp_id), "pfx": "H10-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:
        logger.warning("H10 render failed: %s", e)
    tb_values = await _fetch_tb_pl_amount(ctx)
    return {
        "component_type": "h10-asset-disposal-income",
        "account_code": _H10_ACCOUNT_PREFIX,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "prefix": "H10",
        "sheets": H10_SHEETS,
    }
