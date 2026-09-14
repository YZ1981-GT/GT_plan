"""A18-1 向监管部门报送审计小结 — 专属渲染策略.

component_type = "a18-1-regulatory-submission"
极简组件：3 区块（收件人 + 正文 + 签发），总共 5 个可编辑字段。
数据持久化在 checklist_responses 表。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """A18-1 渲染策略.

    返回 {recipient, body, issuance, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 默认结构 ────────────────────────────────────────────────────────
    recipient: dict = {"bureau": ""}
    body: dict = {"contact_person": "", "contact_phone": ""}
    issuance: dict = {"partner": "", "date": ""}

    # ─── 从 checklist_responses 加载已保存数据 ───────────────────────────
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a181-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            value = row.remark or row.conclusion or ""
            if item_id == "a181-recipient-bureau":
                recipient["bureau"] = value
            elif item_id == "a181-body-contact_person":
                body["contact_person"] = value
            elif item_id == "a181-body-contact_phone":
                body["contact_phone"] = value
            elif item_id == "a181-issuance-partner":
                issuance["partner"] = value
            elif item_id == "a181-issuance-date":
                issuance["date"] = value
    except Exception as e:  # noqa: BLE001
        logger.warning("A18-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文（自动填充） ──────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "firm_name": "致同会计师事务所（特殊普通合伙）",
        "partner_name": "",
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
            project_context["audit_year"] = str(proj_row.audit_year or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("A18-1 project context 查询失败: %s", e)

    return {
        "recipient": recipient,
        "body": body,
        "issuance": issuance,
        "project_context": project_context,
    }
