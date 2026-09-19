"""epoch 失效 Redis dispatcher 后台 worker（visibility-isolation-go-live-hardening Task 3 / R2）。

Feature: visibility-isolation-go-live-hardening
Design: 组件 H2 DispatcherLifecycle。
Requirements: 2.1–2.10。

把父 spec 已构建的失效派发器（``app.services.wp_visibility.invalidation_dispatcher``）从
"已构建" 挂载为 "LIVE"：从 ``app.main`` lifespan 的 ``_start_workers`` 启动、``stop_event``
优雅关闭，与既有 worker（如 ``procedure_dispatcher_worker``）**同范式**。本 worker 只做
**挂载 + 优雅降级 + 重连编排**，不改 ``epoch_cache`` / ``invalidation_dispatcher`` 语义
（两者恒 fail-closed，父 spec 已建已测）。

两条并发子循环（``run`` 内 ``asyncio.gather``）：

  1. **subscriber（快路径淘汰）**：``run_invalidation_subscriber`` psubscribe 全项目失效 channel，
     收到即 ``PersistentEpochCache.invalidate(project_id)`` 立即丢弃本地 epoch 新鲜度 →
     下次请求重读 DB epoch → 撤权 ≤1s 收敛（Req 2.3/2.4）。外层加**指数退避重连**：
     Redis 启动时不可用 → 不阻塞启动、进入退避重连（Req 2.5）；运行期断连 → 重连并 resubscribe
     （Req 2.9）；重连期间由 DB epoch ≤1s 安全网兜底 fail-closed（Req 2.6/2.7）。

  2. **publisher（提交后 fan-out）**：轮询 ``wp_visibility_invalidation_outbox``（``_bump_epoch``
     在权限/委派事务内写入，router commit 后可见），经 ``InvalidationDispatcher.publish_pending``
     fan-out 到各项目 Redis channel（Req 2.2）。用**自有 session**（不占请求 session），
     Redis 不可得时 ``publish_pending`` 返回 0（no-op 降级，Req 2.5/2.6）。

开关铁律：``VISIBILITY_INVALIDATION_DISPATCHER_ENABLED=False`` → worker 直接退出（回退路径，
撤权仍由 DB ≤1s 安全网兜底，绝不 stale-allow）。任何 Redis 异常只 warning，绝不冒泡改变授权结果。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from app.core.config import settings
from app.services.wp_visibility.epoch_cache import PersistentEpochCache, get_epoch_cache
from app.services.wp_visibility.invalidation_dispatcher import (
    InvalidationDispatcher,
    run_invalidation_subscriber,
)

logger = logging.getLogger("wp_visibility.invalidation_dispatcher_worker")

# 重连退避（Redis 不可用时）：指数退避，上界 30s。
_BASE_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 30.0
# subscriber 连续健康运行超过此秒数视为一次成功连接 → 断连后重置退避。
_HEALTHY_RUN_SECONDS = 2.0
# publisher 轮询间隔（提交后 fan-out 延迟上界；正确性不依赖它，由 DB ≤1s 安全网保证）。
_PUBLISH_INTERVAL_SECONDS = 1.0


async def _sleep_or_stop(stop_event: asyncio.Event, timeout: float) -> bool:
    """等待 ``timeout`` 秒或 ``stop_event`` 置位；置位（应关闭）返回 True。"""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


async def _run_subscriber_with_reconnect(
    stop_event: asyncio.Event,
    *,
    cache: PersistentEpochCache | None = None,
    redis_factory: Callable[[], Awaitable[object]] | None = None,
    base_backoff: float = _BASE_BACKOFF_SECONDS,
    max_backoff: float = _MAX_BACKOFF_SECONDS,
) -> None:
    """订阅失效 channel 并在 Redis 不可用/断连时指数退避重连（Req 2.5/2.9）。

    Redis 不可用（``redis_factory`` 返回 None 或抛错）→ 退避重连，绝不冒泡（应用照常运行，
    DB ≤1s 安全网兜底）。``run_invalidation_subscriber`` 返回（正常 psubscribe 断连）→ 重连
    并 resubscribe。``stop_event`` 置位 → 优雅退出。
    """
    if redis_factory is None:
        from app.core.redis import get_redis as _get_redis

        redis_factory = _get_redis
    cache = cache if cache is not None else get_epoch_cache()

    backoff = base_backoff
    while not stop_event.is_set():
        client = None
        try:
            client = await redis_factory()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — Redis 获取失败即降级重连
            logger.warning("invalidation_subscriber: get_redis 失败，退避重连: %s", exc)

        if client is None:
            # Redis 不可用（启动时或运行期）：应用不阻塞，退避重连，DB ≤1s 安全网兜底。
            if await _sleep_or_stop(stop_event, backoff):
                break
            backoff = min(backoff * 2, max_backoff)
            continue

        started = time.monotonic()
        try:
            # 复用父 spec 组件；psubscribe → 收到即 invalidate 本地缓存（快路径）。
            await run_invalidation_subscriber(cache, redis=client, stop_event=stop_event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — 订阅循环异常不冒泡
            logger.warning("invalidation_subscriber: 循环异常，重连: %s", exc)

        if stop_event.is_set():
            break

        # subscriber 返回（运行期断连）→ resubscribe。若曾健康运行一段时间则重置退避。
        if time.monotonic() - started >= _HEALTHY_RUN_SECONDS:
            backoff = base_backoff
        if await _sleep_or_stop(stop_event, backoff):
            break
        backoff = min(backoff * 2, max_backoff)


async def _run_publisher_loop(
    stop_event: asyncio.Event,
    *,
    dispatcher: InvalidationDispatcher | None = None,
    session_factory: Callable[[], object] | None = None,
    interval: float = _PUBLISH_INTERVAL_SECONDS,
) -> None:
    """轮询 invalidation outbox（提交后行）→ fan-out 到 Redis（Req 2.2）。

    自有 session（不占请求 session）；只读已提交 outbox 行故只 fan-out 权限事务提交后的失效。
    Redis 不可得 → ``publish_pending`` 返回 0（降级 no-op），正确性由 DB ≤1s 安全网保证。
    """
    if session_factory is None:
        from app.core.database import async_session as _async_session

        session_factory = _async_session
    # local_cache 用进程单例 → 同节点发布时即时收敛（快于跨节点 pub-sub）。
    dispatcher = dispatcher if dispatcher is not None else InvalidationDispatcher(
        local_cache=get_epoch_cache()
    )

    while not stop_event.is_set():
        try:
            async with session_factory() as db:
                await dispatcher.publish_pending(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — 单轮异常不终止 worker
            logger.warning("invalidation_publisher: 单轮异常: %s", exc)
        if await _sleep_or_stop(stop_event, interval):
            break


async def run(stop_event: asyncio.Event) -> None:
    """dispatcher 主入口（由 ``_start_workers`` 挂载）。开关关闭时直接退出（回退路径）。"""
    if not settings.VISIBILITY_INVALIDATION_DISPATCHER_ENABLED:
        logger.info(
            "[invalidation_dispatcher] VISIBILITY_INVALIDATION_DISPATCHER_ENABLED=false，"
            "worker 退出（撤权由 DB ≤1s epoch 安全网兜底）"
        )
        return

    logger.info("[invalidation_dispatcher] 启动（subscriber + publisher）")
    try:
        await asyncio.gather(
            _run_subscriber_with_reconnect(stop_event),
            _run_publisher_loop(stop_event),
        )
    except asyncio.CancelledError:
        raise
    finally:
        logger.info("[invalidation_dispatcher] worker 停止")
