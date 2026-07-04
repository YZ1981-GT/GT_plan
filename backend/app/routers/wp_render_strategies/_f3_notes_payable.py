"""F3 应付票据 — 专属渲染策略."""
from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

F3_SHEETS = [
    "F3A",
    "F3-1",
    "F3-2",
    "F3-3",
    "F3-4",
    "F3-5",
    "F3-6",
    "F3-7",
    "附注披露(上市)",
    "附注披露(国企)",
]


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND (item_id LIKE :pfx OR item_id LIKE 'F3A%') LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "F3-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:
        logger.warning("F3 render failed: %s", e)

    return {
        "component_type": "f3-notes-payable",
        "account_code": "2201",
        "prefix": "F3",
        "sheets": F3_SHEETS,
        "responses_snapshot": responses_snapshot,
    }
