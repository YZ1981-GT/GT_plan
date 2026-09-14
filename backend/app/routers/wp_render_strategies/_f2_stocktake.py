"""F2 存货监盘 — 渲染策略."""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

STOCKTAKE_SHEETS = [
    "F2-21A", "F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26",
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
                "AND (item_id LIKE 'F2-21%' OR item_id LIKE 'F2-2%') "
                "LIMIT 200"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 stocktake render: checklist_responses 失败: %s", e)

    project_context: dict = {}
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context = {
                "client_name": proj_row.client_name or "",
                "audit_year": str(proj_row.audit_year or ""),
                "business_category": proj_row.business_category or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 stocktake render: project context 失败: %s", e)

    return {
        "sheets": STOCKTAKE_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
