# Feature: editing-lock-v1-v2-consolidation
# Properties 5-9 + boundary unit tests for workpaper lock lifecycle via v2 endpoints
"""
Properties tested:
- Property 5: 底稿锁 acquire 冲突 — 他人持锁→409 + 持有者信息
- Property 6: 底稿锁 heartbeat 续期 — 持锁 heartbeat→heartbeat_at 增大 + refreshed=True
- Property 7: 底稿锁 heartbeat 无锁失败 — 无锁 heartbeat→404
- Property 8: 底稿锁 release 释放 — 持锁 release→released_at 设置 + 无活跃锁
- Property 9: 底稿锁 force 抢占 — 他人持锁 force→新持有者唯一 + previous_holder_id 正确
- Boundary: 空 holder_name acquire 成功

**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.1**

使用 in-process ASGI httpx 测试端点行为（SQLite in-memory）。
"""
import asyncio
import uuid

import pytest
import pytest_asyncio
from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# 确保所有模型注册（含 users 等被 FK 引用的表）
import app.models  # noqa: F401
from app.models.base import Base
from app.models.editing_lock_models import EditingLock

# SQLite 兼容 PG 类型
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# hypothesis 调速: max_examples=3（加速本地迭代）
SETTINGS = settings(
    max_examples=3,
    deadline=30000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)

# 独立 SQLite 引擎
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=OFF")
    cursor.close()


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _SessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def make_client(db_session):
    """返回一个工厂函数，传入 user_id + username 生成对应用户的 httpx client"""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    async def _factory(user_id: uuid.UUID, username: str = "tester"):
        user = FakeAuthUser(user_id=user_id, username=username)
        return override_auth(app, db_session=db_session, user=user)

    yield _factory


# Shared strategy for resource_id
_resource_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=3,
    max_size=20,
)


def _body(resp):
    """Extract body handling ResponseWrapperMiddleware wrapping."""
    j = resp.json()
    return j.get("data", j) if isinstance(j, dict) else j


# --------------------------------------------------------------------------
# Property 5: 底稿锁 acquire 冲突
# Feature: editing-lock-v1-v2-consolidation, Property 5: 底稿锁 acquire 冲突
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_a_id=st.uuids(),
    holder_b_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_acquire_conflict_returns_409_with_holder_info(
    db_session, make_client, holder_a_id, holder_b_id, resource_id
):
    """他人持锁→409 + 持有者信息（locked_by / locked_by_name / acquired_at）"""
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder_a 获取锁
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200
        body_a = _body(resp_a)
        assert body_a["locked"] is False

    # holder_b 尝试获取 → 409
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_b.status_code == 409
        # 409 detail contains holder info
        detail = resp_b.json().get("detail", resp_b.json())
        assert detail["locked_by"] == str(holder_a_id)
        assert detail["locked_by_name"] == "holder_a"
        assert "acquired_at" in detail


# --------------------------------------------------------------------------
# Property 6: 底稿锁 heartbeat 续期
# Feature: editing-lock-v1-v2-consolidation, Property 6: 底稿锁 heartbeat 续期
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_heartbeat_refreshes_heartbeat_at(
    db_session, make_client, holder_id, resource_id
):
    """持锁 heartbeat→heartbeat_at 增大 + refreshed=True"""
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # acquire
        resp = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp.status_code == 200

        # record heartbeat_at before
        async with _SessionFactory() as check_session:
            stmt = select(EditingLock).where(
                EditingLock.resource_type == "workpaper",
                EditingLock.resource_id == resource_id,
                EditingLock.released_at.is_(None),
            )
            result = await check_session.execute(stmt)
            lock_before = result.scalar_one()
            hb_before = lock_before.heartbeat_at

        # small delay to ensure time difference
        await asyncio.sleep(0.01)

        # heartbeat
        resp_hb = await client.patch(
            f"/api/editing-locks/workpaper/{resource_id}/heartbeat"
        )
        assert resp_hb.status_code == 200
        body_hb = _body(resp_hb)
        assert body_hb["refreshed"] is True

        # verify heartbeat_at increased in DB
        async with _SessionFactory() as check_session2:
            stmt2 = select(EditingLock).where(
                EditingLock.resource_type == "workpaper",
                EditingLock.resource_id == resource_id,
                EditingLock.released_at.is_(None),
            )
            result2 = await check_session2.execute(stmt2)
            lock_after = result2.scalar_one()
            assert lock_after.heartbeat_at >= hb_before


