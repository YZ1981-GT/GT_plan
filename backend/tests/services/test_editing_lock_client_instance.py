"""
编辑锁 client_instance 窗口级隔离测试

spec: multi-window-ledger-workbench Phase 4 Task 19+20

验证：
- 同 user_id + 不同 client_instance → acquire 返回 locked（第二窗口只读）
- 同 user_id + 同 client_instance → acquire 成功（续期）
- release 只释放匹配 client_instance 的锁
- 不传 client_instance → 旧行为兼容（同人续期）
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.editing_lock_models import EditingLock
from app.services.editing_lock_service import (
    acquire_lock,
    release_lock,
    heartbeat_lock,
)

# SQLite compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

RT = "workpaper"

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _fresh_db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return _SessionFactory()


# ── Task 19: 同 user_id 不同 client_instance → locked ──────────────────────


@pytest.mark.asyncio
async def test_same_user_different_instance_returns_locked():
    """同一用户在不同浏览器标签页打开同一底稿，第二个窗口应收到 locked=True"""
    db = await _fresh_db()
    try:
        rid = f"wp-{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()
        instance_a = "window-aaa-111"
        instance_b = "window-bbb-222"

        # 窗口 A 获取锁
        r1 = await acquire_lock(db, RT, rid, user_id, "admin", client_instance=instance_a)
        assert r1["locked"] is False, f"窗口 A 应获取成功: {r1}"

        # 窗口 B（同用户，不同 instance）获取锁 → 冲突
        r2 = await acquire_lock(db, RT, rid, user_id, "admin", client_instance=instance_b)
        assert r2["locked"] is True, f"窗口 B 应被拒绝: {r2}"
        assert r2["locked_by"] == str(user_id)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_same_user_same_instance_renews():
    """同一用户同一窗口重复 acquire → 续期成功"""
    db = await _fresh_db()
    try:
        rid = f"wp-{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()
        instance = "window-ccc-333"

        r1 = await acquire_lock(db, RT, rid, user_id, "admin", client_instance=instance)
        assert r1["locked"] is False

        r2 = await acquire_lock(db, RT, rid, user_id, "admin", client_instance=instance)
        assert r2["locked"] is False, f"同实例重复 acquire 应续期: {r2}"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_no_instance_backward_compat():
    """不传 client_instance 时走旧行为（同人续期）"""
    db = await _fresh_db()
    try:
        rid = f"wp-{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()

        r1 = await acquire_lock(db, RT, rid, user_id, "admin")
        assert r1["locked"] is False

        # 不传 client_instance 的第二次 acquire → 续期
        r2 = await acquire_lock(db, RT, rid, user_id, "admin")
        assert r2["locked"] is False
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_different_users_still_conflict():
    """不同用户之间仍然冲突（不受 client_instance 影响）"""
    db = await _fresh_db()
    try:
        rid = f"wp-{uuid.uuid4().hex[:8]}"
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        r1 = await acquire_lock(db, RT, rid, user_a, "alice", client_instance="win-1")
        assert r1["locked"] is False

        r2 = await acquire_lock(db, RT, rid, user_b, "bob", client_instance="win-2")
        assert r2["locked"] is True
        assert r2["locked_by"] == str(user_a)
    finally:
        await db.close()


# ── Task 20: release 只释放匹配 instance 的锁 ──────────────────────────────


@pytest.mark.asyncio
async def test_release_with_instance_only_releases_matching():
    """关闭窗口 A 的 release(instance_a) 不应释放窗口 B 的锁"""
    db = await _fresh_db()
    try:
        rid = f"wp-{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()
        instance_a = "window-aaa"

        # 窗口 A 获取锁
        r1 = await acquire_lock(db, RT, rid, user_id, "admin", client_instance=instance_a)
        assert r1["locked"] is False

        # 用不匹配的 instance 释放 → 应该找不到锁
        r_release = await release_lock(db, RT, rid, user_id, client_instance="window-other")
        assert r_release["released"] is False, "不匹配的 instance 不应释放锁"

        # 用匹配的 instance 释放 → 成功
        r_release2 = await release_lock(db, RT, rid, user_id, client_instance=instance_a)
        assert r_release2["released"] is True
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_release_without_instance_releases_any():
    """不传 client_instance 的 release 仍能释放锁（旧行为兼容）"""
    db = await _fresh_db()
    try:
        rid = f"wp-{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()

        await acquire_lock(db, RT, rid, user_id, "admin", client_instance="win-x")

        # 不传 instance → 释放成功
        r = await release_lock(db, RT, rid, user_id)
        assert r["released"] is True
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_heartbeat_with_instance():
    """heartbeat 只续期匹配 instance 的锁"""
    db = await _fresh_db()
    try:
        rid = f"wp-{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()
        instance = "window-hb"

        await acquire_lock(db, RT, rid, user_id, "admin", client_instance=instance)

        # 匹配 instance → 续期成功
        r1 = await heartbeat_lock(db, RT, rid, user_id, client_instance=instance)
        assert r1["refreshed"] is True

        # 不匹配 instance → 续期失败
        r2 = await heartbeat_lock(db, RT, rid, user_id, client_instance="wrong-instance")
        assert r2["refreshed"] is False
    finally:
        await db.close()
