"""A3-8 商誉减值测试 — 双模式渲染策略

component_type = "a3-8-goodwill-impairment"
解析 A3-8/A3-8-1 模板为结构骨架，合并 field_overrides 用户录入数据。
返回 {impairmentData, recoverableData, responses} 供 GtA38GoodwillImpairment.vue 消费。
"""

from __future__ import annotations

import logging

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """A3-8 商誉减值测试渲染策略入口.

    流程:
    1. 解析模板获取 impairmentData/recoverableData 骨架 + 编制说明
    2. 从 field_overrides(scope=a3_8_goodwill:{wp_id}) 查询用户录入的 responses
    3. 合并返回
    """
    from app.services.a3_8_goodwill_parser import parse_a3_8_goodwill
    from app.services.field_override_service import FieldOverrideService

    skeleton = parse_a3_8_goodwill(ctx.template_file_path)

    responses: dict = {
        "impairment_rows": [],
        "allocation_rows": [],
        "recoverable": {},
        "header": {},
    }

    try:
        svc = FieldOverrideService(ctx.db)
        scope = f"a3_8_goodwill:{ctx.wp_id}"
        overrides = await svc.get_batch(
            project_id=ctx.project_id,
            year=ctx.year or 0,
            scope=scope,
        )
        # overrides 结构: {item_key: {field: value}}
        # item_key 约定：impairment_rows / allocation_rows / recoverable / header
        for item_key, fields in overrides.items():
            raw = fields.get("value")
            if item_key in ("impairment_rows", "allocation_rows") and isinstance(raw, list):
                responses[item_key] = raw
            elif item_key in ("recoverable", "header") and isinstance(raw, dict):
                responses[item_key] = raw
    except Exception as e:  # noqa: BLE001
        logger.warning("A3-8 field_overrides 查询失败 wp_id=%s: %s", ctx.wp_id, e)

    return {
        "impairmentData": skeleton["impairmentData"],
        "recoverableData": skeleton["recoverableData"],
        "responses": responses,
    }
