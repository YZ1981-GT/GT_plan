"""G9 其他非流动金融资产 — 专属渲染策略."""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

_G9_ACCOUNT_PREFIX = "1504"
_ADJUDICATED_ITEM_ID = "G9-1-adjudicated-amount"

G9_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "其他非流动金融资产实质性程序表G9A", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "审定表G9-1", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "附注披露信息（国企）", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "明细表G9-2", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "调整分录汇总G9-3", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "公允价值测试表G9-4", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "第三层次公允价值计量的调节表G9-5", "component_type": "g9-other-noncurrent-financial"},
    {"sheet_name": "凭证检查表G9-6", "component_type": "g9-other-noncurrent-financial"},
]


async def _fetch_tb_closing_balance(ctx: RenderContext) -> dict:
    """资产类 1504：期末余额 = 借方 - 贷方。"""
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
            if code == _G9_ACCOUNT_PREFIX or code.startswith(_G9_ACCOUNT_PREFIX):
                debit += float(row.debit_amount or 0)
                credit += float(row.credit_amount or 0)
                matched = True
        if matched:
            tb = {"current_amount": debit - credit, "debit_amount": debit, "credit_amount": credit}
    except Exception as e:  # noqa: BLE001
        logger.warning("G9 TB fetch failed: %s", e)
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
            {"wp_id": str(ctx.wp_id), "pfx": "G9-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("G9 responses fetch failed: %s", e)

    tb = await _fetch_tb_closing_balance(ctx)
    return {
        "account_code": _G9_ACCOUNT_PREFIX,
        "responses_snapshot": responses_snapshot,
        "prefix": "G9",
        "adjudicated_amount": adjudicated_amount,
        "trial_balance": tb,
        "sheets": G9_SHEETS,
        "component_type": "g9-other-noncurrent-financial",
    }
