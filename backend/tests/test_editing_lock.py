"""底稿编辑软锁 — 单元测试

测试 editing_lock_service 的核心逻辑：
- acquire / heartbeat / release / force_acquire
- 过期锁惰性清理
- 同一用户重复 acquire 续期
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Import all models so Base.metadata knows about referenced tables
import app.models  # noqa: F401
from app.models.base import Base
from app.models.workpaper_editing_lock_models import WorkpaperEditingLock
from app.services.editing_lock_service import (
    LOCK_EXPIRY_SECONDS,
    _now_naive,
    acquire_lock,
    force_acquire_lock,
    get_active_locks,
    heartbeat_lock,
    release_lock,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    """创建内存 SQLite 异步会话用于测试"""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def wp_id():
    return uuid.uuid4()


@pytest.fixture
def user_a():
    return uuid.uuid4()


@pytest.fixture
def user_b():
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_lock_success(db_session, wp_id, user_a):
    """首次 acquire 应成功"""
    result = await acquire_lock(db_session, wp_id, user_a)
    assert result["acquired"] is True
    assert "lock_id" in result


@pytest.mark.asyncio
async def test_acquire_lock_conflict(db_session, wp_id, user_a, user_b):
    """另一用户持有锁时 acquire 应返回冲突"""
    await acquire_lock(db_session, wp_id, user_a)

    result = await acquire_lock(db_session, wp_id, user_b)
    assert result["acquired"] is False
    assert result["locked_by"] == str(user_a)
    assert "acquired_at" in result


@pytest.mark.asyncio
async def test_acquire_lock_same_user_renews(db_session, wp_id, user_a):
    """同一用户重复 acquire 应续期而非冲突"""
    result1 = await acquire_lock(db_session, wp_id, user_a)
    assert result1["acquired"] is True

    result2 = await acquire_lock(db_session, wp_id, user_a)
    assert result2["acquired"] is True
    assert result2["lock_id"] == result1["lock_id"]


@pytest.mark.asyncio
async def test_heartbeat_success(db_session, wp_id, user_a):
    """持有锁时 heartbeat 应成功"""
    await acquire_lock(db_session, wp_id, user_a)

    result = await heartbeat_lock(db_session, wp_id, user_a)
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_heartbeat_no_lock(db_session, wp_id, user_a):
    """无锁时 heartbeat 应失败"""
    result = await heartbeat_lock(db_session, wp_id, user_a)
    assert result["ok"] is False
    assert result["reason"] == "no_active_lock"


@pytest.mark.asyncio
async def test_release_lock_success(db_session, wp_id, user_a):
    """释放锁应成功"""
    await acquire_lock(db_session, wp_id, user_a)

    result = await release_lock(db_session, wp_id, user_a)
    assert result["released"] is True


@pytest.mark.asyncio
async def test_release_lock_no_lock(db_session, wp_id, user_a):
    """无锁时释放应失败"""
    result = await release_lock(db_session, wp_id, user_a)
    assert result["released"] is False


@pytest.mark.asyncio
async def test_expired_lock_allows_new_acquire(db_session, wp_id, user_a, user_b):
    """过期锁应被惰性清理，允许新用户 acquire"""
    # 创建一个锁
    await acquire_lock(db_session, wp_id, user_a)

    # 手动将 heartbeat_at 设为 6 分钟前（超过 5 分钟阈值）
    expired_time = _now_naive() - timedelta(seconds=LOCK_EXPIRY_SECONDS + 60)
    stmt = (
        sa.update(WorkpaperEditingLock)
        .where(WorkpaperEditingLock.wp_id == wp_id)
        .values(heartbeat_at=expired_time)
    )
    await db_session.execute(stmt)
    await db_session.flush()

    # 另一用户应能成功 acquire
    result = await acquire_lock(db_session, wp_id, user_b)
    assert result["acquired"] is True


@pytest.mark.asyncio
async def test_force_acquire_overrides_existing(db_session, wp_id, user_a, user_b):
    """强制 acquire 应覆盖现有锁"""
    await acquire_lock(db_session, wp_id, user_a)

    result = await force_acquire_lock(db_session, wp_id, user_b)
    assert result["acquired"] is True
    assert result["previous_holder"] == str(user_a)


@pytest.mark.asyncio
async def test_force_acquire_no_existing_lock(db_session, wp_id, user_a):
    """无现有锁时强制 acquire 应成功"""
    result = await force_acquire_lock(db_session, wp_id, user_a)
    assert result["acquired"] is True
    assert result["previous_holder"] is None


@pytest.mark.asyncio
async def test_get_active_locks(db_session, wp_id, user_a):
    """获取活跃锁列表"""
    await acquire_lock(db_session, wp_id, user_a)

    locks = await get_active_locks(db_session)
    assert len(locks) == 1
    assert locks[0]["wp_id"] == str(wp_id)
    assert locks[0]["staff_id"] == str(user_a)


@pytest.mark.asyncio
async def test_get_active_locks_excludes_expired(db_session, wp_id, user_a):
    """活跃锁列表应排除过期锁"""
    await acquire_lock(db_session, wp_id, user_a)

    # 手动过期
    expired_time = _now_naive() - timedelta(seconds=LOCK_EXPIRY_SECONDS + 60)
    stmt = (
        sa.update(WorkpaperEditingLock)
        .where(WorkpaperEditingLock.wp_id == wp_id)
        .values(heartbeat_at=expired_time)
    )
    await db_session.execute(stmt)
    await db_session.flush()

    locks = await get_active_locks(db_session)
    assert len(locks) == 0


@pytest.mark.asyncio
async def test_release_then_acquire(db_session, wp_id, user_a, user_b):
    """释放后另一用户应能 acquire"""
    await acquire_lock(db_session, wp_id, user_a)
    await release_lock(db_session, wp_id, user_a)

    result = await acquire_lock(db_session, wp_id, user_b)
    assert result["acquired"] is True
