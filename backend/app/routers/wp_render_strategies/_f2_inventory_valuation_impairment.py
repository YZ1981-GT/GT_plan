"""F2 存货计价减值组 — 专属渲染策略."""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

VALUATION_SHEETS = [
    "F2-33", "F2-34", "F2-35",
    "F2-38", "F2-39", "F2-40",
    "F2-41", "F2-42", "F2-43", "F2-44",
    "F2-47", "F2-48", "F2-49", "F2-52",
]


async def render(ctx: RenderContext) -> dict | None:
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND (item_id LIKE 'F2-3%' OR item_id LIKE 'F2-4%' OR item_id LIKE 'F2-5%') "
                "LIMIT 1200"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 valuation render: checklist_responses 失败: %s", e)

    return {
        "valuation_sheets": VALUATION_SHEETS,
        "responses_snapshot": responses_snapshot,
    }
