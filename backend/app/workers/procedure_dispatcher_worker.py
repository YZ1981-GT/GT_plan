"""程序行任务有序投递 dispatcher 后台 worker（Task 10）。

Feature: procedure-delegation-notification
需求：10.1-10.6, 10.9, 13.2, 13.8
Design：C10（ProcedureDeliveryDispatcher）、Deployment matrix（PROCEDURE_TASK_DISPATCHER_ENABLED
        gate dispatcher claim）

从 main.py lifespan 的 `_start_workers` 启动、`stop_event` 优雅关闭。
开关 `PROCEDURE_TASK_DISPATCHER_ENABLED=False`（expand 阶段默认）时 worker 直接退出，
已有 outbox 事件保留（Req 13.2/13.8）。

连接铁律：dispatcher 每步用自有 session（``ProcedureDeliveryDispatcher`` 内部
``async_session_factory``），不占请求 session；SSE 走 broadcast_raw 不持有 asyncpg 连接。
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.services.procedure_delivery_dispatcher import ProcedureDeliveryDispatcher

logger = logging.getLogger("procedure_dispatcher")

# 空闲轮询间隔（有事件时快速连续处理；无事件时退避到此间隔）。
IDLE_INTERVAL_SECONDS = float(
    __import__("os").getenv("PROCEDURE_DISPATCHER_POLL_INTERVAL", "2")
)
BUSY_INTERVAL_SECONDS = 0.05


async def run(stop_event: asyncio.Event) -> None:
    """dispatcher 主循环。开关关闭时直接退出（不 claim，保留事件）。"""
    if not settings.PROCEDURE_TASK_DISPATCHER_ENABLED:
        logger.info("[dispatcher] PROCEDURE_TASK_DISPATCHER_ENABLED=false，worker 退出（事件保留）")
        return

    dispatcher = ProcedureDeliveryDispatcher()
    logger.info("[dispatcher] 启动 worker_id=%s", dispatcher.worker_id)

    while not stop_event.is_set():
        interval = IDLE_INTERVAL_SECONDS
        try:
            result = await dispatcher.run_once()
            if result.get("skipped"):
                interval = IDLE_INTERVAL_SECONDS
            elif result.get("claimed", 0) > 0:
                # 本轮领到事件 → 尽快继续拉下一批（避免大 backlog 时空转等待）。
                interval = BUSY_INTERVAL_SECONDS
                if result.get("dead_letter"):
                    logger.warning(
                        "[dispatcher] 本轮 %d 事件进入 dead-letter，需人工排查/replay",
                        result["dead_letter"],
                    )
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 — 单轮异常不终止 worker
            logger.warning("[dispatcher] 主循环异常: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass

    logger.info("[dispatcher] worker 停止")
