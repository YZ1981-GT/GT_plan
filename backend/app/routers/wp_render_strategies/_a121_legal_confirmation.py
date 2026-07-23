"""A12-1 法律事务确认函及律师回复函 — 专属渲染策略.

component_type = "a12-1-legal-confirmation"
两部分结构：发函(收件人+3问询+签章) + 回函(诉讼确认+费用+签字)。
跨引用联动: A5-3 (或有事项底稿)。
数据持久化在 checklist_responses 表，item_id 前缀 `a121-`。
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 固定说明段文本
EXPLANATION_TEXT = (
    "根据中国注册会计师审计准则的要求，在对贵公司（以下简称\u201c贵公司\u201d）"
    "财务报表进行审计时，我们需要了解贵公司涉及的诉讼、索赔及税务纠纷等事项。"
    "请贵律师事务所就下列问询事项予以确认并函复。"
)

# 简化流程说明
SIMPLIFIED_NOTE = (
    "如贵公司确认截至资产负债表日止无未决诉讼、仲裁及行政处罚等或有事项，"
    "可直接在本函尾部签章确认即可。"
)

# 跨引用 wp_code
CROSS_REF_WP_CODE = "A5-3"


async def _load_cross_reference(project_id, db) -> dict:
    """查找 A5-3 底稿的 wp_id."""
    cross_refs: dict[str, str | None] = {"a5_3_wp_id": None}

    try:
        result = await db.execute(
            sa.text(
                "SELECT wi.wp_code, wp.id AS wp_id "
                "FROM wp_index wi "
                "JOIN working_paper wp ON wp.wp_index_id = wi.id "
                "WHERE wi.wp_code = :code AND wp.project_id = :project_id"
            ),
            {"code": CROSS_REF_WP_CODE, "project_id": str(project_id)},
        )
        row = result.fetchone()
        if row:
            cross_refs["a5_3_wp_id"] = str(row.wp_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("A12-1 跨引用查询失败 project_id=%s: %s", project_id, e)

    return cross_refs


async def render(ctx: RenderContext) -> dict | None:
    """A12-1 法律事务确认函渲染策略.

    返回 {meta_info, send_section, reply_section, cross_references, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    # ─── 1. 加载 checklist_responses (item_id LIKE 'a121-%') ─────────────
    send_data: dict = {
        "recipient": {"firm_name": None, "lawyer_name": None},
        "inquiry_2": {"content": None},
        "inquiry_3": {"content": None},
        "litigation_list": [],
        "sign_info": {"company_name": None, "date": None},
        "reply_info_table": {"address": None, "phone": None, "contact": None},
    }
    reply_data: dict = {
        "litigation_status": None,
        "litigation_details": None,
        "fee_status": None,
        "outstanding_amount": None,
        "sign": {"firm_name": None, "lawyer_name": None, "date": None},
    }

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a121-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            _parse_row(row.item_id, row, send_data, reply_data)
    except Exception as e:  # noqa: BLE001
        logger.warning("A12-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 2. 加载项目上下文 ───────────────────────────────────────────────
    project_context: dict = {"client_name": "", "audit_period": ""}
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
        logger.warning("A12-1 project context 查询失败: %s", e)

    # ─── 3. 加载跨引用 wp_id ─────────────────────────────────────────────
    cross_references = await _load_cross_reference(project_id, db)

    # ─── 4. 自动填充公司名 ───────────────────────────────────────────────
    if not send_data["sign_info"]["company_name"]:
        send_data["sign_info"]["company_name"] = project_context["client_name"]

    # ─── 5. 构建 meta_info ───────────────────────────────────────────────
    meta_info = {
        "client_name": project_context["client_name"],
        "audit_period": project_context["audit_period"],
        "index_no": "A12-1",
    }

    # ─── 6. 构建 send_section ────────────────────────────────────────────
    send_section = {
        "recipient": send_data["recipient"],
        "explanation_text": EXPLANATION_TEXT,
        "inquiry_1": {"litigation_list": send_data["litigation_list"]},
        "inquiry_2": send_data["inquiry_2"],
        "inquiry_3": send_data["inquiry_3"],
        "simplified_note": SIMPLIFIED_NOTE,
        "sign_info": send_data["sign_info"],
        "reply_info_table": send_data["reply_info_table"],
    }

    return {
        "meta_info": meta_info,
        "send_section": send_section,
        "reply_section": reply_data,
        "cross_references": cross_references,
        "project_context": project_context,
    }


def _parse_row(
    item_id: str,
    row,
    send_data: dict,
    reply_data: dict,
) -> None:
    """解析单条 checklist_response 行并填入对应结构."""
    # ─── Send section ─────────────────────────────────────────────────────
    if item_id == "a121-send-recipient-firm":
        send_data["recipient"]["firm_name"] = row.conclusion or row.remark or None

    elif item_id == "a121-send-recipient-lawyer":
        send_data["recipient"]["lawyer_name"] = row.conclusion or row.remark or None

    elif item_id == "a121-send-inquiry2-content":
        send_data["inquiry_2"]["content"] = row.remark or row.conclusion or None

    elif item_id == "a121-send-inquiry3-content":
        send_data["inquiry_3"]["content"] = row.remark or row.conclusion or None

    elif item_id == "a121-send-litigation":
        # remark = JSON array of litigation records
        if row.remark:
            try:
                data = json.loads(row.remark)
                if isinstance(data, list):
                    send_data["litigation_list"] = [
                        {
                            "description": item.get("description"),
                            "opinion": item.get("opinion"),
                            "estimated_loss": item.get("estimated_loss"),
                        }
                        for item in data
                        if isinstance(item, dict)
                    ]
            except (json.JSONDecodeError, TypeError):
                logger.warning("A12-1 litigation JSON 解析失败 item_id=%s", item_id)

    elif item_id == "a121-send-sign-company":
        send_data["sign_info"]["company_name"] = row.conclusion or row.remark or None

    elif item_id == "a121-send-sign-date":
        send_data["sign_info"]["date"] = row.conclusion or row.remark or None

    elif item_id == "a121-send-reply-address":
        send_data["reply_info_table"]["address"] = row.conclusion or row.remark or None

    elif item_id == "a121-send-reply-phone":
        send_data["reply_info_table"]["phone"] = row.conclusion or row.remark or None

    elif item_id == "a121-send-reply-contact":
        send_data["reply_info_table"]["contact"] = row.conclusion or row.remark or None

    # ─── Reply section ────────────────────────────────────────────────────
    elif item_id == "a121-reply-status":
        reply_data["litigation_status"] = row.conclusion or None

    elif item_id == "a121-reply-details":
        reply_data["litigation_details"] = row.remark or row.conclusion or None

    elif item_id == "a121-reply-fee-status":
        reply_data["fee_status"] = row.conclusion or None

    elif item_id == "a121-reply-fee-amount":
        val = row.conclusion or row.remark or None
        if val is not None:
            try:
                reply_data["outstanding_amount"] = float(val)
            except (ValueError, TypeError):
                reply_data["outstanding_amount"] = None
        else:
            reply_data["outstanding_amount"] = None

    elif item_id == "a121-reply-sign-firm":
        reply_data["sign"]["firm_name"] = row.conclusion or row.remark or None

    elif item_id == "a121-reply-sign-lawyer":
        reply_data["sign"]["lawyer_name"] = row.conclusion or row.remark or None

    elif item_id == "a121-reply-sign-date":
        reply_data["sign"]["date"] = row.conclusion or row.remark or None
