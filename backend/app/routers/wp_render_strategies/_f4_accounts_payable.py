"""F4 应付账款 — 专属渲染策略.

componentType: f4-accounts-payable
科目2202应付账款（贷方/负债类）
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

F4_SHEETS = [
    "F4A",
    "F4-1",
    "附注披露(上市)",
    "附注披露(国企)",
    "F4-2",
    "F4-3",
    "F4-4",
    "F4-5",
    "F4-6",
    "F4-7",
    "F4-8",
    "F4-9",
]


async def render(ctx: RenderContext) -> dict | None:
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND (item_id LIKE :pfx OR item_id LIKE 'F4A%') LIMIT 800"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "F4-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:
        logger.warning("F4 render failed: %s", e)

    return {
        "component_type": "f4-accounts-payable",
        "account_code": "2202",
        "prefix": "F4",
        "sheets": F4_SHEETS,
        "responses_snapshot": responses_snapshot,
    }
