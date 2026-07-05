"""G10 交易性金融负债 — 专属渲染策略."""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

_G10_ACCOUNT_PREFIX = "2101"
_ADJUDICATED_ITEM_ID = "G10-1-adjudicated-amount"

G10_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "交易性金融负债实质性程序表G10A", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "审定表G10-1", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "明细表G10-2", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "调整分录汇总G10-3", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "分类的适当性检查表G10-4", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "公允价值测试表G10-5", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "第三层次公允价值计量的调节表G10-6", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "凭证检查表G10-7", "component_type": "g10-trading-financial-liabilities"},
    {"sheet_name": "衍生金融工具核查表G10-8", "component_type": "g10-trading-financial-liabilities"},
]


async def _fetch_tb_closing_balance(ctx: RenderContext) -> dict:
    """负债类 2101：期末余额 = 贷方 - 借方。"""
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
            if code == _G10_ACCOUNT_PREFIX or code.startswith(_G10_ACCOUNT_PREFIX):
                debit += float(row.debit_amount or 0)
                credit += float(row.credit_amount or 0)
                matched = True
        if matched:
            tb = {"current_amount": credit - debit, "debit_amount": debit, "credit_amount": credit}
    except Exception as e:  # noqa: BLE001
        logger.warning("G10 TB fetch failed: %s", e)
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
            {"wp_id": str(ctx.wp_id), "pfx": "G10-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("G10 render failed: %s", e)
    tb_values = await _fetch_tb_closing_balance(ctx)
    return {
        "component_type": "g10-trading-financial-liabilities",
        "account_code": _G10_ACCOUNT_PREFIX,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        "tb_values": tb_values,
        "prefix": "G10",
        "sheets": G10_SHEETS,
    }
