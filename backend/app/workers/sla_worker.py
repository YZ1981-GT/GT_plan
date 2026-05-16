"""SLA 超时检查 Worker — 每 15 分钟检查一次 + 每 30 秒写心跳

需求 10.1/10.3/10.5：从 main.py lifespan 中拆出 `_sla_check_loop`，
使用独立的 async 会话避免与请求连接池竞争。

R10 Spec C Sprint 1.1.2：每 30s 写心跳到 Redis（不阻断主检查间隔）。
"""

from __future__ import annotations

import asyncio
import logging

from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("sla_check")

INTERVAL_SECONDS = 900  # 15 分钟主检查间隔
HEARTBEAT_INTERVAL_SECONDS = 30


async def run(stop_event: asyncio.Event) -> None:
    """SLA 超时检查主循环。

    - 每 30s 写一次心跳（不依赖业务检查节奏）
    - 每 15 分钟做一次 SLA 检查
    - stop_event.set() 后退出循环
    """
    last_check_at = 0.0
    loop_count = 0
    while not stop_event.is_set():
        # 每轮先写心跳
        await write_heartbeat("sla_worker")

        # 计算距离上次 check 还剩多久
        loop_count += 1
        elapsed = loop_count * HEARTBEAT_INTERVAL_SECONDS

        if elapsed >= INTERVAL_SECONDS:
            try:
                from app.core.database import async_session
                from app.services.issue_ticket_service import issue_ticket_service
                async with async_session() as db:
                    escalated = await issue_ticket_service.check_sla_timeout(db)
                    if escalated:
                        await db.commit()
                        logger.info("[SLA] auto-escalated %d issues", len(escalated))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[SLA] check loop error: %s", e)
            loop_count = 0  # 重置计数

        # 等待 30s 或 stop_event
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            break
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            break
