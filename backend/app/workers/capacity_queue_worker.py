"""耐久任务队列深度 / 排队年龄采样器（spec platform-heavy-jobs-and-capacity-closure 任务 0.2）。

``/api/health`` 明确不在请求里扫任务表，所以队列深度由本 worker 周期采样后写进
进程内快照与 Prometheus，health 只读快照。

两条队列各用**独立 session**：PG 上首条查询失败会让事务 aborted，连带后面的查询全挂，
一条队列读不到不该把另一条也变成「不可用」。采样失败只标记不可用并保留上次已知值，
绝不把「读不到」发布成 0（见 ``platform_metrics.mark_durable_queue_unavailable``）。
"""

from __future__ import annotations

import asyncio
import logging

from app.core.database import async_session
from app.services.platform_metrics import (
    mark_durable_queue_unavailable,
    observe_durable_queue,
)

logger = logging.getLogger("capacity_queue")
INTERVAL_SECONDS = 15.0


async def _sample(queue: str, reader) -> None:
    loop = asyncio.get_running_loop()
    try:
        async with async_session() as db:
            snapshot = await reader(db)
            # 只读采样，不留开启的事务给连接池。
            await db.rollback()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - 采样失败不得中断 worker，也不得伪装成 0
        mark_durable_queue_unavailable(
            queue,
            reason=f"{type(exc).__name__}: {exc}"[:200],
            sampled_at=loop.time(),
        )
        logger.warning("耐久队列采样失败 queue=%s: %s", queue, exc)
        return
    observe_durable_queue(
        queue,
        counts={
            "queued": int(snapshot.get("queued") or 0),
            "retry_wait": int(snapshot.get("retry_wait") or 0),
            "running": int(snapshot.get("running") or 0),
        },
        oldest_age_seconds=float(snapshot.get("oldest_queue_age_seconds") or 0.0),
        sampled_at=loop.time(),
    )


async def sample_once() -> None:
    from app.services import ai_task_job_service, platform_job_service

    await _sample("platform_jobs", platform_job_service.queue_snapshot)
    await _sample("ai_task_items", ai_task_job_service.queue_snapshot)


async def run(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            await sample_once()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_SECONDS)
                return
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        logger.info("capacity queue worker stopped")
        raise
