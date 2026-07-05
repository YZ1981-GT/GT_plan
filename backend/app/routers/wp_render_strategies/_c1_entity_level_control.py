"""C1 企业层面控制测试 — 专属渲染策略.

componentType: c1-entity-level-control
覆盖 12 个 sheet（11 内容 + 1 GT_Custom 元数据隐藏）。
前端 GtC1EntityControl.vue 按 sheetName v-if 分发。

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免被 onlyoffice-sheet 吞掉。
2. 返回 sheets 配置供前端 sheetName v-if 分发。
3. 回读已持久化的数据（checklist_responses，item_id 前缀 C1-）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 向导式组件只暴露1个 sheet 给外层tab导航（主程序表）
# 其他子sheet（C1-1~C1-4-6示例/过程记录）由组件内部弹窗/Drawer处理
C1_SHEETS = [
    {
        "code": "C1",
        "sheetName": "C1 企业层面控制测试程序表",
        "componentType": "c1-entity-level-control",
        "renderMode": "program",
        "default": True,
    },
]


async def render(ctx: RenderContext) -> dict | None:
    """C1 企业层面控制测试渲染策略：返回 sheets 配置 + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    # 回读已持久化的 checklist_responses（item_id 前缀 C1-）
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'C1-%' "
                "LIMIT 2000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("C1 entity control render: checklist_responses 失败: %s", e)

    # 项目上下文
    project_context: dict = {"client_name": "", "audit_year": ""}
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("C1 entity control render: project context 失败: %s", e)

    return {
        "component_type": "c1-entity-level-control",
        "sheets": C1_SHEETS,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "prefix": "C1",
    }
