"""A17-2-1 关键审计事项(KAM) — 专属渲染策略.

component_type = "a17-2-1-kam"
KAM 动态增删卡片列表 + 候选清单 + 适用性开关。
数据持久化在 checklist_responses 表，item_id 前缀 `a1721-`。
"""

from __future__ import annotations

import json
import logging
import re

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# KAM item_id patterns
_RE_KAM_INDEX = re.compile(r"^a1721-kam(\d+)$")
_RE_NOTES_INDEX = re.compile(r"^a1721-notes-(\d+)$")


async def render(ctx: RenderContext) -> dict | None:
    """A17-2-1 关键审计事项渲染策略.

    返回 {candidates, kams, notes, applicability, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    # ─── 1. 加载 checklist_responses (item_id LIKE 'a1721-%') ─────────────
    candidates: list[dict] = []
    kams: list[dict] = []
    notes: list[dict] = []
    applicability: dict = {"no_kam": False, "reason": None}

    # Temporary storage for ordering
    kam_map: dict[int, dict] = {}
    notes_map: dict[int, str] = {}

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a1721-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id

            if item_id == "a1721-candidates":
                # candidates: remark = JSON array
                if row.remark:
                    try:
                        data = json.loads(row.remark)
                        if isinstance(data, list):
                            candidates = data
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("A17-2-1 candidates JSON 解析失败")
                        candidates = []

            elif item_id == "a1721-applicability":
                # applicability: conclusion = "Y" (no KAM) or "N" (has KAM)
                applicability["no_kam"] = row.conclusion == "Y"
                applicability["reason"] = row.remark or None

            else:
                # Check KAM detail: a1721-kam{N}
                kam_match = _RE_KAM_INDEX.match(item_id)
                if kam_match:
                    idx = int(kam_match.group(1))
                    if row.remark:
                        try:
                            data = json.loads(row.remark)
                            if isinstance(data, dict):
                                kam_map[idx] = {
                                    "index": idx,
                                    "basic": data.get("basic", ""),
                                    "policy": data.get("policy", ""),
                                    "reason": data.get("reason", ""),
                                    "response": data.get("response", ""),
                                    "result": data.get("result", ""),
                                    "ref_index": data.get("ref_index", ""),
                                }
                        except (json.JSONDecodeError, TypeError):
                            logger.warning("A17-2-1 kam%d JSON 解析失败", idx)
                    continue

                # Check notes: a1721-notes-{N}
                notes_match = _RE_NOTES_INDEX.match(item_id)
                if notes_match:
                    idx = int(notes_match.group(1))
                    notes_map[idx] = row.remark or ""

    except Exception as e:  # noqa: BLE001
        logger.warning("A17-2-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # Build ordered kams list
    for idx in sorted(kam_map.keys()):
        kams.append(kam_map[idx])

    # Build ordered notes list
    for idx in sorted(notes_map.keys()):
        notes.append({"kam_index": idx, "content": notes_map[idx]})

    # ─── 2. 加载项目上下文 ───────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_period": "",
    }
    try:
        proj_result = await db.execute(
            sa.text("SELECT client_name, audit_year FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            year = proj_row.audit_year
            if year:
                project_context["audit_period"] = f"{year}年度"
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-2-1 project context 查询失败: %s", e)

    return {
        "candidates": candidates,
        "kams": kams,
        "notes": notes,
        "applicability": applicability,
        "project_context": project_context,
    }
