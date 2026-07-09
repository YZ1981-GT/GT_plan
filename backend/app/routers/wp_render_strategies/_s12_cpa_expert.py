"""S12 利用专家（注册会计师的专家）的工作 — 专属渲染策略.

component_type = "s12-cpa-expert"

S12 前端组件 GtS12CpaExpert 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（程序表S12 / S12-1 / S12-1-1 / S12-2 / S12-3 / S12-3-1~4）。
S12-3-2~4 为专家多分支渲染（general/股份支付/金融工具公允价值），由 domain 字段决定。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 S12 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "S12-*"。

Requirements: 1.4
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

S12_SHEETS = [
    {"sheet_name": "S12 利用专家的工作程序表", "component_type": "s12-cpa-expert"},
    {"sheet_name": "S12-1 评价胜任能力、专业素质和客观性", "component_type": "s12-cpa-expert"},
    {"sheet_name": "S12-1-1 评价专家的客观性", "component_type": "s12-cpa-expert"},
    {"sheet_name": "S12-2 了解专家的专长领域", "component_type": "s12-cpa-expert"},
    {"sheet_name": "S12-3 评价专家工作的恰当性", "component_type": "s12-cpa-expert"},
    {"sheet_name": "S12-3-1 注册会计师的专家的报告", "component_type": "s12-cpa-expert"},
    {"sheet_name": "S12-3-2 利用专家评价管理层的工作的适当性", "component_type": "s12-cpa-expert"},
    {"sheet_name": "S12-3-3 利用专家评价管理层的工作(股份支付)", "component_type": "s12-cpa-expert"},
    {"sheet_name": "S12-3-4 利用专家评价管理层的工作(金融工具公允价值）", "component_type": "s12-cpa-expert"},
]


async def render(ctx: RenderContext) -> dict | None:
    """S12 利用CPA专家渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtS12CpaExpert，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 S12-* 数据快照 ──────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'S12-%' "
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
        logger.warning("S12 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("S12 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "sheets": S12_SHEETS,
        "component_type": "s12-cpa-expert",
        "s12_metadata": {
            "expert_type": "cpa",
            "domain_branches": {
                "general": "S12-3-2 利用专家评价管理层的工作的适当性",
                "share-based-payment": "S12-3-3 利用专家评价管理层的工作(股份支付)",
                "financial-instrument-fair-value": "S12-3-4 利用专家评价管理层的工作(金融工具公允价值）",
            },
            "evaluation_steps": [
                "S12-1 评价胜任能力、专业素质和客观性",
                "S12-1-1 评价专家的客观性",
                "S12-2 了解专家的专长领域",
                "S12-3 评价专家工作的恰当性",
            ],
        },
    }
