"""Batch 1 P0.3/P0.4 权限守卫端点测试

覆盖:
- P0.3: /api/workpapers/batch-assign-enhanced 的权限守卫
    - wp_ids 跨项目 → 400
    - 无项目 manager/signing_partner 角色 → 403
- P0.4: /api/workhours/batch-approve 的项目级权限守卫
    - manager 跨项目审批 → 403
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.routers.batch_assign_enhanced import router as bae_router
from app.routers.workhour_approve import router as wa_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.manager):
        self.id = uid
        self.username = "test_user"
        self.email = "test@x.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


MANAGER_USER_ID = uuid.uuid4()
MANAGER_STAFF_ID = uuid.uuid4()
AUDITOR_STAFF_ID = uuid.uuid4()
PROJECT_A_ID = uuid.uuid4()
PROJECT_B_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """种子：Project A 由 MANAGER 管；Project B 不属于 MANAGER。"""
    pa = Project(
        id=PROJECT_A_ID, name="A", client_name="客A",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=MANAGER_USER_ID,
    )
    pb = Project(
        id=PROJECT_B_ID, name="B", client_name="客B",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=uuid.uuid4(),
    )
    db_session.add_all([pa, pb])
    await db_session.flush()

    mgr_staff = StaffMember(
        id=MANAGER_STAFF_ID, user_id=MANAGER_USER_ID,
        name="经理", title="经理",
    )
    aud_staff = StaffMember(
        id=AUDITOR_STAFF_ID, user_id=uuid.uuid4(),
        name="审计员", title="审计员",
    )
    db_session.add_all([mgr_staff, aud_staff])
    await db_session.flush()

    # MANAGER 只负责 A 项目
    db_session.add(ProjectAssignment(
        id=uuid.uuid4(), project_id=PROJECT_A_ID,
        staff_id=MANAGER_STAFF_ID, role="manager",
    ))
    await db_session.flush()

    # A/B 项目各 1 张底稿
    idx_a = WpIndex(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-1",
        wp_name="A1", audit_cycle="D", status=WpStatus.in_progress,
    )
    idx_b = WpIndex(
        id=uuid.uuid4(), project_id=PROJECT_B_ID, wp_code="B-1",
        wp_name="B1", audit_cycle="D", status=WpStatus.in_progress,
    )
    db_session.add_all([idx_a, idx_b])
    await db_session.flush()

    wp_a = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_index_id=idx_a.id,
        file_path="/tmp/a.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        file_version=1,
    )
    wp_b = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_B_ID, wp_index_id=idx_b.id,
        file_path="/tmp/b.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        file_version=1,
    )
    db_session.add_all([wp_a, wp_b])
    await db_session.flush()

    # Project B 一条 confirmed 工时（需要有 staff_id）
    wh_b = WorkHour(
        id=uuid.uuid4(), staff_id=AUDITOR_STAFF_ID, project_id=PROJECT_B_ID,
        work_date=date.today(), hours=Decimal("4"), status="confirmed",
    )
    db_session.add(wh_b)
    await db_session.commit()

    return {"wp_a_id": wp_a.id, "wp_b_id": wp_b.id, "wh_b_id": wh_b.id}


def _client(db_session: AsyncSession, router, user_id=MANAGER_USER_ID, role=UserRole.manager):
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db_session

    async def _user():
        return _FakeUser(user_id, role=role)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ─── P0.3: batch-assign-enhanced ─────────────────────────────────────


@pytest.mark.asyncio
async def test_bae_rejects_cross_project_wp_ids(db_session, seeded_db):
    """跨项目的 wp_ids 返回 400。"""
    async with _client(db_session, bae_router, role=UserRole.admin) as c:
        resp = await c.post(
            "/api/workpapers/batch-assign-enhanced",
            json={
                "wp_ids": [str(seeded_db["wp_a_id"]), str(seeded_db["wp_b_id"])],
                "strategy": "manual",
                "candidates": [str(uuid.uuid4())],
            },
        )
    assert resp.status_code == 400
    assert "同一项目" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_bae_rejects_unauthorized_manager(db_session, seeded_db):
    """manager 对未参与的项目返回 403。"""
    stranger_id = uuid.uuid4()
    async with _client(db_session, bae_router, user_id=stranger_id) as c:
        resp = await c.post(
            "/api/workpapers/batch-assign-enhanced",
            json={
                "wp_ids": [str(seeded_db["wp_a_id"])],
                "strategy": "manual",
                "candidates": [str(uuid.uuid4())],
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bae_admin_can_assign_any_project(db_session, seeded_db):
    """admin 角色可对任何项目批量委派（通过权限检查，即使后续失败）。"""
    async with _client(db_session, bae_router, role=UserRole.admin) as c:
        resp = await c.post(
            "/api/workpapers/batch-assign-enhanced",
            json={
                "wp_ids": [str(seeded_db["wp_b_id"])],
                "strategy": "manual",
                "candidates": [str(AUDITOR_STAFF_ID)],
            },
        )
    # admin 通过权限校验，能到业务逻辑；不会因为权限返回 403
    assert resp.status_code != 403


# ─── P0.4: workhours/batch-approve 项目级权限 ───────────────────────


@pytest.mark.asyncio
async def test_batch_approve_manager_cannot_approve_other_project(db_session, seeded_db):
    """manager 跨项目审批返回 403。"""
    async with _client(db_session, wa_router) as c:
        resp = await c.post(
            "/api/workhours/batch-approve",
            json={
                "hour_ids": [str(seeded_db["wh_b_id"])],
                "action": "approve",
            },
        )
    assert resp.status_code == 403
    assert "管理范围" in resp.json()["detail"]
