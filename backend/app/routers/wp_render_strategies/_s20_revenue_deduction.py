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

    # S20 的营业收入不是组件内手填初值：通过统一 auto-data 调度器读取
    # D4 resolver。外层 SAVEPOINT 兜住调度器/注册表级异常；resolver 自身
    # 还会把两条 TB 查询放在内层 SAVEPOINT，确保 PG aborted 不污染后续渲染查询。
    auto_data: dict = {
        "summary": "S20暂无D4营业收入审定数",
        "_error": True,
        "_error_detail": "缺少审计年度，无法读取 D4 营业收入审定数",
        "_error_source": "revenue_audited_for_s20",
    }
    try:
        if ctx.year is not None:
            from app.services.auto_data_resolvers import resolve_auto_data_source

            async with db.begin_nested():
                resolved = await resolve_auto_data_source(
                    db,
                    ctx.project_id,
                    int(ctx.year),
                    "revenue_audited_for_s20",
                )
            if resolved is None:
                auto_data["_error_detail"] = (
                    "未注册 auto_data_source: revenue_audited_for_s20"
                )
            else:
                auto_data = resolved
    except Exception as exc:  # noqa: BLE001 - 诊断保留且不阻断 S20 其余载荷
        detail = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "S20 D4 营业收入审定数取数失败 wp_id=%s project_id=%s: %s",
            wp_id,
            ctx.project_id,
            detail,
            exc_info=True,
        )
        auto_data = {
            "summary": "⚠️ S20营业收入审定数获取失败",
            "_error": True,
            "_error_detail": detail,
            "_error_source": "revenue_audited_for_s20",
        }

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
        "auto_data_source": "revenue_audited_for_s20",
        "auto_data": auto_data,
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
