"""A17-6 总结会会议纪要 — 专属渲染策略.

component_type = "a17-6-closing-meeting"
极简组件：6 字段卡片（会议时间/参加人员/会议纪要/结论/附件）+ 元信息(6)。
数据持久化在 checklist_responses 表。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """A17-6 总结会会议纪要渲染策略.

    返回 {meta_info, fields, project_context}
    前端组件自带静态字段定义，后端只负责加载已保存数据。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 1. 从 checklist_responses 加载已保存数据 ────────────────────────
    meta_info: dict = {
        "client_name": "",
        "period": "",
        "preparer": "",
        "reviewer": "",
        "date": "",
        "index_no": "A17-6",
    }
    fields: dict = {
        "meeting_time": "",
        "attendees": "",
        "minutes": "",
        "conclusion": "",
        "attachments": "",
    }

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a176-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            if item_id.startswith("a176-meta-"):
                key = item_id.removeprefix("a176-meta-")
                if key in meta_info:
                    meta_info[key] = row.conclusion or row.remark or ""
            elif item_id.startswith("a176-"):
                key = item_id.removeprefix("a176-")
                if key in fields:
                    fields[key] = row.remark or row.conclusion or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-6 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 2. 从项目上下文获取自动填充信息 ─────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "period": "",
        "current_user": "",
    }

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
            year = proj_row.audit_year
            if year:
                project_context["period"] = f"{year}年12月31日"
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-6 project context 查询失败: %s", e)

    # 自动填充元信息（仅在用户未手动覆盖时）
    if not meta_info["client_name"]:
        meta_info["client_name"] = project_context["client_name"]
    if not meta_info["period"]:
        meta_info["period"] = project_context["period"]

    return {
        "meta_info": meta_info,
        "fields": fields,
        "project_context": project_context,
    }
