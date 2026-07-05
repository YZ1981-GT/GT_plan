"""C2~C15 业务循环控制测试 — 专属渲染策略.

componentType: c-control-test
覆盖 C2~C15 共 14 个循环，每个循环含 5~7 个 sheet。
前端 GtCControlTest.vue 弹窗层叠模式（L0汇总表+L1详情+L2偏差评价）。

render 策略的关键作用：
1. 让 component_type 命中 RENDERER_DISPATCH，避免被 onlyoffice-sheet 吞掉。
2. 返回 sheets 配置供前端接收。
3. 回读已持久化的数据（checklist_responses，item_id 前缀 C{n}-）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """C2~C15 控制测试渲染策略：返回 componentType + responses 回读。"""
    wp_id = ctx.wp_id
    db = ctx.db

    # 从 wp_code 提取循环编号
    wp_code = getattr(ctx, "wp_code", "") or ""

    # 回读已持久化的 checklist_responses
    responses_snapshot: dict = {}
    try:
        # C{n}- 前缀匹配（如 C2- / C10- 等）
        prefix_pattern = f"{wp_code}-%"
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE :prefix "
                "LIMIT 2000"
            ),
            {"wp_id": str(wp_id), "prefix": prefix_pattern},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("C control test render: checklist_responses 失败: %s", e)

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
        logger.warning("C control test render: project context 失败: %s", e)

    return {
        "component_type": "c-control-test",
        "wp_code": wp_code,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }
