"""Staged dataset orphan cleaner — Sprint 6 / F26.

每小时扫一次：找 ``status='staged'`` 且创建超过 24h、对应 ImportJob 已不活跃
（terminal 状态或不存在）的 dataset 孤儿，自动清理 Tb* 行 + 标 failed。

孤儿成因：
- Worker 崩溃后 job 被 mark_failed 但 dataset 忘了清
- 手工 DB 改动
- Worker 启动时意外退出（dataset 建好但 job 未创建成功）

Worker 模式：``async def run(stop_event)`` — 可中断睡眠，异常不影响主应用。
"""

from __future__ import annotations

import asyncio
import logging

import sqlalchemy as sa

logger = logging.getLogger("staged_orphan_cleaner")

# 每小时跑一次（3600s）；首次启动延迟 300s 避免启动瞬间打 DB
_INTERVAL_SECONDS = 3600
_INITIAL_DELAY_SECONDS = 300
_ORPHAN_AGE_HOURS = 24


async def run(stop_event: asyncio.Event) -> None:
    """主循环：每 1h 跑一次 _scan_and_clean，直到 stop_event 触发。"""
    logger.info(
        "[STAGED_ORPHAN] started, interval=%ds, first run in %ds",
        _INTERVAL_SECONDS,
        _INITIAL_DELAY_SECONDS,
    )

    # 首次延迟
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=_INITIAL_DELAY_SECONDS)
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            await _scan_and_clean()
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001
            logger.warning("[STAGED_ORPHAN] loop error: %s", e, exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_INTERVAL_SECONDS)
            break
        except asyncio.TimeoutError:
            pass


async def _scan_and_clean() -> None:
    """执行一轮孤儿扫描 + 清理。"""
    from app.core.database import async_session
    from app.models.dataset_models import (
        ImportJob,
        JobStatus,
        LedgerDataset,
        DatasetStatus,
    )
    from app.services.dataset_service import DatasetService

    # 活跃 job 状态：这些状态下的 job 仍在处理 dataset，不应清
    active_statuses = [
        JobStatus.pending,
        JobStatus.queued,
        JobStatus.running,
        JobStatus.validating,
        JobStatus.writing,
        JobStatus.activating,
    ]

    async with async_session() as db:
        # 查 status=staged 且创建 >24h，且没有活跃 job 关联
        # 关联方向：LedgerDataset.job_id → ImportJob.id
        # 使用 NOT EXISTS 语义：dataset.job_id 不指向任何活跃 job
        cutoff_expr = sa.text(
            f"CURRENT_TIMESTAMP - INTERVAL '{_ORPHAN_AGE_HOURS} hours'"
        )
        subq = sa.select(ImportJob.id).where(
            ImportJob.id == LedgerDataset.job_id,
            ImportJob.status.in_(active_statuses),
        )
        result = await db.execute(
            sa.select(LedgerDataset.id, LedgerDataset.project_id, LedgerDataset.year)
            .where(
                LedgerDataset.status == DatasetStatus.staged,
                LedgerDataset.created_at < cutoff_expr,
                sa.not_(subq.exists()),
            )
            .limit(100)  # 单次处理上限，防压 DB
        )
        orphans = list(result.all())

    if not orphans:
        logger.debug("[STAGED_ORPHAN] no orphans found")
        return

    logger.info("[STAGED_ORPHAN] found %d orphans to clean", len(orphans))

    cleaned = 0
    for orphan in orphans:
        try:
            async with async_session() as db:
                await DatasetService.mark_failed(db, orphan.id, cleanup_rows=True)
                await db.commit()
            cleaned += 1
            logger.info(
                "[STAGED_ORPHAN] cleaned orphan dataset=%s project=%s year=%s",
                orphan.id,
                orphan.project_id,
                orphan.year,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[STAGED_ORPHAN] failed to clean dataset=%s: %s",
                orphan.id,
                e,
            )

    logger.info("[STAGED_ORPHAN] round complete: cleaned=%d/%d", cleaned, len(orphans))
