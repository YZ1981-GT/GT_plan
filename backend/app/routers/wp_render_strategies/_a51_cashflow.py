"""A5-1 现金流量表审计 — 极简渲染策略.

component_type = "a5-1-cashflow-audit"
所有逻辑在前端，后端只返回 saved responses.
数据持久化在 checklist_responses 表，item_id 前缀 `a51-`。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """A5-1 现金流量表审计 — 极简渲染策略.

    所有逻辑在前端，后端只返回 saved responses.
    """
    result = await ctx.db.execute(
        sa.text(
            "SELECT item_id, conclusion, remark "
            "FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE 'a51-%'"
        ),
        {"wp_id": str(ctx.wp_id)},
    )
    responses: dict[str, dict] = {}
    for row in result.fetchall():
        responses[row.item_id] = {"conclusion": row.conclusion, "remark": row.remark}
    return {"responses": responses}
