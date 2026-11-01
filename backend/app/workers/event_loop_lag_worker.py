"""每个 Web worker 的事件循环延迟采样器。"""
from __future__ import annotations

import asyncio
import logging

from app.services.platform_metrics import observe_event_loop_lag

logger = logging.getLogger("event_loop_lag")
INTERVAL_SECONDS = 1.0


async def run(stop_event: asyncio.Event) -> None:
    """按绝对目标时刻采样，阻塞造成的延迟不会被下一次 sleep 吞掉。"""
    loop = asyncio.get_running_loop()
    target = loop.time() + INTERVAL_SECONDS
    try:
        while not stop_event.is_set():
            timeout = max(0.0, target - loop.time())
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=timeout)
                return
            except asyncio.TimeoutError:
                pass
            sampled_at = loop.time()
            observe_event_loop_lag(max(0.0, sampled_at - target), sampled_at)
            target += INTERVAL_SECONDS
            # 长阻塞后跳过已经过期的采样点，避免立即忙循环补样本。
            if target <= sampled_at:
                missed = int((sampled_at - target) // INTERVAL_SECONDS) + 1
                target += missed * INTERVAL_SECONDS
    except asyncio.CancelledError:
        logger.info("event-loop lag worker stopped")
        raise
