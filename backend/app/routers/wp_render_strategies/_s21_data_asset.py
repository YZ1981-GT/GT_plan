"""S21 数据资产 — 专属渲染策略.

component_type = "s21-data-asset"

S21 前端组件 GtS21DataAsset 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（数据资产S21/基本情况S21-1/开发支出资本化S21-2/成本归集分摊S21-3/摊销政策S21-4）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 S21 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "S21-*"。
S21 含资本化按月归集（12月SUM+占比）/ 成本归集分摊 / 摊销政策检查 纯函数公式引擎。

Requirements: 1.4
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

S21_SHEETS = [
    {"sheet_name": "数据资产S21", "component_type": "s21-data-asset"},
    {"sheet_name": "数据资产的基本情况S21-1", "component_type": "s21-data-asset"},
    {"sheet_name": "开发支出资本化分析表S21-2", "component_type": "s21-data-asset"},
    {"sheet_name": "成本归集与分摊检查表S21-3", "component_type": "s21-data-asset"},
    {"sheet_name": "摊销政策检查表S21-4", "component_type": "s21-data-asset"},
]


async def render(ctx: RenderContext) -> dict | None:
    """S21 数据资产专属渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtS21DataAsset，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 S21-* 数据快照 ──────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'S21-%' "
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
        logger.warning("S21 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("S21 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "sheets": S21_SHEETS,
        "component_type": "s21-data-asset",
        "s21_metadata": {
            "engine": "capitalization",
            "formulas": {
                "category_total": "SUM(monthly[k][0..11])",
                "total": "SUM(category_totals)",
                "category_ratio": "category_totals[k] / total",
                "monthly_total": "SUM(categories[month_i])",
                "monthly_ratio": "monthly_totals[m] / total",
            },
            "capitalization_conditions": [
                "技术可行性",
                "使用或出售意图",
                "市场需求或内部使用价值",
                "技术和财力资源",
                "支出能够可靠计量",
            ],
        },
    }
