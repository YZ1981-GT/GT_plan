"""R1 Bug Fix 7 测试：/api/my/pending-independence 批量端点

覆盖：
1. 返回当前用户被分配核心角色但未提交声明的项目
2. 排除已归档项目
3. 无核心角色分配时返回空列表
4. submitted/approved 状态的声明算已完成

Validates: Requirements 10 (refinement-round1-review-closure) + R1 Bug Fix 7
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.independence_models  # noqa: F401
import app.models.extension_models  # noqa: F401
import app.models.staff_models  # noqa: F401
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole
from app.models.core import Project
from app.models.independence_models import IndependenceDeclaration
from app.models.staff_models import ProjectAssignment
from app.routers.independence import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_partner"
        self.email = "partner@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()
CURRENT_YEAR = datetime.now(timezone.utc).year


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return TEST_USER

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_project(
    db: AsyncSession,
    name: str = "P",
    archived: bool = False,
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        client_name=f"{name} 客户",
    )
    if archived:
        project.archived_at = datetime.now(timezone.utc)
    db.add(project)
    await db.flush()
    return project


async def _assign_core_role(
    db: AsyncSession,
    project_id,
    staff_id,
    role: str = "signing_partner",
):
    assignment = ProjectAssignment(
        id=uuid.uuid4(),
        project_id=project_id,
        staff_id=staff_id,
        role=role,
        is_deleted=False,
    )
    db.add(assignment)
    await db.flush()


async def _create_declaration(
    db: AsyncSession,
    project_id,
    declarant_id,
    status: str = "submitted",
    year: int = CURRENT_YEAR,
):
    decl = IndependenceDeclaration(
        id=uuid.uuid4(),
        project_id=project_id,
        declarant_id=declarant_id,
        declaration_year=year,
        status=status,
    )
    db.add(decl)
    await db.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_pending_projects_only(
    db_session: AsyncSession, client: AsyncClient
):
    """用户被分配 3 个项目（2 未提交，1 已 submitted）→ 返回 2 个 pending。"""
    # 3 个项目，用户都是 signing_partner
    p1 = await _create_project(db_session, name="Pending1")
    p2 = await _create_project(db_session, name="Pending2")
    p3 = await _create_project(db_session, name="Submitted")
    for p in (p1, p2, p3):
        await _assign_core_role(db_session, p.id, TEST_USER.id)
    # p3 已 submitted
    await _create_declaration(db_session, p3.id, TEST_USER.id, status="submitted")
    await db_session.commit()

    resp = await client.get("/api/my/pending-independence")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    returned_names = {p["name"] for p in body["projects"]}
    assert returned_names == {"Pending1", "Pending2"}


@pytest.mark.asyncio
async def test_excludes_archived_projects(
    db_session: AsyncSession, client: AsyncClient
):
    """archived_at 非空的项目不返回。"""
    p_active = await _create_project(db_session, name="Active")
    p_archived = await _create_project(db_session, name="Archived", archived=True)
    for p in (p_active, p_archived):
        await _assign_core_role(db_session, p.id, TEST_USER.id)
    await db_session.commit()

    resp = await client.get("/api/my/pending-independence")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["projects"][0]["name"] == "Active"


@pytest.mark.asyncio
async def test_empty_when_no_assignments(
    db_session: AsyncSession, client: AsyncClient
):
    """用户无核心角色分配 → 返回空列表。"""
    # 创建项目但不分配
    await _create_project(db_session, name="NoAssign")
    await db_session.commit()

    resp = await client.get("/api/my/pending-independence")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["projects"] == []


@pytest.mark.asyncio
async def test_excludes_approved_declarations(
    db_session: AsyncSession, client: AsyncClient
):
    """status='approved' 也算已完成 → 不返回。"""
    p = await _create_project(db_session, name="Approved")
    await _assign_core_role(db_session, p.id, TEST_USER.id)
    await _create_declaration(db_session, p.id, TEST_USER.id, status="approved")
    await db_session.commit()

    resp = await client.get("/api/my/pending-independence")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# Batch 2-10: limit parameter test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limit_parameter_truncates_results(
    db_session: AsyncSession, client: AsyncClient
):
    """limit 参数截断返回列表，has_more 反映是否有更多。"""
    # 创建 5 个 pending 项目
    for i in range(5):
        p = await _create_project(db_session, name=f"P{i}")
        await _assign_core_role(db_session, p.id, TEST_USER.id)
    await db_session.commit()

    # limit=2 → 返回 2 个，has_more=true
    resp = await client.get("/api/my/pending-independence?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["projects"]) == 2
    assert body.get("has_more") is True

    # limit=50（默认）→ 全返回，has_more=false
    resp = await client.get("/api/my/pending-independence")
    body = resp.json()
    assert len(body["projects"]) == 5
    assert body.get("has_more") is False
