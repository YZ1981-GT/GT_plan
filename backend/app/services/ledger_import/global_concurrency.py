"""F51 / Sprint 8 批次 E：全局并发限流

平台级 worker 上限（默认 3 个并发导入），防止 100 并发导入打爆 PG / 内存。

实现策略（对齐 design §D13.2）：
- **Redis semaphore（生产）**：基于 ``INCR`` + ``DECR`` 原子操作 + TTL 兜底
  (2h)；key = ``ledger_import:active_count``；超限时 ``DECR`` 回滚计数保证
  一致性。多实例部署下全局生效。
- **进程内 asyncio.Lock + counter（开发/测试）**：Redis 不可达或 ping 失败时
  自动降级；只在单进程内有效，够用于单元测试与本地开发。

配置（环境变量）：
- ``LEDGER_IMPORT_MAX_CONCURRENT``：默认 ``3``，运行时从 ``os.getenv`` 动态
  读取（不缓存），便于测试 monkeypatch。

典型用法::

    acquired = await GLOBAL_CONCURRENCY.try_acquire(job_id)
    if not acquired:
        return  # 保持 queued，recover_jobs 下一轮会重试
    try:
        await do_work()
    finally:
        await GLOBAL_CONCURRENCY.release()

队列位置查询（供 ``/active-job`` 端点展示）::

    pos = await GLOBAL_CONCURRENCY.queue_position(db, job_id)  # 1-indexed
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "GlobalImportConcurrency",
    "GLOBAL_CONCURRENCY",
    "REDIS_KEY",
    "DEFAULT_MAX_CONCURRENT",
]

REDIS_KEY = "ledger_import:active_count"
DEFAULT_MAX_CONCURRENT = 3
_REDIS_TTL_SECONDS = 7200  # 2h 兜底 TTL，防进程崩溃后计数永久 stuck
_REDIS_PING_TIMEOUT_SECONDS = 0.5


def _read_max_concurrent() -> int:
    """从 env 读取并发上限；运行时动态读（便于测试 monkeypatch）。"""
    raw = os.getenv("LEDGER_IMPORT_MAX_CONCURRENT", str(DEFAULT_MAX_CONCURRENT))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "LEDGER_IMPORT_MAX_CONCURRENT=%r not int, using default %d",
            raw, DEFAULT_MAX_CONCURRENT,
        )
        return DEFAULT_MAX_CONCURRENT
    return max(1, value)


class GlobalImportConcurrency:
    """全局并发限流器（Redis semaphore + 进程内兜底）。

    一次性实例化（见模块底部 ``GLOBAL_CONCURRENCY``）。实例状态：

    - ``_fallback_count``：进程内当前持有的槽数
    - ``_fallback_lock``：保护 ``_fallback_count`` 的 asyncio 锁
    - ``_redis_failed``：一次 Redis 失败后永久走 fallback，避免每次 ping 开销
    """

    def __init__(self) -> None:
        self._fallback_count: int = 0
        self._fallback_lock: asyncio.Lock | None = None
        self._redis_failed: bool = False

    # ------------------------------------------------------------------
    # 配置访问
    # ------------------------------------------------------------------

    @property
    def max_concurrent(self) -> int:
        """当前并发上限（每次访问都重新读 env，不缓存）。"""
        return _read_max_concurrent()

    # ------------------------------------------------------------------
    # 测试辅助：重置内部状态
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置内部状态（测试专用；生产代码不应调用）。"""
        self._fallback_count = 0
        self._fallback_lock = None
        self._redis_failed = False

    # ------------------------------------------------------------------
    # Redis 访问（延迟 + 失败一次则永久降级）
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """返回 Redis 客户端；不可达返回 None 进入 fallback 分支。"""
        if self._redis_failed:
            return None
        try:
            from app.core.redis import redis_client  # noqa: WPS433
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "GlobalImportConcurrency: redis_client import failed (%s), "
                "falling back to in-process semaphore",
                exc,
            )
            self._redis_failed = True
            return None
        try:
            await asyncio.wait_for(
                redis_client.ping(), timeout=_REDIS_PING_TIMEOUT_SECONDS
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "GlobalImportConcurrency: Redis ping failed (%s), "
                "falling back to in-process semaphore",
                exc,
            )
            self._redis_failed = True
            return None
        return redis_client

    def _get_fallback_lock(self) -> asyncio.Lock:
        if self._fallback_lock is None:
            self._fallback_lock = asyncio.Lock()
        return self._fallback_lock

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def try_acquire(self, job_id: UUID | None = None) -> bool:
        """尝试获取一个并发槽。

        Returns:
            True：成功获取，caller 必须在完成后调用 :meth:`release`。
            False：已达上限，caller 应保持 job 为 ``queued`` 状态等下轮重试。
        """
        max_n = self.max_concurrent
        redis = await self._get_redis()
        if redis is not None:
            try:
                count = await redis.incr(REDIS_KEY)
                if count > max_n:
                    # 超限：立即 DECR 回滚，保持计数一致
                    await redis.decr(REDIS_KEY)
                    logger.info(
                        "GlobalImportConcurrency: slot denied "
                        "(count=%d > max=%d) job=%s",
                        count, max_n, job_id,
                    )
                    return False
                # 首次持有时设置 TTL 兜底；后续 INCR 不会重置 TTL
                await redis.expire(REDIS_KEY, _REDIS_TTL_SECONDS)
                logger.debug(
                    "GlobalImportConcurrency(redis): acquired %d/%d job=%s",
                    count, max_n, job_id,
                )
                return True
            except Exception:
                logger.exception(
                    "GlobalImportConcurrency: Redis INCR failed, "
                    "falling back to in-process semaphore",
                )
                self._redis_failed = True
                # fall through to in-process path

        # Fallback：进程内计数
        lock = self._get_fallback_lock()
        async with lock:
            if self._fallback_count >= max_n:
                logger.info(
                    "GlobalImportConcurrency(local): slot denied "
                    "(count=%d >= max=%d) job=%s",
                    self._fallback_count, max_n, job_id,
                )
                return False
            self._fallback_count += 1
            logger.debug(
                "GlobalImportConcurrency(local): acquired %d/%d job=%s",
                self._fallback_count, max_n, job_id,
            )
            return True

    async def release(self) -> None:
        """释放之前通过 :meth:`try_acquire` 获取的槽。"""
        redis = await self._get_redis()
        if redis is not None:
            try:
                count = await redis.decr(REDIS_KEY)
                # 兜底：计数不应小于 0（理论上不会但防御一下）
                if count < 0:
                    logger.warning(
                        "GlobalImportConcurrency: negative count %d after DECR, "
                        "resetting to 0", count,
                    )
                    await redis.set(REDIS_KEY, 0)
                return
            except Exception:
                logger.exception(
                    "GlobalImportConcurrency: Redis DECR failed, "
                    "falling back to in-process semaphore",
                )
                self._redis_failed = True
                # fall through

        lock = self._get_fallback_lock()
        async with lock:
            self._fallback_count = max(0, self._fallback_count - 1)

    async def current_count(self) -> int:
        """返回当前已占用的槽数（观测/调试用）。"""
        redis = await self._get_redis()
        if redis is not None:
            try:
                raw = await redis.get(REDIS_KEY)
                return int(raw) if raw else 0
            except Exception:
                logger.exception(
                    "GlobalImportConcurrency: Redis GET current_count failed"
                )
                self._redis_failed = True
        return self._fallback_count

    async def queue_position(
        self,
        db: "AsyncSession",
        job_id: UUID,
    ) -> int:
        """返回 ``job_id`` 在 queued 队列中的位置（1-indexed）。

        Returns:
            1 表示下一个将被执行；2 表示前面还有 1 个；依此类推。
            若 job 不存在或已不在 queued 状态，返回 0（caller 应不显示位置）。
        """
        from app.models.dataset_models import ImportJob, JobStatus  # noqa: WPS433

        # 先查自己的 created_at；不存在直接返回 0
        row = await db.execute(
            sa.select(ImportJob.created_at, ImportJob.status)
            .where(ImportJob.id == job_id)
        )
        pair = row.first()
        if pair is None:
            return 0
        my_created_at, my_status = pair
        if my_created_at is None or my_status != JobStatus.queued:
            return 0

        count_result = await db.execute(
            sa.select(sa.func.count())
            .select_from(ImportJob)
            .where(
                ImportJob.status == JobStatus.queued,
                ImportJob.created_at < my_created_at,
                ImportJob.id != job_id,
            )
        )
        ahead = int(count_result.scalar() or 0)
        return ahead + 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

GLOBAL_CONCURRENCY: GlobalImportConcurrency = GlobalImportConcurrency()
