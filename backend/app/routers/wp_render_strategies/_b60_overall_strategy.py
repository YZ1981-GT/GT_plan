"""B60 总体审计策略 — 专属渲染策略.

component_type = "b60-strategy"
返回 html_data 含：chapter_definitions（章节定义列表）、responses_snapshot（已保存内容）、
project_context（项目上下文含 client_name/audit_year/business_category/partner_name）。

数据持久化在 checklist_responses 表，item_id 前缀为 "B60-CH-" 或 "B60-applicability"。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 静态章节定义 JSON 文件路径
# backend/app/routers/wp_render_strategies/_b60_overall_strategy.py
#   parents[0] = wp_render_strategies
#   parents[1] = routers
#   parents[2] = app  → app/data/b60_chapter_definitions.json
_CHAPTER_DEFINITIONS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "b60_chapter_definitions.json"
)


def _load_chapter_definitions() -> list[dict]:
    """从静态 JSON 文件加载章节定义列表.

    文件不存在或解析失败时返回空列表并记录 warning。
    """
    if not _CHAPTER_DEFINITIONS_PATH.exists():
        logger.warning(
            "B60 render: 章节定义文件不存在: %s", _CHAPTER_DEFINITIONS_PATH
        )
        return []
    try:
        data = json.loads(
            _CHAPTER_DEFINITIONS_PATH.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("B60 render: 章节定义文件加载失败: %s", e)
        return []
    if isinstance(data, list):
        return data
    logger.warning("B60 render: 章节定义文件格式错误（非数组）")
    return []


async def render(ctx: RenderContext) -> dict | None:
    """B60 总体策略渲染.

    返回:
    {
        "chapter_definitions": [...],
        "responses_snapshot": {"B60-CH-01": {"conclusion": null, "remark": "..."}, ...},
        "project_context": {"client_name": "...", "audit_year": "...", ...}
    }
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 加载章节定义 ─────────────────────────────────────────────────────
    chapter_definitions = _load_chapter_definitions()

    # ─── 从 checklist_responses 加载已保存内容快照 ────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id "
                "AND (item_id LIKE 'B60-CH-%' OR item_id = 'B60-applicability')"
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
            "B60 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e
        )
        # 异常时返回空 responses_snapshot，不阻断渲染

    # ─── 项目上下文 ───────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "partner_name": "",
    }
    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT p.client_name, p.audit_year, p.business_category, "
                "s.name AS partner_name "
                "FROM projects p "
                "LEFT JOIN project_assignments pa "
                "  ON pa.project_id = p.id AND pa.role = 'partner' "
                "LEFT JOIN staff_members s "
                "  ON s.id = pa.staff_id "
                "WHERE p.id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = (
                proj_row.business_category or ""
            )
            project_context["partner_name"] = proj_row.partner_name or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("B60 render: project context 查询失败: %s", e)

    return {
        "chapter_definitions": chapter_definitions,
        "responses_snapshot": responses_snapshot,
        "project_context": project_context,
    }
