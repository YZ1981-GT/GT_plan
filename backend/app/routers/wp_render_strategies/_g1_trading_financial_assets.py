"""G1 交易性金融资产 — 专属渲染策略.

componentType: g1-trading-financial-assets
科目 1501 交易性金融资产（借方/资产类）。

除返回 checklist 快照外，为 G1-1 审定表自动取数：
- 1501 交易性金融资产 的期初/期末余额（tb_balance，get_active_filter）
供前端 G1-1 审定表试算表列（只读）seed。
并回读已持久化的审定数（EventBus substantive:adjudicated 落库的独立 item_id），
供 render 回填 seed，避免刷新后丢失。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# G1-1 审定表 TB 取数科目（前缀匹配，兼容明细科目如 150101）
_G1_ACCOUNT_PREFIX = "1501"

# EventBus 审定值持久化的独立 item_id（render 回读 seed）
_ADJUDICATED_ITEM_ID = "G1-1-adjudicated-amount"

G1_INVEST_TYPES = [
    {"rowKey": "stock", "label": "股票"},
    {"rowKey": "fund", "label": "基金"},
    {"rowKey": "bond", "label": "债券"},
    {"rowKey": "derivative", "label": "衍生工具"},
    {"rowKey": "other", "label": "其他"},
]

G1_MEASURE_TYPES = [
    {"rowKey": "cost", "label": "成本"},
    {"rowKey": "fv-change", "label": "公允价值变动"},
    {"rowKey": "disposal", "label": "处置损益"},
]


async def _fetch_tb_values(ctx: RenderContext) -> dict:
    """取 1501 交易性金融资产 期初/期末余额，按父科目前缀聚合。

    返回 {"opening": float, "closing": float}，取数失败降级为空 dict，前端允许手填。
    """
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
            if code == _G1_ACCOUNT_PREFIX or code.startswith(_G1_ACCOUNT_PREFIX):
                opening += float(row.opening_balance or 0)
                closing += float(row.closing_balance or 0)
                matched = True
        if matched:
            tb = {"opening": opening, "closing": closing}
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G1 TB fetch failed: %s", e)
    return tb


async def render(ctx: RenderContext) -> dict | None:
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'G1-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
        # 审定值回读：EventBus substantive:adjudicated 落库的独立 item_id
        adjudicated_amount = responses_snapshot.get(_ADJUDICATED_ITEM_ID, {}).get(
            "conclusion", ""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("G1 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": _G1_ACCOUNT_PREFIX,
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
        logger.warning("G1 render: project context 失败: %s", e)

    tb_values = await _fetch_tb_values(ctx)

    return {
        "component_type": "g1-trading-financial-assets",
        "invest_types": G1_INVEST_TYPES,
        "measure_types": G1_MEASURE_TYPES,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": _G1_ACCOUNT_PREFIX,
        "prefix": "G1",
        # G1-1 审定表试算表列只读 seed（真接线：render→html_data→FormData→组件 watch）
        "tb_values": tb_values,
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
    }
