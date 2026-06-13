# Feature: editing-lock-v1-v2-consolidation
# Properties 5-9 + 边界单元测试: v2 service 承载 workpaper 锁等价测试
"""
底稿锁（workpaper）通过 v2 通用编辑锁端点的等价行为测试。

Property 5: 底稿锁 acquire 冲突 — holder A holds lock, holder B tries acquire → 409 + holder info
Property 6: 底稿锁 heartbeat 续期 — holder has lock, heartbeat → heartbeat_at refreshed + refreshed=True
Property 7: 底稿锁 heartbeat 无锁 — no active lock, heartbeat → 404
Property 8: 底稿锁 release — holder releases → released_at set + no active lock
Property 9: 底稿锁 force 抢占 — holder A has lock, holder B force → new holder is B + previous_holder_id = A
边界: 空 holder_name acquire succeeds (SQLite compatible)

**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.1**

使用 in-process ASGI httpx 测试端点行为（SQLite 可跑）。
"""
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 确保所有模型注册（含 users 等被 FK 引用的表）
import app.models  # noqa: F401
from app.models.base import Base
from app.models.editing_lock_models import EditingLock

# SQLite 兼容 PG 类型
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

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
_SessionFactory = async_sessionmaker(
    _engine, class_=AsyncSession, expire_on_commit=False
)


@event.listens_for(_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=OFF")
    cursor.close()


# Reusable strategies
_resource_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=3,
    max_size=20,
)


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
    from tests._test_auth_helper import FakeAuthUser, override_auth
    from app.main import app

    async def _factory(user_id: uuid.UUID, username: str = "tester"):
        user = FakeAuthUser(user_id=user_id, username=username)
        return override_auth(app, db_session=db_session, user=user)

    yield _factory



# --------------------------------------------------------------------------
# Property 5: 底稿锁 acquire 冲突
# Feature: editing-lock-v1-v2-consolidation, Property 5: 底稿锁 acquire 冲突
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
    """holder A holds lock, holder B tries acquire → 409 + holder info"""
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder A acquires
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder B tries acquire → 409
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_b.status_code == 409
        detail = resp_b.json()["detail"]
        assert "locked_by" in detail
        assert detail["locked_by"] == str(holder_a_id)
        assert "locked_by_name" in detail
        assert detail["locked_by_name"] == "holder_a"


# --------------------------------------------------------------------------
# Property 6: 底稿锁 heartbeat 续期
# Feature: editing-lock-v1-v2-consolidation, Property 6: 底稿锁 heartbeat 续期
# **Validates: Requirements 3.3**
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_heartbeat_refreshes_when_lock_held(
    db_session, make_client, holder_id, resource_id
):
    """持锁 heartbeat → heartbeat_at refreshed + refreshed=True"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # Acquire lock first
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200

        # Record initial heartbeat_at
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        async with _SessionFactory() as check_session:
            result = await check_session.execute(stmt)
            lock_before = result.scalar_one()
            hb_before = lock_before.heartbeat_at

        # Heartbeat
        resp_hb = await client.patch(
            f"/api/editing-locks/workpaper/{resource_id}/heartbeat"
        )
        assert resp_hb.status_code == 200
        body = resp_hb.json()
        # Response includes refreshed=True
        assert body.get("refreshed") is True or body.get("data", {}).get("refreshed") is True

        # Verify heartbeat_at was updated
        async with _SessionFactory() as check_session2:
            result2 = await check_session2.execute(stmt)
            lock_after = result2.scalar_one()
            assert lock_after.heartbeat_at >= hb_before


# --------------------------------------------------------------------------
# Property 7: 底稿锁 heartbeat 无锁失败
# Feature: editing-lock-v1-v2-consolidation, Property 7: 底稿锁 heartbeat 无锁
# **Validates: Requirements 3.4**
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
    """无活跃锁 heartbeat → 404"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        resp = await client.patch(
            f"/api/editing-locks/workpaper/{resource_id}/heartbeat"
        )
        assert resp.status_code == 404


# --------------------------------------------------------------------------
# Property 8: 底稿锁 release 释放
# Feature: editing-lock-v1-v2-consolidation, Property 8: 底稿锁 release
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
    """持锁 release → released_at set + 无活跃锁 + subsequent acquire succeeds"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # Acquire
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200

        # Release
        resp_rel = await client.delete(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_rel.status_code == 200

    # Verify no active lock
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        active_locks = result.scalars().all()
        assert len(active_locks) == 0

    # Verify released lock has released_at set
    async with _SessionFactory() as check_session2:
        stmt2 = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
        )
        result2 = await check_session2.execute(stmt2)
        released_lock = result2.scalar_one()
        assert released_lock.released_at is not None

    # Subsequent acquire by same holder succeeds (lock no longer held)
    async with await make_client(holder_id, "holder") as client2:
        resp_re_acq = await client2.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_re_acq.status_code == 200


# --------------------------------------------------------------------------
# Property 9: 底稿锁 force 抢占
# Feature: editing-lock-v1-v2-consolidation, Property 9: 底稿锁 force 抢占
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
    """holder A has lock, holder B force → new holder is B + previous_holder_id = A"""
    assume(holder_a_id != holder_b_id)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder A acquires
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder B force-acquires (mock broadcast_raw to prevent SSE errors)
    with patch("app.routers.editing_locks.event_bus") as mock_event_bus:
        mock_event_bus.broadcast_raw = lambda *a, **kw: None
        async with await make_client(holder_b_id, "holder_b") as client_b:
            resp_b = await client_b.post(
                f"/api/editing-locks/workpaper/{resource_id}/force"
            )
            assert resp_b.status_code == 200
            body = resp_b.json()
            # Handle potential data wrapper
            data = body.get("data", body)
            assert data["previous_holder_id"] == str(holder_a_id)

    # Verify new holder is B
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        active_lock = result.scalar_one()
        assert active_lock.holder_id == holder_b_id


# --------------------------------------------------------------------------
# Task 3.7: 边界单元测试 — 空 holder_name acquire succeeds (SQLite compatible)
# Feature: editing-lock-v1-v2-consolidation, Task 3.7: v2 workpaper 锁边界
# **Validates: Requirements 3.7, 8.1**
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_holder_name_acquire_succeeds(db_session, make_client):
    """边界: holder_name 为空字符串时 acquire 仍成功"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from tests._test_auth_helper import FakeAuthUser, override_auth
    from app.main import app

    user_id = uuid.uuid4()
    # FakeAuthUser with empty username → _holder_name returns ""
    user = FakeAuthUser(user_id=user_id, username="")
    async with override_auth(app, db_session=db_session, user=user) as client:
        resp = await client.post("/api/editing-locks/workpaper/test-resource-123")
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)
        assert data["locked"] is False
        assert "lock_id" in data

    # Verify lock exists
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == "test-resource-123",
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        lock = result.scalar_one()
        assert lock.holder_id == user_id
