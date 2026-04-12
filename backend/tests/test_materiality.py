"""重要性水平计算测试

Validates: Requirements 8.1-8.9
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    MappingType,
    TbBalance,
    TrialBalance,
)
from app.models.audit_platform_schemas import (
    MaterialityInput,
    MaterialityOverride,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.materiality_service import MaterialityService
from app.services.trial_balance_service import TrialBalanceService
from app.routers.materiality import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_manager"
        self.email = "manager@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建重要性水平测试数据（含试算表）"""
    project = Project(
        id=uuid.uuid4(),
        name="重要性水平测试_2025",
        client_name="重要性水平测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=TEST_USER.id,
    )
    db_session.add(project)
    await db_session.flush()
    pid = project.id

    # 标准科目
    db_session.add_all([
        AccountChart(
            project_id=pid, account_code="1001", account_name="库存现金",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="1002", account_name="银行存款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="2001", account_name="短期借款",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.liability, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="6001", account_name="营业收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="6050", account_name="营业利润",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
    ])

    # 试算表数据
    db_session.add_all([
        TrialBalance(
            project_id=pid, year=2025, company_code="001",
            standard_account_code="1001", account_name="库存现金",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("500000"),
            audited_amount=Decimal("500000"),
        ),
        TrialBalance(
            project_id=pid, year=2025, company_code="001",
            standard_account_code="1002", account_name="银行存款",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("2000000"),
            audited_amount=Decimal("2000000"),
        ),
        TrialBalance(
            project_id=pid, year=2025, company_code="001",
            standard_account_code="2001", account_name="短期借款",
            account_category=AccountCategory.liability,
            unadjusted_amount=Decimal("800000"),
            audited_amount=Decimal("800000"),
        ),
        TrialBalance(
            project_id=pid, year=2025, company_code="001",
            standard_account_code="6001", account_name="营业收入",
            account_category=AccountCategory.revenue,
            unadjusted_amount=Decimal("5000000"),
            audited_amount=Decimal("5000000"),
        ),
        TrialBalance(
            project_id=pid, year=2025, company_code="001",
            standard_account_code="6050", account_name="营业利润",
            account_category=AccountCategory.revenue,
            unadjusted_amount=Decimal("1200000"),
            audited_amount=Decimal("1200000"),
        ),
    ])

    await db_session.commit()
    return pid


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


# ===== 15.1 calculate =====

@pytest.mark.asyncio
async def test_calculate_basic(db_session: AsyncSession, seeded_db):
    """基本计算：整体=基准×百分比, 执行=整体×执行比例, 微小=整体×微小比例"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    params = MaterialityInput(
        benchmark_type="revenue",
        benchmark_amount=Decimal("5000000"),
        overall_percentage=Decimal("5"),
        performance_ratio=Decimal("50"),
        trivial_ratio=Decimal("5"),
    )
    result = await svc.calculate(pid, 2025, params, TEST_USER.id)
    await db_session.commit()

    # 整体 = 5000000 × 5% = 250000
    assert result.overall_materiality == Decimal("250000.00")
    # 执行 = 250000 × 50% = 125000
    assert result.performance_materiality == Decimal("125000.00")
    # 微小 = 250000 × 5% = 12500
    assert result.trivial_threshold == Decimal("12500.00")
    assert result.is_override is False


@pytest.mark.asyncio
async def test_calculate_custom_ratios(db_session: AsyncSession, seeded_db):
    """自定义执行比例和微小比例"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    params = MaterialityInput(
        benchmark_type="total_assets",
        benchmark_amount=Decimal("10000000"),
        overall_percentage=Decimal("1"),
        performance_ratio=Decimal("75"),
        trivial_ratio=Decimal("3"),
    )
    result = await svc.calculate(pid, 2025, params, TEST_USER.id)
    await db_session.commit()

    # 整体 = 10000000 × 1% = 100000
    assert result.overall_materiality == Decimal("100000.00")
    # 执行 = 100000 × 75% = 75000
    assert result.performance_materiality == Decimal("75000.00")
    # 微小 = 100000 × 3% = 3000
    assert result.trivial_threshold == Decimal("3000.00")


@pytest.mark.asyncio
async def test_calculate_recalculate_updates(db_session: AsyncSession, seeded_db):
    """重新计算更新已有记录"""
    pid = seeded_db
    svc = MaterialityService(db_session)

    # 第一次计算
    params1 = MaterialityInput(
        benchmark_type="revenue",
        benchmark_amount=Decimal("5000000"),
        overall_percentage=Decimal("5"),
    )
    r1 = await svc.calculate(pid, 2025, params1, TEST_USER.id)
    await db_session.commit()

    # 第二次计算（不同参数）
    params2 = MaterialityInput(
        benchmark_type="total_assets",
        benchmark_amount=Decimal("10000000"),
        overall_percentage=Decimal("2"),
    )
    r2 = await svc.calculate(pid, 2025, params2, TEST_USER.id)
    await db_session.commit()

    assert r2.id == r1.id  # 同一条记录
    assert r2.benchmark_type == "total_assets"
    assert r2.overall_materiality == Decimal("200000.00")


