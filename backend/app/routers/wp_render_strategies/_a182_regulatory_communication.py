"""A18-2 与监管层沟通函 — 专属渲染策略.

component_type = "a18-2-regulatory-communication"
5 区块组件（收件人 + 引言 + 4事项适用性 + 双签签发 + 提示折叠）。
数据持久化在 checklist_responses 表，item_id 前缀 `a182-`。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 4 事项标题定义
_MATTER_TITLES: list[str] = [
    "舞弊",
    "重大违反法律法规行为",
    "年度报告中信息不一致或错报",
    "其他事项",
]


async def render(ctx: RenderContext) -> dict | None:
    """A18-2 与监管层沟通函渲染策略.

    返回 {recipient, matters, issuance, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 默认结构 ────────────────────────────────────────────────────────
    recipient: dict = {"authority": "", "custom": ""}
    matters: list[dict] = [
        {"id": i + 1, "title": _MATTER_TITLES[i], "applicability": None, "content": ""}
        for i in range(4)
    ]
    issuance: dict = {"cpa1": "", "cpa2": "", "date": ""}

    # ─── 从 checklist_responses 加载已保存数据 ───────────────────────────
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a182-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            value = row.remark or row.conclusion or ""
            if item_id == "a182-recipient-authority":
                recipient["authority"] = value
            elif item_id == "a182-recipient-custom":
                recipient["custom"] = value
            elif item_id == "a182-sign-cpa1":
                issuance["cpa1"] = value
            elif item_id == "a182-sign-cpa2":
                issuance["cpa2"] = value
            elif item_id == "a182-sign-date":
                issuance["date"] = value
            elif item_id.startswith("a182-matter"):
                # e.g. a182-matter1-applicability, a182-matter2-content
                parts = item_id.removeprefix("a182-matter").split("-", 1)
                if len(parts) == 2:
                    try:
                        idx = int(parts[0]) - 1  # 1-based → 0-based
                        field = parts[1]
                        if 0 <= idx < 4 and field in ("applicability", "content"):
                            matters[idx][field] = value or None if field == "applicability" else value
                    except (ValueError, IndexError):
                        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("A18-2 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文（自动填充） ──────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "firm_name": "致同会计师事务所（特殊普通合伙）",
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
        logger.warning("A18-2 project context 查询失败: %s", e)

    return {
        "recipient": recipient,
        "matters": matters,
        "issuance": issuance,
        "project_context": project_context,
    }
