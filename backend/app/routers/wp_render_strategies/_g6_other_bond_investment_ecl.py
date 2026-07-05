"""G6 其他债权投资(ECL组) — 专属渲染策略.

componentType: g6-other-bond-investment-ecl
科目 1503 其他债权投资（借方/资产类，FVOCI-Debt，CAS22/CAS24 预期信用损失计量核心逻辑）。

覆盖 5 个 sheet（sheetName v-if dispatch 主入口 GtG6OtherBondInvestmentEcl.vue 分发）：
    G6-11 三阶段划分 / G6-12 减值准备测算表 / G6-13 预期信用损失计量测试 /
    G6-14 转回核销检查表 / G6-15 凭证检查表

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免 G6-11~G6-15 被误判为 onlyoffice-sheet。
2. 返回 5 个 sheet 的配置（componentType / sheetName / columns / rows）供前端分发。
3. 回读已持久化的 checklist_responses 数据供前端 seed。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 5 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）/
# componentType / group（子目录分组：impairment / voucher）。
# columns / rows 的具体列定义由前端 composable 提供，此处返回轻量占位供主入口分发。
G6_ECL_SHEETS = [
    {
        "code": "G6-11",
        "sheetName": "其他债权投资三阶段划分G6-11",
        "componentType": "g6-other-bond-investment-ecl",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-12",
        "sheetName": "其他债权投资减值准备测算表G6-12",
        "componentType": "g6-other-bond-investment-ecl",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-13",
        "sheetName": "预期信用损失的计量测试G6-13",
        "componentType": "g6-other-bond-investment-ecl",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-14",
        "sheetName": "减值准备转回（收回）、核销检查表G6-14",
        "componentType": "g6-other-bond-investment-ecl",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G6-15",
        "sheetName": "凭证检查表G6-15",
        "componentType": "g6-other-bond-investment-ecl",
        "group": "voucher",
        "columns": [],
        "rows": [],
    },
]


async def render(ctx: RenderContext) -> dict | None:
    """G6 其他债权投资(ECL组) 渲染策略：返回 5 sheet 配置 + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    # 回读已持久化的 checklist_responses（G6-11~G6-15 前缀）
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND (item_id LIKE 'G6-11-%' OR item_id LIKE 'G6-12-%' "
                "     OR item_id LIKE 'G6-13-%' OR item_id LIKE 'G6-14-%' "
                "     OR item_id LIKE 'G6-15-%' "
                "     OR item_id LIKE 'G6-ecl-%') "
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
        logger.warning("G6-ECL render: checklist_responses 回读失败: %s", e)

    # 项目上下文（客户/年度/科目）
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "account_code": "1503",
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
        logger.warning("G6-ECL render: project context 失败: %s", e)

    return {
        "component_type": "g6-other-bond-investment-ecl",
        # 5 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G6_ECL_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": "1503",
        "prefix": "G6-ECL",
    }
