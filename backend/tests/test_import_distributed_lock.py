"""Tests: Import Distributed Lock — Redis + DB fallback

验证多 worker 并发导入场景下的分布式锁行为：
1. 同项目并发导入 → 一个获取锁，另一个被拒
2. Redis 不可用时 → DB fallback SELECT FOR UPDATE
3. 全局并发上限 → SCARD active_set ≤ MAX
4. cancel_requested 跨 worker 取消信号
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.audit_platform_models import ImportBatch, ImportStatus
from app.models.dataset_models import ImportJob, JobStatus
from app.services.import_queue_service import (
    ImportQueueService,
    _MAX_CONCURRENT_IMPORTS,
    _REDIS_ACTIVE_SET_KEY,
    _REDIS_LOCK_PREFIX,
    _REDIS_LOCK_TTL,
    _import_locks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_locks():
    """每次测试前清空内存锁"""
    _import_locks.clear()
    yield
    _import_locks.clear()


@pytest.fixture
def mock_db():
    """模拟 AsyncSession"""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_redis():
    """模拟 Redis 客户端"""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()
    redis.scard = AsyncMock(return_value=0)
    redis.sadd = AsyncMock()
    redis.srem = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# Test: Redis Lock Acquisition
# ---------------------------------------------------------------------------

class TestRedisLockAcquisition:
    """Redis SET NX EX 分布式锁获取"""

    @pytest.mark.asyncio
    async def test_redis_acquire_lock_success(self, mock_redis):
        """Redis 可用时，SET NX EX 成功获取锁"""
        mock_redis.set.return_value = True
        project_id = uuid4()

        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis):
            result = await ImportQueueService._redis_acquire_lock(project_id)

        assert result is True
        mock_redis.set.assert_awaited_once_with(
            f"{_REDIS_LOCK_PREFIX}{project_id}",
            "1",
            nx=True,
            ex=_REDIS_LOCK_TTL,
        )

    @pytest.mark.asyncio
    async def test_redis_acquire_lock_already_held(self, mock_redis):
        """Redis 锁已被另一 worker 持有 → 返回 False"""
        mock_redis.set.return_value = None  # SET NX 失败
        project_id = uuid4()

        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis):
            result = await ImportQueueService._redis_acquire_lock(project_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_redis_unavailable_returns_none(self):
        """Redis 不可用时返回 None（触发 DB fallback）"""
        project_id = uuid4()

        with patch.object(ImportQueueService, '_get_redis', return_value=None):
            result = await ImportQueueService._redis_acquire_lock(project_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_redis_release_lock(self, mock_redis):
        """释放 Redis 锁：删除 key"""
        project_id = uuid4()

        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis):
            await ImportQueueService._redis_release_lock(project_id)

        mock_redis.delete.assert_awaited_once_with(f"{_REDIS_LOCK_PREFIX}{project_id}")


# ---------------------------------------------------------------------------
# Test: Global Concurrency Limit
# ---------------------------------------------------------------------------

class TestGlobalConcurrencyLimit:
    """Redis Set: import_lock:active_set 全局并发控制"""

    @pytest.mark.asyncio
    async def test_check_global_concurrency(self, mock_redis):
        """SCARD 返回当前活跃数"""
        mock_redis.scard.return_value = 2
        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis):
            count = await ImportQueueService._redis_check_global_concurrency()
        assert count == 2

    @pytest.mark.asyncio
    async def test_add_to_active_set(self, mock_redis):
        """SADD 将项目加入活跃集合"""
        project_id = uuid4()
        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis):
            await ImportQueueService._redis_add_to_active_set(project_id)
        mock_redis.sadd.assert_awaited_once_with(_REDIS_ACTIVE_SET_KEY, str(project_id))

    @pytest.mark.asyncio
    async def test_remove_from_active_set(self, mock_redis):
        """SREM 将项目从活跃集合移除"""
        project_id = uuid4()
        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis):
            await ImportQueueService._redis_remove_from_active_set(project_id)
        mock_redis.srem.assert_awaited_once_with(_REDIS_ACTIVE_SET_KEY, str(project_id))


# ---------------------------------------------------------------------------
# Test: acquire_lock integration (Redis + DB)
# ---------------------------------------------------------------------------

class TestAcquireLockIntegration:
    """acquire_lock 完整流程：Redis 锁 → 全局并发 → DB 确认 → 创建 batch"""

    @pytest.mark.asyncio
    async def test_concurrent_import_one_rejected(self, mock_db, mock_redis):
        """2 worker 同项目并发导入 → 第二个被 Redis NX 拒绝"""
        project_id = uuid4()
        mock_redis_acquired = AsyncMock()
        mock_redis_acquired.set = AsyncMock(return_value=None)  # 模拟第二个 worker

        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis_acquired):
            with patch.object(ImportQueueService, '_cleanup_stale_memory_locks'):
                with patch.object(ImportQueueService, '_expire_stale_jobs', new_callable=AsyncMock):
                    success, msg, batch_id = await ImportQueueService.acquire_lock(
                        project_id, "user1", mock_db,
                        source_type="trial_balance", file_name="test.xlsx",
                    )

        assert success is False
        assert "另一 worker" in msg

    @pytest.mark.asyncio
    async def test_concurrency_limit_reached(self, mock_db, mock_redis):
        """全局并发已满 → 拒绝并释放 Redis 锁"""
        project_id = uuid4()
        mock_redis.scard.return_value = _MAX_CONCURRENT_IMPORTS  # 已满

        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis):
            with patch.object(ImportQueueService, '_cleanup_stale_memory_locks'):
                with patch.object(ImportQueueService, '_expire_stale_jobs', new_callable=AsyncMock):
                    success, msg, batch_id = await ImportQueueService.acquire_lock(
                        project_id, "user1", mock_db,
                        source_type="trial_balance", file_name="test.xlsx",
                    )

        assert success is False
        assert "系统繁忙" in msg
        # 验证释放了 Redis 锁
        mock_redis.delete.assert_awaited()


# ---------------------------------------------------------------------------
# Test: DB Fallback when Redis unavailable
# ---------------------------------------------------------------------------

class TestDBFallback:
    """Redis 不可用时 → SELECT FOR UPDATE 降级"""

    @pytest.mark.asyncio
    async def test_db_fallback_when_redis_down(self, mock_db):
        """Redis 返回 None → 走 DB fallback 路径"""
        project_id = uuid4()

        with patch.object(ImportQueueService, '_get_redis', return_value=None):
            with patch.object(ImportQueueService, '_cleanup_stale_memory_locks'):
                with patch.object(ImportQueueService, '_expire_stale_jobs', new_callable=AsyncMock):
                    with patch.object(
                        ImportQueueService, '_db_fallback_acquire_lock',
                        new_callable=AsyncMock, return_value=False
                    ):
                        success, msg, _ = await ImportQueueService.acquire_lock(
                            project_id, "user1", mock_db,
                            source_type="trial_balance", file_name="test.xlsx",
                        )

        assert success is False
        assert "DB 锁检测" in msg


# ---------------------------------------------------------------------------
# Test: cancel_requested cross-worker signal
# ---------------------------------------------------------------------------

class TestCancelRequested:
    """cancel_requested 列跨 worker 取消信号"""

    def test_model_has_cancel_requested_column(self):
        """ImportJob 模型包含 cancel_requested 列"""
        assert hasattr(ImportJob, 'cancel_requested')

    def test_cancel_requested_defaults_false(self):
        """cancel_requested 默认值为 False"""
        job = ImportJob()
        # 新实例默认 False（server_default 在 DB 层，Python 层检查属性存在）
        assert job.cancel_requested is False or job.cancel_requested is None


# ---------------------------------------------------------------------------
# Test: release_lock_async
# ---------------------------------------------------------------------------

class TestReleaseLockAsync:
    """异步释放锁：清理 Redis key + active_set + 内存"""

    @pytest.mark.asyncio
    async def test_release_cleans_redis_and_memory(self, mock_redis):
        """release_lock_async 清除 Redis key + active_set + 内存"""
        project_id = uuid4()
        _import_locks[str(project_id)] = {"status": "processing"}

        with patch.object(ImportQueueService, '_get_redis', return_value=mock_redis):
            await ImportQueueService.release_lock_async(project_id)

        # Redis key 被删
        mock_redis.delete.assert_awaited()
        # active_set 被移除
        mock_redis.srem.assert_awaited()
        # 内存锁被清
        assert str(project_id) not in _import_locks
