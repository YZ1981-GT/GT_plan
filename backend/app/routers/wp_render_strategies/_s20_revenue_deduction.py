"""S20 营业收入扣除情况核查 — 专属渲染策略.

component_type = "s20-revenue-deduction"

S20 前端组件 GtS20RevenueDeduction 为单 sheet 多区段底稿（无内部 sheet 分发），
前端为自加载组件（拉取 checklist-responses + auto_data_source 取数）。
本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免 dispatch
循环把 S20 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "S20-*"。
S20 单 sheet 多区段：核查目标/扣非净利润/营收扣除汇总/与主营无关明细/不具备商业实质明细/其他核查。
含 22 个公式：revenue=main+other, deductionTotal, ratio, afterDeduction。

Requirements: 1.4
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

S20_SHEETS = [
    {"sheet_name": "营业收入扣除情况核查", "component_type": "s20-revenue-deduction"},
]


async def render(ctx: RenderContext) -> dict | None:
    """S20 营业收入扣除情况核查专属渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtS20RevenueDeduction，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 S20-* 数据快照 ──────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'S20-%' "
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
        logger.warning("S20 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("S20 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "sheets": S20_SHEETS,
        "component_type": "s20-revenue-deduction",
        "s20_metadata": {
            "engine": "revenue_deduction",
            "layout": "single_sheet_multi_segment",
            "segments": [
                "核查目标",
                "扣非净利润判断",
                "营收扣除汇总",
                "与主营业务无关收入明细",
                "不具备商业实质收入明细",
                "其他核查事项",
            ],
            "formulas": {
                "revenue": "SUM(main_business) + SUM(other_business)",
                "deduction_total": "unrelated_revenue + no_substance_revenue",
                "deduction_ratio": "deduction_total / revenue",
                "revenue_after_deduction": "revenue - deduction_total",
            },
            "dual_period": True,  # 本年审定(C列) + 上年追溯调整后(D列)
        },
    }
