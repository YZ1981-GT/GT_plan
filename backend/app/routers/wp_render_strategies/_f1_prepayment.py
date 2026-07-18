"""F1 预付账款 — 专属渲染策略.

component_type = "f1-prepayment"
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """F1 预付账款渲染策略."""
    wp_id = ctx.wp_id
    db = ctx.db

    adjudication_config = {
        "nature_rows": [
            {"rowKey": "goods-payment", "label": "货款"},
            {"rowKey": "project-payment", "label": "工程款"},
            {"rowKey": "equipment-payment", "label": "设备款"},
            {"rowKey": "service-payment", "label": "服务费"},
            {"rowKey": "other", "label": "其他"},
        ],
        "aging_rows": [
            {"rowKey": "within-1-year", "label": "1年以内含1年"},
            {"rowKey": "1-to-2-years", "label": "1至2年含2年"},
            {"rowKey": "2-to-3-years", "label": "2至3年含3年"},
            {"rowKey": "over-3-years", "label": "3年以上"},
        ],
    }

    sections = [
        {"code": "F1A", "label": "F1A 程序表", "type": "procedure"},
        {"code": "F1-1", "label": "F1-1 审定表", "type": "adjudication"},
        {"code": "F1-2", "label": "F1-2 明细表", "type": "detail"},
        {"code": "F1-3", "label": "F1-3 调整分录", "type": "adjustment"},
        {"code": "F1-4", "label": "F1-4 实质性分析", "type": "analysis"},
        {"code": "F1-5", "label": "F1-5 长期挂款检查", "type": "long_term"},
        {"code": "F1-6", "label": "F1-6 关联方检查", "type": "related_party"},
        {"code": "F1-7", "label": "F1-7 综合检查", "type": "comprehensive_check"},
        {"code": "F1-NOTE", "label": "附注", "type": "disclosure"},
        {"code": "F1-CONF", "label": "函证程序", "type": "confirmation_procedure"},
    ]

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'F1-%' "
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
        logger.warning("F1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category, "
                "applicable_standard_v2 AS applicable_standards "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = proj_row.business_category or ""
            raw_standards = proj_row.applicable_standards
            # applicable_standard_v2 可能是 JSONB(dict) 或 string 或 None
            if isinstance(raw_standards, dict):
                project_context["applicable_standards"] = (
                    raw_standards.get("type")
                    or raw_standards.get("entity_type")
                    or ""
                )
            elif isinstance(raw_standards, str):
                project_context["applicable_standards"] = raw_standards
            else:
                project_context["applicable_standards"] = ""
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: project context 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    raw_std = project_context["applicable_standards"]
    standards = raw_std.lower() if isinstance(raw_std, str) else ""
    disclosure_visibility = {
        "listed": "listed" in standards,
        "soe": "soe" in standards,
    }

    return {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
        "account_code": "1123",
    }
