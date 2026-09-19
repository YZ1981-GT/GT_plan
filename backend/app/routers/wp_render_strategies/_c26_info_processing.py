"""C26 信息处理控制测试 — 专属渲染策略.

component_type = "c26-info-processing-control"

C26 前端组件 GtC26InfoControl 为自加载组件（渲染信息处理控制矩阵，动态行 + 四要素标记），
单 sheet 无需 sheetName 分发。

本渲染策略的关键作用（对齐 render_c1_entity_control）：
让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch 循环把 C26
误判为非白名单而重写成 onlyoffice-sheet（铁律：D~N/专属组件必须注册）。

返回轻量 html_data（project_context + responses_snapshot），前端组件自行消费。

数据持久化在 checklist_responses 表，item_id 前缀为 "C26-*"。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """C26 信息处理控制测试渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtC26InfoControl，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 C26-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'C26-%' "
                "LIMIT 2000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("C26 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    try:
        proj_row = (
            await db.execute(
                sa.text(
                    "SELECT client_name, audit_year, business_category "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = (
                proj_row.business_category or ctx.business_category or ""
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("C26 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
