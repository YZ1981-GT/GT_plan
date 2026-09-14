"""G6 其他债权投资(SPPI组) — 专属渲染策略.

componentType: g6-other-bond-investment-sppi
覆盖 6 个 sheet（sheetName v-if dispatch 主入口 GtG6OtherBondSppi.vue 分发）：
    G6-5 公允价值测试表 / G6-6 利息测算表 / G6-7 业务模式分析 /
    G6-8 合同现金流量特征分析(SPPI) / G6-9 有价证券盘点表 / G6-10 盘点倒轧表

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免 G6-5~G6-10 被误判为 onlyoffice-sheet。
2. 返回 6 个 sheet 的配置（componentType / sheetName / columns / rows）供前端分发。
3. 回读已持久化的 checklist_responses 数据供前端 seed。

本策略为轻量版本，不含 TB 取数（SPPI组无审定表）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 6 个 sheet 配置
G6_SPPI_SHEETS = [
    {
        "code": "G6-5",
        "sheetName": "公允价值测试表G6-5",
        "componentType": "g6-other-bond-investment-sppi",
        "group": "fair-value",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-6",
        "sheetName": "利息测算表G6-6",
        "componentType": "g6-other-bond-investment-sppi",
        "group": "interest",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-7",
        "sheetName": "业务模式分析G6-7",
        "componentType": "g6-other-bond-investment-sppi",
        "group": "classification",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-8",
        "sheetName": "合同现金流量特征分析G6-8",
        "componentType": "g6-other-bond-investment-sppi",
        "group": "classification",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-9",
        "sheetName": "有价证券盘点表G6-9",
        "componentType": "g6-other-bond-investment-sppi",
        "group": "inspection",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-10",
        "sheetName": "盘点倒轧表G6-10",
        "componentType": "g6-other-bond-investment-sppi",
        "group": "inspection",
        "columns": [],
        "rows": [],
    },
]


async def render(ctx: RenderContext) -> dict | None:
    """G6 其他债权投资(SPPI组) 渲染策略：返回 6 sheet 配置 + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    # 回读已持久化的 checklist_responses（G6-5~G6-10 前缀）
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND (item_id LIKE 'G6-5-%' OR item_id LIKE 'G6-6-%' "
                "     OR item_id LIKE 'G6-7-%' OR item_id LIKE 'G6-8-%' "
                "     OR item_id LIKE 'G6-9-%' OR item_id LIKE 'G6-10-%' "
                "     OR item_id LIKE 'G6-sppi-%') "
                "LIMIT 1000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("G6-SPPI render: checklist_responses 失败: %s", e)

    # 项目上下文（客户/年度）
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
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
        logger.warning("G6-SPPI render: project context 失败: %s", e)

    return {
        "component_type": "g6-other-bond-investment-sppi",
        "sheets": G6_SPPI_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "prefix": "G6-SPPI",
    }
