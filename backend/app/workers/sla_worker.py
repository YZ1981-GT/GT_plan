"""SLA 超时检查 Worker — 每 15 分钟检查一次

需求 10.1/10.3/10.5：从 main.py lifespan 中拆出 `_sla_check_loop`，
使用独立的 async 会话避免与请求连接池竞争。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("sla_check")

INTERVAL_SECONDS = 900  # 15 分钟


async def run(stop_event: asyncio.Event) -> None:
    """SLA 超时检查主循环。

    - stop_event.set() 后退出循环
    - 异常不影响主应用，记录 warning 后继续下一周期
    """
    while not stop_event.is_set():
        try:
            # 等待 INTERVAL_SECONDS 或 stop_event
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_SECONDS)
                # 提前被 stop_event 唤醒，退出循环
                break
            except asyncio.TimeoutError:
                pass  # 正常到达间隔，继续执行检查

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
