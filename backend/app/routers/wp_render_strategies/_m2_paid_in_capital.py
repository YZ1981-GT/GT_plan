"""M2 实收资本（股本）— 专属渲染策略.

component_type = "m2-paid-in-capital"

M2 前端组件 GtM2PaidInCapital 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细(上市/非上市双版本)/外币投资汇率/检查表/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 M2 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目4001实收资本/股本（贷方/权益类！）：期末=期初+贷方-借方
M股东权益循环中标准权益类科目。增资在贷方，减资在借方。
数据持久化在 checklist_responses 表，item_id 前缀为 "M2-*"。

权益类公式验证逻辑：
- 期末 = 期初 + 贷方 - 借方（权益类标准公式）
- 增资（含验资）在贷方增加
- 减资（减少注册资本）在借方减少
- 外币出资需汇率折算（差异计入M4资本公积）

Requirements: 1.6
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """M2 实收资本（股本）渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtM2PaidInCapital，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 M2-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'M2-%' "
                "LIMIT 3000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("M2 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict[str, Any] = {
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
        logger.warning("M2 render: project context 查询失败: %s", e)

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        # 权益类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": "4001",
            "account_name": "实收资本",
            "direction": "credit",  # 贷方/权益类
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
        },
    }
