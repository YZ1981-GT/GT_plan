"""解除归档端点测试 — V3 收官 Req 1.3

Validates: Requirements 1.7
- POST /api/projects/{pid}/unarchive with valid request → 200 + status changed
- Non-admin/partner role (qc/auditor/manager) → 403
- Wrong project_code → 400（二次确认失败）
- Project not archived → 400（already active）
- Empty reason → 422
- audit_log entry created with event_type='archive_unarchive'
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
from app.models.base import Base, ProjectStatus, UserRole

# SQLite 兼容 JSONB + ARRAY
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# 仅注册测试所需的模型
import app.models.core  # noqa: F401
import app.models.audit_log_models  # noqa: F401

from app.models.audit_log_models import AuditLogEntry
from app.models.core import Project
from app.routers.archived_exception import unarchive_router

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
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
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


async def _create_project(
    db: AsyncSession,
    name: str = "YG2101-测试项目",
    status: ProjectStatus = ProjectStatus.archived,
) -> Project:
    """创建测试项目。"""
    project = Project(
        id=uuid.uuid4(),
        name=name,
        client_name="测试客户",
        status=status,
    )
    db.add(project)
    await db.flush()
    return project


def _make_client(db_session: AsyncSession, user: _FakeUser):
    """构造测试客户端，注入指定用户。"""
    app = FastAPI()
    app.include_router(unarchive_router)

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


@pytest.mark.asyncio
async def test_admin_unarchive_returns_200(db_session: AsyncSession):
    """admin 角色 + 正确 project_code + archived 项目 → 200 + 状态变更"""
    project = await _create_project(db_session)

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "项目需要补充审计程序",
                "password_confirm": "admin123",
                "project_code": project.name,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "项目已成功解除归档"
    assert data["new_status"] == "execution"

    # 验证数据库中项目状态已变更
    await db_session.refresh(project)
    assert project.status == ProjectStatus.execution


@pytest.mark.asyncio
async def test_partner_unarchive_returns_200(db_session: AsyncSession):
    """partner 角色 + 正确 project_code + archived 项目 → 200"""
    project = await _create_project(db_session)

    async with _make_client(db_session, PARTNER_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "合伙人要求重新审阅",
                "password_confirm": "pass",
                "project_code": project.name,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["new_status"] == "execution"


# ---------------------------------------------------------------------------
# Tests: 403 forbidden (non-admin/partner roles)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qc_unarchive_returns_403(db_session: AsyncSession):
    """qc 角色 → 403（解除归档比例外通道更严格）"""
    project = await _create_project(db_session)

    async with _make_client(db_session, QC_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "质控想解除归档",
                "password_confirm": "pass",
                "project_code": project.name,
            },
        )
    assert resp.status_code == 403
    assert "权限不足" in resp.json()["detail"]
    assert "管理员/合伙人" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auditor_unarchive_returns_403(db_session: AsyncSession):
    """auditor 角色 → 403"""
    project = await _create_project(db_session)

    async with _make_client(db_session, AUDITOR_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "审计员想解除归档",
                "password_confirm": "pass",
                "project_code": project.name,
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_manager_unarchive_returns_403(db_session: AsyncSession):
    """manager 角色 → 403"""
    project = await _create_project(db_session)

    async with _make_client(db_session, MANAGER_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "经理想解除归档",
                "password_confirm": "pass",
                "project_code": project.name,
            },
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: 400 wrong project_code（二次确认失败）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_project_code_returns_400(db_session: AsyncSession):
    """project_code 不匹配 → 400（二次确认失败）"""
    project = await _create_project(db_session, name="YG2101-正确名称")

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "需要解除归档",
                "password_confirm": "admin123",
                "project_code": "错误的项目名称",
            },
        )
    assert resp.status_code == 400
    assert "项目编码校验失败" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: 400 project not archived（已处于活跃状态）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_not_archived_returns_400(db_session: AsyncSession):
    """项目非 archived 状态 → 400"""
    project = await _create_project(
        db_session, name="活跃项目", status=ProjectStatus.execution
    )

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "想解除归档",
                "password_confirm": "admin123",
                "project_code": "活跃项目",
            },
        )
    assert resp.status_code == 400
    assert "未处于归档状态" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: 422 validation error (empty reason)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_reason_returns_422(db_session: AsyncSession):
    """空 reason → 422"""
    project = await _create_project(db_session)

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "",
                "password_confirm": "admin123",
                "project_code": project.name,
            },
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: audit_log 写入验证
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_entry_created(db_session: AsyncSession):
    """成功解除归档后 audit_log 写入 event_type='archive_unarchive'"""
    project = await _create_project(db_session, name="审计日志测试项目")

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/projects/{project.id}/unarchive",
            json={
                "reason": "审计日志验证",
                "password_confirm": "admin123",
                "project_code": "审计日志测试项目",
            },
        )
    assert resp.status_code == 200

    # 查询 audit_log_entries 表
    result = await db_session.execute(
        select(AuditLogEntry).where(
            AuditLogEntry.action_type == "archive_unarchive"
        )
    )
    entry = result.scalar_one_or_none()
    assert entry is not None
    assert entry.object_type == "project"
    assert entry.user_id == ADMIN_USER.id
    # payload 中包含 event_type 和 reason
    assert entry.payload["event_type"] == "archive_unarchive"
    assert entry.payload["reason"] == "审计日志验证"
    assert entry.payload["previous_status"] == "archived"
