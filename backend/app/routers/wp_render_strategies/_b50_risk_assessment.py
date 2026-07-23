"""B50 汇总风险评估结果 — 专属渲染策略.

component_type = "b50-risk-assessment"

背景（与 B19/B2 同款防坑）：b50-risk-assessment 是整册专属前端组件
（GtB50RiskAssessment，4/5-Tab 自加载），但此前**无后端 renderer** →
render-config 走通用网格提取，B50 汇总程序表（43 行）产出 html_data.cells
（isGridOnly）→ GtWpRenderer 的 noRendererGridFallback 会用 GtGridSheet 兜底
shadow 掉专属组件。

本策略返回**结构化 html_data（不含 cells）**，使 isGridOnly=false，
GtWpRenderer 据 componentType 分发到 GtB50RiskAssessment。

同时注入：
  - program_available：程序表由前端 GtAProgramConsole 自加载 /procedure-tables/B50
  - oo_sheet_map：双模式 per-tab 源子底稿 wp_code + 源 xlsx tab 名（完全一致），
    供前端经 wp-id-by-code 解析各 Tab 对应 OnlyOffice 视图。

Spec: .kiro/specs/b50-workpaper-rework/
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# per-tab 源子底稿 → 源 xlsx tab 名（必须与源模板 sheet tab 名完全一致）
_OO_SHEET_MAP = {
    "program": {"source_wp_code": "B50", "oo_sheet_name": "B50 汇总风险评估结果"},
    "tab1": {"source_wp_code": "B50-1", "oo_sheet_name": "B50-1 汇总识别出的风险因素"},
    "tab2": {"source_wp_code": "B50-2", "oo_sheet_name": "B50-2 财务报表层次风险"},
    "tab3": {"source_wp_code": "B50-3", "oo_sheet_name": "B50-3认定层次风险评估"},
    "tab4": {"source_wp_code": "B50-4", "oo_sheet_name": "B50-4 特别风险"},
}


async def render(ctx: RenderContext) -> dict | None:
    """B50 风险评估渲染策略：返回结构化 html_data（无 cells）。"""
    project_context: dict = {
        "client_name": "",
        "audit_year": None,
        "program_available": True,
        "oo_sheet_map": _OO_SHEET_MAP,
    }
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
    except Exception as e:  # noqa: BLE001 — 上下文查询失败按降级处理，不 500
        logger.warning("B50 render: project context 查询失败: %s", e)

    return {
        "component_type": "b50-risk-assessment",
        "project_context": project_context,
    }
