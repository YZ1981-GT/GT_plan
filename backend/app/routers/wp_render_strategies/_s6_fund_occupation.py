"""S6 大股东及关联方资金占用和违规担保情况审核 — 专属渲染策略.

component_type = "s6-fund-occupation"

S6 前端组件 GtS6FundOccupation 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表S6-1 / 大型核查程序S6 / 监管风险提示第9号上下文区块）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 S6 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "S6-*"。

Requirements: 1.4
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

S6_SHEETS = [
    {"sheet_name": "审定表S6-1", "component_type": "s6-fund-occupation"},
    {"sheet_name": "对大股东及关联方资金占用和违规担保情况审核程序S6", "component_type": "s6-fund-occupation"},
    {"sheet_name": "会计监管风险提示第9号——上市公司控股股东资金占用及其审计", "component_type": "s6-fund-occupation"},
]


async def render(ctx: RenderContext) -> dict | None:
    """S6 资金占用审核专属渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtS6FundOccupation，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 S6-* 数据快照 ──────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'S6-%' "
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
        logger.warning("S6 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("S6 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "sheets": S6_SHEETS,
        "component_type": "s6-fund-occupation",
        "s6_metadata": {
            "regulatory_reference": "会计监管风险提示第9号",
            "applicable_standards": ["listed_standalone", "listed_consolidated"],
            "has_adjudication": True,
            "adjudication_sheet": "审定表S6-1",
        },
    }
