"""HandoverService — 人员交接服务测试

验证 POST /api/staff/{staff_id}/handover 端点：
- 批量转移底稿/工单/项目委派
- 写 HandoverRecord + audit_log（哈希链）
- resignation 时标记 IndependenceDeclaration.status='superseded_by_handover'
- 发 Notification(type='handover_received') 给新负责人

Validates: Refinement Round 2 需求 10
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Notification, Project
from app.models.handover_models import HandoverRecord
from app.models.independence_models import IndependenceDeclaration
from app.models.phase15_models import IssueTicket
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.routers.staff import router as staff_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fake User
# ---------------------------------------------------------------------------


class _FakeUser:
    """轻量级用户替身"""

    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.manager):
        self.id = uid
        self.username = "manager_test"
        self.email = "manager@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


# ---------------------------------------------------------------------------
# Test IDs
# ---------------------------------------------------------------------------

MANAGER_USER_ID = uuid.uuid4()
FROM_STAFF_ID = uuid.uuid4()
TO_STAFF_ID = uuid.uuid4()
PROJECT_A_ID = uuid.uuid4()
PROJECT_B_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每测试独立内存库。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """种子数据：from_staff 有底稿/工单/委派，to_staff 是接收人。"""
    import sqlalchemy as sa

    # 项目
    project_a = Project(
        id=PROJECT_A_ID, name="项目 Alpha", client_name="客户 A",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        manager_id=MANAGER_USER_ID, created_by=MANAGER_USER_ID,
    )
    project_b = Project(
        id=PROJECT_B_ID, name="项目 Beta", client_name="客户 B",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        manager_id=MANAGER_USER_ID, created_by=MANAGER_USER_ID,
    )
    db_session.add_all([project_a, project_b])

    # Staff members
    from_staff = StaffMember(
        id=FROM_STAFF_ID, name="离职员工", user_id=FROM_STAFF_ID,
    )
    to_staff = StaffMember(
        id=TO_STAFF_ID, name="接收员工", user_id=TO_STAFF_ID,
    )
    db_session.add_all([from_staff, to_staff])

    # WpIndex (needed for WorkingPaper FK) - one per working paper
    wp_index_ids_a = [uuid.uuid4() for _ in range(3)]
    for i, wpi_id in enumerate(wp_index_ids_a):
        wp_index = WpIndex(
            id=wpi_id,
            project_id=PROJECT_A_ID,
            wp_code=f"D1-{i+1}",
            wp_name=f"测试底稿{i+1}",
            audit_cycle="D",
            status=WpStatus.not_started,
        )
        db_session.add(wp_index)

    wp_index_id_b = uuid.uuid4()
    wp_index_b = WpIndex(
        id=wp_index_id_b,
        project_id=PROJECT_B_ID,
        wp_code="D1-1",
        wp_name="测试底稿B",
        audit_cycle="D",
        status=WpStatus.not_started,
    )
    db_session.add(wp_index_b)

    # WorkingPapers assigned to from_staff
    for i in range(3):
        wp = WorkingPaper(
            id=uuid.uuid4(),
            project_id=PROJECT_A_ID,
            wp_index_id=wp_index_ids_a[i],
            file_path=f"/test/wp_{i}.xlsx",
            source_type=WpSourceType.template,
            status=WpFileStatus.draft,
            assigned_to=FROM_STAFF_ID,
            reviewer=None if i < 2 else FROM_STAFF_ID,
        )
        db_session.add(wp)

    # WorkingPaper in project B (assigned to from_staff)
    wp_b = WorkingPaper(
        id=uuid.uuid4(),
        project_id=PROJECT_B_ID,
        wp_index_id=wp_index_id_b,
        file_path="/test/wp_b.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        assigned_to=FROM_STAFF_ID,
    )
    db_session.add(wp_b)

    # IssueTickets owned by from_staff
    for i in range(2):
        ticket = IssueTicket(
            id=uuid.uuid4(),
            project_id=PROJECT_A_ID,
            source="L2",
            severity="major",
            category="data_mismatch",
            title=f"问题 {i}",
            owner_id=FROM_STAFF_ID,
            status="open",
            trace_id=str(uuid.uuid4()),
        )
        db_session.add(ticket)

    # Closed ticket (should NOT be transferred)
    closed_ticket = IssueTicket(
        id=uuid.uuid4(),
        project_id=PROJECT_A_ID,
        source="L2",
        severity="minor",
        category="evidence_missing",
        title="已关闭问题",
        owner_id=FROM_STAFF_ID,
        status="closed",
        trace_id=str(uuid.uuid4()),
    )
    db_session.add(closed_ticket)

    # ProjectAssignment for from_staff
    assign_a = ProjectAssignment(
        id=uuid.uuid4(),
        project_id=PROJECT_A_ID,
        staff_id=FROM_STAFF_ID,
        role="auditor",
    )
    assign_b = ProjectAssignment(
        id=uuid.uuid4(),
        project_id=PROJECT_B_ID,
        staff_id=FROM_STAFF_ID,
        role="senior_auditor",
    )
    db_session.add_all([assign_a, assign_b])

    # IndependenceDeclaration for from_staff (draft status)
    decl = IndependenceDeclaration(
        id=uuid.uuid4(),
        project_id=PROJECT_A_ID,
        declarant_id=FROM_STAFF_ID,
        declaration_year=2026,
        status="draft",
    )
    db_session.add(decl)

    await db_session.commit()
    return db_session


@pytest_asyncio.fixture
async def client(seeded_db: AsyncSession):
    """HTTP 测试客户端（admin 角色，绕过权限限制）。"""
    app = FastAPI()
    app.include_router(staff_router)

    # 使用 admin 角色避免 Batch 1 P0.2 的权限限制影响既有 scope='all' 测试
    fake_user = _FakeUser(MANAGER_USER_ID, role=UserRole.admin)

    async def _override_db():
        yield seeded_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.handover_service.audit_logger.log_action", new_callable=AsyncMock)
async def test_handover_all_scope(mock_log_action, client: AsyncClient, seeded_db: AsyncSession):
    """scope='all' 时转移所有项目的底稿/工单/委派。"""
    import sqlalchemy as sa

    resp = await client.post(
        f"/api/staff/{FROM_STAFF_ID}/handover",
        json={
            "scope": "all",
            "target_staff_id": str(TO_STAFF_ID),
            "reason_code": "rotation",
            "reason_detail": "岗位轮换",
            "effective_date": "2026-05-10",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # 3 assigned_to + 1 reviewer + 1 project_b = 5 workpapers
    assert data["workpapers_moved"] == 5
    # 2 open tickets (closed one not transferred)
    assert data["issues_moved"] == 2
    # 2 assignments (project A + B)
    assert data["assignments_moved"] == 2
    # Not resignation, so no independence superseded
    assert data["independence_superseded"] == 0
    assert data["handover_record_id"]

    # Verify audit_logger was called
    mock_log_action.assert_called_once()
    call_kwargs = mock_log_action.call_args[1]
    assert call_kwargs["action"] == "staff_handover"
    assert call_kwargs["object_type"] == "handover_record"

    # Verify HandoverRecord was created
    result = await seeded_db.execute(sa.select(HandoverRecord))
    records = result.scalars().all()
    assert len(records) == 1
    assert records[0].from_staff_id == FROM_STAFF_ID
    assert records[0].to_staff_id == TO_STAFF_ID
    assert records[0].scope == "all"

    # Verify notification was sent
    result = await seeded_db.execute(
        sa.select(Notification).where(
            Notification.recipient_id == TO_STAFF_ID,
            Notification.message_type == "handover_received",
        )
    )
    notif = result.scalar_one_or_none()
    assert notif is not None
    assert "转交给您" in notif.content


@pytest.mark.asyncio
@patch("app.services.handover_service.audit_logger.log_action", new_callable=AsyncMock)
async def test_handover_by_project(mock_log_action, client: AsyncClient, seeded_db: AsyncSession):
    """scope='by_project' 时只转移指定项目的工作。"""
    resp = await client.post(
        f"/api/staff/{FROM_STAFF_ID}/handover",
        json={
            "scope": "by_project",
            "project_ids": [str(PROJECT_A_ID)],
            "target_staff_id": str(TO_STAFF_ID),
            "reason_code": "long_leave",
            "reason_detail": "产假",
            "effective_date": "2026-06-01",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Only project A: 3 assigned_to + 1 reviewer = 4 workpapers
    assert data["workpapers_moved"] == 4
    # 2 open tickets in project A
    assert data["issues_moved"] == 2
    # 1 assignment in project A
    assert data["assignments_moved"] == 1
    assert data["independence_superseded"] == 0


@pytest.mark.asyncio
@patch("app.services.handover_service.audit_logger.log_action", new_callable=AsyncMock)
async def test_handover_resignation_supersedes_independence(
    mock_log_action, client: AsyncClient, seeded_db: AsyncSession
):
    """resignation 时标记独立性声明为 superseded_by_handover。"""
    import sqlalchemy as sa

    resp = await client.post(
        f"/api/staff/{FROM_STAFF_ID}/handover",
        json={
            "scope": "all",
            "target_staff_id": str(TO_STAFF_ID),
            "reason_code": "resignation",
            "reason_detail": "离职",
            "effective_date": "2026-05-15",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["independence_superseded"] == 1

    # Verify the declaration status was updated
    result = await seeded_db.execute(
        sa.select(IndependenceDeclaration).where(
            IndependenceDeclaration.declarant_id == FROM_STAFF_ID
        )
    )
    decl = result.scalar_one()
    assert decl.status == "superseded_by_handover"


@pytest.mark.asyncio
async def test_handover_same_person_rejected(client: AsyncClient):
    """交接人和接收人不能是同一人。"""
    resp = await client.post(
        f"/api/staff/{FROM_STAFF_ID}/handover",
        json={
            "scope": "all",
            "target_staff_id": str(FROM_STAFF_ID),
            "reason_code": "rotation",
            "effective_date": "2026-05-10",
        },
    )
    assert resp.status_code == 400
    assert "同一人" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_handover_preview(client: AsyncClient, seeded_db: AsyncSession):
    """预览交接影响数据量。"""
    resp = await client.get(
        f"/api/staff/{FROM_STAFF_ID}/handover/preview",
        params={"scope": "all"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # 3 assigned + 1 reviewer + 1 project_b = 5 (but count uses OR, so unique WPs)
    # Actually: 3 WPs assigned in A + 1 WP as reviewer in A + 1 WP in B
    # The query uses OR(assigned_to, reviewer), so WP with both assigned_to AND reviewer
    # counts once. WP index 2 (i=2) has both assigned_to=FROM and reviewer=FROM
    # So unique WPs: wp_0(assigned), wp_1(assigned), wp_2(assigned+reviewer), wp_b(assigned) = 4
    assert data["workpapers"] == 4
    assert data["issues"] == 2
    assert data["assignments"] == 2


@pytest.mark.asyncio
async def test_handover_by_project_missing_ids(client: AsyncClient):
    """scope='by_project' 但未提供 project_ids 应报错。"""
    resp = await client.post(
        f"/api/staff/{FROM_STAFF_ID}/handover",
        json={
            "scope": "by_project",
            "target_staff_id": str(TO_STAFF_ID),
            "reason_code": "other",
            "effective_date": "2026-05-10",
        },
    )
    assert resp.status_code == 400



# ===========================================================================
# Batch 1 P0.2: 权限守卫测试
# ===========================================================================


def _make_permission_client(seeded_db: AsyncSession, role: UserRole):
    """构造特定角色的测试客户端。"""
    app = FastAPI()
    app.include_router(staff_router)

    fake_user = _FakeUser(MANAGER_USER_ID, role=role)

    async def _override_db():
        yield seeded_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: fake_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_handover_auditor_blocked(seeded_db: AsyncSession):
    """auditor 角色访问 handover 端点应返回 403。"""
    async with _make_permission_client(seeded_db, UserRole.auditor) as c:
        resp = await c.post(
            f"/api/staff/{FROM_STAFF_ID}/handover",
            json={
                "scope": "all",
                "target_staff_id": str(TO_STAFF_ID),
                "reason_code": "rotation",
                "effective_date": "2026-05-10",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_handover_manager_cannot_use_all_scope(seeded_db: AsyncSession):
    """manager 角色不能使用 scope='all'（必须 by_project）。"""
    async with _make_permission_client(seeded_db, UserRole.manager) as c:
        resp = await c.post(
            f"/api/staff/{FROM_STAFF_ID}/handover",
            json={
                "scope": "all",
                "target_staff_id": str(TO_STAFF_ID),
                "reason_code": "rotation",
                "effective_date": "2026-05-10",
            },
        )
    assert resp.status_code == 403
    assert "by_project" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_handover_preview_auditor_blocked(seeded_db: AsyncSession):
    """auditor 角色访问 handover 预览应返回 403。"""
    async with _make_permission_client(seeded_db, UserRole.auditor) as c:
        resp = await c.get(
            f"/api/staff/{FROM_STAFF_ID}/handover/preview",
            params={"scope": "all"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_handover_preview_manager_cannot_use_all_scope(seeded_db: AsyncSession):
    """manager 预览不能使用 scope='all'（避免跨项目信息泄露）。"""
    async with _make_permission_client(seeded_db, UserRole.manager) as c:
        resp = await c.get(
            f"/api/staff/{FROM_STAFF_ID}/handover/preview",
            params={"scope": "all"},
        )
    assert resp.status_code == 403