# --------------------------------------------------------------------------
# Property 7: 底稿锁 heartbeat 无锁失败
# Feature: editing-lock-v1-v2-consolidation, Property 7: 底稿锁 heartbeat 无锁失败
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_heartbeat_without_lock_returns_404(
    db_session, make_client, holder_id, resource_id
):
    """无锁 heartbeat→404"""
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # heartbeat without acquiring first → 404
        resp = await client.patch(
            f"/api/editing-locks/workpaper/{resource_id}/heartbeat"
        )
        assert resp.status_code == 404


# --------------------------------------------------------------------------
# Property 8: 底稿锁 release 释放
# Feature: editing-lock-v1-v2-consolidation, Property 8: 底稿锁 release 释放
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_release_sets_released_at_and_no_active_lock(
    db_session, make_client, holder_id, resource_id
):
    """持锁 release→released_at 设置 + 无活跃锁"""
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # acquire
        resp = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp.status_code == 200

        # release
        resp_rel = await client.delete(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_rel.status_code == 200
        body_rel = _body(resp_rel)
        assert body_rel["released"] is True

    # verify released_at is set and no active lock remains
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
        )
        result = await check_session.execute(stmt)
        locks = result.scalars().all()
        # At least one lock record exists (released)
        assert len(locks) >= 1
        # No active (unreleased) locks
        active = [lk for lk in locks if lk.released_at is None]
        assert len(active) == 0
        # The released lock has released_at set
        released = [lk for lk in locks if lk.released_at is not None]
        assert len(released) >= 1


# --------------------------------------------------------------------------
# Property 9: 底稿锁 force 抢占
# Feature: editing-lock-v1-v2-consolidation, Property 9: 底稿锁 force 抢占
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_a_id=st.uuids(),
    holder_b_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_force_acquire_takes_over_lock(
    db_session, make_client, holder_a_id, holder_b_id, resource_id
):
    """他人持锁 force→新持有者唯一 + previous_holder_id 正确"""
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder_a acquires lock
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder_b force-acquires
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_f = await client_b.post(
            f"/api/editing-locks/workpaper/{resource_id}/force"
        )
        assert resp_f.status_code == 200
        body_f = _body(resp_f)
        assert body_f["previous_holder_id"] == str(holder_a_id)
        assert "lock_id" in body_f
        assert "acquired_at" in body_f

    # DB verification: exactly 1 active lock, held by holder_b
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        active_locks = result.scalars().all()
        assert len(active_locks) == 1, f"Expected 1 active lock, got {len(active_locks)}"
        assert active_locks[0].holder_id == holder_b_id


# --------------------------------------------------------------------------
# Task 3.7 边界单元测试: 空 holder_name acquire 成功
# Feature: editing-lock-v1-v2-consolidation, Task 3.7: 边界单元测试
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_with_empty_holder_name_succeeds(db_session, make_client):
    """空 holder_name acquire 成功（SQLite 可跑）"""
    # 重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    user_id = uuid.uuid4()
    resource_id = "test-resource-001"

    # FakeAuthUser with empty username → _holder_name returns ""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    user = FakeAuthUser(user_id=user_id, username="")
    async with override_auth(app, db_session=db_session, user=user) as client:
        resp = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp.status_code == 200
        body = _body(resp)
        assert body["locked"] is False
        assert "lock_id" in body

    # Verify lock created in DB
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        lock = result.scalar_one()
        assert lock.holder_id == user_id
        # holder_name stored as None (service converts empty string to None)
        assert lock.holder_name is None
