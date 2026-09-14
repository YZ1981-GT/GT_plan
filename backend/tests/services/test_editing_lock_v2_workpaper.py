# Feature: editing-lock-v1-v2-consolidation
# Properties 5-9: v2 service 承载 workpaper 锁等价测试 + 边界单元测试
"""
Tests for v2 editing lock workpaper behavior:
- Property 5: acquire conflict (holder A locks, holder B tries → 409 + holder info)
- Property 6: heartbeat renewal (holder locks, heartbeat → heartbeat_at increases + refreshed=True)
- Property 7: heartbeat no lock (no active lock, heartbeat → 404)
- Property 8: release (holder locks then releases → released_at set + no active lock)
- Property 9: force acquire (holder A locks, holder B force → new holder is B + previous_holder_id = A)
- Boundary: empty holder_name; service only flush, router commits

**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.1**

Uses in-process ASGI httpx + SQLite in-memory + hypothesis max_examples=3.
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



# Hypothesis strategy for resource IDs (safe URL path segments)
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
    """返回工厂函数，传入 user_id + username 生成对应用户的 httpx client"""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    async def _factory(user_id: uuid.UUID, username: str = "tester"):
        user = FakeAuthUser(user_id=user_id, username=username)
        return override_auth(app, db_session=db_session, user=user)

    yield _factory


async def _rebuild_tables():
    """每次 hypothesis 迭代重建表（清理上次数据）"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


# --------------------------------------------------------------------------
# Property 5: 底稿锁 acquire 冲突
# Feature: editing-lock-v1-v2-consolidation, Property 5: acquire conflict
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
    """他人持锁→409 + detail 含 locked_by 和 locked_by_name"""
    assume(holder_a_id != holder_b_id)
    await _rebuild_tables()

    # holder_a 获取锁
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder_b 尝试 acquire → 409
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_b.status_code == 409
        detail = resp_b.json()["detail"]
        assert detail["locked_by"] == str(holder_a_id)
        assert detail["locked_by_name"] == "holder_a"


# --------------------------------------------------------------------------
# Property 6: 底稿锁 heartbeat 续期
# Feature: editing-lock-v1-v2-consolidation, Property 6: heartbeat renewal
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_heartbeat_renewal_refreshes_heartbeat_at(
    db_session, make_client, holder_id, resource_id
):
    """持锁后 heartbeat → 200 + refreshed=True + heartbeat_at 增大"""
    await _rebuild_tables()

    async with await make_client(holder_id, "holder") as client:
        # acquire
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200

        # heartbeat
        resp_hb = await client.patch(
            f"/api/editing-locks/workpaper/{resource_id}/heartbeat"
        )
        assert resp_hb.status_code == 200
        body = resp_hb.json()
        assert body["refreshed"] is True
        assert "heartbeat_at" in body

    # DB 验证: heartbeat_at >= acquired_at
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        lock = result.scalar_one()
        assert lock.heartbeat_at >= lock.acquired_at


# --------------------------------------------------------------------------
# Property 7: 底稿锁 heartbeat 无锁失败
# Feature: editing-lock-v1-v2-consolidation, Property 7: heartbeat no lock
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_heartbeat_no_lock_returns_404(
    db_session, make_client, holder_id, resource_id
):
    """无活跃锁时 heartbeat → 404"""
    await _rebuild_tables()

    async with await make_client(holder_id, "holder") as client:
        resp = await client.patch(
            f"/api/editing-locks/workpaper/{resource_id}/heartbeat"
        )
        assert resp.status_code == 404


# --------------------------------------------------------------------------
# Property 8: 底稿锁 release 释放
# Feature: editing-lock-v1-v2-consolidation, Property 8: release
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
    """持锁后 release → 200 + released_at 设置 + 无活跃锁"""
    await _rebuild_tables()

    async with await make_client(holder_id, "holder") as client:
        # acquire
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200

        # release
        resp_rel = await client.delete(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_rel.status_code == 200
        body = resp_rel.json()
        assert body["released"] is True

    # DB 验证: 无活跃锁
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        active_locks = result.scalars().all()
        assert len(active_locks) == 0

        # released_at 已设置
        stmt_all = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
        )
        result_all = await check_session.execute(stmt_all)
        lock = result_all.scalar_one()
        assert lock.released_at is not None


# --------------------------------------------------------------------------
# Property 9: 底稿锁 force 抢占
# Feature: editing-lock-v1-v2-consolidation, Property 9: force acquire
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_a_id=st.uuids(),
    holder_b_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_force_acquire_replaces_holder(
    db_session, make_client, holder_a_id, holder_b_id, resource_id
):
    """他人持锁→force→新持有者=B + previous_holder_id=A"""
    assume(holder_a_id != holder_b_id)
    await _rebuild_tables()

    # holder_a 获取锁
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder_b force acquire
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_force = await client_b.post(
            f"/api/editing-locks/workpaper/{resource_id}/force"
        )
        assert resp_force.status_code == 200
        body = resp_force.json()
        assert body["previous_holder_id"] == str(holder_a_id)
        assert "lock_id" in body

    # DB 验证: 唯一活跃锁持有者=holder_b
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
# Task 3.7: Boundary unit tests
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_holder_name_acquire_succeeds(db_session, make_client):
    """边界: 空 holder_name 的 acquire 应成功（SQLite 允许）"""
    await _rebuild_tables()

    user_id = uuid.uuid4()
    # FakeAuthUser.username="" → _holder_name returns ""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    user = FakeAuthUser(user_id=user_id, username="")
    async with override_auth(app, db_session=db_session, user=user) as client:
        resource_id = "boundary-test-empty-name"
        resp = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["locked"] is False


@pytest.mark.asyncio
async def test_service_flush_router_commit(db_session, make_client):
    """边界: service 只 flush 不 commit, 数据通过 router commit 持久化

    验证方式: endpoint 调用成功后, 从独立 session 能查到锁记录
    (endpoint 内 router 已 commit, 而非仅 flush 到 session cache)
    """
    await _rebuild_tables()

    user_id = uuid.uuid4()
    resource_id = "boundary-flush-commit-test"

    async with await make_client(user_id, "flusher") as client:
        resp = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp.status_code == 200

    # 独立 session 查询 — 如果 service 没 commit 但 router 有, 这里能查到
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        lock = result.scalar_one_or_none()
        assert lock is not None, "Lock should be persisted after router commit"
        assert lock.holder_id == user_id
