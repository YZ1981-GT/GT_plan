"""A1-17 对应数据程序表 — 专属渲染策略.

component_type = "a1-17-corresponding-data"
极简程序表：5 个静态步骤，用户填写是否适用/执行人/执行情况/索引号。
数据持久化在 checklist_responses 表。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """A1-17 对应数据渲染策略.

    返回 {responses: {step-id: {applicable, executor, description, ref_index}}}
    前端组件自带静态步骤定义，不需要后端返回模板。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    responses: dict[str, dict] = {}

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark, wp_ref "
                "FROM checklist_responses WHERE wp_id = :wp_id"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            # remark 存储为 JSON（含 executor/description/ref_index）
            extra: dict = {}
            if row.remark:
                try:
                    extra = json.loads(row.remark)
                except (json.JSONDecodeError, TypeError):
                    extra = {"description": row.remark}

            responses[item_id] = {
                "applicable": row.conclusion or "",
                "executor": extra.get("executor", ""),
                "description": extra.get("description", ""),
                "ref_index": extra.get("ref_index", "") or row.wp_ref or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("A1-17 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    return {"responses": responses}
