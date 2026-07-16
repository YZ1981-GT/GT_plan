"""F2 存货底稿核心组 — 专属渲染策略."""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

F2_CATEGORIES = [
    {"rowKey": "raw-materials", "label": "原材料", "account": "1401"},
    {"rowKey": "material-in-transit", "label": "材料采购在途", "account": "1402"},
    {"rowKey": "revolving-materials", "label": "周转材料", "account": "1403"},
    {"rowKey": "semi-finished", "label": "自制半成品", "account": "1404"},
    {"rowKey": "outsourced-processing", "label": "委托加工物资", "account": "1405"},
    {"rowKey": "finished-goods", "label": "库存商品", "account": "1406"},
    {"rowKey": "goods-in-transit", "label": "发出商品", "account": "1407"},
    {"rowKey": "dev-products", "label": "开发产品", "account": "1408"},
    {"rowKey": "dev-costs", "label": "开发成本", "account": "1409"},
    {"rowKey": "contract-performance", "label": "合同履约成本", "account": "1410"},
    {"rowKey": "consumable-bio", "label": "消耗性生物资产", "account": "1411"},
    {"rowKey": "price-difference", "label": "商品进销差价", "account": "1412"},
    {"rowKey": "impairment-provision", "label": "存货跌价准备", "account": "1471"},
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
                "AND item_id LIKE 'F2-%' "
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
        logger.warning("F2 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "applicable_standards": "",
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, applicable_standard_v2 AS applicable_standards "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            raw_std = proj_row.applicable_standards
            if isinstance(raw_std, dict):
                project_context["applicable_standards"] = raw_std.get("type", "")
            else:
                project_context["applicable_standards"] = raw_std or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 render: project context 失败: %s", e)

    return {
        "categories": F2_CATEGORIES,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudication_blocks": ["gross", "impairment", "net"],
    }
