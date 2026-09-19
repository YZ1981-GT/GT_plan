"""A11-1 期后事项问询函 — 专属渲染策略.

component_type = "a11-1-subsequent-events-inquiry"
10 个 CAS 1332 规定的问询事项（静态），答复存 checklist_responses。
元信息 4 字段 + 证据区 1 字段 + 10 问答 = 最多 15 条 checklist_responses 记录。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─── 10 个问询事项静态定义（CAS 1332 期后事项问询） ─────────────────────────

QUESTIONS_CONFIG: list[dict] = [
    {
        "number": 1,
        "title": "承诺、借款及担保",
        "text": "自资产负债表日后，是否存在新的承诺、借款或对外担保？",
        "has_guidance": False,
        "guidance_text": None,
    },
    {
        "number": 2,
        "title": "资产出售或购置",
        "text": "是否存在已经完成或预计将要完成的资产出售或购置计划？",
        "has_guidance": False,
        "guidance_text": None,
    },
    {
        "number": 3,
        "title": "资本发行/债务",
        "text": "是否发行了新的股本或债务工具，或是否签订或预计签订合并或清算协议？",
        "has_guidance": False,
        "guidance_text": None,
    },
    {
        "number": 4,
        "title": "政府征用/灾害损失",
        "text": "是否发生了政府征用或火灾、水灾等自然灾害导致的资产毁损？",
        "has_guidance": False,
        "guidance_text": None,
    },
    {
        "number": 5,
        "title": "或有事项进展",
        "text": "或有事项（如诉讼、仲裁）有何进展或新的变化？",
        "has_guidance": True,
        "guidance_text": "如涉及诉讼案例，请列明案号、诉讼金额、判决结果等详细信息",
    },
    {
        "number": 6,
        "title": "重大调整事项",
        "text": "是否发生了可能需要调整财务报表的重大事项或异常交易？",
        "has_guidance": False,
        "guidance_text": None,
    },
    {
        "number": 7,
        "title": "持续经营事项",
        "text": "是否存在可能影响持续经营假设适当性的事项或情况？",
        "has_guidance": False,
        "guidance_text": None,
    },
    {
        "number": 8,
        "title": "会计估计变更",
        "text": "是否存在需要修订会计估计或变更会计政策的情况？",
        "has_guidance": False,
        "guidance_text": None,
    },
    {
        "number": 9,
        "title": "资产可收回性",
        "text": "是否存在资产减值或可收回性发生重大变化的情况？",
        "has_guidance": False,
        "guidance_text": None,
    },
    {
        "number": 10,
        "title": "其他重大事项",
        "text": "是否存在其他可能影响财务报表的重大期后事项？",
        "has_guidance": False,
        "guidance_text": None,
    },
]


async def render(ctx: RenderContext) -> dict | None:
    """A11-1 渲染策略.

    返回 {meta_data, qa_list, evidence, project_context, questions_config}
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 默认结构 ────────────────────────────────────────────────────────
    meta_data: dict = {
        "inquiry_date": None,
        "interviewee": None,
        "location": None,
        "team_signature": None,
    }
    qa_list: list[dict] = [{"number": i + 1, "answer": None} for i in range(10)]
    evidence: str | None = None

    # ─── 从 checklist_responses 加载已保存数据 ───────────────────────────
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a111-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            value = row.remark or row.conclusion or ""

            if item_id.startswith("a111-meta-"):
                field = item_id.replace("a111-meta-", "")
                if field in meta_data:
                    meta_data[field] = value or None
            elif item_id.startswith("a111-qa-"):
                try:
                    num = int(item_id.replace("a111-qa-", ""))
                    if 1 <= num <= 10:
                        qa_list[num - 1]["answer"] = value or None
                except (ValueError, IndexError):
                    pass
            elif item_id == "a111-evidence-description":
                evidence = value or None
    except Exception as e:  # noqa: BLE001
        logger.warning("A11-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "balance_sheet_date": None,
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, balance_sheet_date FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["balance_sheet_date"] = (
                str(proj_row.balance_sheet_date) if proj_row.balance_sheet_date else None
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("A11-1 project context 查询失败: %s", e)

    return {
        "meta_data": meta_data,
        "qa_list": qa_list,
        "evidence": evidence,
        "project_context": project_context,
        "questions_config": QUESTIONS_CONFIG,
    }
