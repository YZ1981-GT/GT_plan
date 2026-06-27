"""A8-1 管理层对审计报告日后公布其他信息的书面声明 — 专属渲染策略.

component_type = "a8-1-other-info-representation"
6 条声明卡片：3 条含动态文件清单(JSON array)、1 条日期、1 条 Y/N、1 条 textarea。
签字区自动填充公司名和法定代表人。
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
        logger.warning("A8-1 文件清单 JSON 解析失败: %s", remark[:100])
        return []


async def render(ctx: RenderContext) -> dict | None:
    """A8-1 渲染策略.

    返回 {statements, signature_data, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 默认结构 ────────────────────────────────────────────────────────
    statements: dict = {
        "1": {"files": []},
        "2": {"date": None},
        "3": {"consistency": None, "explanation": None},
        "4": {"files": []},
        "5": {"files": []},
        "6": {"other": None},
    }
    signature_data: dict = {
        "representative": None,
        "signature_date": None,
    }

    # ─── 从 checklist_responses 加载已保存数据 ───────────────────────────
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a81-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            remark = row.remark or ""
            conclusion = row.conclusion or ""

            if item_id == "a81-statement-1-files":
                statements["1"]["files"] = _parse_file_list(remark)
            elif item_id == "a81-statement-2-date":
                statements["2"]["date"] = conclusion or remark or None
            elif item_id == "a81-statement-3-consistency":
                statements["3"]["consistency"] = conclusion or remark or None
                statements["3"]["explanation"] = remark if conclusion else None
            elif item_id == "a81-statement-3-explanation":
                statements["3"]["explanation"] = remark or None
            elif item_id == "a81-statement-4-files":
                statements["4"]["files"] = _parse_file_list(remark)
            elif item_id == "a81-statement-5-files":
                statements["5"]["files"] = _parse_file_list(remark)
            elif item_id == "a81-statement-6-other":
                statements["6"]["other"] = remark or None
            elif item_id == "a81-signature-representative":
                signature_data["representative"] = remark or conclusion or None
            elif item_id == "a81-signature-date":
                signature_data["signature_date"] = remark or conclusion or None
    except Exception as e:  # noqa: BLE001
        logger.warning("A8-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文（自动填充） ──────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_report_date": None,
        "cpa_names": [],
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_report_date FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_report_date"] = str(proj_row.audit_report_date) if proj_row.audit_report_date else None
    except Exception as e:  # noqa: BLE001
        logger.warning("A8-1 project context 查询失败: %s", e)

    return {
        "statements": statements,
        "signature_data": signature_data,
        "project_context": project_context,
    }
