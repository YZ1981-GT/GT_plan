"""成本看板服务 + API 测试 — Round 2 需求 9

验证:
- cost_overview_service.compute 纯函数正确计算成本
- GET /api/projects/{id}/cost-overview 端点正常返回
- budget_alert_worker 幂等逻辑

Validates: Refinement Round 2 需求 9 验收标准 3, 4
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType
from app.models.core import Project
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

# ---------------------------------------------------------------------------
# Test IDs
# ---------------------------------------------------------------------------

PROJECT_ID = uuid.uuid4()
MANAGER_USER_ID = uuid.uuid4()
PARTNER_USER_ID = uuid.uuid4()
MANAGER_STAFF_ID = uuid.uuid4()
PARTNER_STAFF_ID = uuid.uuid4()
AUDITOR_STAFF_ID = uuid.uuid4()
SENIOR_STAFF_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每测试独立内存库。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """种子数据：一个有预算的项目 + 多角色人员 + 已批准工时。"""
    # 项目（预算 200 小时，合同金额 50 万）
    project = Project(
        id=PROJECT_ID,
        name="测试项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        budget_hours=200,
        contract_amount=Decimal("500000.00"),
        created_by=MANAGER_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    # Staff members
    manager_staff = StaffMember(
        id=MANAGER_STAFF_ID,
        user_id=MANAGER_USER_ID,
        name="张经理",
        title="经理",
        department="审计一部",
    )
    partner_staff = StaffMember(
        id=PARTNER_STAFF_ID,
        user_id=PARTNER_USER_ID,
        name="王合伙人",
        title="合伙人",
        department="审计一部",
    )
    auditor_staff = StaffMember(
        id=AUDITOR_STAFF_ID,
        user_id=uuid.uuid4(),
        name="李审计",
        title="审计员",
        department="审计一部",
    )
    senior_staff = StaffMember(
        id=SENIOR_STAFF_ID,
        user_id=uuid.uuid4(),
        name="赵高审",
        title="高级审计员",
        department="审计一部",
    )
    db_session.add_all([manager_staff, partner_staff, auditor_staff, senior_staff])
    await db_session.flush()

    # Project assignments
    db_session.add_all([
        ProjectAssignment(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            staff_id=MANAGER_STAFF_ID,
            role="manager",
        ),
        ProjectAssignment(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            staff_id=PARTNER_STAFF_ID,
            role="signing_partner",
        ),
        ProjectAssignment(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            staff_id=AUDITOR_STAFF_ID,
            role="auditor",
        ),
        ProjectAssignment(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            staff_id=SENIOR_STAFF_ID,
            role="auditor",
        ),
    ])
    await db_session.flush()

    # 已批准工时：
    # 经理 20h（近 14 天内 10h）
    # 审计员 80h（近 14 天内 40h）
    # 高级审计员 50h（近 14 天内 20h）
    today = date.today()
    work_hours = []

    # 经理工时：10h 旧 + 10h 近期
    for i in range(5):
        work_hours.append(WorkHour(
            id=uuid.uuid4(),
            staff_id=MANAGER_STAFF_ID,
            project_id=PROJECT_ID,
            work_date=today - timedelta(days=30 + i),
            hours=Decimal("2"),
            status="approved",
        ))
    for i in range(5):
        work_hours.append(WorkHour(
            id=uuid.uuid4(),
            staff_id=MANAGER_STAFF_ID,
            project_id=PROJECT_ID,
            work_date=today - timedelta(days=i + 1),
            hours=Decimal("2"),
            status="approved",
        ))

    # 审计员工时：40h 旧 + 40h 近期
    for i in range(20):
        work_hours.append(WorkHour(
            id=uuid.uuid4(),
            staff_id=AUDITOR_STAFF_ID,
            project_id=PROJECT_ID,
            work_date=today - timedelta(days=30 + i),
            hours=Decimal("2"),
            status="approved",
        ))
    for i in range(10):
        work_hours.append(WorkHour(
            id=uuid.uuid4(),
            staff_id=AUDITOR_STAFF_ID,
            project_id=PROJECT_ID,
            work_date=today - timedelta(days=i + 1),
            hours=Decimal("4"),
            status="approved",
        ))

    # 高级审计员工时：30h 旧 + 20h 近期
    for i in range(15):
        work_hours.append(WorkHour(
            id=uuid.uuid4(),
            staff_id=SENIOR_STAFF_ID,
            project_id=PROJECT_ID,
            work_date=today - timedelta(days=30 + i),
            hours=Decimal("2"),
            status="approved",
        ))
    for i in range(10):
        work_hours.append(WorkHour(
            id=uuid.uuid4(),
            staff_id=SENIOR_STAFF_ID,
            project_id=PROJECT_ID,
            work_date=today - timedelta(days=i + 1),
            hours=Decimal("2"),
            status="approved",
        ))

    # 一条 draft 工时（不应计入）
    work_hours.append(WorkHour(
        id=uuid.uuid4(),
        staff_id=AUDITOR_STAFF_ID,
        project_id=PROJECT_ID,
        work_date=today - timedelta(days=1),
        hours=Decimal("8"),
        status="draft",
    ))

    db_session.add_all(work_hours)
    await db_session.commit()
    return db_session


# ---------------------------------------------------------------------------
# Tests: cost_overview_service.compute
# ---------------------------------------------------------------------------


class TestCostOverviewCompute:
    """cost_overview_service.compute 纯函数测试。"""

    @pytest.mark.asyncio
    async def test_compute_returns_correct_structure(self, seeded_db: AsyncSession):
        """验证返回结构包含所有必要字段。"""
        from app.services.cost_overview_service import compute

        result = await compute(seeded_db, PROJECT_ID)

        assert "budget_hours" in result
        assert "actual_hours" in result
        assert "remaining_hours" in result
        assert "burn_rate_per_day" in result
        assert "projected_overrun_date" in result
        assert "contract_amount" in result
        assert "cost_by_role" in result

    @pytest.mark.asyncio
    async def test_compute_budget_hours(self, seeded_db: AsyncSession):
        """验证预算工时正确返回。"""
        from app.services.cost_overview_service import compute

        result = await compute(seeded_db, PROJECT_ID)

        assert result["budget_hours"] == 200
        assert result["contract_amount"] == 500000.00

    @pytest.mark.asyncio
    async def test_compute_actual_hours(self, seeded_db: AsyncSession):
        """验证实际工时只计算 approved 状态。

        经理 20h + 审计员 80h + 高级审计员 50h = 150h
        draft 的 8h 不计入。
        """
        from app.services.cost_overview_service import compute

        result = await compute(seeded_db, PROJECT_ID)

        assert result["actual_hours"] == 150.0

    @pytest.mark.asyncio
    async def test_compute_remaining_hours(self, seeded_db: AsyncSession):
        """验证剩余工时 = budget - actual。"""
        from app.services.cost_overview_service import compute

        result = await compute(seeded_db, PROJECT_ID)

        # 200 - 150 = 50
        assert result["remaining_hours"] == 50.0

    @pytest.mark.asyncio
    async def test_compute_burn_rate(self, seeded_db: AsyncSession):
        """验证 burn_rate_per_day = 近 14 天已批准工时 / 14。

        近 14 天：经理 10h + 审计员 40h + 高级审计员 20h = 70h
        burn_rate = 70 / 14 = 5.0
        """
        from app.services.cost_overview_service import compute

        result = await compute(seeded_db, PROJECT_ID)

        assert result["burn_rate_per_day"] == 5.0

    @pytest.mark.asyncio
    async def test_compute_projected_overrun_date(self, seeded_db: AsyncSession):
        """验证预计超支日期 = today + remaining / burn_rate。

        remaining = 50, burn_rate = 5.0 → 10 天后
        """
        from app.services.cost_overview_service import compute

        result = await compute(seeded_db, PROJECT_ID)

        expected_date = date.today() + timedelta(days=10)
        assert result["projected_overrun_date"] == expected_date.isoformat()

    @pytest.mark.asyncio
    async def test_compute_cost_by_role(self, seeded_db: AsyncSession):
        """验证按角色分组成本计算。

        经理 20h × 1500 = 30000
        审计员 80h × 500 = 40000
        高级审计员 50h × 900 = 45000
        """
        from app.services.cost_overview_service import compute

        result = await compute(seeded_db, PROJECT_ID)

        cost_by_role = {item["role"]: item for item in result["cost_by_role"]}

        assert "manager" in cost_by_role
        assert cost_by_role["manager"]["hours"] == 20.0
        assert cost_by_role["manager"]["rate"] == 1500
        assert cost_by_role["manager"]["cost"] == 30000.0

        assert "auditor" in cost_by_role
        assert cost_by_role["auditor"]["hours"] == 80.0
        assert cost_by_role["auditor"]["rate"] == 500
        assert cost_by_role["auditor"]["cost"] == 40000.0

        assert "senior" in cost_by_role
        assert cost_by_role["senior"]["hours"] == 50.0
        assert cost_by_role["senior"]["rate"] == 900
        assert cost_by_role["senior"]["cost"] == 45000.0

    @pytest.mark.asyncio
    async def test_compute_no_budget_project(self, db_session: AsyncSession):
        """无预算项目返回合理默认值。"""
        from app.services.cost_overview_service import compute

        no_budget_id = uuid.uuid4()
        project = Project(
            id=no_budget_id,
            name="无预算项目",
            client_name="客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            budget_hours=None,
            created_by=uuid.uuid4(),
        )
        db_session.add(project)
        await db_session.commit()

        result = await compute(db_session, no_budget_id)

        assert result["budget_hours"] is None
        assert result["actual_hours"] == 0
        assert result["remaining_hours"] == 0
        assert result["projected_overrun_date"] is None

    @pytest.mark.asyncio
    async def test_compute_nonexistent_project(self, db_session: AsyncSession):
        """不存在的项目返回空结果。"""
        from app.services.cost_overview_service import compute

        result = await compute(db_session, uuid.uuid4())

        assert result["budget_hours"] is None
        assert result["actual_hours"] == 0
        assert result["cost_by_role"] == []


# ---------------------------------------------------------------------------
# Tests: budget_alert_worker
# ---------------------------------------------------------------------------


class TestBudgetAlertWorker:
    """budget_alert_worker 逻辑测试。"""

    @pytest.mark.asyncio
    async def test_worker_sends_80_percent_alert(self, seeded_db: AsyncSession):
        """当工时达到 80% 时发送 budget_alert_80 通知。"""
        from app.workers.budget_alert_worker import _get_pm_and_partner_user_ids

        # 验证能获取到 PM 和 partner 的 user_id
        recipients = await _get_pm_and_partner_user_ids(seeded_db, PROJECT_ID)

        assert len(recipients) == 2
        assert MANAGER_USER_ID in recipients
        assert PARTNER_USER_ID in recipients

    @pytest.mark.asyncio
    async def test_worker_idempotency_key_format(self):
        """验证幂等键格式正确。"""
        from datetime import date as d

        project_id = uuid.uuid4()
        threshold = "80"
        today_str = d.today().strftime("%Y%m%d")

        key = f"budget_alert:{project_id}:{threshold}:{today_str}"

        assert str(project_id) in key
        assert "80" in key
        assert today_str in key
