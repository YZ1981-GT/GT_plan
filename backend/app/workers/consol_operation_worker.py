"""持久合并 operation worker；数据库 claim/lease 是执行权真源。"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

from app.services.consol_operation_runner import ExecutionResult, execute_claim, fail_claim
from app.services.consol_operation_service import (
    OperationClaim,
    claim_next_operation,
    renew_lease,
)
from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("audit_platform.consol_operation_worker")
WORKER_KEY = "consol_operation_worker"
POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 20.0
_TASKS: set[asyncio.Task] = set()


def _session_factory():
    from app.core.database import async_session
    return async_session()


async def _lease_heartbeat(claim: OperationClaim, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        try:
            async with _session_factory() as db:
                if not await renew_lease(db, claim):
                    return
                await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("[consol_operation] lease 心跳失败 operation=%s: %s", claim.operation_id, exc)


def _broadcast(execution: ExecutionResult) -> None:
    if not execution.event:
        return
    try:
        from app.services.event_bus import event_bus
        event_bus.broadcast_raw(execution.event, execution.event_payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[consol_operation] 终态广播失败: %s", exc)


async def run_operation_once(operation_id: UUID | None = None) -> UUID | None:
    owner = uuid4()
    async with _session_factory() as db:
        claim = await claim_next_operation(db, lease_owner=owner, operation_id=operation_id)
        if claim is None:
            return None
        await db.commit()

    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_lease_heartbeat(claim, stop))
    execution: ExecutionResult | None = None
    try:
        async with _session_factory() as db:
            try:
                execution = await execute_claim(db, claim)
                await db.commit()
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                logger.exception("[consol_operation] 执行失败 operation=%s", claim.operation_id)
                async with _session_factory() as failure_db:
                    execution = await fail_claim(failure_db, claim, exc)
                    await failure_db.commit()
        if execution is not None:
            _broadcast(execution)
        return claim.operation_id
    finally:
        stop.set()
        await asyncio.gather(heartbeat, return_exceptions=True)


async def drain() -> int:
    """执行当前可认领的全部 operation；被其他 running 阻塞的 queued 留待下一轮。"""
    count = 0
    while await run_operation_once() is not None:
        count += 1
    return count


def wake() -> asyncio.Task | None:
    """HTTP/事件入队后立即唤醒；即使任务丢失，常驻 worker 仍会从 DB 恢复。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    task = loop.create_task(drain())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return task


async def wait_for_operations() -> None:
    while _TASKS:
        await asyncio.gather(*list(_TASKS), return_exceptions=True)
    await drain()


async def run(stop_event: asyncio.Event) -> None:
    from app.workers._leader_lock import try_acquire_leadership

    while not stop_event.is_set():
        await write_heartbeat(WORKER_KEY)
        try:
            if await try_acquire_leadership(WORKER_KEY, ttl_ms=3000):
                await drain()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("[consol_operation] 本轮出错：%s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass

#: 注册到统一唤醒表：业务域只调 `wake_worker("consol_operation_worker")`，不 import 本模块
#: （🔴 2026-11-14 解 domain-boundary 的 `<domain> -> backend-workers` 反向依赖）。
from app.core.worker_wakeup import register_waker as _register_waker

_register_waker("consol_operation_worker", wake)
