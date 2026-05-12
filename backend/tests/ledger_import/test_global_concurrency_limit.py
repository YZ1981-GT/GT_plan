"""F51 / Sprint 8.32: 全局并发限流单元测试

覆盖点：
1. ``try_acquire`` 在达到 MAX 之前都能获取；超出后返回 False
2. ``release`` 释放槽位 — 释放后再次 ``try_acquire`` 成功
3. ``max_concurrent`` 从 ``LEDGER_IMPORT_MAX_CONCURRENT`` env 动态读取（monkeypatch）
4. Redis path（fakeredis）—— ``INCR`` + ``DECR`` + ``EXPIRE`` 行为一致
5. Fallback path（Redis 不可达）—— asyncio.Lock + counter
6. 负数 DECR 自动归零保护
7. ``queue_position`` 按 ``created_at`` 升序返回 1-indexed 位置
8. Redis DECR 失败时降级到 fallback，计数不泄漏

Validates: Requirements F51
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import fakeredis.aioredis
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.services.ledger_import import global_concurrency as gc_module
from app.services.ledger_import.global_concurrency import (
    DEFAULT_MAX_CONCURRENT,
    REDIS_KEY,
    GlobalImportConcurrency,
)


@pytest.fixture(autouse=True)
def _reset_env_and_singleton(monkeypatch):
    """每个测试前清理 env 并重置 singleton 状态。"""
    monkeypatch.delenv("LEDGER_IMPORT_MAX_CONCURRENT", raising=False)
    gc_module.GLOBAL_CONCURRENCY.reset()
    yield
    gc_module.GLOBAL_CONCURRENCY.reset()


# ---------------------------------------------------------------------------
# Case 1-3：基础 acquire / release / env
# ---------------------------------------------------------------------------


class TestConfigurableMax:
    def test_default_max_is_three(self):
        gc = GlobalImportConcurrency()
        assert gc.max_concurrent == DEFAULT_MAX_CONCURRENT == 3

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "5")
        gc = GlobalImportConcurrency()
        assert gc.max_concurrent == 5

    def test_env_invalid_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "not-int")
        gc = GlobalImportConcurrency()
        assert gc.max_concurrent == DEFAULT_MAX_CONCURRENT

    def test_env_zero_coerced_to_one(self, monkeypatch):
        """0 会导致永远无法获取槽；clamp 到最少 1。"""
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "0")
        gc = GlobalImportConcurrency()
        assert gc.max_concurrent == 1

    def test_env_negative_coerced_to_one(self, monkeypatch):
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "-5")
        gc = GlobalImportConcurrency()
        assert gc.max_concurrent == 1


# ---------------------------------------------------------------------------
# Case 4：Redis path（fakeredis）
# ---------------------------------------------------------------------------


class TestRedisPath:
    @pytest_asyncio.fixture
    async def gc_with_fake_redis(self, monkeypatch):
        """GC 实例强制走 fakeredis。"""
        gc = GlobalImportConcurrency()
        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

        async def _fake_get_redis(self):
            return fake

        monkeypatch.setattr(
            GlobalImportConcurrency, "_get_redis", _fake_get_redis
        )
        try:
            yield gc, fake
        finally:
            await fake.aclose()

    @pytest.mark.asyncio
    async def test_acquire_up_to_max_then_deny(self, gc_with_fake_redis, monkeypatch):
        gc, fake = gc_with_fake_redis
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "3")

        # 3 次都成功
        assert await gc.try_acquire(uuid4()) is True
        assert await gc.try_acquire(uuid4()) is True
        assert await gc.try_acquire(uuid4()) is True
        assert int(await fake.get(REDIS_KEY)) == 3

        # 第 4 次拒绝 + 计数已回滚
        assert await gc.try_acquire(uuid4()) is False
        assert int(await fake.get(REDIS_KEY)) == 3

    @pytest.mark.asyncio
    async def test_release_frees_slot(self, gc_with_fake_redis, monkeypatch):
        gc, fake = gc_with_fake_redis
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "2")

        assert await gc.try_acquire(uuid4()) is True
        assert await gc.try_acquire(uuid4()) is True
        assert await gc.try_acquire(uuid4()) is False  # 满

        await gc.release()
        # 释放后 +1 应可用
        assert await gc.try_acquire(uuid4()) is True

    @pytest.mark.asyncio
    async def test_ttl_set_on_first_acquire(self, gc_with_fake_redis, monkeypatch):
        gc, fake = gc_with_fake_redis
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "3")

        await gc.try_acquire(uuid4())
        ttl = await fake.ttl(REDIS_KEY)
        # 应该有 TTL（> 0）
        assert ttl > 0
        # TTL 应该接近 7200
        assert 7000 < ttl <= 7200

    @pytest.mark.asyncio
    async def test_release_below_zero_resets_to_zero(
        self, gc_with_fake_redis, monkeypatch,
    ):
        gc, fake = gc_with_fake_redis

        # 直接 release（没有对应 acquire）— count 会变 -1
        await gc.release()
        assert int(await fake.get(REDIS_KEY)) == 0

    @pytest.mark.asyncio
    async def test_current_count(self, gc_with_fake_redis, monkeypatch):
        gc, _fake = gc_with_fake_redis
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "5")

        assert await gc.current_count() == 0
        await gc.try_acquire(uuid4())
        await gc.try_acquire(uuid4())
        assert await gc.current_count() == 2


# ---------------------------------------------------------------------------
# Case 5：Fallback path（Redis 不可达）
# ---------------------------------------------------------------------------


class TestFallbackPath:
    @pytest.mark.asyncio
    async def test_acquire_falls_back_when_redis_unavailable(self, monkeypatch):
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "2")

        gc = GlobalImportConcurrency()

        async def _no_redis(self):
            return None

        monkeypatch.setattr(GlobalImportConcurrency, "_get_redis", _no_redis)

        assert await gc.try_acquire(uuid4()) is True
        assert await gc.try_acquire(uuid4()) is True
        assert await gc.try_acquire(uuid4()) is False  # 满

        await gc.release()
        assert await gc.try_acquire(uuid4()) is True

    @pytest.mark.asyncio
    async def test_fallback_concurrent_safety(self, monkeypatch):
        """并发 100 个 task 竞争 MAX=3 槽，最终计数 ≤ 3。"""
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "3")

        gc = GlobalImportConcurrency()

        async def _no_redis(self):
            return None

        monkeypatch.setattr(GlobalImportConcurrency, "_get_redis", _no_redis)

        async def _worker():
            return await gc.try_acquire(uuid4())

        results = await asyncio.gather(*[_worker() for _ in range(100)])
        granted = sum(1 for r in results if r)
        assert granted == 3, f"expected exactly 3 slots granted, got {granted}"
        # 内部计数应等于 3
        assert gc._fallback_count == 3

    @pytest.mark.asyncio
    async def test_fallback_release_never_negative(self, monkeypatch):
        gc = GlobalImportConcurrency()

        async def _no_redis(self):
            return None

        monkeypatch.setattr(GlobalImportConcurrency, "_get_redis", _no_redis)

        # 没有 acquire 就 release — 不应变负
        await gc.release()
        await gc.release()
        assert gc._fallback_count == 0


# ---------------------------------------------------------------------------
# Case 6：Redis 异常时降级到 fallback
# ---------------------------------------------------------------------------


class TestRedisFailureDegradation:
    @pytest.mark.asyncio
    async def test_incr_exception_falls_back_to_local(self, monkeypatch):
        """Redis INCR 抛异常后，try_acquire 走 fallback 路径。"""
        monkeypatch.setenv("LEDGER_IMPORT_MAX_CONCURRENT", "2")

        gc = GlobalImportConcurrency()

        # 自制一个 incr 抛异常的 redis client
        class _BrokenRedis:
            async def ping(self):
                return True

            async def incr(self, key):
                raise RuntimeError("redis network broken")

            async def decr(self, key):
                return 0

            async def expire(self, key, ttl):
                return True

            async def get(self, key):
                return "0"

            async def set(self, key, value):
                return True

        async def _broken_redis(self):
            # 只第一次返回 broken；之后都返回 None（走 fallback）
            if getattr(self, "_broken_called", False):
                return None
            self._broken_called = True
            return _BrokenRedis()

        monkeypatch.setattr(GlobalImportConcurrency, "_get_redis", _broken_redis)

        # 第一次 acquire：Redis INCR 抛异常，但 fallback 成功
        assert await gc.try_acquire(uuid4()) is True
        # 之后都走 fallback
        assert await gc.try_acquire(uuid4()) is True
        assert await gc.try_acquire(uuid4()) is False  # 2 + 1 = 满


# ---------------------------------------------------------------------------
# Case 7：queue_position —— 按 created_at 升序返回 1-indexed
# ---------------------------------------------------------------------------


class TestQueuePosition:
    @pytest_asyncio.fixture
    async def db_session(self):
        """建 SQLite 内存库 + import_jobs + projects 最小表。"""
        from app.models.dataset_models import Base as DatasetBase

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        # 只创建 import_jobs 依赖的 projects 表（避免全表 registry 解析）
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: sync_conn.execute(
                    sa.text(
                        "CREATE TABLE projects (id CHAR(32) PRIMARY KEY, "
                        "name VARCHAR, tenant_id VARCHAR DEFAULT 'default')"
                    )
                )
            )
            # 再用 ORM metadata 创建 import_jobs（同一 Base）
            def _create_jobs(sync_conn):
                from app.models.dataset_models import ImportJob
                ImportJob.__table__.create(bind=sync_conn, checkfirst=True)

            await conn.run_sync(_create_jobs)

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as db:
            # seed project
            await db.execute(
                sa.text(
                    "INSERT INTO projects (id, name) VALUES (:id, :name)"
                ),
                {"id": uuid4().hex, "name": "test"},
            )
            # seed 另一个项目（测试 queue_position 不区分 project）
            project_ids = []
            for _ in range(2):
                pid = uuid4()
                project_ids.append(pid)
                await db.execute(
                    sa.text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
                    {"id": pid.hex, "name": f"p-{pid}"},
                )
            await db.commit()
            yield db, project_ids
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_queue_position_returns_one_indexed(self, db_session):
        db, project_ids = db_session
        from app.models.dataset_models import ImportJob, JobStatus

        gc = GlobalImportConcurrency()
        pid = project_ids[0]

        # 建 3 个 queued job，时间递增
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        j1 = ImportJob(
            id=uuid4(), project_id=pid, year=2025,
            status=JobStatus.queued, created_at=now - timedelta(seconds=30),
        )
        j2 = ImportJob(
            id=uuid4(), project_id=pid, year=2025,
            status=JobStatus.queued, created_at=now - timedelta(seconds=20),
        )
        j3 = ImportJob(
            id=uuid4(), project_id=pid, year=2025,
            status=JobStatus.queued, created_at=now - timedelta(seconds=10),
        )
        db.add_all([j1, j2, j3])
        await db.commit()

        # j1 最早 → 位置 1
        assert await gc.queue_position(db, j1.id) == 1
        # j2 中间 → 位置 2
        assert await gc.queue_position(db, j2.id) == 2
        # j3 最新 → 位置 3
        assert await gc.queue_position(db, j3.id) == 3

    @pytest.mark.asyncio
    async def test_queue_position_running_job_returns_zero(self, db_session):
        """running 状态的 job 不应有 queue_position。"""
        db, project_ids = db_session
        from app.models.dataset_models import ImportJob, JobStatus

        gc = GlobalImportConcurrency()
        pid = project_ids[0]

        j_running = ImportJob(
            id=uuid4(), project_id=pid, year=2025,
            status=JobStatus.running, created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(j_running)
        await db.commit()

        assert await gc.queue_position(db, j_running.id) == 0

    @pytest.mark.asyncio
    async def test_queue_position_nonexistent_returns_zero(self, db_session):
        db, _ = db_session

        gc = GlobalImportConcurrency()
        assert await gc.queue_position(db, uuid4()) == 0

    @pytest.mark.asyncio
    async def test_queue_position_counts_completed_jobs_correctly(self, db_session):
        """completed / failed / canceled 的旧 job 不算在 queued 排队中。"""
        db, project_ids = db_session
        from app.models.dataset_models import ImportJob, JobStatus

        gc = GlobalImportConcurrency()
        pid = project_ids[0]
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 2 个 completed（不影响排队）
        for offset in (40, 35):
            db.add(
                ImportJob(
                    id=uuid4(), project_id=pid, year=2025,
                    status=JobStatus.completed,
                    created_at=now - timedelta(seconds=offset),
                )
            )
        # 2 个 queued
        j_first = ImportJob(
            id=uuid4(), project_id=pid, year=2025,
            status=JobStatus.queued, created_at=now - timedelta(seconds=30),
        )
        j_second = ImportJob(
            id=uuid4(), project_id=pid, year=2025,
            status=JobStatus.queued, created_at=now - timedelta(seconds=20),
        )
        db.add_all([j_first, j_second])
        await db.commit()

        # j_first 位置 1（前面 completed 不算），j_second 位置 2
        assert await gc.queue_position(db, j_first.id) == 1
        assert await gc.queue_position(db, j_second.id) == 2
