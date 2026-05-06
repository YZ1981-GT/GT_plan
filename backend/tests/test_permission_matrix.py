"""权限矩阵测试 — Round 2 Batch 2 P2 测试覆盖

验证:
- auditor 不能调用 remind 端点（需要 project edit 权限）
- commitment PATCH 端点需要 project edit 权限

Validates: Refinement Round 2 复盘 P2 测试覆盖第 3 项
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.routers.pm_dashboard import router as pm_router
from app.routers.workpaper_remind import router as remind_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)


class _FakeUser:
    def __init__(self, uid, role=UserRole.auditor):
        self.id = uid
        self.username = "test_user"
        self.email = "test@x.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


MGR_USER_ID = uuid.uuid4()
AUD_USER_ID = uuid.uuid4()
MGR_STAFF_ID = uuid.uuid4()
AUD_STAFF_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    """一个项目，MGR 有 edit 权限，AUD 只有 auditor 角色。"""
    proj = Project(
        id=PROJECT_ID, name="权限测试项目", client_name="客户",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=MGR_USER_ID, wizard_state={},
    )
    db_session.add(proj)
    await db_session.flush()

    mgr = StaffMember(id=MGR_STAFF_ID, user_id=MGR_USER_ID, name="经理", title="经理")
    aud = StaffMember(id=AUD_STAFF_ID, user_id=AUD_USER_ID, name="审计员", title="审计员")
    db_session.add_all([mgr, aud])
    await db_session.flush()

    db_session.add_all([
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_ID,
                          staff_id=MGR_STAFF_ID, role="manager"),
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_ID,
                          staff_id=AUD_STAFF_ID, role="auditor"),
    ])
    await db_session.flush()

    # 底稿
    idx = WpIndex(id=uuid.uuid4(), project_id=PROJECT_ID, wp_code="T-001",
                  wp_name="测试底稿", audit_cycle="D循环", status=WpStatus.in_progress)
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_ID, wp_index_id=idx.id,
        file_path="/tmp/t.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        assigned_to=AUD_USER_ID, file_version=1,
    )
    db_session.add(wp)
    await db_session.commit()
    return {"wp_id": wp.id}


def _make_remind_client(db_session: AsyncSession, user_id: uuid.UUID, role: UserRole) -> AsyncClient:
    """构造 remind 端点测试客户端。

    require_project_access("edit") 对非 admin 用户会查 project_users 表。
    为简化测试，admin 角色跳过检查，非 admin 会被拒绝（因为没有 project_users 记录）。
    """
    app = FastAPI()
    app.include_router(remind_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(user_id, role=role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _make_commitment_client(db_session: AsyncSession, user_id: uuid.UUID, role: UserRole) -> AsyncClient:
    """构造 commitment PATCH 端点测试客户端。"""
    app = FastAPI()
    app.include_router(pm_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(user_id, role=role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestRemindPermission:
    """POST /api/projects/{project_id}/workpapers/{wp_id}/remind 权限测试。"""

    @pytest.mark.asyncio
    async def test_auditor_cannot_remind(self, db_session, seeded):
        """auditor 角色（非 admin）调用 remind 应返回 403。

        require_project_access("edit") 对非 admin 查 project_users 表，
        auditor 无 edit 权限记录 → 403。
        """
        wp_id = seeded["wp_id"]

        async with _make_remind_client(db_session, AUD_USER_ID, UserRole.auditor) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/workpapers/{wp_id}/remind",
                json={},
            )

        # 非 admin 且无 project_users edit 记录 → 403
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_remind(self, db_session, seeded):
        """admin 角色调用 remind 应通过权限检查。"""
        wp_id = seeded["wp_id"]

        # Mock Redis to avoid connection errors in remind service
        with patch("app.services.workpaper_remind_service.WorkpaperRemindService._get_remind_count",
                   new_callable=AsyncMock, return_value=0), \
             patch("app.services.workpaper_remind_service.WorkpaperRemindService._increment_remind_count",
                   new_callable=AsyncMock, return_value=1):
            async with _make_remind_client(db_session, MGR_USER_ID, UserRole.admin) as client:
                resp = await client.post(
                    f"/api/projects/{PROJECT_ID}/workpapers/{wp_id}/remind",
                    json={},
                )

        # admin 跳过 project_access 检查，应成功（200）
        assert resp.status_code == 200


class TestCommitmentPermission:
    """PATCH /api/projects/{project_id}/communications/{comm_id}/commitments/{commitment_id} 权限测试。"""

    @pytest.mark.asyncio
    async def test_auditor_cannot_complete_commitment(self, db_session, seeded):
        """auditor 角色调用 commitment PATCH 应返回 403。"""
        async with _make_commitment_client(db_session, AUD_USER_ID, UserRole.auditor) as client:
            resp = await client.patch(
                f"/api/projects/{PROJECT_ID}/communications/fake-comm/commitments/fake-id",
                json={"status": "done"},
            )

        # 非 admin 且无 project_users edit 记录 → 403
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_passes_permission_check(self, db_session, seeded):
        """admin 角色调用 commitment PATCH 应通过权限检查（可能 404 因为数据不存在）。"""
        async with _make_commitment_client(db_session, MGR_USER_ID, UserRole.admin) as client:
            resp = await client.patch(
                f"/api/projects/{PROJECT_ID}/communications/fake-comm/commitments/fake-id",
                json={"status": "done"},
            )

        # admin 通过权限检查，但数据不存在 → 404（不是 403）
        assert resp.status_code in (404, 422)  # 404 or validation error, not 403
