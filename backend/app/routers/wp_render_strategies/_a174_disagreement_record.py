"""A17-4 重大专业分歧事项记录 — 专属渲染策略.

component_type = "a17-4-disagreement-record"
人员表(动态增删) + 6 章卡片 + 签字区：
  Section 一: 分歧事项描述
  Section 二: 各方意见
  Section 三: 咨询/讨论过程
  Section 四: 最终结论
  Section 五: 后续措施
  Section 六: 备注
数据持久化在 checklist_responses 表 (item_id LIKE 'a174-%')。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


def _parse_personnel_json(remark: str | None) -> list[dict]:
    """安全解析 personnel JSON 数组，失败降级为空列表."""
    if not remark:
        return []
    try:
        data = json.loads(remark)
        if isinstance(data, list):
            return [
                {
                    "name": str(item.get("name", "")),
                    "position": str(item.get("position", "")),
                    "role": str(item.get("role", "")),
                }
                for item in data
                if isinstance(item, dict)
            ]
        return []
    except (json.JSONDecodeError, TypeError):
        logger.warning("A17-4 personnel JSON 解析失败: %s", remark[:100] if remark else "")
        return []


async def render(ctx: RenderContext) -> dict | None:
    """A17-4 重大专业分歧事项记录渲染策略.

    返回 {personnel, sections, signature_data, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 默认结构 ────────────────────────────────────────────────────────
    personnel: list[dict] = []

    sections: dict = {
        "1": {"parties": ""},
        "2": {"cause": ""},
        "3": {"procedures": ""},
        "4": {"opinions": ""},
        "5": {"considerations": ""},
        "6": {"conclusion": ""},
    }

    signature_data: dict = {
        "preparer": "",
        "reviewer": "",
        "date": "",
    }

    # ─── 从 checklist_responses 加载已保存数据 ───────────────────────────
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a174-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            remark = row.remark or ""
            conclusion = row.conclusion or ""

            # Personnel (JSON array in remark)
            if item_id == "a174-personnel":
                personnel = _parse_personnel_json(remark)

            # Section 1~6
            elif item_id == "a174-sec1-parties":
                sections["1"]["parties"] = remark
            elif item_id == "a174-sec2-cause":
                sections["2"]["cause"] = remark
            elif item_id == "a174-sec3-procedures":
                sections["3"]["procedures"] = remark
            elif item_id == "a174-sec4-opinions":
                sections["4"]["opinions"] = remark
            elif item_id == "a174-sec5-considerations":
                sections["5"]["considerations"] = remark
            elif item_id == "a174-sec6-conclusion":
                sections["6"]["conclusion"] = remark

            # Signature
            elif item_id == "a174-signature-preparer":
                signature_data["preparer"] = conclusion or remark
            elif item_id == "a174-signature-reviewer":
                signature_data["reviewer"] = conclusion or remark
            elif item_id == "a174-signature-date":
                signature_data["date"] = conclusion or remark

    except Exception as e:  # noqa: BLE001
        logger.warning("A17-4 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文（自动填充） ──────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "current_user": "",
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("A17-4 project context 查询失败: %s", e)

    return {
        "personnel": personnel,
        "sections": sections,
        "signature_data": signature_data,
        "project_context": project_context,
    }
