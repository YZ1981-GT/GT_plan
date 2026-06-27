"""A17-3 业务咨询记录 — 专属渲染策略.

component_type = "a17-3-consultation-record"
元信息表 + 4 章卡片：
  Section 一: 咨询事项(业务概况+问题背景+相关文件tag)
  Section 二: 项目组初步讨论意见
  Section 三: 专业技术部反馈(准则依据+回复意见)
  Section 四: 专业技术委员会意见及所外咨询回复
数据持久化在 checklist_responses 表。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


def _parse_file_list(remark: str | None) -> list[str]:
    """安全解析 JSON 文件清单，失败降级为空列表."""
    if not remark:
        return []
    try:
        data = json.loads(remark)
        if isinstance(data, list):
            return [str(item) for item in data if item]
        return []
    except (json.JSONDecodeError, TypeError):
        logger.warning("A17-3 文件清单 JSON 解析失败: %s", remark[:100])
        return []


async def render(ctx: RenderContext) -> dict | None:
    """A17-3 业务咨询记录渲染策略.

    返回 {meta_info, sections, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 默认结构 ────────────────────────────────────────────────────────
    meta_info: dict = {
        "department": "",
        "client_name": "",
        "consult_type": "",
        "period": "",
    }

    sections: dict = {
        "1": {"overview": "", "background": "", "files": []},
        "2": {"opinion": ""},
        "3": {"standards": "", "reply": ""},
        "4": {"opinion": ""},
    }

    # ─── 从 checklist_responses 加载已保存数据 ───────────────────────────
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a173-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            remark = row.remark or ""
            conclusion = row.conclusion or ""

            # Meta fields
            if item_id.startswith("a173-meta-"):
                key = item_id.removeprefix("a173-meta-")
                if key in meta_info:
                    meta_info[key] = conclusion or remark or ""

            # Section 1
            elif item_id == "a173-sec1-overview":
                sections["1"]["overview"] = remark or ""
            elif item_id == "a173-sec1-background":
                sections["1"]["background"] = remark or ""
            elif item_id == "a173-sec1-files":
                sections["1"]["files"] = _parse_file_list(remark)

            # Section 2
            elif item_id == "a173-sec2-opinion":
                sections["2"]["opinion"] = remark or ""

            # Section 3
            elif item_id == "a173-sec3-standards":
                sections["3"]["standards"] = remark or ""
            elif item_id == "a173-sec3-reply":
                sections["3"]["reply"] = remark or ""

            # Section 4
            elif item_id == "a173-sec4-opinion":
                sections["4"]["opinion"] = remark or ""

    except Exception as e:  # noqa: BLE001
        logger.warning("A17-3 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文（自动填充） ──────────────────────────────────────────
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
        logger.warning("A17-3 project context 查询失败: %s", e)

    # 自动填充元信息（仅在用户未手动覆盖时）
    if not meta_info["client_name"]:
        meta_info["client_name"] = project_context["client_name"]
    if not meta_info["period"]:
        meta_info["period"] = project_context["period"]

    return {
        "meta_info": meta_info,
        "sections": sections,
        "project_context": project_context,
    }
