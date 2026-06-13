# Feature: editing-lock-v1-v2-consolidation, Properties 5-9 + boundary tests
"""
Properties 5-9: 底稿锁 acquire冲突 / heartbeat续期 / heartbeat无锁失败 / release释放 / force抢占
+ 边界单元测试 (Requirements 3.7, 8.1)

使用 in-process ASGI httpx 测试端点行为（SQLite in-memory）。
"""
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

# hypothesis 调速: max_examples=3
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
    """返回一个工厂函数，传入 user_id 生成对应用户的 httpx client"""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    async def _factory(user_id: uuid.UUID, username: str = "tester"):
        user = FakeAuthUser(user_id=user_id, username=username)
        return override_auth(app, db_session=db_session, user=user)

    yield _factory


# Strategies
_resource_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=3,
    max_size=20,
)


# --------------------------------------------------------------------------
# Feature: editing-lock-v1-v2-consolidation, Property 5
# Property 5: 底稿锁 acquire 冲突
# **Validates: Requirements 3.2**
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
    """holder A acquires, holder B tries same resource → HTTP 409 + holder info"""
    assume(holder_a_id != holder_b_id)

    # Rebuild tables each hypothesis iteration
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder A acquires successfully
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200
        body_a = resp_a.json().get("data", resp_a.json())
        assert body_a["locked"] is False

    # holder B tries to acquire same resource → 409
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_b.status_code == 409
        detail = resp_b.json().get("detail", resp_b.json())
        # Verify holder info is present in 409 response
        assert "locked_by" in detail
        assert "locked_by_name" in detail
        assert "acquired_at" in detail
        assert detail["locked_by"] == str(holder_a_id)



# --------------------------------------------------------------------------
# Feature: editing-lock-v1-v2-consolidation, Property 6
# Property 6: 底稿锁 heartbeat 续期
# **Validates: Requirements 3.3**
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_heartbeat_renews_lock(db_session, make_client, holder_id, resource_id):
    """holder acquires, then PATCH heartbeat → refreshed=True + heartbeat_at updated"""
    # Rebuild tables each hypothesis iteration
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # Acquire lock
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200

        # Call heartbeat
        resp_hb = await client.patch(f"/api/editing-locks/workpaper/{resource_id}/heartbeat")
        assert resp_hb.status_code == 200
        body_hb = resp_hb.json().get("data", resp_hb.json())
        assert body_hb["refreshed"] is True

    # Verify heartbeat_at was updated in DB
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        lock = result.scalar_one_or_none()
        assert lock is not None
        assert lock.heartbeat_at >= lock.acquired_at



# --------------------------------------------------------------------------
# Feature: editing-lock-v1-v2-consolidation, Property 7
# Property 7: 底稿锁 heartbeat 无锁失败
# **Validates: Requirements 3.4**
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_heartbeat_without_lock_returns_404(db_session, make_client, holder_id, resource_id):
    """no active lock, call PATCH heartbeat → HTTP 404"""
    # Rebuild tables each hypothesis iteration
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # No acquire — directly heartbeat
        resp_hb = await client.patch(f"/api/editing-locks/workpaper/{resource_id}/heartbeat")
        assert resp_hb.status_code == 404



# --------------------------------------------------------------------------
# Feature: editing-lock-v1-v2-consolidation, Property 8
# Property 8: 底稿锁 release 释放
# **Validates: Requirements 3.5**
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
    """holder acquires, then DELETE release → released_at set, no active lock remains"""
    # Rebuild tables each hypothesis iteration
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # Acquire lock
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200

        # Release lock
        resp_rel = await client.delete(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_rel.status_code == 200

    # Verify released_at is set and no active lock remains
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
        )
        result = await check_session.execute(stmt)
        locks = result.scalars().all()

        # There should be exactly one lock record with released_at set
        assert len(locks) == 1
        assert locks[0].released_at is not None

        # No active locks (released_at IS NULL)
        active = [lk for lk in locks if lk.released_at is None]
        assert len(active) == 0



# --------------------------------------------------------------------------
# Feature: editing-lock-v1-v2-consolidation, Property 9
# Property 9: 底稿锁 force 抢占
# **Validates: Requirements 3.6**
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
    """holder A has lock, holder B calls POST force → new lock for B, previous_holder_id = A"""
    assume(holder_a_id != holder_b_id)

    # Rebuild tables each hypothesis iteration
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder A acquires lock
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder B force-acquires
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}/force")
        assert resp_b.status_code == 200
        body_b = resp_b.json().get("data", resp_b.json())
        assert "lock_id" in body_b
        assert body_b["previous_holder_id"] == str(holder_a_id)

    # Verify only one active lock remains and it belongs to holder B
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        active_locks = result.scalars().all()
        assert len(active_locks) == 1
        assert active_locks[0].holder_id == holder_b_id



# --------------------------------------------------------------------------
# Requirements 3.7, 8.1 — 边界单元测试
# Non-hypothesis known example: empty holder_name
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_holder_name_acquire(db_session, make_client):
    """边界：空 holder_name 应正常 acquire（holder_name 可选）"""
    # Rebuild tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    user_id = uuid.uuid4()
    # FakeAuthUser username used as holder_name via router's _holder_name()
    # When username is empty string, holder_name becomes ""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    user = FakeAuthUser(user_id=user_id, username="")
    async with override_auth(app, db_session=db_session, user=user) as client:
        resp = await client.post("/api/editing-locks/workpaper/test-resource-123")
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["locked"] is False
        assert "lock_id" in body

    # Verify lock was created with empty/None holder_name
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == "test-resource-123",
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        lock = result.scalar_one_or_none()
        assert lock is not None
        # holder_name stored as None when empty string passed (service converts "" → None)
        assert lock.holder_name is None or lock.holder_name == ""
