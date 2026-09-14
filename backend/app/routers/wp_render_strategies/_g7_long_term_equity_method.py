"""G7 长期股权投资(权益法组) — 专属渲染策略.

componentType: g7-long-term-equity-method
科目 1511 长期股权投资（借方/资产类，权益法核算部分）。

覆盖 8 个 sheet（sheetName v-if dispatch 主入口 GtG7EquityMethod.vue 分发）：
    G7-4 被投资单位基本信息 / G7-5 被投资单位财务信息 /
    G7-6 被投资公司会计政策 / G7-13 投资成本测试表 /
    G7-14 权益法测算表 / G7-15 内部交易抵销测算表 /
    G7-16 未确认投资损失测试表 / G7-17 减值测试表

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免被 onlyoffice-sheet 吞掉。
2. 返回 8 个 sheet 配置供前端 sheetName v-if 分发。
3. 回读已持久化的数据（checklist_responses）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 8 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）
G7_EQUITY_METHOD_SHEETS = [
    {
        "code": "G7-4",
        "sheetName": "被投资单位基本信息G7-4",
        "componentType": "g7-long-term-equity-method",
        "group": "info",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-5",
        "sheetName": "被投资单位财务信息G7-5",
        "componentType": "g7-long-term-equity-method",
        "group": "info",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-6",
        "sheetName": "被投资公司会计政策G7-6",
        "componentType": "g7-long-term-equity-method",
        "group": "info",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-13",
        "sheetName": "投资成本测试表G7-13",
        "componentType": "g7-long-term-equity-method",
        "group": "calculation",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-14",
        "sheetName": "权益法测算表G7-14",
        "componentType": "g7-long-term-equity-method",
        "group": "calculation",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-15",
        "sheetName": "内部交易抵销测算表G7-15",
        "componentType": "g7-long-term-equity-method",
        "group": "calculation",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-16",
        "sheetName": "未确认投资损失测试表G7-16",
        "componentType": "g7-long-term-equity-method",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-17",
        "sheetName": "减值测试表G7-17",
        "componentType": "g7-long-term-equity-method",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
]


async def render(ctx: RenderContext) -> dict | None:
    """G7 长期股权投资(权益法组) 渲染策略：返回 8 sheet 配置 + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND (item_id LIKE 'G7-4-%' OR item_id LIKE 'G7-5-%' "
                "OR item_id LIKE 'G7-6-%' OR item_id LIKE 'G7-13-%' "
                "OR item_id LIKE 'G7-14-%' OR item_id LIKE 'G7-15-%' "
                "OR item_id LIKE 'G7-16-%' OR item_id LIKE 'G7-17-%') "
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
        logger.warning("G7 equity-method render: checklist_responses 失败: %s", e)

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
        logger.warning("G7 equity-method render: project context 失败: %s", e)

    return {
        "component_type": "g7-long-term-equity-method",
        # 8 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G7_EQUITY_METHOD_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "prefix": "G7",
    }
