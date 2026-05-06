"""Sprint 3 集成测试：编辑锁并发场景

验证同时打开同张底稿时的锁行为：
- acquire_lock 成功/冲突
- heartbeat 续期
- release 释放
- force_acquire 强制获取
- 过期锁惰性清理
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

from app.models.base import Base
from app.models.workpaper_editing_lock_models import WorkpaperEditingLock

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()
WP_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


class TestEditingLockConcurrent:
    """编辑锁并发测试"""

    @pytest.mark.asyncio
    async def test_first_user_acquires_lock(self, db_session):
        """第一个用户成功获取锁"""
        from app.services.editing_lock_service import acquire_lock

        result = await acquire_lock(db_session, WP_ID, USER_A)
        await db_session.commit()

        assert result["acquired"] is True
        assert result.get("locked_by") is None or result["locked_by"] == str(USER_A)

    @pytest.mark.asyncio
    async def test_second_user_blocked(self, db_session):
        """第二个用户被阻止（锁未过期）"""
        from app.services.editing_lock_service import acquire_lock

        # User A acquires
        result_a = await acquire_lock(db_session, WP_ID, USER_A)
        await db_session.commit()
        assert result_a["acquired"] is True

        # User B tries to acquire
        result_b = await acquire_lock(db_session, WP_ID, USER_B)
        await db_session.commit()
        assert result_b["acquired"] is False
        assert "locked_by" in result_b

    @pytest.mark.asyncio
    async def test_same_user_reacquires(self, db_session):
        """同一用户重复 acquire 自动续期"""
        from app.services.editing_lock_service import acquire_lock

        result1 = await acquire_lock(db_session, WP_ID, USER_A)
        await db_session.commit()
        assert result1["acquired"] is True

        result2 = await acquire_lock(db_session, WP_ID, USER_A)
        await db_session.commit()
        assert result2["acquired"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_extends_lock(self, db_session):
        """heartbeat 续期成功"""
        from app.services.editing_lock_service import acquire_lock, heartbeat_lock

        await acquire_lock(db_session, WP_ID, USER_A)
        await db_session.commit()

        result = await heartbeat_lock(db_session, WP_ID, USER_A)
        await db_session.commit()
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_release_frees_lock(self, db_session):
        """释放锁后其他用户可获取"""
        from app.services.editing_lock_service import acquire_lock, release_lock

        await acquire_lock(db_session, WP_ID, USER_A)
        await db_session.commit()

        release_result = await release_lock(db_session, WP_ID, USER_A)
        await db_session.commit()
        assert release_result["released"] is True

        # User B can now acquire
        result_b = await acquire_lock(db_session, WP_ID, USER_B)
        await db_session.commit()
        assert result_b["acquired"] is True

    @pytest.mark.asyncio
    async def test_expired_lock_allows_new_acquire(self, db_session):
        """过期锁（heartbeat > 5min ago）允许新用户获取"""
        from app.services.editing_lock_service import acquire_lock
        from sqlalchemy import select, update

        # User A acquires
        await acquire_lock(db_session, WP_ID, USER_A)
        await db_session.commit()

        # Manually expire the lock (set heartbeat_at to 10 minutes ago)
        expired_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
        await db_session.execute(
            update(WorkpaperEditingLock)
            .where(WorkpaperEditingLock.wp_id == WP_ID)
            .values(heartbeat_at=expired_time)
        )
        await db_session.commit()

        # User B should be able to acquire (expired lock gets cleaned up)
        result_b = await acquire_lock(db_session, WP_ID, USER_B)
        await db_session.commit()
        assert result_b["acquired"] is True

    @pytest.mark.asyncio
    async def test_force_acquire_overrides(self, db_session):
        """强制获取覆盖现有锁"""
        from app.services.editing_lock_service import acquire_lock, force_acquire_lock

        await acquire_lock(db_session, WP_ID, USER_A)
        await db_session.commit()

        result = await force_acquire_lock(db_session, WP_ID, USER_B)
        await db_session.commit()
        assert result["acquired"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_fails_without_lock(self, db_session):
        """无锁时 heartbeat 返回失败"""
        from app.services.editing_lock_service import heartbeat_lock

        result = await heartbeat_lock(db_session, WP_ID, USER_A)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_get_active_locks(self, db_session):
        """获取所有活跃锁列表"""
        from app.services.editing_lock_service import acquire_lock, get_active_locks

        wp_id_2 = uuid.uuid4()
        await acquire_lock(db_session, WP_ID, USER_A)
        await acquire_lock(db_session, wp_id_2, USER_B)
        await db_session.commit()

        locks = await get_active_locks(db_session)
        assert len(locks) >= 2
