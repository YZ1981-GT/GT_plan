"""A1-12 重大事项决定程序核查表 — 双模式渲染策略

component_type = "a1-12-dual-checklist"
解析 A1-12 DOCX 模板为结构化 A112ChecklistData，合并 field_overrides 响应数据。
"""

from __future__ import annotations

import logging

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """A1-12 双模式渲染策略入口.

    返回 {checklistData, responses} 供前端 GtA112DualChecklist 消费。

    流程:
    1. 解析 DOCX 模板获取 checklistData（header/categories/signatures）
    2. 从 field_overrides 查询用户填写的 responses（scope=a112_checklist:{wp_id}）
    3. 合并返回
    """
    from app.services.a112_checklist_parser import parse_a112_checklist
    from app.services.field_override_service import FieldOverrideService

    # ─── 1. 解析 DOCX 获取 checklistData ────────────────────────────────
    docx_path = ctx.template_file_path
    checklist_data = parse_a112_checklist(docx_path)

    # ─── 2. 从 field_overrides 获取用户 responses ───────────────────────
    responses: dict = {"items": {}, "header": {}, "custom_items": []}

    try:
        svc = FieldOverrideService(ctx.db)
        scope = f"a112_checklist:{ctx.wp_id}"
        overrides = await svc.get_batch(
            project_id=ctx.project_id,
            year=ctx.year or 0,
            scope=scope,
        )

        # overrides 结构: {item_key: {field: value}}
        # 按 item_key 前缀分类归入 responses 子结构
        for item_key, fields in overrides.items():
            if item_key.startswith("item-"):
                # 核查项响应: applicable / ref_index
                responses["items"][item_key] = fields
            elif item_key == "header":
                # 头部信息覆盖: business_class / is_first_engagement
                responses["header"] = fields
            elif item_key == "custom_items":
                # 第二类自定义事项（JSON 序列化存储）
                raw = fields.get("value")
                if isinstance(raw, list):
                    responses["custom_items"] = raw
            elif item_key.startswith("custom-"):
                # 单条自定义事项（备选存储模式）
                responses["items"][item_key] = fields

    except Exception as e:  # noqa: BLE001
        logger.warning(
            "A1-12 field_overrides 查询失败 wp_id=%s: %s", ctx.wp_id, e,
        )

    return {"checklistData": checklist_data, "responses": responses}
