"""复核表（review-checklist）渲染策略

当 component_type=review-checklist 时，从模板缓存取静态检查项结构，
从 checklist_responses 取用户填写数据，并调用 evaluate_guard 注入 RBAC/Gate/Lock 状态。

A21~A25 五级复核表走此策略。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，包含 template + responses + guard 状态。"""

    from app.services.checklist_docx_parser import get_checklist_template
    from app.services.checklist_xlsx_parser import get_checklist_xlsx_template, is_xlsx_checklist
    from app.services.review_rbac_guard import evaluate_guard

    wp_code = ctx.wp_code
    wp_id = ctx.wp_id
    db = ctx.db
    project_id = ctx.project_id

    # ─── 1. 模板加载（全局缓存，静态） ──────────────────────────────────────
    template_data = None
    try:
        if is_xlsx_checklist(wp_code):
            template_data = await get_checklist_xlsx_template(wp_code)
        else:
            template_data = await get_checklist_template(wp_code)
    except FileNotFoundError:
        logger.warning("复核表模板文件未找到: wp_code=%s", wp_code)
    except Exception as e:  # noqa: BLE001
        logger.warning("复核表模板解析失败 wp_code=%s: %s", wp_code, e)

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
        logger.warning("复核表响应数据查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 3. RBAC + Sequential Gate + Sign-Lock guard ─────────────────────
    guard_data: dict = {}
    if ctx.user_id:
        try:
            guard_result = await evaluate_guard(
                db=db,
                user_id=ctx.user_id,
                project_id=project_id,
                wp_code=wp_code,
                wp_id=wp_id,
            )
            guard_data = {
                "readonly": guard_result.readonly,
                "locked": guard_result.locked,
                "signed_by": guard_result.signed_by,
                "signed_at": guard_result.signed_at,
                "gate_reason": guard_result.gate_reason,
                "unresolved_count": guard_result.unresolved_count,
                "rbac_denied": guard_result.rbac_denied,
            }
        except Exception as e:  # noqa: BLE001
            # 异常安全降级为 readonly
            logger.warning(
                "复核表 guard 评估失败 wp_code=%s: %s", wp_code, e,
            )
            guard_data = {"readonly": True}
    else:
        # 无 user_id 时安全降级
        guard_data = {"readonly": True}

    return {
        "template": template_data,
        "responses": responses,
        "guard": guard_data,
    }
