"""
# Feature: global-refinement-v5-closure, Property 3~7
编辑锁 service 属性测试

Validates: Requirements 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.editing_lock_models import EditingLock
from app.services.editing_lock_service import (
    acquire_lock,
    release_lock,
    heartbeat_lock,
    force_acquire_lock,
    get_active_locks,
    LOCK_EXPIRY,
)

# SQLite compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# hypothesis max_examples=5（项目铁律）
SETTINGS = settings(max_examples=5, deadline=10000, suppress_health_check=[HealthCheck.too_slow])

# 固定 resource 维度避免测试间互扰
RT = "test_resource"

# 独立引擎（避免和 conftest 冲突）
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _fresh_db() -> AsyncSession:
    """每次调用创建全新表 + session"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return _SessionFactory()


# --------------------------------------------------------------------------
# Property 3: 活跃锁唯一不变量
# Feature: global-refinement-v5-closure, Property 3
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(holder_count=st.integers(min_value=2, max_value=5))
async def test_p3_active_lock_uniqueness(holder_count: int):
    """Property 3: 同资源活跃锁≤1，第二持有人被拒

    **Validates: Requirements 7.1, 8.1, 8.2**
    """
    db = await _fresh_db()
    try:
        rid = f"p3-{uuid.uuid4().hex[:8]}"
        holders = [uuid.uuid4() for _ in range(holder_count)]

        # 第一人 acquire 成功
        r1 = await acquire_lock(db, RT, rid, holders[0], "user0")
        assert r1["locked"] is False

        # 后续人 acquire 被拒
        for i in range(1, holder_count):
            r = await acquire_lock(db, RT, rid, holders[i], f"user{i}")
            assert r["locked"] is True
            assert r["locked_by"] == str(holders[0])

        # 活跃锁数≤1
        locks = await get_active_locks(db, resource_type=RT)
        active_for_rid = [lock for lock in locks if lock["resource_id"] == rid]
        assert len(active_for_rid) <= 1
    finally:
        await db.close()


# --------------------------------------------------------------------------
# Property 4: 锁获取-释放往返
# Feature: global-refinement-v5-closure, Property 4
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(dummy=st.integers(min_value=1, max_value=100))
async def test_p4_acquire_release_roundtrip(dummy: int):
    """Property 4: acquire→release→acquire 成功

    **Validates: Requirements 7.2**
    """
    db = await _fresh_db()
    try:
        rid = f"p4-{uuid.uuid4().hex[:8]}"
        h1 = uuid.uuid4()
        h2 = uuid.uuid4()

        r1 = await acquire_lock(db, RT, rid, h1, "A")
        assert r1["locked"] is False

        r2 = await release_lock(db, RT, rid, h1)
        assert r2["released"] is True

        r3 = await acquire_lock(db, RT, rid, h2, "B")
        assert r3["locked"] is False
    finally:
        await db.close()


# --------------------------------------------------------------------------
# Property 5: 心跳续约保持锁有效并刷新时间
# Feature: global-refinement-v5-closure, Property 5
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(dummy=st.integers(min_value=1, max_value=100))
async def test_p5_heartbeat_refreshes(dummy: int):
    """Property 5: heartbeat 后 heartbeat_at 不早于调用前且锁仍活跃

    **Validates: Requirements 7.3**
    """
    db = await _fresh_db()
    try:
        rid = f"p5-{uuid.uuid4().hex[:8]}"
        h = uuid.uuid4()

        await acquire_lock(db, RT, rid, h, "X")
        before = datetime.now(timezone.utc)

        r = await heartbeat_lock(db, RT, rid, h)
        assert r["refreshed"] is True
        assert r["heartbeat_at"] >= before.isoformat()

        # 锁仍活跃
        locks = await get_active_locks(db, resource_type=RT)
        active = [lock for lock in locks if lock["resource_id"] == rid]
        assert len(active) == 1
    finally:
        await db.close()


# --------------------------------------------------------------------------
# Property 6: 强制获取转移持有权
# Feature: global-refinement-v5-closure, Property 6
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(dummy=st.integers(min_value=1, max_value=100))
async def test_p6_force_acquire_transfers(dummy: int):
    """Property 6: force-acquire 后新持有人唯一 + 返回前持有人

    **Validates: Requirements 7.4**
    """
    db = await _fresh_db()
    try:
        rid = f"p6-{uuid.uuid4().hex[:8]}"
        h1 = uuid.uuid4()
        h2 = uuid.uuid4()

        await acquire_lock(db, RT, rid, h1, "原持有人")
        r = await force_acquire_lock(db, RT, rid, h2, "新持有人")

        assert r["previous_holder_id"] == str(h1)
        assert r["previous_holder_name"] == "原持有人"
        assert "lock_id" in r

        # 新持有人唯一活跃
        locks = await get_active_locks(db, resource_type=RT)
        active = [lock for lock in locks if lock["resource_id"] == rid]
        assert len(active) == 1
        assert active[0]["holder_id"] == str(h2)
    finally:
        await db.close()


# --------------------------------------------------------------------------
# Property 7: 过期锁不阻塞新获取
# Feature: global-refinement-v5-closure, Property 7
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(dummy=st.integers(min_value=1, max_value=100))
async def test_p7_expired_lock_not_blocking(dummy: int):
    """Property 7: 过期锁不阻塞新 acquire

    **Validates: Requirements 8.3**
    """
    db = await _fresh_db()
    try:
        rid = f"p7-{uuid.uuid4().hex[:8]}"
        h1 = uuid.uuid4()
        h2 = uuid.uuid4()

        # 手动创建过期锁（heartbeat 6 分钟前）
        from sqlalchemy import update
        await acquire_lock(db, RT, rid, h1, "过期人")
        # 强制设 heartbeat 为过期
        stmt = update(EditingLock).where(
            EditingLock.resource_type == RT,
            EditingLock.resource_id == rid,
        ).values(heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=6))
        await db.execute(stmt)
        await db.flush()

        # 新人 acquire 应成功（惰性清理过期锁）
        r = await acquire_lock(db, RT, rid, h2, "新人")
        assert r["locked"] is False
    finally:
        await db.close()
