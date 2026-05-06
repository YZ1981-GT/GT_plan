"""cost_overview 端点集成测试 — Round 2 Batch 2 P2 测试覆盖

验证 GET /api/projects/{id}/cost-overview 端点：
- 通过 httpx AsyncClient 命中端点
- 响应结构正确

Validates: Refinement Round 2 复盘 P2 测试覆盖第 2 项
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

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
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
from app.routers.cost_overview import router as cost_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)


class _FakeUser:
    def __init__(self, uid, role=UserRole.admin):
        self.id = uid
        self.username = "test_user"
        self.email = "test@x.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


MGR_USER_ID = uuid.uuid4()
STAFF_ID = uuid.uuid4()
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
    """一个有预算的项目 + 一些已批准工时。"""
    proj = Project(
        id=PROJECT_ID, name="成本测试项目", client_name="客户",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        budget_hours=100, contract_amount=Decimal("200000.00"),
        created_by=MGR_USER_ID,
    )
    db_session.add(proj)
    await db_session.flush()

    staff = StaffMember(
        id=STAFF_ID, user_id=MGR_USER_ID, name="张经理", title="经理",
    )
    db_session.add(staff)
    await db_session.flush()

    db_session.add(ProjectAssignment(
        id=uuid.uuid4(), project_id=PROJECT_ID,
        staff_id=STAFF_ID, role="manager",
    ))
    await db_session.flush()

    # 添加一些已批准工时
    today = date.today()
    for i in range(5):
        db_session.add(WorkHour(
            id=uuid.uuid4(), staff_id=STAFF_ID, project_id=PROJECT_ID,
            work_date=today - timedelta(days=i + 1), hours=Decimal("8"),
            status="approved",
        ))
    await db_session.commit()
    return db_session


def _make_client(db_session: AsyncSession, user_id: uuid.UUID) -> AsyncClient:
    app = FastAPI()
    app.include_router(cost_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(user_id, role=UserRole.admin)

    # require_project_access returns a dependency function; override get_current_user
    # which is used inside require_project_access. Admin role skips project check.
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestCostOverviewEndpoint:
    """GET /api/projects/{id}/cost-overview 端点测试。"""

    @pytest.mark.asyncio
    async def test_returns_200_with_correct_structure(self, db_session, seeded):
        """端点返回 200 且包含所有必需字段。"""
        async with _make_client(db_session, MGR_USER_ID) as client:
            resp = await client.get(f"/api/projects/{PROJECT_ID}/cost-overview")

        assert resp.status_code == 200
        body = resp.json()

        required_fields = [
            "budget_hours", "actual_hours", "remaining_hours",
            "burn_rate_per_day", "projected_overrun_date",
            "contract_amount", "cost_by_role",
        ]
        for field in required_fields:
            assert field in body, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_actual_hours_correct(self, db_session, seeded):
        """实际工时应为 5 天 × 8h = 40h。"""
        async with _make_client(db_session, MGR_USER_ID) as client:
            resp = await client.get(f"/api/projects/{PROJECT_ID}/cost-overview")

        body = resp.json()
        assert body["actual_hours"] == 40.0
        assert body["budget_hours"] == 100
        assert body["remaining_hours"] == 60.0

    @pytest.mark.asyncio
    async def test_cost_by_role_populated(self, db_session, seeded):
        """cost_by_role 应包含 manager 角色的成本。"""
        async with _make_client(db_session, MGR_USER_ID) as client:
            resp = await client.get(f"/api/projects/{PROJECT_ID}/cost-overview")

        body = resp.json()
        assert len(body["cost_by_role"]) >= 1
        roles = {item["role"] for item in body["cost_by_role"]}
        assert "manager" in roles

    @pytest.mark.asyncio
    async def test_nonexistent_project_returns_defaults(self, db_session, seeded):
        """不存在的项目返回默认空值。"""
        fake_id = uuid.uuid4()
        async with _make_client(db_session, MGR_USER_ID) as client:
            resp = await client.get(f"/api/projects/{fake_id}/cost-overview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["budget_hours"] is None
        assert body["actual_hours"] == 0
        assert body["cost_by_role"] == []

    @pytest.mark.asyncio
    async def test_burn_rate_calculation(self, db_session, seeded):
        """burn_rate = 近 14 天工时 / 14。5 天 × 8h = 40h / 14 ≈ 2.857。"""
        async with _make_client(db_session, MGR_USER_ID) as client:
            resp = await client.get(f"/api/projects/{PROJECT_ID}/cost-overview")

        body = resp.json()
        # 40h / 14 ≈ 2.857
        assert 2.5 < body["burn_rate_per_day"] < 3.0
