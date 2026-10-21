"""耐久 Outbox 重放 Worker。

同一 lifespan worker 处理两类耐久事件：
- import_event_outbox（受 LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED 控制）；
- formula_runtime_outbox（始终轮询，发布 formula_runtime.* SSE，业务 stale 已在主事务触发）。

两类发布都使用独立 session；失败保留 pending/attempts，后续轮询重试。
"""

from __future__ import annotations

import asyncio
import logging
import random
import time as _time

from app.core.config import settings
from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("import_outbox")


async def run(stop_event: asyncio.Event) -> None:
    """Outbox 重放主循环。"""
    import_enabled = bool(settings.LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED)
    if not import_enabled:
        logger.info("[OutboxReplay] import replay disabled; formula runtime replay remains active")

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
        # R10 Spec C 1.1.4：每轮先写心跳
        await write_heartbeat("outbox_replay_worker")

        try:
            from app.core.database import async_session
            from app.services.event_bus import event_bus
            from app.services.formula_runtime.outbox import publish_pending_events

            async def _publish_formula_runtime(event_type: str, payload: dict) -> None:
                event_bus.broadcast_raw(f"formula_runtime.{event_type}", payload)

            report = {"failed_count": 0, "moved_to_dlq_count": 0, "exhausted_total_count": 0}
            cleanup_report = {"deleted_count": 0}
            formula_delivered = 0
            async with async_session() as db:
                formula_delivered = await publish_pending_events(
                    db,
                    publisher=_publish_formula_runtime,
                    batch_size=limit,
                )

                if import_enabled:
                    from app.services.import_event_consumption_service import ImportEventConsumptionService
                    from app.services.import_event_outbox_service import ImportEventOutboxService

                    replay_kwargs = {"limit": limit}
                    if max_attempts > 0:
                        replay_kwargs["max_attempts"] = max_attempts
                    report = await ImportEventOutboxService.replay_pending(db, **replay_kwargs)

                    if cleanup_enabled and (_time.monotonic() - last_cleanup_monotonic) >= cleanup_interval_seconds:
                        cleanup_report = await ImportEventConsumptionService.cleanup_older_than_days(
                            db,
                            retention_days=cleanup_retention_days,
                            batch_size=cleanup_batch_size,
                        )
                        last_cleanup_monotonic = _time.monotonic()
                    try:
                        from app.services.ledger_import.metrics import set_dlq_depth
                        dlq_depth = await ImportEventOutboxService.dlq_depth(db)
                        set_dlq_depth(dlq_depth)
                    except Exception:  # pragma: no cover - metrics 失败不阻断主循环
                        logger.debug("[OutboxReplay] failed to update DLQ gauge", exc_info=True)
                await db.commit()

            if formula_delivered:
                logger.info("[OutboxReplay] delivered %s formula runtime event(s)", formula_delivered)

            if report.get("failed_count"):
                logger.warning(
                    "[OutboxReplay] failed_count=%s report=%s",
                    report.get("failed_count"), report,
                )
            if report.get("moved_to_dlq_count", 0) > 0:
                logger.warning(
                    "[OutboxReplay] moved_to_dlq_count=%s (events exhausted retries, "
                    "investigate DLQ table event_outbox_dlq)",
                    report.get("moved_to_dlq_count"),
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
