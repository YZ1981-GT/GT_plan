"""G1 交易性金融资产 — 专属渲染策略."""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

G1_INVEST_TYPES = [
    {"rowKey": "stock", "label": "股票"},
    {"rowKey": "fund", "label": "基金"},
    {"rowKey": "bond", "label": "债券"},
    {"rowKey": "derivative", "label": "衍生工具"},
    {"rowKey": "other", "label": "其他"},
]

G1_MEASURE_TYPES = [
    {"rowKey": "cost", "label": "成本"},
    {"rowKey": "fv-change", "label": "公允价值变动"},
    {"rowKey": "disposal", "label": "处置损益"},
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
                "AND item_id LIKE 'G1-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("G1 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "1501",
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("G1 render: project context 失败: %s", e)

    return {
        "invest_types": G1_INVEST_TYPES,
        "measure_types": G1_MEASURE_TYPES,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": "1501",
    }
