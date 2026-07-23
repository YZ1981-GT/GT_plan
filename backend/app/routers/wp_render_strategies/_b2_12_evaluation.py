"""B2-12 对前任注册会计师的评价底稿 — 专属渲染策略.

component_type = "b2-12-evaluation"

依据审计准则 1153 号 §5.2：注册会计师接受委托对已审计财务报表进行重新审计
（含 IPO 三年一期 / 重大资产重组两年一期期间内变更审计机构等），后任拟查阅前任
底稿或取得审计证据时，对前任注册会计师进行评价的记录。

返回 html_data：
- responses_snapshot: 已保存的 9 步了解程序 / 7 点结论判断 / 审计说明（item_id B2-12-*）
- project_context: client_name / audit_year（供抬头填充）

9 步程序定义与 7 点结论项定义在前端组件内置（静态），后端仅提供上下文与已存数据。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """B2-12 评价底稿渲染。"""
    db = ctx.db
    wp_id = ctx.wp_id

    # ─── 已保存内容快照（item_id 前缀 B2-12-） ────────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'B2-12-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion,
                "remark": row.remark,
            }
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "B2-12 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e
        )

    # ─── 项目上下文 ───────────────────────────────────────────────────────
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
        logger.warning("B2-12 render: project context 查询失败: %s", e)

    return {
        "responses_snapshot": responses_snapshot,
        "project_context": project_context,
    }
