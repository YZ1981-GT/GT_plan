# Feature: editing-lock-v1-v2-consolidation, Properties 5-9: 底稿锁 v2 workpaper 端点
"""
Properties 5-9: 底稿锁 v2 workpaper 端点等价测试

Property 5: 底稿锁 acquire 冲突 — holder A holds, holder B acquires → 409 + holder info
Property 6: 底稿锁 heartbeat 续期 — holder acquires then heartbeats → refreshed=True
Property 7: 底稿锁 heartbeat 无锁失败 — no lock exists, heartbeat → 404
Property 8: 底稿锁 release 释放 — holder acquires then releases → released_at set
Property 9: 底稿锁 force 抢占 — holder A holds, holder B force → B is new holder

**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.1**

使用 in-process ASGI httpx + SQLite in-memory 测试端点行为。
"""
import uuid

import pytest
import pytest_asyncio
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
from sqlalchemy import event as sa_event, select
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

# Strategies
_resource_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=3,
    max_size=20,
)

# 独立 SQLite 引擎
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@sa_event.listens_for(_engine.sync_engine, "connect")
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
    """他人持锁 → acquire 返回 409 + 持有者信息

    **Validates: Requirements 3.2**
    """
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder_a 先获取锁
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200
        body_a = resp_a.json().get("data", resp_a.json())
        assert body_a["locked"] is False

    # holder_b 尝试获取 → 409
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_b.status_code == 409

        # 409 detail 应包含持有者信息
        detail = resp_b.json().get("detail", resp_b.json())
        assert detail["error_code"] == "LOCK_HELD"
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
async def test_heartbeat_refreshes_lock(db_session, make_client, holder_id, resource_id):
    """持锁后 heartbeat → refreshed=True, heartbeat_at 更新

    **Validates: Requirements 3.3**
    """
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # acquire
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200
        body_acq = resp_acq.json().get("data", resp_acq.json())
        assert body_acq["locked"] is False

        # heartbeat
        resp_hb = await client.patch(f"/api/editing-locks/workpaper/{resource_id}/heartbeat")
        assert resp_hb.status_code == 200
        body_hb = resp_hb.json().get("data", resp_hb.json())
        assert body_hb["refreshed"] is True
        assert "heartbeat_at" in body_hb

    # 验证 DB 中 heartbeat_at >= acquired_at
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
# Property 7: 底稿锁 heartbeat 无锁失败
# Feature: editing-lock-v1-v2-consolidation, Property 7: 底稿锁 heartbeat 无锁失败
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_heartbeat_no_lock_returns_404(db_session, make_client, holder_id, resource_id):
    """无活跃锁时 heartbeat → 404

    **Validates: Requirements 3.4**
    """
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # heartbeat without prior acquire → 404
        resp = await client.patch(f"/api/editing-locks/workpaper/{resource_id}/heartbeat")
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
async def test_release_sets_released_at(db_session, make_client, holder_id, resource_id):
    """持锁后 release → released_at 设置 + 无活跃锁

    **Validates: Requirements 3.5**
    """
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # acquire
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200

        # release
        resp_rel = await client.delete(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_rel.status_code == 200
        body_rel = resp_rel.json().get("data", resp_rel.json())
        assert body_rel["released"] is True

    # 验证 DB 中 released_at 已设置，无活跃锁
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
        )
        result = await check_session.execute(stmt)
        locks = result.scalars().all()
        # 至少一条记录，且全部 released
        assert len(locks) >= 1
        for lock in locks:
            assert lock.released_at is not None

        # 无活跃锁
        stmt_active = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result_active = await check_session.execute(stmt_active)
        assert result_active.scalar_one_or_none() is None


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
async def test_force_acquire_replaces_holder(
    db_session, make_client, holder_a_id, holder_b_id, resource_id
):
    """他人持锁 force-acquire → B 成新持有者 + previous_holder_id = A

    **Validates: Requirements 3.6**
    """
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder_a 获取锁
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder_b force-acquire (mock event_bus to avoid WorkingPaper lookup)
    from unittest.mock import patch, MagicMock

    mock_broadcast = MagicMock()
    with patch("app.services.event_bus.event_bus.broadcast_raw", mock_broadcast):
        async with await make_client(holder_b_id, "holder_b") as client_b:
            resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}/force")
            assert resp_b.status_code == 200
            body_b = resp_b.json().get("data", resp_b.json())
            assert body_b["previous_holder_id"] == str(holder_a_id)
            assert "lock_id" in body_b

    # 验证 DB: B 是唯一活跃持有者
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
# Task 3.7: 边界单元测试 — 空 holder_name (SQLite 可跑)
# Feature: editing-lock-v1-v2-consolidation
# **Validates: Requirements 3.7, 8.1**
# --------------------------------------------------------------------------

_HOLDER_ID = uuid.UUID("aaaaaaaa-1111-2222-3333-444444444444")
_RESOURCE_ID = "boundary-test-001"


@pytest.mark.asyncio
async def test_acquire_with_empty_holder_name(db_session, make_client):
    """空 holder_name 不应导致 acquire 失败

    FakeAuthUser 的 username 用于 _holder_name(user)，传空串验证 service 兼容。

    **Validates: Requirements 3.7, 8.1**
    """
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # FakeAuthUser with empty username → _holder_name returns ""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    user = FakeAuthUser(user_id=_HOLDER_ID, username="")
    async with override_auth(app, db_session=db_session, user=user) as client:
        resp = await client.post(f"/api/editing-locks/workpaper/{_RESOURCE_ID}")
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["locked"] is False
        assert "lock_id" in body

    # 验证 DB 中 holder_name 为 None（service 将空串转 None: `holder_name or None`）
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == _RESOURCE_ID,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        lock = result.scalar_one_or_none()
        assert lock is not None
        # service 存 `holder_name or None` → 空串转 None
        assert lock.holder_name is None


@pytest.mark.asyncio
async def test_release_no_lock_returns_404(db_session, make_client):
    """无活跃锁时 release → 404

    **Validates: Requirements 3.7, 8.1**
    """
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(_HOLDER_ID, "holder") as client:
        resp = await client.delete(f"/api/editing-locks/workpaper/{_RESOURCE_ID}")
        assert resp.status_code == 404
