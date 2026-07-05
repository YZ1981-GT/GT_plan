"""G7 长期股权投资(子公司组) — 专属渲染策略.

componentType: g7-long-term-equity-subsidiary
科目 1511 长期股权投资（借方/资产类，子公司组）。

覆盖 7 个 sheet（sheetName v-if dispatch 主入口 GtG7EquitySubsidiary.vue 分发）：
    G7-7 投资初始确认判断（CAS33控制六要素）
    G7-8 同一控制下企业合并
    G7-9 非同一控制下企业合并
    G7-10 后续计量检查（成本法）
    G7-11 处置检查（非一揽子交易）
    G7-12 处置检查（一揽子交易）
    G7-18 凭证检查表（19列→3区段Tab）

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免被 onlyoffice-sheet 吞掉。
2. 返回 7 个 sheet 配置供前端 sheetName v-if 分发。
3. 回读已持久化的数据（checklist_responses）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 7 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）
G7_SUBSIDIARY_SHEETS = [
    {
        "code": "G7-7",
        "sheetName": "投资初始确认判断G7-7",
        "componentType": "g7-long-term-equity-subsidiary",
        "group": "initial",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-8",
        "sheetName": "同一控制下企业合并G7-8",
        "componentType": "g7-long-term-equity-subsidiary",
        "group": "initial",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-9",
        "sheetName": "非同一控制下企业合并G7-9",
        "componentType": "g7-long-term-equity-subsidiary",
        "group": "initial",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-10",
        "sheetName": "后续计量检查G7-10",
        "componentType": "g7-long-term-equity-subsidiary",
        "group": "subsequent",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-11",
        "sheetName": "处置检查（非一揽子交易）G7-11",
        "componentType": "g7-long-term-equity-subsidiary",
        "group": "disposal",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-12",
        "sheetName": "处置检查（一揽子交易）G7-12",
        "componentType": "g7-long-term-equity-subsidiary",
        "group": "disposal",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G7-18",
        "sheetName": "凭证检查表G7-18",
        "componentType": "g7-long-term-equity-subsidiary",
        "group": "voucher",
        "columns": [],
        "rows": [],
    },
]


async def render(ctx: RenderContext) -> dict | None:
    """G7 长期股权投资(子公司组) 渲染策略：返回 7 sheet 配置 + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND (item_id LIKE 'G7-7-%' OR item_id LIKE 'G7-8-%' "
                "OR item_id LIKE 'G7-9-%' OR item_id LIKE 'G7-10-%' "
                "OR item_id LIKE 'G7-11-%' OR item_id LIKE 'G7-12-%' "
                "OR item_id LIKE 'G7-18-%') "
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
        logger.warning("G7 subsidiary render: checklist_responses 失败: %s", e)

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
        logger.warning("G7 subsidiary render: project context 失败: %s", e)

    return {
        "component_type": "g7-long-term-equity-subsidiary",
        # 7 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G7_SUBSIDIARY_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "prefix": "G7",
    }
