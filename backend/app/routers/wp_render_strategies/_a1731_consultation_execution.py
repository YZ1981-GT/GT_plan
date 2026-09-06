"""A17-3-1 业务咨询结果执行情况记录 — 专属渲染策略.

component_type = "a17-3-1-consultation-execution"
极简 5 区块：元信息(4) + 4 章 textarea + A17-3 引用(只读)。
数据持久化在 checklist_responses 表。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """A17-3-1 业务咨询结果执行情况记录渲染策略.

    返回 {meta_info, sections, a173_reference, project_context}
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 默认结构 ────────────────────────────────────────────────────────
    meta_info: dict = {
        "executor": "",
        "execution_date": "",
        "review_date": "",
        "reviewer": "",
        "not_required": "",
        "consultation_id": "",
    }

    sections: dict = {
        "1": {"supplementary": ""},
        "2": {"execution_details": ""},
        "3": {"results": ""},
        "4": {"follow_up": ""},
    }

    # ─── 从 checklist_responses 加载已保存数据 (a1731-%) ─────────────────
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'a1731-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id

            # Meta fields: a1731-meta-{field}
            if item_id.startswith("a1731-meta-"):
                key = item_id.removeprefix("a1731-meta-")
                if key in meta_info:
                    meta_info[key] = row.conclusion or row.remark or ""

            # Section 1: a1731-sec1-supplementary
            elif item_id == "a1731-sec1-supplementary":
                sections["1"]["supplementary"] = row.remark or ""

            # Section 2: a1731-sec2-execution_details
            elif item_id == "a1731-sec2-execution_details":
                sections["2"]["execution_details"] = row.remark or ""

            # Section 3: a1731-sec3-results
            elif item_id == "a1731-sec3-results":
                sections["3"]["results"] = row.remark or ""

            # Section 4: a1731-sec4-follow_up
            elif item_id == "a1731-sec4-follow_up":
                sections["4"]["follow_up"] = row.remark or ""

            # Section 3 Y/N 状态（UI 附加字段）
            elif item_id == "a1731-sec3-yn_state":
                sections["3"]["yn_state"] = row.remark or ""

    except Exception as e:  # noqa: BLE001
        logger.warning("A17-3-1 checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 加载 A17-3 引用（跨底稿：经 wp_index 解析 A17-3 的 wp_id）────────
    a173_reference: dict = {
        "overview": "",
        "background": "",
        "reply": "",
    }

    try:
        a173_wp_id: str | None = None
        idx = await db.execute(
            sa.text(
                # wp_index 无 wp_id 列；wp_id 须经 working_paper.wp_index_id 反查。
                # 原 `AND wp_id IS NOT NULL` 的意图由 INNER JOIN 承担。
                "SELECT wp.id AS wp_id FROM wp_index wi "
                "JOIN working_paper wp ON wp.wp_index_id = wi.id "
                "WHERE wi.project_id = :pid AND wi.wp_code = 'A17-3' LIMIT 1"
            ),
            {"pid": str(ctx.project_id)},
        )
        idx_row = idx.fetchone()
        if idx_row and idx_row.wp_id:
            a173_wp_id = str(idx_row.wp_id)

        if a173_wp_id:
            ref_result = await db.execute(
                sa.text(
                    "SELECT item_id, remark "
                    "FROM checklist_responses WHERE wp_id = :wp_id "
                    "AND ("
                    "  item_id IN ("
                    "    'a173-sec1-overview',"
                    "    'a173-sec1-background',"
                    "    'a173-sec3-reply'"
                    "  )"
                    ")"
                ),
                {"wp_id": a173_wp_id},
            )
            for row in ref_result.fetchall():
                if row.item_id == "a173-sec1-overview":
                    a173_reference["overview"] = row.remark or ""
                elif row.item_id == "a173-sec1-background":
                    a173_reference["background"] = row.remark or ""
                elif row.item_id == "a173-sec3-reply":
                    a173_reference["reply"] = row.remark or ""
        else:
            logger.info(
                "A17-3-1: 项目 %s 无 A17-3 底稿，跳过引用",
                ctx.project_id,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "A17-3-1 A17-3 跨底稿引用查询失败 project=%s: %s",
            ctx.project_id,
            e,
        )

    # ─── 项目上下文（自动填充） ──────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "period": "",
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
        logger.warning("A17-3-1 project context 查询失败: %s", e)

    return {
        "meta_info": meta_info,
        "sections": sections,
        "a173_reference": a173_reference,
        "project_context": project_context,
    }
