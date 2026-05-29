"""归档项目例外通道测试

Validates: Requirements 1.2, AC 1.5
- POST with valid reason + admin role → 200
- POST with non-admin/partner/qc role → 403
- POST with empty reason → 422
- Verify audit_log entry is created with event_type='archived_exception_access'
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole

# SQLite 兼容 JSONB + ARRAY
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# 仅注册测试所需的模型
import app.models.core  # noqa: F401
import app.models.audit_log_models  # noqa: F401

from app.models.audit_log_models import AuditLogEntry
from app.routers.archived_exception import router

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fake users
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, role: UserRole = UserRole.admin):
        self.id = uuid.uuid4()
        self.username = f"test_{role.value}"
        self.email = f"{role.value}@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


ADMIN_USER = _FakeUser(UserRole.admin)
PARTNER_USER = _FakeUser(UserRole.partner)
QC_USER = _FakeUser(UserRole.qc)
AUDITOR_USER = _FakeUser(UserRole.auditor)
MANAGER_USER = _FakeUser(UserRole.manager)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # 仅创建测试所需的表（避免其他模型的 PG 特有语法在 SQLite 报错）
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["audit_log_entries"],
        ]
        await conn.run_sync(
            Base.metadata.create_all, tables=tables_to_create
        )
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


def _make_client(db_session: AsyncSession, user: _FakeUser):
    """构造测试客户端，注入指定用户。"""
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Tests: 200 success cases
# ---------------------------------------------------------------------------

PROJECT_ID = str(uuid.uuid4())


@pytest.mark.asyncio
async def test_admin_access_returns_200(db_session: AsyncSession):
    """admin 角色 + 有效 reason → 200"""
    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/archived-exception/edit",
            json={"reason": "紧急修正审计底稿", "password_confirm": "admin123"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["action"] == "edit"


@pytest.mark.asyncio
async def test_partner_access_returns_200(db_session: AsyncSession):
    """partner 角色 + 有效 reason → 200"""
    async with _make_client(db_session, PARTNER_USER) as client:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/archived-exception/review",
            json={"reason": "合伙人复核需要修改", "password_confirm": "pass"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_qc_access_returns_200(db_session: AsyncSession):
    """qc 角色 + 有效 reason → 200"""
    async with _make_client(db_session, QC_USER) as client:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/archived-exception/inspect",
            json={"reason": "质控检查发现问题需修正", "password_confirm": "pass"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# ---------------------------------------------------------------------------
# Tests: 403 forbidden
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auditor_access_returns_403(db_session: AsyncSession):
    """auditor 角色 → 403"""
    async with _make_client(db_session, AUDITOR_USER) as client:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/archived-exception/edit",
            json={"reason": "想修改底稿", "password_confirm": "pass"},
        )
    assert resp.status_code == 403
    assert "权限不足" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_manager_access_returns_403(db_session: AsyncSession):
    """manager 角色 → 403"""
    async with _make_client(db_session, MANAGER_USER) as client:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/archived-exception/edit",
            json={"reason": "经理想修改", "password_confirm": "pass"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: 422 validation error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_reason_returns_422(db_session: AsyncSession):
    """空 reason → 422"""
    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/archived-exception/edit",
            json={"reason": "", "password_confirm": "admin123"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_whitespace_reason_returns_422(db_session: AsyncSession):
    """纯空格 reason → 422"""
    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/archived-exception/edit",
            json={"reason": "   ", "password_confirm": "admin123"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: audit_log 写入验证
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_entry_created(db_session: AsyncSession):
    """成功调用后 audit_log 写入 event_type=archived_exception_access"""
    pid = str(uuid.uuid4())
    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{pid}/archived-exception/edit",
            json={"reason": "审计日志测试", "password_confirm": "admin123"},
        )
    assert resp.status_code == 200

    # 查询 audit_log_entries 表
    result = await db_session.execute(
        select(AuditLogEntry).where(
            AuditLogEntry.action_type == "archived_exception_access"
        )
    )
    entry = result.scalar_one_or_none()
    assert entry is not None
    assert entry.object_type == "project"
    assert entry.user_id == ADMIN_USER.id
    # payload 中包含 event_type 和 reason
    assert entry.payload["event_type"] == "archived_exception_access"
    assert entry.payload["reason"] == "审计日志测试"
    assert entry.payload["approver_id"] == str(ADMIN_USER.id)
    assert "archived-exception/edit" in entry.payload["endpoint"]
