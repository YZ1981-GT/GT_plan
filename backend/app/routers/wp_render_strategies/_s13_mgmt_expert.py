"""S13 利用管理层的专家编制的信息形成审计证据 — 专属渲染策略.

component_type = "s13-mgmt-expert"

S13 前端组件 GtS13MgmtExpert 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（程序表S13 / S13-1 / S13-2 / S13-3 / S13-3-1~4）。
S13-3-2~4 为专家多分支渲染（general/股份支付/金融工具公允价值），由 domain 字段决定。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 S13 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "S13-*"。

Requirements: 1.4
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

S13_SHEETS = [
    {"sheet_name": "S13 利用管理层的专家形成审计证据程序表", "component_type": "s13-mgmt-expert"},
    {"sheet_name": "S13-1 评价胜任能力、专业素质和客观性", "component_type": "s13-mgmt-expert"},
    {"sheet_name": "S13-2 了解专家的工作", "component_type": "s13-mgmt-expert"},
    {"sheet_name": "S13-3 评价管理层专家工作的适当性", "component_type": "s13-mgmt-expert"},
    {"sheet_name": "S13-3-1 管理层专家的报告", "component_type": "s13-mgmt-expert"},
    {"sheet_name": "S13-3-2 评价管理层专家工作的适当性", "component_type": "s13-mgmt-expert"},
    {"sheet_name": "S13-3-3 评价管理层专家工作的适当性(股份支付)", "component_type": "s13-mgmt-expert"},
    {"sheet_name": "S13-3-4 评价管理层专家工作的适当性(金融工具公允价值)", "component_type": "s13-mgmt-expert"},
]


async def render(ctx: RenderContext) -> dict | None:
    """S13 利用管理层专家渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtS13MgmtExpert，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 S13-* 数据快照 ──────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'S13-%' "
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
        logger.warning("S13 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("S13 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "sheets": S13_SHEETS,
        "component_type": "s13-mgmt-expert",
        "s13_metadata": {
            "expert_type": "management",
            "domain_branches": {
                "general": "S13-3-2 评价管理层专家工作的适当性",
                "share-based-payment": "S13-3-3 评价管理层专家工作的适当性(股份支付)",
                "financial-instrument-fair-value": "S13-3-4 评价管理层专家工作的适当性(金融工具公允价值)",
            },
            "evaluation_steps": [
                "S13-1 评价胜任能力、专业素质和客观性",
                "S13-2 了解专家的工作",
                "S13-3 评价管理层专家工作的适当性",
            ],
        },
    }
