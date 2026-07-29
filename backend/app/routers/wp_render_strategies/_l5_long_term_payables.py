"""L5 长期应付款 — 专属渲染策略.

component_type = "l5-long-term-payables"

L5 前端组件 GtL5LongTermPayables 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/未确认融资费用明细/摊销测算/关联方/检查表/
调整分录/附注等）。因此本渲染策略只需返回轻量 html_data（project_context +
responses_snapshot），关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，
避免多 sheet dispatch 循环把 L5 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目2701长期应付款（贷方/负债类！）：期末=期初+贷方-借方
未确认融资费用（借方/负债备抵类）：期末=期初+借方-贷方
核心特殊：未确认融资费用实际利率法摊销（每期摊销=期初摊余成本×实际利率）
数据持久化在 checklist_responses 表，item_id 前缀为 "L5-*"。

Requirements: 1.6
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext
from ._lmn_tb_helper import fetch_tb_for_balance

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """L5 长期应付款渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtL5LongTermPayables，而非 grid 兜底或 OnlyOffice。

    包含负债类公式验证元数据，供前端初始化时校验方向正确性。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 L5-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'L5-%' "
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
        logger.warning("L5 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

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
        logger.warning("L5 render: project context 查询失败: %s", e)

    # ─── TB 取数（L 循环四表取数 spec） ─────────────────────────────────────
    tb = await fetch_tb_for_balance(ctx, "2701")

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        # 负债类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": "2701",
            "account_name": "长期应付款",
            "direction": "credit",  # 贷方/负债类
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
        },
        # 备抵类（未确认融资费用）公式方向
        "contra_formula_direction": {
            "account_name": "未确认融资费用",
            "direction": "debit",  # 借方/备抵类
            "end_balance_formula": "begin + debit - credit",  # 期末=期初+借方-贷方
        },
        "trial_balance": tb,
    }
