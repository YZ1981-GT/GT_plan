"""导入事件 Outbox 重放 Worker

需求 10.1/10.3/10.5：从 main.py lifespan 中拆出 `_outbox_replay_loop`。
受 `settings.LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED` 控制；未启用时直接返回。

功能：
  - 重放 import_event_outbox 中 pending/failed 的事件
  - 定期清理 import_event_consumptions 中过期的记录
  - 支持指数退避与抖动
"""

from __future__ import annotations

import asyncio
import logging
import random
import time as _time

from app.core.config import settings

logger = logging.getLogger("import_outbox")


async def run(stop_event: asyncio.Event) -> None:
    """Outbox 重放主循环。"""
    if not settings.LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED:
        logger.info("[OutboxReplay] disabled by settings, worker exits")
        return

    base_interval = max(5, int(settings.LEDGER_IMPORT_OUTBOX_REPLAY_INTERVAL_SECONDS))
    max_backoff = max(base_interval, int(settings.LEDGER_IMPORT_OUTBOX_REPLAY_MAX_BACKOFF_SECONDS))
    jitter_ratio = min(max(float(settings.LEDGER_IMPORT_OUTBOX_REPLAY_JITTER_RATIO), 0.0), 0.5)
    limit = max(1, int(settings.LEDGER_IMPORT_OUTBOX_REPLAY_LIMIT))
    max_attempts = int(settings.LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS or 0)
    cleanup_enabled = bool(settings.LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_ENABLED)
    cleanup_retention_days = max(1, int(settings.LEDGER_IMPORT_EVENT_CONSUMPTION_RETENTION_DAYS))
    cleanup_interval_seconds = max(60, int(settings.LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_INTERVAL_SECONDS))
    cleanup_batch_size = max(1, int(settings.LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_BATCH_SIZE))
    last_cleanup_monotonic = 0.0
    consecutive_failures = 0

    while not stop_event.is_set():
        try:
            from app.core.database import async_session
            from app.services.import_event_consumption_service import ImportEventConsumptionService
            from app.services.import_event_outbox_service import ImportEventOutboxService

            async with async_session() as db:
                replay_kwargs = {"limit": limit}
                if max_attempts > 0:
                    replay_kwargs["max_attempts"] = max_attempts
                report = await ImportEventOutboxService.replay_pending(db, **replay_kwargs)

                cleanup_report = {"deleted_count": 0}
                if cleanup_enabled and (_time.monotonic() - last_cleanup_monotonic) >= cleanup_interval_seconds:
                    cleanup_report = await ImportEventConsumptionService.cleanup_older_than_days(
                        db,
                        retention_days=cleanup_retention_days,
                        batch_size=cleanup_batch_size,
                    )
                    last_cleanup_monotonic = _time.monotonic()
                await db.commit()

            if report.get("failed_count"):
                logger.warning(
                    "[OutboxReplay] failed_count=%s report=%s",
                    report.get("failed_count"), report,
                )
            if report.get("exhausted_total_count", 0):
                logger.warning(
                    "[OutboxReplay] exhausted_total_count=%s, manual intervention required",
                    report.get("exhausted_total_count"),
                )
            if cleanup_report.get("deleted_count", 0) > 0:
                logger.info(
                    "[OutboxReplay] cleaned up %s import event consumption rows",
                    cleanup_report.get("deleted_count"),
                )

            if report.get("failed_count", 0) > 0:
                consecutive_failures += 1
            else:
                consecutive_failures = 0

            effective_interval = min(
                max_backoff, base_interval * (2 ** min(consecutive_failures, 5))
            )
            jitter = effective_interval * jitter_ratio * random.random()
            # 等待 (interval + jitter) 或 stop_event
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=effective_interval + jitter)
                break
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[OutboxReplay] loop error: %s", e)
            consecutive_failures += 1
            effective_interval = min(
                max_backoff, base_interval * (2 ** min(consecutive_failures, 5))
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=effective_interval)
                break
            except asyncio.TimeoutError:
                pass
