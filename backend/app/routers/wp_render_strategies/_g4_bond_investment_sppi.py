"""G4 债权投资(SPPI组) — 专属渲染策略.

componentType: g4-bond-investment-sppi
科目 1501 债权投资（借方/资产类，CAS22 金融工具分类核心判定逻辑）。

覆盖 4 个 sheet（sheetName v-if dispatch 主入口 GtG4BondInvestmentSppi.vue 分发）：
    G4-5 业务模式分析 / G4-6 SPPI合同现金流量特征分析 /
    G4-7 有价证券盘点表 / G4-8 盘点倒轧结存表

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免多 sheet dispatch 循环把 G4 各 sheet
   误判为非白名单而重写成 onlyoffice-sheet（否则专属组件被吞掉）。
2. 返回 4 个 sheet 的配置（componentType / sheetName / columns / rows）供前端分发。
3. 回读已持久化的 checklist_responses 数据供前端 seed。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 4 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）/
# componentType（全部走主入口子组件）。
# columns / rows 的具体列定义由前端 composable 提供，此处返回轻量占位供主入口分发。
G4_SPPI_SHEETS = [
    {
        "code": "G4-5",
        "sheetName": "业务模式分析G4-5",
        "componentType": "g4-bond-investment-sppi",
        "group": "classification",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-6",
        "sheetName": "SPPI合同现金流量特征分析G4-6",
        "componentType": "g4-bond-investment-sppi",
        "group": "classification",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-7",
        "sheetName": "有价证券盘点表G4-7",
        "componentType": "g4-bond-investment-sppi",
        "group": "inspection",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-8",
        "sheetName": "盘点倒轧结存表G4-8",
        "componentType": "g4-bond-investment-sppi",
        "group": "inspection",
        "columns": [],
        "rows": [],
    },
]


async def render(ctx: RenderContext) -> dict | None:
    """G4 SPPI 组渲染策略：返回 4 sheet 配置 + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    # 回读 checklist_responses 持久化数据
    responses_snapshot: dict = {}
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
    except Exception as e:  # noqa: BLE001
        logger.warning("G4 SPPI render: checklist_responses 失败: %s", e)

    # 项目上下文
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "1501",
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
        logger.warning("G4 SPPI render: project context 失败: %s", e)

    return {
        "component_type": "g4-bond-investment-sppi",
        # 4 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G4_SPPI_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": "1501",
        "prefix": "G4",
    }
