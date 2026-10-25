"""S1/S8/S9/S10/S17 checklist sheet 渲染策略。

这些 componentType 在前端已有专属组件，但不能让多 sheet dispatch 落入
``onlyoffice-sheet`` 或模板网格 fallback。本策略只读取对应的
``checklist_responses.remark`` JSON，并把其内容作为专属 payload 返回。

S17 的三个 detail sheet 共用 ``s17-nonrecurring-detail``；sheet identity
始终来自当前 ClassificationResult，而不是通过名称 substring 猜测。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


# D3.1 的 canonical componentType → checklist_responses.item_id 映射。
# 参考/说明型 sheet 没有可写保存项，仍需要命中专属 renderer，故值为 None。
S_CHECKLIST_ITEM_IDS: dict[str, str | None] = {
    "s1-regulation-record": "S1-1-sheet-data",
    "s8-adjudication": "S8-1-sheet-data",
    "s9-adjudication": "S9-1-sheet-data",
    "s9-internal-control": "S9-2-sheet-data",
    "s9-legal-regulations": None,
    "s9-program-description": None,
    "s10-adjudication": "S10-1-sheet-data",
    "s10-internal-control": "S10-2-sheet-data",
    "s10-environmental-regulations": None,
    "s17-nonrecurring-detail": "S17-1-sheet-data",
    "s17-reconciliation": "S17-11-sheet-data",
    "s17-tax-impact": "S17-21-sheet-data",
}


def _sheet_name(ctx: RenderContext) -> str:
    """返回当前模板分类中的精确 sheet 名，不做模糊匹配或重写。"""
    classification = getattr(ctx, "classification", None)
    return str(getattr(classification, "sheet_name", "") or "")


def _light_payload(ctx: RenderContext, *, error: str | None = None) -> dict[str, Any]:
    """构造不含 cells 的轻量专属结果。"""
    payload: dict[str, Any] = {
        "component_type": ctx.component_type,
        "sheet_name": _sheet_name(ctx),
    }
    if error:
        payload["error"] = error
    return payload


async def render(ctx: RenderContext) -> dict | None:
    """渲染 S checklist sheet，返回专属 payload 而非网格数据。

    ``remark`` 保存的是组件 payload 的 JSON 对象；其字段合并到返回值顶层，
    以兼容现有 S-checklist 组件读取 ``html_data.<field>`` 的约定。数据库读取
    包在 SAVEPOINT 内，查询失败只返回可诊断的轻量结果，不污染 render-config
    外层事务，也不会触发后续 OnlyOffice/grid fallback。
    """
    component_type = ctx.component_type
    if component_type not in S_CHECKLIST_ITEM_IDS:
        # 该函数只应由 RENDERER_DISPATCH 中的 canonical key 调用；保持安全的
        # 专属结果而不是把未知类型误当作 checklist 数据读取。
        return _light_payload(ctx, error="unsupported_component_type")

    item_id = S_CHECKLIST_ITEM_IDS[component_type]
    if item_id is None:
        return _light_payload(ctx)

    try:
        async with ctx.db.begin_nested():
            result = await ctx.db.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = :item_id"
                ),
                {"wp_id": str(ctx.wp_id), "item_id": item_id},
            )
            row = result.fetchone()
    except Exception as exc:  # noqa: BLE001 — SAVEPOINT 已隔离查询失败
        logger.warning(
            "S checklist payload 查询失败 component_type=%s wp_id=%s item_id=%s: %s",
            component_type,
            ctx.wp_id,
            item_id,
            exc,
        )
        return _light_payload(ctx, error="checklist_responses_unavailable")

    if row is None or not getattr(row, "remark", None):
        return _light_payload(ctx)

    raw_payload = row.remark
    try:
        payload = raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "S checklist payload JSON 解析失败 component_type=%s wp_id=%s item_id=%s: %s",
            component_type,
            ctx.wp_id,
            item_id,
            exc,
        )
        return _light_payload(ctx, error="invalid_checklist_payload")

    if not isinstance(payload, dict):
        logger.warning(
            "S checklist payload 必须为 JSON object component_type=%s wp_id=%s item_id=%s",
            component_type,
            ctx.wp_id,
            item_id,
        )
        return _light_payload(ctx, error="invalid_checklist_payload")

    # 只接受专属组件 payload；历史数据若残留顶层 cells 也不得重新暴露，
    # 否则 GtWpRenderer 可能把它识别为通用网格数据。
    payload = {key: value for key, value in payload.items() if key != "cells"}

    # 身份字段最后写入，避免用户 payload 覆盖当前 dispatch 的 component/sheet 身份。
    return {**payload, **_light_payload(ctx)}
