# Feature: editing-lock-v1-v2-consolidation, Property 13: 底稿锁同人重复 acquire 续期
"""
Property 13: 底稿锁同人重复 acquire 续期（不冲突）

For any 由某持有者持有 Active_Lock 的底稿，同一持有者再次调用 acquire 应返回获取成功
（locked=False）并刷新 heartbeat_at，且该资源活跃锁数量保持为 1（不新增、不返回 409）。
另：不同持有者 acquire → 409 冲突。

**Validates: Requirements 3.2a**

使用 in-process ASGI httpx 测试端点行为。
"""
import uuid

import pytest
import pytest_asyncio
from hypothesis import given, settings, HealthCheck
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
    """返回一个工厂函数，传入 user_id 生成对应用户的 httpx client"""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    async def _factory(user_id: uuid.UUID, username: str = "tester"):
        user = FakeAuthUser(user_id=user_id, username=username)
        return override_auth(app, db_session=db_session, user=user)

    yield _factory


# --------------------------------------------------------------------------
# Property 13: 底稿锁同人重复 acquire 续期
# Feature: editing-lock-v1-v2-consolidation, Property 13: 底稿锁同人重复 acquire 续期
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_id=st.uuids(),
    resource_id=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=3,
        max_size=20,
    ),
)
async def test_same_holder_acquire_renews(db_session, make_client, holder_id, resource_id):
    """同一持有者重复 acquire 应续期成功（locked=False），活跃锁=1，heartbeat 刷新"""
    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with await make_client(holder_id, "holder_a") as client:
        # 首次 acquire — 成功创建锁
        resp1 = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp1.status_code == 200
        body1 = resp1.json().get("data", resp1.json())
        assert body1["locked"] is False
        first_lock_id = body1["lock_id"]

        # 同人重复 acquire — 应续期成功，不是 409
        resp2 = await client.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp2.status_code == 200, f"Expected 200 but got {resp2.status_code}: {resp2.text}"
        body2 = resp2.json().get("data", resp2.json())
        assert body2["locked"] is False
        # lock_id 应该保持一致（续期同一锁，不新建）
        assert body2["lock_id"] == first_lock_id

    # 验证活跃锁数量 = 1
    async with _SessionFactory() as check_session:
        stmt = select(EditingLock).where(
            EditingLock.resource_type == "workpaper",
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await check_session.execute(stmt)
        active_locks = result.scalars().all()
        assert len(active_locks) == 1, f"Expected 1 active lock, got {len(active_locks)}"
        # heartbeat_at 应被刷新（≥ acquired_at）
        lock = active_locks[0]
        assert lock.heartbeat_at >= lock.acquired_at


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_a_id=st.uuids(),
    holder_b_id=st.uuids(),
    resource_id=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=3,
        max_size=20,
    ),
)
async def test_different_holder_acquire_conflicts(db_session, make_client, holder_a_id, holder_b_id, resource_id):
    """不同持有者 acquire 已持锁资源 → 409 冲突"""
    # 确保两人不同
    from hypothesis import assume
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
