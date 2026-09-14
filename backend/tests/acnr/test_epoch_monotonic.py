"""PBT: Durable_Epoch 单调递增 — DB-first（acnr-invalidation-overlay-hardening R11）

**Validates: Requirements 11.4, 12.1；Property P10**

原 acnr-consumer-wiring 的 Redis-authoritative epoch 契约已被 DB-first 取代：
- increment_epoch DB 权威单调递增（Redis 不可用仍递增，不再返回 0）。
- Redis 仅作 commit 后 fan-out（publish 通知其他 worker）。

一次性临时 PG16 库隔离（传 session，避免跨事件循环共享 app engine 的 "Event loop is closed"）。
无 PG 环境 graceful skip（SQLite 不替代）。
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

import fakeredis.aioredis as fakeredis_aio
import pytest

from app.services.acnr.cache_epoch import (
    INVALIDATE_CHANNEL_PREFIX,
    get_epoch,
    increment_epoch,
    set_redis_client,
    _read_db_epoch,
    _UNSET,
)


def _pg_available() -> bool:
    from app.core.config import settings
    return settings.DATABASE_URL.startswith("postgresql")


def _base_url() -> str:
    from app.core.config import settings
    head, _db = settings.DATABASE_URL.rsplit("/", 1)
    return head


def _connect_args() -> dict:
    from app.core.config import settings
    return {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}


_EPOCH_TABLE_SQL = """
CREATE TABLE acnr_invalidation_epoch (
    project_id UUID PRIMARY KEY,
    epoch BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"acnr_epoch_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
    )
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()

    eng = create_async_engine(head + "/" + tmp_db, poolclass=NullPool, connect_args=ca)
    try:
        async with eng.begin() as conn:
            await conn.exec_driver_sql(_EPOCH_TABLE_SQL)
        yield eng
    finally:
        await eng.dispose()
        admin = create_async_engine(
            admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
        )
        async with admin.connect() as c:
            await c.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{tmp_db}' AND pid<>pg_backend_pid()"
            )
            await c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{tmp_db}"')


pytestmark = pytest.mark.skipif(not _pg_available(), reason="需真实 PostgreSQL 16（SQLite 不替代）")


def test_epoch_monotonic_sequential():
    """P10: DB-first 顺序 increment_epoch 严格单调递增（Redis 不可用亦然）。"""
    async def _run():
        from sqlalchemy.ext.asyncio import async_sessionmaker
        set_redis_client(None)  # Redis 不可用 → DB-first 仍递增（R11.4）
        try:
            async with _throwaway_engine() as eng:
                pid = str(uuid.uuid4())
                SM = async_sessionmaker(eng, expire_on_commit=False)
                async with SM() as s:
                    epochs = [await increment_epoch(pid, session=s) for _ in range(5)]
                    await s.commit()
                assert epochs == [1, 2, 3, 4, 5]
                async with SM() as s:
                    cur = await get_epoch(pid, session=s)
                assert cur == 5
        finally:
            set_redis_client(_UNSET)

    asyncio.run(_run())


def test_epoch_redis_unavailable_still_increments():
    """P10/R11.4: Redis 不可用时 DB epoch 仍单调递增（不再返回 0 丢失失效）。"""
    async def _run():
        from sqlalchemy.ext.asyncio import async_sessionmaker
        set_redis_client(None)
        try:
            async with _throwaway_engine() as eng:
                pid = str(uuid.uuid4())
                SM = async_sessionmaker(eng, expire_on_commit=False)
                async with SM() as s:
                    e1 = await increment_epoch(pid, session=s)
                    e2 = await increment_epoch(pid, session=s)
                    await s.commit()
                assert e1 == 1 and e2 == 2  # 关键：非 0
        finally:
            set_redis_client(_UNSET)

    asyncio.run(_run())


def test_epoch_project_isolation():
    """P10 隔离: 不同 project 的 Durable_Epoch 互不影响。"""
    async def _run():
        from sqlalchemy.ext.asyncio import async_sessionmaker
        set_redis_client(None)
        try:
            async with _throwaway_engine() as eng:
                pa, pb = str(uuid.uuid4()), str(uuid.uuid4())
                SM = async_sessionmaker(eng, expire_on_commit=False)
                async with SM() as s:
                    for _ in range(3):
                        await increment_epoch(pa, session=s)
                    await increment_epoch(pb, session=s)
                    await s.commit()
                async with SM() as s:
                    assert await _read_db_epoch(pa, session=s) == 3
                    assert await _read_db_epoch(pb, session=s) == 1
        finally:
            set_redis_client(_UNSET)

    asyncio.run(_run())


def test_epoch_redis_fanout_publish_on_incr():
    """R11: Redis 可用时 increment_epoch 发布到 acnr:invalidate:{project_id} 频道（fan-out）。"""
    async def _run():
        from sqlalchemy.ext.asyncio import async_sessionmaker
        redis = fakeredis_aio.FakeRedis()
        set_redis_client(redis)
        try:
            async with _throwaway_engine() as eng:
                pid = str(uuid.uuid4())
                SM = async_sessionmaker(eng, expire_on_commit=False)
                pubsub = redis.pubsub()
                channel = f"{INVALIDATE_CHANNEL_PREFIX}{pid}"
                await pubsub.subscribe(channel)
                async with SM() as s:
                    for _ in range(3):
                        await increment_epoch(pid, session=s)
                    await s.commit()
                msgs = []
                for _ in range(4):
                    m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if m and m["type"] == "message":
                        msgs.append(m)
                await pubsub.unsubscribe(channel)
                assert len(msgs) >= 3  # 每次 increment 发布一次
        finally:
            set_redis_client(_UNSET)
            await redis.aclose()

    asyncio.run(_run())
