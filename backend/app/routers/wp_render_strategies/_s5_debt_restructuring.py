"""S5 债务重组 — 专属渲染策略.

component_type = "s5-debt-restructuring"

S5 前端组件 GtS5DebtRestructuring 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审计程序S5 / 审定表S5-1 / 损益确认时点S5-2）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 S5 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "S5-*"。
S5 含 calcCreditorGainLoss / calcDebtorGainLoss 纯函数公式引擎。

Requirements: 1.4
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

S5_SHEETS = [
    {"sheet_name": "债务重组审计程序S5", "component_type": "s5-debt-restructuring"},
    {"sheet_name": "审定表S5-1", "component_type": "s5-debt-restructuring"},
    {"sheet_name": "债务重组损益确认时点S5-2", "component_type": "s5-debt-restructuring"},
]


async def render(ctx: RenderContext) -> dict | None:
    """S5 债务重组专属渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtS5DebtRestructuring，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 S5-* 数据快照 ──────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'S5-%' "
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
        logger.warning("S5 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("S5 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "sheets": S5_SHEETS,
        "component_type": "s5-debt-restructuring",
        "s5_metadata": {
            "engine": "debt_restructuring",
            "formulas": {
                "creditor_gain_loss": "origBook - origFair - recvFair - otherCost (源模板口径)",
                "debtor_gain_loss": "debtBook - assetBook - equityFair",
            },
            "timing_sheet": "债务重组损益确认时点S5-2",
            "non_recurring": True,
            "warning": "不得提前确认重组损益",
        },
    }
