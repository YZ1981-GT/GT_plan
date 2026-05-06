"""复核人深度指标定时任务 Worker — 每日凌晨计算

Refinement Round 3 — 需求 6.4：
指标用于年度考评，非实时数据，允许每天凌晨刷新一次落 reviewer_metrics_snapshots 表。

Worker 模式与 qc_rating_worker 一致：导出 `async def run(stop_event: asyncio.Event)`。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("reviewer_metrics_worker")

# 每小时检查一次是否到了凌晨（0 点）
CHECK_INTERVAL_SECONDS = 3600


async def run(stop_event: asyncio.Event) -> None:
    """复核人指标定时任务主循环。

    每小时检查一次当前时间：
    - 如果是凌晨 0 点且当天尚未执行过，则计算当年所有复核人的指标快照。
    - stop_event.set() 后退出循环。
    """
    logger.info("[REVIEWER-METRICS-WORKER] started, worker_id=reviewer_metrics_worker")
    last_executed_date: str | None = None

    while not stop_event.is_set():
        try:
            # 等待 CHECK_INTERVAL_SECONDS 或 stop_event
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=CHECK_INTERVAL_SECONDS
                )
                # 提前被 stop_event 唤醒，退出循环
                break
            except asyncio.TimeoutError:
                pass  # 正常到达间隔，继续检查

            now = datetime.now(timezone.utc)
            today_key = now.strftime("%Y-%m-%d")

            # 每天凌晨 0 点执行一次（UTC 0 点）
            if now.hour == 0 and last_executed_date != today_key:
                logger.info(
                    "[REVIEWER-METRICS-WORKER] daily trigger: computing reviewer metrics"
                )
                await _compute_daily_metrics(now)
                last_executed_date = today_key
                logger.info("[REVIEWER-METRICS-WORKER] daily computation completed")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[REVIEWER-METRICS-WORKER] check loop error: %s", e)


async def _compute_daily_metrics(now: datetime) -> None:
    """计算当年所有复核人的指标快照。"""
    from app.core.database import async_session
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    year = now.year

    async with async_session() as db:
        try:
            count = await reviewer_metrics_service.compute_all_reviewers(db, year)
            await db.commit()
            logger.info(
                "[REVIEWER-METRICS-WORKER] computed metrics for %d reviewers, year=%d",
                count,
                year,
            )
        except Exception as e:
            await db.rollback()
            logger.error(
                "[REVIEWER-METRICS-WORKER] batch computation failed: %s", e
            )
            raise
