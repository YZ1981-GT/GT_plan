"""M1 应付股利（利润）— 专属渲染策略.

component_type = "m1-dividends-payable"

M1 前端组件 GtM1DividendsPayable 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/外币汇率/股利测算/检查表/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 M1 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目2232应付股利（贷方/负债类！）：期末=期初+贷方-借方
M股东权益循环中唯一的负债类科目。
数据持久化在 checklist_responses 表，item_id 前缀为 "M1-*"。

负债类公式验证逻辑：
- 期末 = 期初 + 贷方 - 借方（负债类标准公式）
- 宣告分配在贷方增加，实际支付在借方减少
- 外币应付股利需汇率折算

Requirements: 1.6
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from ._context import RenderContext
from ._lmn_tb_helper import fetch_tb_for_balance

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """M1 应付股利渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtM1DividendsPayable，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 M1-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'M1-%' "
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
        logger.warning("M1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("M1 render: project context 查询失败: %s", e)

    # ─── TB 取数（LMN 四表取数 spec） ─────────────────────────────────────
    tb = await fetch_tb_for_balance(ctx, "2232")

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "trial_balance": tb,
        # 负债类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": "2232",
            "account_name": "应付股利",
            "direction": "credit",  # 贷方/负债类
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
        },
    }
