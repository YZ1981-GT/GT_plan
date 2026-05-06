"""ManagerDashboard — 项目经理看板聚合 API 测试

验证 GET /api/dashboard/manager/overview 端点：
- 返回项目卡片 + 跨项目待办 + 团队负载
- 权限守卫：role='manager' 或 project_assignment.role IN ('manager','signing_partner')
- Redis 缓存 5 分钟

Validates: Refinement Round 2 需求 1 验收标准 4
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
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
from app.routers.manager_dashboard import router as mgr_router

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
MANAGER_STAFF_ID = uuid.uuid4()
AUDITOR_STAFF_ID = uuid.uuid4()
PROJECT_A_ID = uuid.uuid4()
PROJECT_B_ID = uuid.uuid4()
PROJECT_C_ID = uuid.uuid4()  # 不属于该经理


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
    """种子数据：经理管理 2 个项目，第 3 个项目不属于该经理。"""
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
    project_c = Project(
        id=PROJECT_C_ID, name="项目 Gamma", client_name="客户 C",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=uuid.uuid4(),
    )
    db_session.add_all([project_a, project_b, project_c])
    await db_session.flush()

    # Staff members
    manager_staff = StaffMember(
        id=MANAGER_STAFF_ID, user_id=MANAGER_USER_ID,
        name="张经理", title="经理", department="审计一部",
    )
    auditor_staff = StaffMember(
        id=AUDITOR_STAFF_ID, user_id=uuid.uuid4(),
        name="李审计", title="审计员", department="审计一部",
    )
    db_session.add_all([manager_staff, auditor_staff])
    await db_session.flush()

    # Project assignments
    assign_a = ProjectAssignment(
        id=uuid.uuid4(), project_id=PROJECT_A_ID,
        staff_id=MANAGER_STAFF_ID, role="manager",
    )
    assign_b = ProjectAssignment(
        id=uuid.uuid4(), project_id=PROJECT_B_ID,
        staff_id=MANAGER_STAFF_ID, role="signing_partner",
    )
    assign_auditor_a = ProjectAssignment(
        id=uuid.uuid4(), project_id=PROJECT_A_ID,
        staff_id=AUDITOR_STAFF_ID, role="auditor",
    )
    db_session.add_all([assign_a, assign_b, assign_auditor_a])
    await db_session.flush()

    # WpIndex + WorkingPaper for project A
    idx_a1 = WpIndex(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-001",
        wp_name="底稿 A1", audit_cycle="D循环", status=WpStatus.in_progress,
    )
    idx_a2 = WpIndex(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-002",
        wp_name="底稿 A2", audit_cycle="D循环", status=WpStatus.in_progress,
    )
    idx_a3 = WpIndex(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-003",
        wp_name="底稿 A3", audit_cycle="F循环", status=WpStatus.not_started,
    )
    db_session.add_all([idx_a1, idx_a2, idx_a3])
    await db_session.flush()

    # wp_a1: 已通过
    wp_a1 = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_index_id=idx_a1.id,
        file_path="/tmp/a1.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.review_passed, review_status=WpReviewStatus.level1_passed,
        reviewer=MANAGER_USER_ID, file_version=1,
    )
    # wp_a2: 待复核（reviewer 是经理）
    wp_a2 = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_index_id=idx_a2.id,
        file_path="/tmp/a2.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.under_review, review_status=WpReviewStatus.pending_level1,
        reviewer=MANAGER_USER_ID, assigned_to=AUDITOR_STAFF_ID, file_version=1,
    )
    # wp_a3: 未分配
    wp_a3 = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_index_id=idx_a3.id,
        file_path="/tmp/a3.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        assigned_to=None, file_version=1,
    )
    db_session.add_all([wp_a1, wp_a2, wp_a3])
    await db_session.flush()

    # WpIndex + WorkingPaper for project B
    idx_b1 = WpIndex(
        id=uuid.uuid4(), project_id=PROJECT_B_ID, wp_code="B-001",
        wp_name="底稿 B1", audit_cycle="K循环", status=WpStatus.in_progress,
    )
    db_session.add(idx_b1)
    await db_session.flush()

    wp_b1 = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_B_ID, wp_index_id=idx_b1.id,
        file_path="/tmp/b1.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        file_version=1,
    )
    db_session.add(wp_b1)
    await db_session.flush()

    # Work hours: auditor 本周有工时
    today = date.today()
    wh1 = WorkHour(
        id=uuid.uuid4(), staff_id=AUDITOR_STAFF_ID, project_id=PROJECT_A_ID,
        work_date=today, hours=Decimal("8.0"), status="confirmed",
        description="编制底稿",
    )
    wh2 = WorkHour(
        id=uuid.uuid4(), staff_id=AUDITOR_STAFF_ID, project_id=PROJECT_A_ID,
        work_date=today - timedelta(days=1), hours=Decimal("7.5"), status="draft",
        description="编制底稿",
    )
    db_session.add_all([wh1, wh2])
    await db_session.commit()

    return {
        "project_a_id": PROJECT_A_ID,
        "project_b_id": PROJECT_B_ID,
        "project_c_id": PROJECT_C_ID,
    }


# ---------------------------------------------------------------------------
# Helper: build test client
# ---------------------------------------------------------------------------


def _make_client(db_session: AsyncSession, user_id: uuid.UUID, role: UserRole = UserRole.manager) -> AsyncClient:
    """构造测试 app，绕过 auth/redis 依赖。"""
    app = FastAPI()
    app.include_router(mgr_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(user_id, role=role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ===========================================================================
# Tests
# ===========================================================================


class TestManagerOverviewEndpoint:
    """GET /api/dashboard/manager/overview"""

    @pytest.mark.asyncio
    async def test_returns_projects_for_manager(self, db_session, seeded_db):
        """经理应看到自己管理的项目卡片。"""
        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/overview")
            assert resp.status_code == 200
            body = resp.json()

        assert "projects" in body
        assert "cross_todos" in body
        assert "team_load" in body

        # 应看到 2 个项目（A 和 B）
        project_names = {p["name"] for p in body["projects"]}
        assert "项目 Alpha" in project_names
        assert "项目 Beta" in project_names
        assert "项目 Gamma" not in project_names

    @pytest.mark.asyncio
    async def test_cross_todos_aggregation(self, db_session, seeded_db):
        """跨项目待办应正确聚合。"""
        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/overview")
            body = resp.json()

        cross_todos = body["cross_todos"]
        # pending_review: wp_a2 待复核（reviewer=MANAGER_USER_ID）
        assert cross_todos["pending_review"] == 1
        # pending_assign: wp_a1(assigned_to未设置) + wp_a3(assigned_to=None) + wp_b1(assigned_to未设置) = 3
        assert cross_todos["pending_assign"] == 3
        # pending_approve: wh1 status=confirmed
        assert cross_todos["pending_approve"] == 1

    @pytest.mark.asyncio
    async def test_team_load_includes_members(self, db_session, seeded_db):
        """团队负载应包含项目团队成员。"""
        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/overview")
            body = resp.json()

        team_load = body["team_load"]
        assert len(team_load) >= 1
        staff_names = {m["staff_name"] for m in team_load}
        assert "李审计" in staff_names or "张经理" in staff_names

    @pytest.mark.asyncio
    async def test_project_card_has_required_fields(self, db_session, seeded_db):
        """项目卡片应包含完成率、待复核、逾期、风险等级等字段。"""
        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/overview")
            body = resp.json()

        assert len(body["projects"]) > 0
        card = body["projects"][0]
        required_fields = [
            "id", "name", "client_name", "status",
            "completion_rate", "total_workpapers", "passed_workpapers",
            "pending_review", "overdue_count", "risk_level",
        ]
        for field in required_fields:
            assert field in card, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_admin_sees_all_projects(self, db_session, seeded_db):
        """admin 角色应看到所有项目。"""
        async with _make_client(db_session, MANAGER_USER_ID, UserRole.admin) as client:
            resp = await client.get("/api/dashboard/manager/overview")
            body = resp.json()

        project_names = {p["name"] for p in body["projects"]}
        assert "项目 Gamma" in project_names

    @pytest.mark.asyncio
    async def test_empty_result_for_unrelated_user(self, db_session, seeded_db):
        """无关用户（无项目关联）应返回空数据。"""
        stranger_id = uuid.uuid4()
        # 需要创建一个 staff member for this user
        stranger_staff = StaffMember(
            id=uuid.uuid4(), user_id=stranger_id,
            name="路人甲", title="审计员", department="审计二部",
        )
        db_session.add(stranger_staff)
        await db_session.commit()

        async with _make_client(db_session, stranger_id, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/overview")
            body = resp.json()

        assert body["projects"] == []
        assert body["cross_todos"]["pending_review"] == 0


class TestManagerOverviewCache:
    """Redis 缓存测试"""

    @pytest.mark.asyncio
    async def test_cache_is_used_on_second_call(self, db_session, seeded_db):
        """第二次调用应命中缓存（mock Redis）。"""
        with patch("app.services.manager_dashboard_service.ManagerDashboardService._get_cache") as mock_get, \
             patch("app.services.manager_dashboard_service.ManagerDashboardService._set_cache") as mock_set:
            mock_get.return_value = None  # 第一次 miss

            async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
                resp = await client.get("/api/dashboard/manager/overview")
                assert resp.status_code == 200

            # 验证 set_cache 被调用
            assert mock_set.called

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self, db_session, seeded_db):
        """缓存命中时直接返回缓存数据。"""
        cached_data = {
            "projects": [{"id": "cached", "name": "Cached Project"}],
            "cross_todos": {"pending_review": 99, "pending_assign": 0, "pending_approve": 0},
            "team_load": [],
        }

        with patch("app.services.manager_dashboard_service.ManagerDashboardService._get_cache") as mock_get:
            mock_get.return_value = cached_data

            async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
                resp = await client.get("/api/dashboard/manager/overview")
                body = resp.json()

            assert body["cross_todos"]["pending_review"] == 99
            assert body["projects"][0]["name"] == "Cached Project"


class TestManagerOverviewPermission:
    """权限守卫测试"""

    @pytest.mark.asyncio
    async def test_auditor_without_assignment_gets_403(self, db_session, seeded_db):
        """auditor 角色且无 manager/signing_partner 委派应被拒绝。"""
        stranger_id = uuid.uuid4()
        # 创建一个 staff 但没有 manager/signing_partner 角色的 assignment
        stranger_staff = StaffMember(
            id=uuid.uuid4(), user_id=stranger_id,
            name="普通审计", title="审计员", department="审计三部",
        )
        db_session.add(stranger_staff)
        await db_session.commit()

        async with _make_client(db_session, stranger_id, UserRole.auditor) as client:
            resp = await client.get("/api/dashboard/manager/overview")

        assert resp.status_code == 403


# ===========================================================================
# Tests: Assignment Status (Task 7)
# ===========================================================================

from app.models.core import Notification


class TestAssignmentStatusEndpoint:
    """GET /api/dashboard/manager/assignment-status

    验证委派已读回执 API：
    - 返回近 N 天委派记录 + 通知已读状态
    - 48 小时未读标记 is_overdue_unread
    - 权限守卫

    Validates: Refinement Round 2 需求 8 验收标准 2, 3
    """

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_assignments(self, db_session, seeded_db):
        """无委派通知时返回空列表。"""
        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/assignment-status?days=7")
            assert resp.status_code == 200
            body = resp.json()

        assert body == []

    @pytest.mark.asyncio
    async def test_returns_assignment_with_read_status(self, db_session, seeded_db):
        """有委派通知时返回正确的已读状态。"""
        # 创建一条 ASSIGNMENT_CREATED 通知（模拟委派）
        auditor_user_id = (
            await db_session.execute(
                __import__("sqlalchemy").select(StaffMember.user_id).where(
                    StaffMember.id == AUDITOR_STAFF_ID
                )
            )
        ).scalar_one()

        notif = Notification(
            id=uuid.uuid4(),
            recipient_id=auditor_user_id,
            message_type="assignment_created",
            title="新委派通知",
            content="项目 Alpha 底稿 A-002 已委派给您",
            related_object_type="project",
            related_object_id=PROJECT_A_ID,
            is_read=True,
            read_at=datetime.now() - timedelta(hours=1),
        )
        db_session.add(notif)
        await db_session.commit()

        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/assignment-status?days=7")
            assert resp.status_code == 200
            body = resp.json()

        assert len(body) >= 1
        # 找到对应记录
        record = body[0]
        assert record["assignee_name"] == "李审计"
        assert record["notification_read_at"] is not None
        assert record["is_overdue_unread"] is False

    @pytest.mark.asyncio
    async def test_overdue_unread_flag_after_48h(self, db_session, seeded_db):
        """48 小时未读应标记 is_overdue_unread=True。"""
        auditor_user_id = (
            await db_session.execute(
                __import__("sqlalchemy").select(StaffMember.user_id).where(
                    StaffMember.id == AUDITOR_STAFF_ID
                )
            )
        ).scalar_one()

        # 创建一条 3 天前的未读通知
        notif = Notification(
            id=uuid.uuid4(),
            recipient_id=auditor_user_id,
            message_type="assignment_created",
            title="新委派通知",
            content="项目 Alpha 底稿已委派给您",
            related_object_type="project",
            related_object_id=PROJECT_A_ID,
            is_read=False,
            read_at=None,
            created_at=datetime.now() - timedelta(hours=72),
        )
        db_session.add(notif)
        await db_session.commit()

        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/assignment-status?days=7")
            assert resp.status_code == 200
            body = resp.json()

        assert len(body) >= 1
        # 找到未读记录
        overdue_records = [r for r in body if r["is_overdue_unread"]]
        assert len(overdue_records) >= 1
        assert overdue_records[0]["notification_read_at"] is None

    @pytest.mark.asyncio
    async def test_recent_unread_not_overdue(self, db_session, seeded_db):
        """24 小时内未读不应标记为 overdue。"""
        auditor_user_id = (
            await db_session.execute(
                __import__("sqlalchemy").select(StaffMember.user_id).where(
                    StaffMember.id == AUDITOR_STAFF_ID
                )
            )
        ).scalar_one()

        # 创建一条 1 小时前的未读通知
        notif = Notification(
            id=uuid.uuid4(),
            recipient_id=auditor_user_id,
            message_type="assignment_created",
            title="新委派通知",
            content="项目 Alpha 底稿已委派给您",
            related_object_type="project",
            related_object_id=PROJECT_A_ID,
            is_read=False,
            read_at=None,
            created_at=datetime.now() - timedelta(hours=1),
        )
        db_session.add(notif)
        await db_session.commit()

        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/assignment-status?days=7")
            assert resp.status_code == 200
            body = resp.json()

        assert len(body) >= 1
        # 最近的未读不应标记为 overdue
        recent_records = [r for r in body if not r["is_overdue_unread"]]
        assert len(recent_records) >= 1

    @pytest.mark.asyncio
    async def test_days_filter(self, db_session, seeded_db):
        """days 参数应正确过滤时间范围。"""
        auditor_user_id = (
            await db_session.execute(
                __import__("sqlalchemy").select(StaffMember.user_id).where(
                    StaffMember.id == AUDITOR_STAFF_ID
                )
            )
        ).scalar_one()

        # 创建一条 10 天前的通知
        old_notif = Notification(
            id=uuid.uuid4(),
            recipient_id=auditor_user_id,
            message_type="assignment_created",
            title="旧委派通知",
            content="旧通知",
            related_object_type="project",
            related_object_id=PROJECT_A_ID,
            is_read=True,
            read_at=datetime.now() - timedelta(days=9),
            created_at=datetime.now() - timedelta(days=10),
        )
        db_session.add(old_notif)
        await db_session.commit()

        # days=7 应不包含 10 天前的通知
        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/assignment-status?days=7")
            body7 = resp.json()

        # days=14 应包含
        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/assignment-status?days=14")
            body14 = resp.json()

        assert len(body14) > len(body7)

    @pytest.mark.asyncio
    async def test_permission_denied_for_unrelated_user(self, db_session, seeded_db):
        """无关用户应被拒绝访问。"""
        stranger_id = uuid.uuid4()
        stranger_staff = StaffMember(
            id=uuid.uuid4(), user_id=stranger_id,
            name="路人乙", title="审计员", department="审计四部",
        )
        db_session.add(stranger_staff)
        await db_session.commit()

        async with _make_client(db_session, stranger_id, UserRole.auditor) as client:
            resp = await client.get("/api/dashboard/manager/assignment-status?days=7")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_response_fields(self, db_session, seeded_db):
        """响应应包含所有必需字段。"""
        auditor_user_id = (
            await db_session.execute(
                __import__("sqlalchemy").select(StaffMember.user_id).where(
                    StaffMember.id == AUDITOR_STAFF_ID
                )
            )
        ).scalar_one()

        notif = Notification(
            id=uuid.uuid4(),
            recipient_id=auditor_user_id,
            message_type="assignment_created",
            title="新委派通知",
            content="底稿已委派",
            related_object_type="project",
            related_object_id=PROJECT_A_ID,
            is_read=False,
            created_at=datetime.now() - timedelta(hours=2),
        )
        db_session.add(notif)
        await db_session.commit()

        async with _make_client(db_session, MANAGER_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/dashboard/manager/assignment-status?days=7")
            body = resp.json()

        assert len(body) >= 1
        record = body[0]
        required_fields = ["wp_code", "assignee_name", "assigned_at", "notification_read_at", "is_overdue_unread"]
        for field in required_fields:
            assert field in record, f"Missing field: {field}"
