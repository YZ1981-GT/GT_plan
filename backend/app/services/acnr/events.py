"""ACNR events.py — 缓存失效钩子 + 降级策略

orchestrator `after_save` 触发 `WORKPAPER_SAVED` →
EventBus handler 调用 `invalidate()` 统一清理 L3 运行时条目与 overlay 缓存，
同时委托旧 address_registry 失效 WP 域（strangler-fig 过渡期）。

Requirements: 23.1, 23.2
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def invalidate(
    project_id: str,
    *,
    wp_id: str | None = None,
    addr_id: str | None = None,
    trigger: str | None = None,
    extra_sheets: list[str] | None = None,
) -> None:
    """ACNR 统一缓存失效（由 WORKPAPER_SAVED 事件驱动）。

    失效策略：
    1. 清除 L3 RuntimeIndex 运行时条目（按 project_id 或增量按 wp_id/sheets）
    2. 清除 L2 overlay 缓存（按 project_id）
    3. 委托旧 address_registry.invalidate_async 失效 WP 域（strangler-fig 过渡）
    4. 记录可观测日志

    增量模式（trigger/extra_sheets 非空时）：
    - 仅清除指定 wp_id 或受影响 sheets 对应的 L3 条目
    - 完整清除仍走 project_id 级别

    Args:
        project_id: 项目 ID（必传）
        wp_id: 底稿 ID（可选，用于增量失效）
        addr_id: 特定地址 ID（可选，预留）
        trigger: 触发来源（html_save / univer_save / onlyoffice_callback 等）
        extra_sheets: 受影响的 sheet 列表（可选，用于增量失效）

    本函数不抛异常 — 失效失败仅 warning，不阻断主流程；TTL 为最终兜底。
    """
    if not project_id:
        return

    logger.info(
        "acnr.invalidate: project=%s wp_id=%s trigger=%s sheets=%s",
        project_id,
        wp_id,
        trigger,
        extra_sheets,
    )

    # ── Step 1: L3 RuntimeIndex 失效 ─────────────────────────────────────
    try:
        from app.services.acnr.runtime import clear_runtime_entries

        # M1 阶段采用 project_id 级全量清除
        # 未来可按 wp_id / extra_sheets 做增量（仅删匹配的 RuntimeCellEntry）
        clear_runtime_entries(project_id)
    except Exception as exc:
        logger.warning("acnr.invalidate L3 clear failed: %s", exc)

    # ── Step 2: L2 overlay 缓存失效 ──────────────────────────────────────
    try:
        from app.services.acnr.overlay import clear_project_overlays

        clear_project_overlays(project_id)
    except Exception as exc:
        logger.warning("acnr.invalidate L2 overlay clear failed: %s", exc)

    # ── Step 3: 委托旧 address_registry 失效 WP 域（strangler-fig 过渡）──
    try:
        from app.services.address_registry import address_registry

        await address_registry.invalidate_async(
            str(project_id), domain="wp"
        )
    except Exception as exc:
        logger.warning(
            "acnr.invalidate address_registry delegate failed: %s", exc
        )


async def on_workpaper_saved(payload: Any) -> None:
    """WORKPAPER_SAVED 事件处理器 — 委托 invalidate() 统一缓存失效。

    EventBus handler 签名: async def handler(payload: EventPayload) -> None
    从 EventPayload 解包参数后调用 invalidate()。

    payload.extra 预期字段（by WorkpaperSaveOrchestrator）:
        - wp_id: str
        - trigger: str
        - sheets: list[str] | None（可选增量）
    """
    project_id = getattr(payload, "project_id", None)
    if not project_id:
        return

    extra = getattr(payload, "extra", {}) or {}
    wp_id = extra.get("wp_id")
    trigger = extra.get("trigger")
    extra_sheets = extra.get("sheets")

    await invalidate(
        str(project_id),
        wp_id=wp_id,
        trigger=trigger,
        extra_sheets=extra_sheets,
    )


def register_acnr_invalidation_handler() -> None:
    """注册 ACNR 失效事件处理器到 EventBus。

    在 register_event_handlers() 末尾调用。
    """
    from app.models.audit_platform_schemas import EventType
    from app.services.event_bus import event_bus

    event_bus.subscribe(EventType.WORKPAPER_SAVED, on_workpaper_saved)
    logger.debug("ACNR: invalidation handler registered (WORKPAPER_SAVED)")
