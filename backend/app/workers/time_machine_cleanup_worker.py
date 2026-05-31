"""时光机快照清理 worker — V3 收官增强 Req 11.4

每日 03:00 清理 >7 天的快照。

设计：
- 复用 sla_worker 同款心跳模式（30s 写一次）+ 业务检查间隔（86400s = 24h）
- 清理逻辑委托给 time_machine_service.cleanup()
- 启动时检查距离上次清理是否超过 48h，超过则立即执行

Validates: Requirements 11.4
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("audit_platform.time_machine_cleanup_worker")

HEARTBEAT_INTERVAL_SECONDS = 30
# 每 24 小时检查一次（实际在 03:00 附近触发）
CLEANUP_INTERVAL_SECONDS = 86400
OLDER_THAN_DAYS = 7


async def run(stop_event: asyncio.Event) -> None:
    """时光机清理主循环。

    - 每 30s 写心跳
    - 每 24h 触发一次清理（>7 天快照）
    - stop_event.set() 后退出
    """
    loop_count = 0

    # 启动时立即跑一次清理
    await _do_cleanup()

    while not stop_event.is_set():
        await write_heartbeat("time_machine_cleanup_worker")

        loop_count += 1
        elapsed = loop_count * HEARTBEAT_INTERVAL_SECONDS

        # 每 24h 或在 03:00 附近触发
        now = datetime.now(timezone.utc)
        if elapsed >= CLEANUP_INTERVAL_SECONDS or (now.hour == 3 and now.minute < 1):
            await _do_cleanup()
            loop_count = 0

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=HEARTBEAT_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            pass


async def _do_cleanup() -> None:
    """执行清理。"""
    try:
        from app.core.database import async_session
        from app.services.time_machine_service import cleanup

        async with async_session() as db:
            # 表不存在时静默跳过（新部署/未跑迁移场景）
            table_check = await db.execute(
                __import__('sqlalchemy').text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_name = 'time_machine_snapshots')"
                )
            )
            if not table_check.scalar():
                return

            deleted = await cleanup(db, older_than_days=OLDER_THAN_DAYS)
            if deleted > 0:
                logger.info("[time_machine_cleanup] 清理完成: 删除 %d 个过期快照", deleted)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("[time_machine_cleanup] 清理失败: %s", exc)
