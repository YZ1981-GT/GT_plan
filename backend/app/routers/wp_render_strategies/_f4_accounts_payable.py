"""F4 应付账款 — 专属渲染策略."""
from __future__ import annotations
import logging
import sqlalchemy as sa
from ._context import RenderContext

logger = logging.getLogger(__name__)

async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "F4-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {"conclusion": row.conclusion or "", "remark": row.remark or ""}
    except Exception as e:
        logger.warning("F4 render failed: %s", e)
    return {"account_code": "2202", "responses_snapshot": responses_snapshot, "prefix": "F4"}
