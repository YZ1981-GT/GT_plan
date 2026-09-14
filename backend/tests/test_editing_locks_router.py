"""编辑锁 router 单元测试

Validates: Requirements 7.1, 7.2, 7.3, 7.4
Feature: global-refinement-v5-closure
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# 确保所有模型注册（含 users 等被 FK 引用的表）
import app.models  # noqa: F401
from app.models.base import Base

# SQLite 兼容 PG 类型
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


# SQLite 不支持 FK 约束，禁用以避免创表时报外键引用错误
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
async def client(db_session):
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    user = FakeAuthUser(
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        username="lock_tester",
    )
    async with override_auth(app, db_session=db_session, user=user) as c:
        yield c


class TestAcquire:
    @pytest.mark.asyncio
    async def test_acquire_success(self, client):
        resp = await client.post("/api/editing-locks/note/res-001")
        assert resp.status_code == 200
        data = resp.json()
        body = data.get("data", data)
        assert body["locked"] is False
        assert "lock_id" in body

    @pytest.mark.asyncio
    async def test_acquire_conflict_409(self, client, db_session):
        """第二人获取同资源应 409"""
        from app.services.editing_lock_service import acquire_lock

        other_holder = uuid.uuid4()
        await acquire_lock(db_session, "note", "res-002", other_holder, "其他人")
        await db_session.commit()

        resp = await client.post("/api/editing-locks/note/res-002")
        assert resp.status_code == 409


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_success(self, client):
        await client.post("/api/editing-locks/note/res-hb")
        resp = await client.patch("/api/editing-locks/note/res-hb/heartbeat")
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["refreshed"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_no_lock_404(self, client):
        resp = await client.patch("/api/editing-locks/note/nonexist/heartbeat")
        assert resp.status_code == 404


class TestRelease:
    @pytest.mark.asyncio
    async def test_release_success(self, client):
        await client.post("/api/editing-locks/note/res-rel")
        resp = await client.delete("/api/editing-locks/note/res-rel")
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["released"] is True

    @pytest.mark.asyncio
    async def test_release_no_lock_404(self, client):
        resp = await client.delete("/api/editing-locks/note/no-lock")
        assert resp.status_code == 404


class TestForceAcquire:
    @pytest.mark.asyncio
    async def test_force_acquire(self, client, db_session):
        from app.services.editing_lock_service import acquire_lock

        other = uuid.uuid4()
        await acquire_lock(db_session, "note", "res-force", other, "前人")
        await db_session.commit()

        resp = await client.post("/api/editing-locks/note/res-force/force")
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["previous_holder_id"] == str(other)
        assert "lock_id" in body


class TestListActive:
    @pytest.mark.asyncio
    async def test_list_active(self, client):
        await client.post("/api/editing-locks/note/res-list-1")
        resp = await client.get("/api/editing-locks/active")
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert "locks" in body
