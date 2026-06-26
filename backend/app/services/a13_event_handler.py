"""A13 错报评价 EventBus Handler — 事件驱动聚合触发 + debounce

当 A13-2/A13-3/A13-4/A13-5 任一 sheet 保存后，
自动触发 Aggregation_Resolver 重算 A13-1 汇总，
完成后 broadcast_raw SSE 通知前端刷新。

Debounce 策略: asyncio.Task + cancel 模式，2 秒窗口，
同 project_id+year 连续保存仅执行一次聚合。

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.models.audit_platform_schemas import EventPayload, EventType

logger = logging.getLogger(__name__)

# A13 子 sheet wp_code 匹配前缀
_A13_SUB_SHEETS = {"A13-2", "A13-3", "A13-4", "A13-5"}

# Debounce 窗口（秒）
_DEBOUNCE_SECONDS = 2.0

# Debounce 缓冲区: key = f"{project_id}:{year}" → asyncio.Task
_pending_tasks: dict[str, asyncio.Task] = {}


def _is_a13_sub_sheet(wp_code: str | None) -> bool:
    """判断 wp_code 是否匹配 A13 子 sheet（A13-2/A13-3/A13-4/A13-5）。"""
    if not wp_code:
        return False
    # 精确匹配或前缀匹配（如 A13-2a 也算）
    for prefix in _A13_SUB_SHEETS:
        if wp_code == prefix or wp_code.startswith(prefix):
            return True
    return False


def _debounce_key(project_id: UUID, year: int | None) -> str:
    """构建 debounce key: project_id + year。"""
    return f"{project_id}:{year or 'ALL'}"


async def _execute_aggregation(project_id: UUID, year: int) -> None:
    """执行 A13 聚合并 broadcast SSE 通知。

    在 debounce 延迟后调用，使用独立 DB session。
    """
    from app.core.database import async_session_factory
    from app.services.auto_data_resolvers import resolve_auto_data_source
    from app.services.event_bus import event_bus

    try:
        async with async_session_factory() as session:
            result = await resolve_auto_data_source(
                session, project_id, year, "a13_misstatement_summary"
            )
            await session.commit()
            logger.info(
                "A13 aggregation completed: project=%s year=%s status=%s",
                project_id, year,
                result.get("materiality", {}).get("status", "unknown"),
            )
    except Exception as e:
        logger.error(
            "A13 aggregation failed: project=%s year=%s: %s",
            project_id, year, e, exc_info=True,
        )
        return  # 异常时不推 SSE（保留旧 summary，Req 1.8）

    # 聚合成功 → broadcast_raw SSE 通知前端
    try:
        event_bus.broadcast_raw(
            event_type="a13_summary_updated",
            extra={
                "project_id": str(project_id),
                "year": year,
            },
        )
    except Exception as e:
        logger.warning("A13 SSE broadcast failed: %s", e)


async def _debounced_execute(project_id: UUID, year: int, key: str) -> None:
    """等待 debounce 窗口后执行聚合。

    如果在等待期间被 cancel，说明有新的保存事件进来，不执行。
    """
    try:
        await asyncio.sleep(_DEBOUNCE_SECONDS)
        # 等待完成，执行聚合
        await _execute_aggregation(project_id, year)
    except asyncio.CancelledError:
        # 被新事件取消，不执行（新事件会重新调度）
        pass
    finally:
        # 清理 pending
        _pending_tasks.pop(key, None)


async def _on_a13_sheet_saved(payload: EventPayload) -> None:
    """EventBus handler: 过滤 A13 子 sheet 保存事件，触发 debounced 聚合。

    注册到 EventType.WORKPAPER_SAVED。
    从 payload.extra 提取 wp_code 判断是否为 A13 子 sheet。
    """
    extra = payload.extra or {}

    # 优先从 extra.wp_code 获取（wp_html_save 路径）
    wp_code = extra.get("wp_code")

    # 如果 extra 中没有 wp_code，尝试从 wp_id 查询（wp_editor_router 路径）
    if not wp_code and extra.get("wp_id"):
        # 需要查 DB 获取 wp_code，但为了不阻塞，跳过
        # （A13 通过 wp_html_save 保存，extra 中会有 wp_code）
        return

    if not _is_a13_sub_sheet(wp_code):
        return

    project_id = payload.project_id
    year = payload.year
    if not project_id or not year:
        logger.warning(
            "A13 handler: missing project_id or year in payload, wp_code=%s",
            wp_code,
        )
        return

    logger.debug(
        "A13 sheet saved: wp_code=%s project=%s year=%s, scheduling aggregation",
        wp_code, project_id, year,
    )

    # Debounce: cancel 旧 task，创建新 task
    key = _debounce_key(project_id, year)
    existing = _pending_tasks.get(key)
    if existing and not existing.done():
        existing.cancel()

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_debounced_execute(project_id, year, key))
        _pending_tasks[key] = task
    except RuntimeError:
        # 无 event loop（测试环境）→ 直接执行
        await _execute_aggregation(project_id, year)


def register_a13_event_handlers() -> None:
    """注册 A13 事件处理器到全局 EventBus。

    在 app 启动时调用（main.py lifespan 中）。
    """
    from app.services.event_bus import event_bus

    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_a13_sheet_saved)

    # Req 4.6: B15 重要性变更时重新聚合 A13（重评估 carried-forward 记录）
    async def _on_materiality_changed(payload: EventPayload) -> None:
        """PM 变更 → 重新执行 A13 聚合（重评估所有错报 vs 新 PM）。"""
        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            return
        logger.info(
            "Materiality changed for project=%s year=%s, re-triggering A13 aggregation",
            project_id, year,
        )
        # 直接执行，不 debounce（PM 变更是低频事件）
        await _execute_aggregation(project_id, year)

    event_bus.subscribe(EventType.MATERIALITY_CHANGED, _on_materiality_changed)

    logger.debug("A13 event handlers registered (WORKPAPER_SAVED + MATERIALITY_CHANGED)")
