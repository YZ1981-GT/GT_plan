"""核对表（checklist-table）渲染策略

当 component_type=checklist-table 时，从全局模板缓存取静态结构（docx/xlsx），
再从 checklist_responses 表按 wp_id 取用户填写数据合并返回。

A1-15/A1-16 等大型核对表：template 从全局 mtime 缓存取（静态，不存每个 wp 实例），
responses 从 checklist_responses 表按 wp_id 取。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）"""

    from app.services.checklist_docx_parser import get_checklist_template
    from app.services.checklist_xlsx_parser import get_checklist_xlsx_template, is_xlsx_checklist

    wp_code = ctx.wp_code
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 1. 模板加载（全局缓存，静态） ──────────────────────────────────────
    template_data = None
    try:
        if is_xlsx_checklist(wp_code):
            template_data = await get_checklist_xlsx_template(wp_code)
        else:
            template_data = await get_checklist_template(wp_code)
    except FileNotFoundError:
        logger.warning("核对表模板文件未找到: wp_code=%s", wp_code)
    except Exception as e:  # noqa: BLE001
        logger.warning("核对表模板解析失败 wp_code=%s: %s", wp_code, e)

    # ─── 2. 用户填写数据从 checklist_responses 表取 ────────────────────────
    responses: dict[str, dict] = {}
    try:
        responses_result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark, wp_ref "
                "FROM checklist_responses WHERE wp_id = :wp_id"
            ),
            {"wp_id": str(wp_id)},
        )
        responses = {
            row.item_id: {
                "conclusion": row.conclusion,
                "remark": row.remark,
                "wp_ref": row.wp_ref,
            }
            for row in responses_result.fetchall()
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("核对表响应数据查询失败 wp_id=%s: %s", wp_id, e)

    return {
        "template": template_data,
        "responses": responses,
    }
