"""函证 router 单元测试

Validates: Requirements 10.3, 10.4, 10.5, 11.2, 11.3
Feature: global-refinement-v5-closure
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# 确保所有模型注册（含 projects/users 等被 FK 引用的表）
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

PROJECT_ID = str(uuid.uuid4())


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
        user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        username="confirm_tester",
    )
    async with override_auth(app, db_session=db_session, user=user) as c:
        yield c


class TestList:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get(f"/api/projects/{PROJECT_ID}/confirmations")
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["items"] == []
        assert body["total"] == 0


class TestCreate:
    @pytest.mark.asyncio
    async def test_create(self, client):
        payload = {"confirm_type": "receivable", "counterparty": "测试客户A"}
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/confirmations", json=payload
        )
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["confirm_type"] == "receivable"
        assert body["counterparty"] == "测试客户A"
        assert body["status"] == "pending"


class TestGetDetail:
    @pytest.mark.asyncio
    async def test_get_detail(self, client):
        payload = {"confirm_type": "bank", "counterparty": "银行A"}
        cr = await client.post(
            f"/api/projects/{PROJECT_ID}/confirmations", json=payload
        )
        cid = cr.json().get("data", cr.json())["id"]

        resp = await client.get(
            f"/api/projects/{PROJECT_ID}/confirmations/{cid}"
        )
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["counterparty"] == "银行A"

    @pytest.mark.asyncio
    async def test_not_found_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/projects/{PROJECT_ID}/confirmations/{fake_id}"
        )
        assert resp.status_code == 404


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update(self, client):
        payload = {"confirm_type": "payable", "counterparty": "供应商B"}
        cr = await client.post(
            f"/api/projects/{PROJECT_ID}/confirmations", json=payload
        )
        cid = cr.json().get("data", cr.json())["id"]

        resp = await client.put(
            f"/api/projects/{PROJECT_ID}/confirmations/{cid}",
            json={"counterparty": "供应商C"},
        )
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["counterparty"] == "供应商C"


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete(self, client):
        payload = {"confirm_type": "loan", "counterparty": "借款方D"}
        cr = await client.post(
            f"/api/projects/{PROJECT_ID}/confirmations", json=payload
        )
        cid = cr.json().get("data", cr.json())["id"]

        resp = await client.delete(
            f"/api/projects/{PROJECT_ID}/confirmations/{cid}"
        )
        assert resp.status_code == 200

        # 确认不在列表
        lr = await client.get(f"/api/projects/{PROJECT_ID}/confirmations")
        items = lr.json().get("data", lr.json())["items"]
        assert cid not in [i["id"] for i in items]


class TestTransition:
    @pytest.mark.asyncio
    async def test_transition_success(self, client):
        payload = {"confirm_type": "receivable", "counterparty": "客户E"}
        cr = await client.post(
            f"/api/projects/{PROJECT_ID}/confirmations", json=payload
        )
        cid = cr.json().get("data", cr.json())["id"]

        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/confirmations/{cid}/transition",
            json={"target_status": "sent"},
        )
        assert resp.status_code == 200
        body = resp.json().get("data", resp.json())
        assert body["status"] == "sent"

    @pytest.mark.asyncio
    async def test_transition_illegal_400(self, client):
        payload = {"confirm_type": "receivable", "counterparty": "客户F"}
        cr = await client.post(
            f"/api/projects/{PROJECT_ID}/confirmations", json=payload
        )
        cid = cr.json().get("data", cr.json())["id"]

        # pending → matched 不合法
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/confirmations/{cid}/transition",
            json={"target_status": "matched"},
        )
        assert resp.status_code == 400
