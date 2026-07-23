"""B19 识别关联方 — 专属渲染策略.

component_type = "b19-bundle"

背景：b19-bundle 是整册专属前端组件（GtB19Bundle），但此前**无后端 renderer**，
导致 render-config 走通用网格提取产出 html_data.cells（isGridOnly）→ GtWpRenderer
的 noRendererGridFallback 抢先用 GtGridSheet 渲染，GtB19Bundle 从未真正挂载。

本策略返回**结构化 html_data（不含 cells）**，使 isGridOnly=false，
GtWpRenderer 据 componentType 分发到 GtB19Bundle。

GtB19Bundle 自身通过 eqcr API（related_party_registry / related_party_transactions）
与 checklist-responses 直接取数，故此处只需提供 project_context 即可。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """B19 识别关联方渲染策略：返回结构化 html_data（无 cells）。"""
    project_context: dict = {"client_name": "", "audit_year": None}
    try:
        row = (
            await ctx.db.execute(
                sa.text(
                    "SELECT client_name, audit_year FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if row:
            project_context["client_name"] = row.client_name or ""
            project_context["audit_year"] = row.audit_year
    except Exception as e:  # noqa: BLE001
        logger.warning("B19 render: project context 查询失败: %s", e)

    return {
        "component_type": "b19-related-party",
        "project_context": project_context,
    }
