"""G4 债权投资(main组) — 专属渲染策略.

componentType: g4-bond-investment-main
科目 1501 债权投资（借方/资产类，以摊余成本计量的金融资产 CAS22 AC 类）。

覆盖 8 个 sheet（sheetName v-if dispatch 主入口 GtG4BondInvestmentMain.vue 分发）：
    G4A 实质性程序表 / G4-1 审定表 / G4-2 明细表(44列→5区段) /
    G4-3 调整分录汇总 / G4-4 利息测算表 /
    附注披露信息（上市公司）/ 附注披露信息（国企）/ 底稿目录

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免多 sheet dispatch 循环把 G4 各 sheet
   误判为非白名单而重写成 onlyoffice-sheet（否则专属组件被吞掉）。
2. 返回 8 个 sheet 的配置（componentType / sheetName / columns / rows）供前端分发。
3. 为 G4-1 审定表自动取数：1501 债权投资 的期初/期末余额（tb_balance，
   get_active_filter）供前端审定表试算表列（只读）seed。
4. 回读已持久化的审定数（EventBus substantive:adjudicated 落库的独立 item_id），
   供 render 回填 seed，避免刷新后丢失。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# G4-1 审定表 TB 取数科目（前缀匹配，兼容明细科目如 150101）
_G4_ACCOUNT_PREFIX = "1501"

# EventBus 审定值持久化的独立 item_id（render 回读 seed）
_ADJUDICATED_ITEM_ID = "G4-1-adjudicated-amount"

# 8 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）/
# componentType（G4A 复用 a-program-console，其余走主入口子组件）。
# columns / rows 的具体列定义由 render schema yaml + 前端 composable 提供，
# 此处返回轻量占位供主入口 sheetName dispatch 命中。
G4_MAIN_SHEETS = [
    {
        "code": "G4A",
        "sheetName": "债权投资实质性程序表G4A",
        "componentType": "a-program-console",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-1",
        "sheetName": "审定表G4-1",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-2",
        "sheetName": "明细表G4-2",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-3",
        "sheetName": "调整分录汇总G4-3",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-4",
        "sheetName": "利息测算表G4-4",
        "componentType": "g4-bond-investment-main",
        "group": "measurement",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（上市公司）",
        "sheetName": "附注披露信息（上市公司）",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "附注披露信息（国企）",
        "sheetName": "附注披露信息（国企）",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
    {
        "code": "底稿目录",
        "sheetName": "底稿目录",
        "componentType": "g4-bond-investment-main",
        "group": "core",
        "columns": [],
        "rows": [],
    },
]


async def _fetch_tb_values(ctx: RenderContext) -> dict:
    """取 1501 债权投资 期初/期末余额，按父科目前缀聚合。

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
            if code == _G4_ACCOUNT_PREFIX or code.startswith(_G4_ACCOUNT_PREFIX):
                opening += float(row.opening_balance or 0)
                closing += float(row.closing_balance or 0)
                matched = True
        if matched:
            tb = {"opening": opening, "closing": closing}
    except Exception as e:  # noqa: BLE001 — 取数失败降级为空，前端允许手填
        logger.warning("G4 TB fetch failed: %s", e)
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
                "AND item_id LIKE 'G4-%' "
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
        logger.warning("G4 render: checklist_responses 失败: %s", e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": _G4_ACCOUNT_PREFIX,
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
        logger.warning("G4 render: project context 失败: %s", e)

    tb_values = await _fetch_tb_values(ctx)

    return {
        "component_type": "g4-bond-investment-main",
        # 8 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G4_MAIN_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": _G4_ACCOUNT_PREFIX,
        "prefix": "G4",
        # G4-1 审定表试算表列只读 seed（真接线：render→html_data→FormData→组件 watch）
        "tb_values": tb_values,
        # 审定数回读 seed（EventBus 持久化后刷新不丢失）
        "adjudicated_amount": adjudicated_amount,
    }