# ===== 15.2 auto_populate_benchmark =====

@pytest.mark.asyncio
async def test_auto_populate_revenue(db_session: AsyncSession, seeded_db):
    """从试算表自动取营业收入"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    amount = await svc.auto_populate_benchmark(pid, 2025, "revenue")
    # 营业收入 = 5000000
    assert amount == Decimal("5000000")


@pytest.mark.asyncio
async def test_auto_populate_total_assets(db_session: AsyncSession, seeded_db):
    """从试算表自动取总资产"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    amount = await svc.auto_populate_benchmark(pid, 2025, "total_assets")
    # 资产类 = 500000 + 2000000 = 2500000
    assert amount == Decimal("2500000")


@pytest.mark.asyncio
async def test_auto_populate_net_assets(db_session: AsyncSession, seeded_db):
    """从试算表自动取净资产（资产-负债）"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    amount = await svc.auto_populate_benchmark(pid, 2025, "net_assets")
    # 资产 2500000 - 负债 800000 = 1700000
    assert amount == Decimal("1700000")


@pytest.mark.asyncio
async def test_auto_populate_pre_tax_profit(db_session: AsyncSession, seeded_db):
    """从试算表自动取利润总额"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    amount = await svc.auto_populate_benchmark(pid, 2025, "pre_tax_profit")
    # 营业利润 = 1200000
    assert amount == Decimal("1200000")


@pytest.mark.asyncio
async def test_auto_populate_invalid_type(db_session: AsyncSession, seeded_db):
    """不支持的基准类型"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    with pytest.raises(ValueError, match="不支持的基准类型"):
        await svc.auto_populate_benchmark(pid, 2025, "invalid_type")


# ===== 15.3 override + get_change_history =====

@pytest.mark.asyncio
async def test_override_overall(db_session: AsyncSession, seeded_db):
    """手动覆盖整体重要性"""
    pid = seeded_db
    svc = MaterialityService(db_session)

    # 先计算
    params = MaterialityInput(
        benchmark_type="revenue",
        benchmark_amount=Decimal("5000000"),
        overall_percentage=Decimal("5"),
    )
    await svc.calculate(pid, 2025, params, TEST_USER.id)
    await db_session.commit()

    # 覆盖
    overrides = MaterialityOverride(
        overall_materiality=Decimal("300000"),
        override_reason="根据行业经验调整",
    )
    result = await svc.override(pid, 2025, overrides, TEST_USER.id)
    await db_session.commit()

    assert result.overall_materiality == Decimal("300000")
    assert result.is_override is True
    assert result.override_reason == "根据行业经验调整"
    # 未覆盖的字段保持不变
    assert result.performance_materiality == Decimal("125000.00")


@pytest.mark.asyncio
async def test_override_multiple_fields(db_session: AsyncSession, seeded_db):
    """同时覆盖多个字段"""
    pid = seeded_db
    svc = MaterialityService(db_session)

    params = MaterialityInput(
        benchmark_type="revenue",
        benchmark_amount=Decimal("5000000"),
        overall_percentage=Decimal("5"),
    )
    await svc.calculate(pid, 2025, params, TEST_USER.id)
    await db_session.commit()

    overrides = MaterialityOverride(
        overall_materiality=Decimal("300000"),
        performance_materiality=Decimal("200000"),
        trivial_threshold=Decimal("20000"),
        override_reason="全面调整",
    )
    result = await svc.override(pid, 2025, overrides, TEST_USER.id)
    await db_session.commit()

    assert result.overall_materiality == Decimal("300000")
    assert result.performance_materiality == Decimal("200000")
    assert result.trivial_threshold == Decimal("20000")


@pytest.mark.asyncio
async def test_override_without_calculate(db_session: AsyncSession, seeded_db):
    """未计算时覆盖应报错"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    overrides = MaterialityOverride(
        overall_materiality=Decimal("300000"),
        override_reason="测试",
    )
    with pytest.raises(ValueError, match="尚未计算"):
        await svc.override(pid, 2025, overrides, TEST_USER.id)


@pytest.mark.asyncio
async def test_change_history(db_session: AsyncSession, seeded_db):
    """变更历史记录"""
    pid = seeded_db
    svc = MaterialityService(db_session)

    # 第一次计算
    params1 = MaterialityInput(
        benchmark_type="revenue",
        benchmark_amount=Decimal("5000000"),
        overall_percentage=Decimal("5"),
    )
    await svc.calculate(pid, 2025, params1, TEST_USER.id)
    await db_session.commit()

    # 覆盖
    overrides = MaterialityOverride(
        overall_materiality=Decimal("300000"),
        override_reason="调整",
    )
    await svc.override(pid, 2025, overrides, TEST_USER.id)
    await db_session.commit()

    history = await svc.get_change_history(pid, 2025)
    assert len(history) > 0
    # 应包含 overall_materiality 的变更
    field_names = {h.field_name for h in history}
    assert "overall_materiality" in field_names


