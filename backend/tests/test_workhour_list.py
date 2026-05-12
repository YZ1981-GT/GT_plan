"""工时审批列表端点测试

验证:
- GET /api/workhours 返回审批人视角的工时列表
- GET /api/workhours/summary 返回本周统计
- 权限守卫：manager 只看自己管理的项目
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.base import Base
from app.models.core import Project, User, UserRole
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
from app.routers.workhour_list import router
from app.core.database import get_db
from app.deps import get_current_user

# SQLite JSONB compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

# ── Fixtures ──

TEST_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:")
TestSession = async_sessionmaker(TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)

MGR_USER_ID = uuid.uuid4()
ADMIN_USER_ID = uuid.uuid4()
PROJECT_A_ID = uuid.uuid4()
PROJECT_B_ID = uuid.uuid4()
STAFF_A_ID = uuid.uuid4()
STAFF_B_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session():
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSession() as session:
        # 创建用户
        mgr_user = User(id=MGR_USER_ID, username="mgr", email="mgr@test.com",
                        hashed_password="x", role=UserRole.manager)
        admin_user = User(id=ADMIN_USER_ID, username="admin", email="admin@test.com",
                          hashed_password="x", role=UserRole.admin)
        session.add_all([mgr_user, admin_user])

        # 创建项目
        proj_a = Project(id=PROJECT_A_ID, name="项目A", client_name="客户甲")
        proj_b = Project(id=PROJECT_B_ID, name="项目B", client_name="客户乙")
        session.add_all([proj_a, proj_b])

        # 创建人员
        staff_a = StaffMember(id=STAFF_A_ID, user_id=MGR_USER_ID, name="经理甲", employee_no="M-001")
        staff_b = StaffMember(id=STAFF_B_ID, name="审计员乙", employee_no="A-001")
        session.add_all([staff_a, staff_b])

        # 经理甲管理项目A
        assign = ProjectAssignment(
            id=uuid.uuid4(), project_id=PROJECT_A_ID,
            staff_id=STAFF_A_ID, role="manager"
        )
        session.add(assign)

        # 工时记录
        today = date.today()
        wh1 = WorkHour(id=uuid.uuid4(), staff_id=STAFF_B_ID, project_id=PROJECT_A_ID,
                       work_date=today, hours=Decimal("8"), status="confirmed", description="审计底稿")
        wh2 = WorkHour(id=uuid.uuid4(), staff_id=STAFF_B_ID, project_id=PROJECT_A_ID,
                       work_date=today - timedelta(days=1), hours=Decimal("4"), status="approved", description="复核")
        wh3 = WorkHour(id=uuid.uuid4(), staff_id=STAFF_B_ID, project_id=PROJECT_B_ID,
                       work_date=today, hours=Decimal("6"), status="confirmed", description="项目B工时")
        session.add_all([wh1, wh2, wh3])
        await session.commit()
        yield session

    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_client(db_session: AsyncSession, user_id: uuid.UUID, role: UserRole = UserRole.manager):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return User(id=user_id, username="test", email="t@t.com",
                    hashed_password="x", role=role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Tests ──

class TestWorkhourList:
    """GET /api/workhours"""

    @pytest.mark.asyncio
    async def test_manager_sees_only_managed_projects(self, db_session):
        """manager 只看到自己管理项目的工时。"""
        async with _make_client(db_session, MGR_USER_ID, UserRole.manager) as client:
            resp = await client.get("/api/workhours")
            assert resp.status_code == 200
            body = resp.json()
            items = body["items"]
            # 经理甲只管理项目A，不应看到项目B的工时
            project_ids = {item["project_id"] for item in items}
            assert str(PROJECT_A_ID) in project_ids
            assert str(PROJECT_B_ID) not in project_ids

    @pytest.mark.asyncio
    async def test_admin_sees_all(self, db_session):
        """admin 看到所有工时。"""
        async with _make_client(db_session, ADMIN_USER_ID, UserRole.admin) as client:
            resp = await client.get("/api/workhours")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] >= 3

    @pytest.mark.asyncio
    async def test_filter_by_status(self, db_session):
        """按状态筛选。"""
        async with _make_client(db_session, ADMIN_USER_ID, UserRole.admin) as client:
            resp = await client.get("/api/workhours", params={"status": "confirmed"})
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert all(item["status"] == "confirmed" for item in items)

    @pytest.mark.asyncio
    async def test_filter_by_date_range(self, db_session):
        """按日期范围筛选。"""
        today = date.today()
        async with _make_client(db_session, ADMIN_USER_ID, UserRole.admin) as client:
            resp = await client.get("/api/workhours", params={
                "date_from": str(today),
                "date_to": str(today),
            })
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert all(item["work_date"] == str(today) for item in items)


class TestWorkhourSummary:
    """GET /api/workhours/summary"""

    @pytest.mark.asyncio
    async def test_summary_returns_hours(self, db_session):
        """summary 返回本周已审批和待审批小时数。"""
        async with _make_client(db_session, ADMIN_USER_ID, UserRole.admin) as client:
            resp = await client.get("/api/workhours/summary")
            assert resp.status_code == 200
            body = resp.json()
            assert "approved_hours" in body
            assert "pending_hours" in body
            assert isinstance(body["approved_hours"], (int, float))
            assert isinstance(body["pending_hours"], (int, float))
