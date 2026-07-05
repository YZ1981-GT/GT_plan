"""G5 长期应收款 — 专属渲染策略.

componentType: g5-long-term-receivable
科目 1531 长期应收款（借方/资产类）。

TB取数：从 tb_balance 获取 1531 期初/期末余额（get_active_filter）。
回读已持久化审定数（EventBus substantive:adjudicated 落库的独立 item_id）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

_G5_ACCOUNT_PREFIX = "1531"
_ADJUDICATED_ITEM_ID = "G5-1-adjudicated-amount"


async def _fetch_tb_values(ctx: RenderContext) -> dict:
    """取 1531 长期应收款 期初/期末余额。"""
    tb: dict[str, float] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
            ).where(active_filter)
        )
        opening = 0.0
        closing = 0.0
        matched = False
        for row in result.fetchall():
            code = (row.account_code or "").strip()
            if code == _G5_ACCOUNT_PREFIX or code.startswith(_G5_ACCOUNT_PREFIX):
                opening += float(row.opening_balance or 0)
                closing += float(row.closing_balance or 0)
                matched = True
        if matched:
            tb = {"opening": opening, "closing": closing}
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 TB fetch failed: %s", e)
    return tb


async def render(ctx: RenderContext) -> dict | None:
    """G5 长期应收款渲染策略入口。"""
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'G5-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        adjudicated_amount = responses_snapshot.get(_ADJUDICATED_ITEM_ID, {}).get(
            "conclusion", ""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": _G5_ACCOUNT_PREFIX,
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("G5 render: project context 失败: %s", e)

    tb_values = await _fetch_tb_values(ctx)

    return {
        "component_type": "g5-long-term-receivable",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": _G5_ACCOUNT_PREFIX,
        "prefix": "G5",
        "tb_values": tb_values,
        "adjudicated_amount": adjudicated_amount,
    }