@pytest.mark.asyncio
async def test_change_history_empty(db_session: AsyncSession, seeded_db):
    """无变更历史"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    history = await svc.get_change_history(pid, 2025)
    assert history == []


# ===== get_current =====

@pytest.mark.asyncio
async def test_get_current_none(db_session: AsyncSession, seeded_db):
    """未计算时返回 None"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    result = await svc.get_current(pid, 2025)
    assert result is None


@pytest.mark.asyncio
async def test_get_current_after_calculate(db_session: AsyncSession, seeded_db):
    """计算后获取"""
    pid = seeded_db
    svc = MaterialityService(db_session)
    params = MaterialityInput(
        benchmark_type="revenue",
        benchmark_amount=Decimal("5000000"),
        overall_percentage=Decimal("5"),
    )
    await svc.calculate(pid, 2025, params, TEST_USER.id)
    await db_session.commit()

    result = await svc.get_current(pid, 2025)
    assert result is not None
    assert result.overall_materiality == Decimal("250000.00")


# ===== 15.4 API 路由测试 =====

@pytest.mark.asyncio
async def test_api_get_materiality_empty(client: AsyncClient, seeded_db):
    """GET 未计算时返回 null"""
    pid = seeded_db
    resp = await client.get(f"/api/projects/{pid}/materiality?year=2025")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_api_calculate(client: AsyncClient, seeded_db):
    """POST calculate"""
    pid = seeded_db
    resp = await client.post(
        f"/api/projects/{pid}/materiality/calculate?year=2025",
        json={
            "benchmark_type": "revenue",
            "benchmark_amount": "5000000",
            "overall_percentage": "5",
            "performance_ratio": "50",
            "trivial_ratio": "5",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["overall_materiality"]) == Decimal("250000")
    assert Decimal(body["performance_materiality"]) == Decimal("125000")
    assert Decimal(body["trivial_threshold"]) == Decimal("12500")


@pytest.mark.asyncio
async def test_api_get_after_calculate(client: AsyncClient, seeded_db):
    """GET 计算后获取"""
    pid = seeded_db
    await client.post(
        f"/api/projects/{pid}/materiality/calculate?year=2025",
        json={
            "benchmark_type": "revenue",
            "benchmark_amount": "5000000",
            "overall_percentage": "5",
        },
    )
    resp = await client.get(f"/api/projects/{pid}/materiality?year=2025")
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["benchmark_type"] == "revenue"


@pytest.mark.asyncio
async def test_api_override(client: AsyncClient, seeded_db):
    """PUT override"""
    pid = seeded_db
    # 先计算
    await client.post(
        f"/api/projects/{pid}/materiality/calculate?year=2025",
        json={
            "benchmark_type": "revenue",
            "benchmark_amount": "5000000",
            "overall_percentage": "5",
        },
    )
    # 覆盖
    resp = await client.put(
        f"/api/projects/{pid}/materiality/override?year=2025",
        json={
            "overall_materiality": "300000",
            "override_reason": "行业调整",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["overall_materiality"]) == Decimal("300000")
    assert body["is_override"] is True


@pytest.mark.asyncio
async def test_api_override_without_calculate(client: AsyncClient, seeded_db):
    """PUT override 未计算时返回 400"""
    pid = seeded_db
    resp = await client.put(
        f"/api/projects/{pid}/materiality/override?year=2025",
        json={
            "overall_materiality": "300000",
            "override_reason": "测试",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_history(client: AsyncClient, seeded_db):
    """GET history"""
    pid = seeded_db
    # 计算
    await client.post(
        f"/api/projects/{pid}/materiality/calculate?year=2025",
        json={
            "benchmark_type": "revenue",
            "benchmark_amount": "5000000",
            "overall_percentage": "5",
        },
    )
    # 覆盖
    await client.put(
        f"/api/projects/{pid}/materiality/override?year=2025",
        json={
            "overall_materiality": "300000",
            "override_reason": "调整",
        },
    )
    resp = await client.get(f"/api/projects/{pid}/materiality/history?year=2025")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 0


@pytest.mark.asyncio
async def test_api_benchmark(client: AsyncClient, seeded_db):
    """GET benchmark 自动取基准"""
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/materiality/benchmark?year=2025&benchmark_type=total_assets"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["benchmark_amount"]) == Decimal("2500000")


@pytest.mark.asyncio
async def test_api_benchmark_invalid_type(client: AsyncClient, seeded_db):
    """GET benchmark 无效类型返回 400"""
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/materiality/benchmark?year=2025&benchmark_type=invalid"
    )
    assert resp.status_code == 400
