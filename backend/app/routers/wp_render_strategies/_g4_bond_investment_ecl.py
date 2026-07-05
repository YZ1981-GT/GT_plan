"""G4 债权投资(ECL组) — 专属渲染策略.

componentType: g4-bond-investment-ecl
科目 1501 债权投资（借方/资产类，CAS22/CAS24 预期信用损失计量核心逻辑）。

覆盖 7 个 sheet（sheetName v-if dispatch 主入口 GtG4BondInvestmentEcl.vue 分发）：
    G4-9 三阶段划分 / G4-10 减值准备测算表 / G4-11 预期信用损失计量测试 /
    G4-12 转回核销检查表 / G4-13 凭证检查表 /
    参考-中证协金融工具减值指引 / 参考-根据剩余期限折算PD

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免多 sheet dispatch 循环把 G4 各 sheet
   误判为非白名单而重写成 onlyoffice-sheet（否则专属组件被吞掉）。
2. 返回 7 个 sheet 的配置（componentType / sheetName / columns / rows）供前端分发。
3. 回读已持久化的 checklist_responses 数据供前端 seed。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 7 个 sheet 配置：sheetName（与源 xlsx tab 名一致）/ code（前端正则提取分发键）/
# componentType / group（子目录分组：impairment / voucher / reference）。
# columns / rows 的具体列定义由前端 composable 提供，此处返回轻量占位供主入口分发。
G4_ECL_SHEETS = [
    {
        "code": "G4-9",
        "sheetName": "债权投资三阶段划分G4-9",
        "componentType": "g4-bond-investment-ecl",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-10",
        "sheetName": "债权投资减值准备测算表G4-10",
        "componentType": "g4-bond-investment-ecl",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-11",
        "sheetName": "预期信用损失的计量测试G4-11",
        "componentType": "g4-bond-investment-ecl",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-12",
        "sheetName": "减值准备转回（收回）、核销检查表G4-12",
        "componentType": "g4-bond-investment-ecl",
        "group": "impairment",
        "columns": [],
        "rows": [],
    },
    {
        "code": "G4-13",
        "sheetName": "凭证检查表G4-13",
        "componentType": "g4-bond-investment-ecl",
        "group": "voucher",
        "columns": [],
        "rows": [],
    },
    {
        "code": "参考-中证协",
        "sheetName": "参考-中证协《证券公司金融工具减值指引》",
        "componentType": "g4-bond-investment-ecl",
        "group": "reference",
        "columns": [],
        "rows": [],
    },
    {
        "code": "参考-根据剩余期限折算PD",
        "sheetName": "参考-根据剩余期限折算PD",
        "componentType": "g4-bond-investment-ecl",
        "group": "reference",
        "columns": [],
        "rows": [],
    },
]


async def render(ctx: RenderContext) -> dict | None:
    """G4 ECL 组渲染策略：返回 7 sheet 配置 + responses 回读。"""
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
        logger.warning("G4 ECL render: checklist_responses 失败: %s", e)

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
        logger.warning("G4 ECL render: project context 失败: %s", e)

    return {
        "component_type": "g4-bond-investment-ecl",
        # 7 个 sheet 配置（componentType / sheetName / columns / rows）
        "sheets": G4_ECL_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "account_code": "1501",
        "prefix": "G4",
    }
