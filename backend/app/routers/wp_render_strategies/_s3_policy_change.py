"""S3 会计政策变更、前期差错、估计变更 — 专属渲染策略.

component_type = "s3-policy-change"

S3 前端组件 GtS3PolicyChange 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/S3-1/S3-2/S3-4/S3-6/S3-8/S3-9/S3-10）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 S3 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "S3-*"。
S3 含首次执行新准则调整 + 简化追溯调整法公式（折现计算核心）。
参考sheet（1979公式）不纳入专属组件，保留 OO 兜底。

Requirements: 1.4
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

S3_SHEETS = [
    {"sheet_name": "审定表", "component_type": "s3-policy-change"},
    {"sheet_name": "会计政策变更和前期差错更正S3-1", "component_type": "s3-policy-change"},
    {"sheet_name": "会计估计变更审计程序S3-2", "component_type": "s3-policy-change"},
    {"sheet_name": "首次执行新金融工具准则的调整S3-4", "component_type": "s3-policy-change"},
    {"sheet_name": "首次执行新收入准则的调整S3-6", "component_type": "s3-policy-change"},
    {"sheet_name": "首次执行新租赁准则的调整S3-8", "component_type": "s3-policy-change"},
    {"sheet_name": "简化的追溯调整法（1）S3-9", "component_type": "s3-policy-change"},
    {"sheet_name": "简化的追溯调整法（2）S3-10", "component_type": "s3-policy-change"},
]


async def render(ctx: RenderContext) -> dict | None:
    """S3 会计政策变更专属渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtS3PolicyChange，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 S3-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'S3-%' "
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
        logger.warning("S3 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("S3 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "sheets": S3_SHEETS,
        "component_type": "s3-policy-change",
        "s3_metadata": {
            "engine": "adjustment",
            "sub_engines": [
                "ifrs9_adjust",    # S3-4 新金融工具准则（41公式）
                "ifrs15_adjust",   # S3-6 新收入准则（4公式）
                "ifrs16_adjust",   # S3-8 新租赁准则（6公式）
                "simplified_retro_1",  # S3-9 简化追溯调整法（137公式）
                "simplified_retro_2",  # S3-10 简化追溯调整法变体（132公式）
            ],
            "skip_sheets": ["参考-简化的追溯调整法（首次执行日）"],
            "event_types": [
                "policy_change",       # 会计政策变更
                "prior_period_error",  # 前期差错更正
                "estimate_change",     # 会计估计变更
            ],
        },
    }
