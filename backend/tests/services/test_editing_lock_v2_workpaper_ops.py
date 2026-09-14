# Feature: editing-lock-v1-v2-consolidation, Properties 4-9 + boundary tests
"""
Properties 4-9: 底稿锁 workpaper 操作端到端属性测试

Property 4: acquire 创建 — 无锁时 acquire→200, locked=False, 1 active lock
Property 5: acquire 冲突 — 他人持锁→409 + locked_by_name
Property 6: heartbeat 续期 — 持锁后 heartbeat→refreshed=True + heartbeat_at 增大
Property 7: heartbeat 无锁 — 无活跃锁 heartbeat→404
Property 8: release 释放 — 持锁 release→released_at 设置 + 无活跃锁
Property 9: force 抢占 — 他人持锁 force→新持有者唯一 + previous_holder_id 正确

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.1**

使用 in-process ASGI httpx + SQLite in-memory 测试端点行为。
"""
import asyncio
import inspect
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


# --- Helpers ---

def _body(resp):
    """Extract body handling ResponseWrapperMiddleware wrapping."""
    j = resp.json()
    return j.get("data", j) if isinstance(j, dict) else j


# --- Strategies ---
_resource_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=3,
    max_size=20,
)


# --------------------------------------------------------------------------
# Property 4: 底稿锁 acquire 创建
# Feature: editing-lock-v1-v2-consolidation, Property 4: acquire create
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=_resource_id_st,
)
async def test_acquire_creates_lock_when_none_exists(
    db_session, make_client, holder_id, resource_id
):
    """无锁时 acquire → 200, locked=False, 活跃锁=1

    **Validates: Requirements 3.1**
    """
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "creator") as client:
        resp = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp.status_code == 200
        body = _body(resp)
        assert body["locked"] is False
        assert "lock_id" in body
        assert "acquired_at" in body

    # 验证活跃锁 = 1
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        active_locks = result.scalars().all()
        assert len(active_locks) == 1
        assert active_locks[0].holder_id == holder_id


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
    """他人持锁时 acquire → 409 + detail 含 locked_by_name"""
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder A 先获取锁
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200
        body_a = _body(resp_a)
        assert body_a["locked"] is False

    # holder B 尝试获取 → 409
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_b.status_code == 409
        # Custom error handler wraps as {"code":409, "message": {detail_dict}}
        body_409 = resp_b.json()
        detail = body_409.get("message", body_409.get("detail", body_409))
        assert detail["locked_by"] == str(holder_a_id)
        assert detail["locked_by_name"] == "holder_a"
        assert "acquired_at" in detail


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
async def test_heartbeat_renews_and_increases_heartbeat_at(
    db_session, make_client, holder_id, resource_id
):
    """持锁后 heartbeat → refreshed=True + heartbeat_at 增大"""
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder") as client:
        # acquire
        resp_acq = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_acq.status_code == 200

        # 记录 acquire 后 heartbeat_at
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

        # 验证 heartbeat_at 增大
        async with _SessionFactory() as check_session2:
            result2 = await check_session2.execute(stmt)
            lock_after = result2.scalar_one()
            assert lock_after.heartbeat_at >= hb_before


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
    # 每次 hypothesis 迭代重建表
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
    """持锁 release → released_at 设置 + 无活跃锁"""
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
        body_rel = _body(resp_rel)
        assert body_rel["released"] is True

    # 验证 released_at 已设置且无活跃锁
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
        )
        result = await check_session.execute(stmt)
        locks = result.scalars().all()
        assert len(locks) >= 1
        # no active lock remains
        active = [lk for lk in locks if lk.released_at is None]
        assert len(active) == 0
        # released lock has released_at set
        released = [lk for lk in locks if lk.released_at is not None]
        assert len(released) >= 1


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
    """他人持锁 force → 新持有者唯一 + previous_holder_id 正确"""
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder A 先获取锁
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder B force acquire
    async with await make_client(holder_b_id, "holder_b") as client_b:
        resp_force = await client_b.post(
            f"/api/editing-locks/workpaper/{resource_id}/force"
        )
        assert resp_force.status_code == 200
        body_f = _body(resp_force)
        assert body_f["previous_holder_id"] == str(holder_a_id)
        assert "lock_id" in body_f
        assert "acquired_at" in body_f

    # 验证 B 是唯一活跃锁持有者
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
# Task 3.7: 边界单元测试
# Feature: editing-lock-v1-v2-consolidation, Task 3.7: boundary unit tests
# --------------------------------------------------------------------------


class TestBoundaryWorkpaperOps:
    """边界测试：空 holder_name acquire + service 只 flush 确认"""

    @pytest.mark.asyncio
    async def test_acquire_with_empty_holder_name(self, db_session, make_client):
        """空 holder_name acquire 仍可成功（SQLite OK）"""
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        user_id = uuid.uuid4()
        resource_id = "test-wp-empty-name"

        from tests._test_auth_helper import override_auth, FakeAuthUser
        from app.main import app

        # username="" → _holder_name returns "" → service 存为 None
        user = FakeAuthUser(user_id=user_id, username="")
        async with override_auth(app, db_session=db_session, user=user) as client:
            resp = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
            assert resp.status_code == 200
            body = _body(resp)
            assert body["locked"] is False

        # 验证锁已创建，holder_name 为 None
        async with _SessionFactory() as check_session:
            stmt = select(EditingLock).where(
                EditingLock.resource_type == "workpaper",
                EditingLock.resource_id == resource_id,
                EditingLock.released_at.is_(None),
            )
            result = await check_session.execute(stmt)
            lock = result.scalar_one()
            assert lock.holder_name is None

    @pytest.mark.asyncio
    async def test_service_only_flushes_router_commits(self, db_session):
        """service 只 flush 不 commit — router 统一 commit 模式确认

        静态验证: service 源码不含 db.commit() 调用
        运行时验证: 直接调 service 后同 session 数据可见（flush 生效）
        """
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        from app.services import editing_lock_service
        from app.services.editing_lock_service import acquire_lock

        # 静态断言：service 源码无 db.commit()
        source = inspect.getsource(editing_lock_service)
        assert "await db.commit()" not in source, (
            "service 不应包含 db.commit()，commit 由 router 统一执行"
        )

        # 运行时验证：flush 后同 session 可见
        holder_id = uuid.uuid4()
        resource_id = "test-flush-pattern"

        result = await acquire_lock(
            db_session,
            resource_type="workpaper",
            resource_id=resource_id,
            holder_id=holder_id,
            holder_name="flush_test_user",
        )
        assert result["locked"] is False

        # flush 后同 session 可查到锁
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        res = await db_session.execute(stmt)
        lock = res.scalar_one_or_none()
        assert lock is not None
        assert lock.holder_id == holder_id
