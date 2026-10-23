"""OO→HTML apply 中断后的后台重驱（spec writeback-followup-issue-closure R3.2）。

候选判据在 ``app.services.workpaper_sync.oo_apply_redrive``；本模块只管循环、选主与心跳：

- 每 :data:`POLL_SECONDS` 秒一轮，多副本只有拿到选主锁的那一个跑；
- 一轮只重驱一条（apply 重，且同一 room 的 apply 本就串行）；
- 重驱走与回调**同一个**入口（注册 / 绑定 / 协调器，``attempt=2``）：失败由那条路径写到
  operation 上（可见、可重试），application 因此离开候选集，不会被反复重驱。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from types import SimpleNamespace

from app.services.workpaper_sync.oo_apply_redrive import find_stuck_application
from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("audit_platform.oo_apply_redrive_worker")

POLL_SECONDS = 60.0
WORKER_KEY = "oo_apply_redrive_worker"


def _default_session_factory():
    from app.core.database import async_session

    return async_session()


async def redrive_once(*, session_factory=None) -> uuid.UUID | None:
    """找到一条中断的 apply 就重驱它，返回 application id；没有候选返回 ``None``。"""
    factory = session_factory or _default_session_factory
    async with factory() as db:
        found = await find_stuck_application(db)
        if found is None:
            return None
        application_id, operation_id = found
        logger.warning("[oo_apply_redrive] 重驱中断的 apply application=%s operation=%s", application_id, operation_id)
        from app.routers.wp_sync_router import _apply_durable_incoming

        outcome = SimpleNamespace(application_id=application_id, operation_id=operation_id, delivery_id=None)
        await _apply_durable_incoming(db, outcome=outcome, attempt=2)
        return application_id


async def run(stop_event: asyncio.Event) -> None:
    from app.workers._leader_lock import try_acquire_leadership

    while not stop_event.is_set():
        await write_heartbeat(WORKER_KEY)
        try:
            if await try_acquire_leadership(WORKER_KEY, ttl_ms=int(POLL_SECONDS * 2000)):
                await redrive_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — 单轮失败不让 worker 退出
            logger.warning("[oo_apply_redrive] 本轮出错：%s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass
