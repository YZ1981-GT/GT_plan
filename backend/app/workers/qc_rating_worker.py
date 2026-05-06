"""QC 评级定时任务 Worker — 每月 1 日凌晨计算上月快照

Refinement Round 3 — 需求 3.7：
评级计算作为定时任务，每月 1 日凌晨批量计算上月快照，
快照存 project_quality_ratings。

Worker 模式与 sla_worker 一致：导出 `async def run(stop_event: asyncio.Event)`。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("qc_rating_worker")

# 每小时检查一次是否到了每月 1 日
CHECK_INTERVAL_SECONDS = 3600


async def run(stop_event: asyncio.Event) -> None:
    """QC 评级定时任务主循环。

    每小时检查一次当前日期：
    - 如果是每月 1 日且当月尚未执行过，则计算上月所有项目的评级快照。
    - stop_event.set() 后退出循环。
    """
    logger.info("[QC-RATING-WORKER] started, worker_id=qc_rating_worker")
    last_executed_month: str | None = None

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
            current_month_key = now.strftime("%Y-%m")

            # 只在每月 1 日执行，且当月只执行一次
            if now.day == 1 and last_executed_month != current_month_key:
                logger.info(
                    "[QC-RATING-WORKER] monthly trigger: computing ratings for previous month"
                )
                await _compute_monthly_ratings(now)
                last_executed_month = current_month_key
                logger.info("[QC-RATING-WORKER] monthly computation completed")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[QC-RATING-WORKER] check loop error: %s", e)


async def _compute_monthly_ratings(now: datetime) -> None:
    """计算上月所有项目的评级快照。"""
    from app.core.database import async_session
    from app.services.quality_rating_service import quality_rating_service

    # 上月的年份
    if now.month == 1:
        year = now.year - 1
    else:
        year = now.year

    async with async_session() as db:
        try:
            count = await quality_rating_service.compute_all_projects(db, year)
            await db.commit()
            logger.info(
                "[QC-RATING-WORKER] computed ratings for %d projects, year=%d",
                count,
                year,
            )
        except Exception as e:
            await db.rollback()
            logger.error("[QC-RATING-WORKER] batch computation failed: %s", e)
            raise
