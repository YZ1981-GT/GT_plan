"""F5 主营业务成本 — 专属渲染策略.

除返回 checklist 快照外，为 F5-7 成本倒轧表自动取数：
- 1401 原材料 / 1404 在产品 / 1405 产成品 的期初/期末余额（tb_balance）
供前端 F5-7 校验区只读字段 seed。
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 成本倒轧 TB 取数科目（前缀匹配，兼容明细科目如 140101）
_ROLLFORWARD_ACCOUNTS = {
    "1401": ("openingMaterial", "closingMaterial"),  # 原材料
    "1404": ("openingWIP", "closingWIP"),            # 在产品
    "1405": ("openingFG", "closingFG"),              # 产成品
}


async def _fetch_rollforward_tb(ctx: RenderContext) -> dict:
    """取 1401/1404/1405 期初/期末余额，按父科目前缀聚合。"""
    tb: dict[str, float] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
            ).where(active_filter)
        )
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            for prefix, (open_key, close_key) in _ROLLFORWARD_ACCOUNTS.items():
                if code == prefix or code.startswith(prefix):
                    tb[open_key] = tb.get(open_key, 0.0) + float(row.opening_balance or 0)
                    tb[close_key] = tb.get(close_key, 0.0) + float(row.closing_balance or 0)
                    break
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("F5 rollforward TB fetch failed: %s", e)
    return tb


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    adjudicated_cogs = ""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "F5-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        # F5-7 校验区回退：读取已持久化的审定营业成本
        adjudicated_cogs = responses_snapshot.get("F5-7-adjudicated-cogs", {}).get("remark", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("F5 render failed: %s", e)

    rollforward_tb = await _fetch_rollforward_tb(ctx)

    return {
        "account_code": "6401",
        "responses_snapshot": responses_snapshot,
        "prefix": "F5",
        "rollforward_tb": rollforward_tb,
        "adjudicated_cogs": adjudicated_cogs,
    }
