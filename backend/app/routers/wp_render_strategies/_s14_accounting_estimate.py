"""S14 会计估计和相关披露 — 专属渲染策略.

component_type = "s14-accounting-estimate"

S14 前端组件 GtS14AccountingEstimate 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（程序表S14 / S14-1 / S14-2 / S14-3 / S14-4）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 S14 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "S14-*"。

Requirements: 1.4
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

S14_SHEETS = [
    {"sheet_name": "S14程序表", "component_type": "s14-accounting-estimate"},
    {"sheet_name": "S14-1了解被审计单位及其环境（会计估计相关）", "component_type": "s14-accounting-estimate"},
    {"sheet_name": "S14-2了解与会计估计相关的控制", "component_type": "s14-accounting-estimate"},
    {"sheet_name": "S14-3应对评估的重大错报风险（会计估计相关）", "component_type": "s14-accounting-estimate"},
    {"sheet_name": "S14-4管理层偏向的迹象", "component_type": "s14-accounting-estimate"},
]


async def render(ctx: RenderContext) -> dict | None:
    """S14 会计估计专属渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtS14AccountingEstimate，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 S14-* 数据快照 ──────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'S14-%' "
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
        logger.warning("S14 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("S14 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "sheets": S14_SHEETS,
        "component_type": "s14-accounting-estimate",
        "s14_metadata": {
            "applicable_standard": "CAS 13 / ISA 540",
            "evaluation_areas": [
                "了解被审计单位及其环境",
                "了解与会计估计相关的控制",
                "应对评估的重大错报风险",
                "管理层偏向的迹象",
            ],
            "risk_assessment": True,
            "bias_detection": True,
        },
    }
