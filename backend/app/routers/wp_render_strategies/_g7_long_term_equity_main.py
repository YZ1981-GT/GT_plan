"""G7 长期股权投资(main组) — 专属渲染策略.

componentType: g7-long-term-equity-main
科目 1511 长期股权投资（借方/资产类）。

覆盖 7 个 sheet（sheetName v-if dispatch 主入口 GtG7LongTermEquityMain.vue 分发）：
    G7A 实质性程序表 / G7-1 审定表(97行×12列，5组分组折叠) /
    G7-2 明细表(54列→5区段Tab) / G7-3 调整分录汇总 /
    附注披露信息（上市公司）(253行) / 附注披露信息（国企）(355行) / 底稿目录

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免被 onlyoffice-sheet 吞掉。
2. 返回 7 个 sheet 配置供前端 sheetName v-if 分发。
3. 为 G7-1 审定表自动取数：1511 长期股权投资期初/期末余额 seed。
4. 回读已持久化的审定数（EventBus substantive:adjudicated 落库）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# G7-1 审定表 TB 取数科目（前缀匹配，兼容明细科目如 151101）
_G7_ACCOUNT_PREFIX = "1511"

# EventBus 审定值持久化的独立 item_id（render 回读 seed）
_ADJUDICATED_ITEM_ID = "G7-1-adjudicated-amount"

# 7 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）
G7_MAIN_SHEETS = [
    {
        "code": "G7A",
        "sheetName": "长期股权投资实质性程序表G7A",
        "componentType": "a-program-console",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-1",
        "sheetName": "审定表G7-1",
        "componentType": "g7-long-term-equity-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-2",
        "sheetName": "明细表G7-2",
        "componentType": "g7-long-term-equity-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-3",
        "sheetName": "调整分录汇总G7-3",
        "componentType": "g7-long-term-equity-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（上市公司）",
        "sheetName": "附注披露信息（上市公司）",
        "componentType": "g7-long-term-equity-main",
        "group": "disclosure",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（国企）",
        "sheetName": "附注披露信息（国企）",
        "componentType": "g7-long-term-equity-main",
        "group": "disclosure",
        "columns": [],
        "rows": [],
    },
    {
        "code": "底稿目录",
        "sheetName": "底稿目录",
        "componentType": "g7-long-term-equity-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
]


async def _fetch_tb_values(ctx: RenderContext) -> dict:
    """取 1511 长期股权投资 期初/期末余额，按父科目前缀聚合。

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
            if code == _G7_ACCOUNT_PREFIX or code.startswith(_G7_ACCOUNT_PREFIX):
                opening += float(row.opening_balance or 0)
                closing += float(row.closing_balance or 0)
                matched = True
        if matched:
            tb = {"opening": opening, "closing": closing}
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G7 TB fetch failed: %s", e)
    return tb


async def render(ctx: RenderContext) -> dict | None:
    """G7 长期股权投资(main组) 渲染策略：返回 7 sheet 配置 + TB seed + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    adjudicated_amount = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'G7-%' "
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
        logger.warning("G7 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": _G7_ACCOUNT_PREFIX,
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
        logger.warning("G7 render: project context 失败: %s", e)

    tb_values = await _fetch_tb_values(ctx)

    return {
        "component_type": "g7-long-term-equity-main",
        # 7 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G7_MAIN_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": _G7_ACCOUNT_PREFIX,
        "prefix": "G7",
        # G7-1 审定表试算表列只读 seed（真接线：render→html_data→FormData→组件 watch）
        "tb_values": tb_values,
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
    }
