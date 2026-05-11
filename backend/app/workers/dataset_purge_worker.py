"""Dataset purge worker — Sprint 10 Task 10.1.

每天凌晨 03:00 扫所有项目，对每个 (project_id, year) 保留最近 3 个 superseded
数据集，其余物理 DELETE（Tb* 行 + LedgerDataset + ActivationRecord）。

purge 完成后对 4 个 ``active_queries`` 索引做 REINDEX CONCURRENTLY，消除
碎片（SQLite 不支持 CONCURRENTLY，跳过）。

Worker 模式：``async def run(stop_event)``；用 ``asyncio.wait_for`` 等待
next 03:00 或 stop_event。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("dataset_purge")

# 每天 03:00 本地时间跑一次（下一次 next_03 = 今天或明天 03:00）
# KEEP_COUNT 可通过环境变量覆盖
_DEFAULT_KEEP_COUNT = 3


def _seconds_until_next_3am() -> float:
    """返回距离下一次本地时间 03:00 的秒数（最少 60s，防止立即重复）。"""
    now = datetime.now().astimezone()
    next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    delta = (next_run - now).total_seconds()
    return max(delta, 60.0)


async def run(stop_event: asyncio.Event) -> None:
    """purge 主循环。

    - 启动 → 等到 next 03:00 再跑第一次（避免启动瞬间打 DB）
    - stop_event.set() → 立即退出
    - 异常不影响主应用，记录 warning 后继续下一周期
    """
    import os

    keep_count = int(os.getenv("LEDGER_PURGE_KEEP_COUNT", _DEFAULT_KEEP_COUNT))
    logger.info(
        "[DATASET_PURGE] started, keep_count=%d, next run in %ds",
        keep_count,
        _seconds_until_next_3am(),
    )

    while not stop_event.is_set():
        try:
            wait_s = _seconds_until_next_3am()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_s)
                break  # stop_event 触发 → 退出
            except asyncio.TimeoutError:
                pass  # 到达 03:00 → 执行 purge

            await _run_once(keep_count)
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001
            logger.warning("[DATASET_PURGE] loop error: %s", e, exc_info=True)


async def _run_once(keep_count: int) -> None:
    """执行一次 purge + 索引维护。"""
    from app.core.database import async_session
    from app.services.dataset_service import DatasetService

    started_at = datetime.now(timezone.utc)
    try:
        async with async_session() as db:
            summary = await DatasetService.purge_all_projects(
                db, keep_count=keep_count
            )
        logger.info(
            "[DATASET_PURGE] completed: projects=%d datasets_deleted=%d rows=%s",
            summary["projects_processed"],
            summary["datasets_deleted"],
            summary["rows_cleaned"],
        )
    except Exception as e:  # noqa: BLE001
        logger.error("[DATASET_PURGE] purge failed: %s", e, exc_info=True)
        return

    # REINDEX CONCURRENTLY 4 个 active_queries 索引（Task 10.4）
    # 注意：REINDEX 需要短暂锁，虽然 CONCURRENTLY 是非阻塞的
    if (datetime.now(timezone.utc) - started_at).total_seconds() > 0:
        await _reindex_active_queries_indexes()


_REINDEX_INDEXES = [
    "idx_tb_balance_active_queries",
    "idx_tb_ledger_active_queries",
    "idx_tb_aux_balance_active_queries",
    "idx_tb_aux_ledger_active_queries",
]


async def _reindex_active_queries_indexes() -> None:
    """对 4 个 active_queries 索引做 REINDEX CONCURRENTLY。

    仅在 PostgreSQL 下执行；SQLite/其他方言直接跳过。
    """
    from app.core.database import async_engine

    dialect = async_engine.dialect.name
    if dialect != "postgresql":
        logger.debug(
            "[DATASET_PURGE] skip REINDEX: dialect=%s (only PG supports CONCURRENTLY)",
            dialect,
        )
        return

    # REINDEX 必须在 AUTOCOMMIT 模式下跑（不能在 transaction 中）
    try:
        async with async_engine.connect() as conn:
            # 获取 raw asyncpg connection
            raw_conn = await conn.get_raw_connection()
            for idx in _REINDEX_INDEXES:
                try:
                    await raw_conn.driver_connection.execute(
                        f"REINDEX INDEX CONCURRENTLY {idx}"
                    )
                    logger.info("[DATASET_PURGE] reindexed %s", idx)
                except Exception as e:  # noqa: BLE001
                    # 索引不存在 / 并发冲突 → warning 不阻断
                    logger.warning(
                        "[DATASET_PURGE] reindex %s failed (ignored): %s",
                        idx,
                        e,
                    )
    except Exception as e:  # noqa: BLE001
        logger.warning("[DATASET_PURGE] reindex step skipped: %s", e)

    # P1-6: purge 后 VACUUM 回收 dead tuple 空间（仅 PG）
    await _vacuum_tb_tables()


_VACUUM_TABLES = ("tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger")


async def _vacuum_tb_tables() -> None:
    """对 4 张 Tb* 表执行 VACUUM (VERBOSE) 回收 dead tuple 空间。

    仅在 PostgreSQL 下执行；SQLite 不支持 VACUUM 单表，跳过。
    VACUUM 不能在事务内执行，需要 AUTOCOMMIT 模式。
    """
    import sqlalchemy as sa

    from app.core.database import async_engine

    if "postgresql" not in str(async_engine.url):
        return

    try:
        async with async_engine.connect() as raw_conn:
            # VACUUM 不能在事务内执行，需要 autocommit
            await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
            for tbl in _VACUUM_TABLES:
                try:
                    await raw_conn.execute(sa.text(f"VACUUM (VERBOSE) {tbl}"))
                    logger.info("[Purge] VACUUM %s completed", tbl)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[Purge] VACUUM %s failed (non-critical): %s", tbl, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Purge] VACUUM failed (non-critical): %s", exc)
