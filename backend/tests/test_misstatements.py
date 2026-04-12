"""未更正错报汇总管理测试

Validates: Requirements 11.1-11.8, 12.1
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
    AccountSource,
    Adjustment,
    AdjustmentType,
    Materiality,
    MisstatementType,
    ReviewStatus,
    UnadjustedMisstatement,
)
from app.models.audit_platform_schemas import (
    MisstatementCreate,
    MisstatementUpdate,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.misstatement_service import UnadjustedMisstatementService
from app.routers.misstatements import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_auditor"
        self.email = "auditor@test.com"
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
    """创建未更正错报测试数据"""
    project = Project(
        id=uuid.uuid4(),
        name="错报测试_2025",
        client_name="错报测试",
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
            project_id=pid, account_code="6001", account_name="主营业务收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
    ])

    # 重要性水平
    db_session.add(Materiality(
        project_id=pid, year=2025,
        benchmark_type="revenue",
        benchmark_amount=Decimal("1000000"),
        overall_percentage=Decimal("5"),
        overall_materiality=Decimal("50000"),
        performance_ratio=Decimal("50"),
        performance_materiality=Decimal("25000"),
        trivial_ratio=Decimal("5"),
        trivial_threshold=Decimal("2500"),
    ))

    # 一笔被拒绝的 AJE（用于 from-aje 测试）
    group_id = uuid.uuid4()
    db_session.add_all([
        Adjustment(
            project_id=pid, year=2025, company_code="001",
            adjustment_no="AJE-001", adjustment_type=AdjustmentType.aje,
            description="应收账款减值",
            account_code="1001", account_name="库存现金",
            debit_amount=Decimal("5000"), credit_amount=Decimal("0"),
            entry_group_id=group_id,
            review_status=ReviewStatus.rejected,
            rejection_reason="客户拒绝调整",
            created_by=TEST_USER.id,
        ),
        Adjustment(
            project_id=pid, year=2025, company_code="001",
            adjustment_no="AJE-001", adjustment_type=AdjustmentType.aje,
            description="应收账款减值",
            account_code="6001", account_name="主营业务收入",
            debit_amount=Decimal("0"), credit_amount=Decimal("5000"),
            entry_group_id=group_id,
            review_status=ReviewStatus.rejected,
            rejection_reason="客户拒绝调整",
            created_by=TEST_USER.id,
        ),
    ])

    await db_session.commit()
    return {"pid": pid, "group_id": group_id}


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


# ===== Service Tests =====

@pytest.mark.asyncio
async def test_create_misstatement(db_session: AsyncSession, seeded_db):
    """创建未更正错报"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)
    data = MisstatementCreate(
        year=2025,
        misstatement_description="存货跌价准备不足",
        affected_account_code="1001",
        affected_account_name="库存现金",
        misstatement_amount=Decimal("10000"),
        misstatement_type=MisstatementType.factual,
    )
    result = await svc.create_misstatement(pid, data, TEST_USER.id)
    await db_session.commit()

    assert result.misstatement_description == "存货跌价准备不足"
    assert result.misstatement_amount == Decimal("10000")
    assert result.misstatement_type == MisstatementType.factual
    assert result.project_id == pid


@pytest.mark.asyncio
async def test_create_from_rejected_aje(db_session: AsyncSession, seeded_db):
    """从被拒绝AJE创建未更正错报"""
    pid = seeded_db["pid"]
    group_id = seeded_db["group_id"]
    svc = UnadjustedMisstatementService(db_session)
    result = await svc.create_from_rejected_aje(pid, group_id, 2025, TEST_USER.id)
    await db_session.commit()

    assert result.source_adjustment_id is not None
    assert result.misstatement_amount == Decimal("5000")
    assert result.misstatement_description == "应收账款减值"


@pytest.mark.asyncio
async def test_create_from_nonexistent_aje(db_session: AsyncSession, seeded_db):
    """从不存在的AJE创建应报错"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)
    with pytest.raises(ValueError, match="调整分录不存在"):
        await svc.create_from_rejected_aje(pid, uuid.uuid4(), 2025)


@pytest.mark.asyncio
async def test_update_misstatement(db_session: AsyncSession, seeded_db):
    """更新未更正错报"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)
    created = await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="原始描述",
        misstatement_amount=Decimal("1000"),
        misstatement_type=MisstatementType.factual,
    ))
    await db_session.flush()

    updated = await svc.update_misstatement(pid, created.id, MisstatementUpdate(
        misstatement_description="修改后描述",
        management_reason="客户认为金额不重大",
        auditor_evaluation="审计师认为需要关注",
    ))
    assert updated.misstatement_description == "修改后描述"
    assert updated.management_reason == "客户认为金额不重大"


@pytest.mark.asyncio
async def test_delete_misstatement(db_session: AsyncSession, seeded_db):
    """软删除未更正错报"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)
    created = await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="待删除",
        misstatement_amount=Decimal("500"),
        misstatement_type=MisstatementType.judgmental,
    ))
    await db_session.flush()

    await svc.delete_misstatement(pid, created.id)
    await db_session.flush()

    items = await svc.list_misstatements(pid, 2025)
    assert all(i.id != created.id for i in items)


@pytest.mark.asyncio
async def test_get_cumulative_amount(db_session: AsyncSession, seeded_db):
    """累计金额计算"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)

    await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="错报1",
        misstatement_amount=Decimal("10000"),
        misstatement_type=MisstatementType.factual,
    ))
    await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="错报2",
        misstatement_amount=Decimal("20000"),
        misstatement_type=MisstatementType.projected,
    ))
    await db_session.flush()

    total = await svc.get_cumulative_amount(pid, 2025)
    assert total == Decimal("30000")


@pytest.mark.asyncio
async def test_get_summary(db_session: AsyncSession, seeded_db):
    """汇总视图"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)

    await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="事实错报",
        misstatement_amount=Decimal("15000"),
        misstatement_type=MisstatementType.factual,
        management_reason="理由", auditor_evaluation="评价",
    ))
    await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="判断错报",
        misstatement_amount=Decimal("8000"),
        misstatement_type=MisstatementType.judgmental,
        management_reason="理由", auditor_evaluation="评价",
    ))
    await db_session.flush()

    summary = await svc.get_summary(pid, 2025)
    assert summary.cumulative_amount == Decimal("23000")
    assert summary.overall_materiality == Decimal("50000")
    assert summary.exceeds_materiality is False
    assert len(summary.by_type) == 2
    assert summary.evaluation_complete is True


@pytest.mark.asyncio
async def test_summary_exceeds_materiality(db_session: AsyncSession, seeded_db):
    """累计超过重要性水平"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)

    await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="大额错报",
        misstatement_amount=Decimal("60000"),
        misstatement_type=MisstatementType.factual,
    ))
    await db_session.flush()

    summary = await svc.get_summary(pid, 2025)
    assert summary.exceeds_materiality is True


@pytest.mark.asyncio
async def test_check_materiality_threshold(db_session: AsyncSession, seeded_db):
    """超限预警"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)

    await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="超限错报",
        misstatement_amount=Decimal("55000"),
        misstatement_type=MisstatementType.factual,
    ))
    await db_session.flush()

    result = await svc.check_materiality_threshold(pid, 2025)
    assert result.exceeds is True
    assert result.warning_message is not None
    assert "保留意见" in result.warning_message


@pytest.mark.asyncio
async def test_check_materiality_threshold_no_materiality(db_session: AsyncSession, seeded_db):
    """无重要性水平时的预警"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)

    # 使用不同年度（无重要性水平）
    result = await svc.check_materiality_threshold(pid, 2024)
    assert result.exceeds is False
    assert result.warning_message == "尚未设置重要性水平"


@pytest.mark.asyncio
async def test_check_evaluation_completeness(db_session: AsyncSession, seeded_db):
    """评价完整性检查"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)

    # 无记录时应完整
    assert await svc.check_evaluation_completeness(pid, 2025) is True

    # 创建不完整记录
    await svc.create_misstatement(pid, MisstatementCreate(
        year=2025, misstatement_description="缺少评价",
        misstatement_amount=Decimal("1000"),
        misstatement_type=MisstatementType.factual,
    ))
    await db_session.flush()
    assert await svc.check_evaluation_completeness(pid, 2025) is False

    # 补充完整
    items = await svc.list_misstatements(pid, 2025)
    await svc.update_misstatement(pid, items[0].id, MisstatementUpdate(
        management_reason="理由", auditor_evaluation="评价",
    ))
    await db_session.flush()
    assert await svc.check_evaluation_completeness(pid, 2025) is True


@pytest.mark.asyncio
async def test_carry_forward(db_session: AsyncSession, seeded_db):
    """上年结转"""
    pid = seeded_db["pid"]
    svc = UnadjustedMisstatementService(db_session)

    # 创建上年错报
    await svc.create_misstatement(pid, MisstatementCreate(
        year=2024, misstatement_description="上年错报1",
        misstatement_amount=Decimal("5000"),
        misstatement_type=MisstatementType.factual,
        management_reason="理由", auditor_evaluation="评价",
    ))
    await svc.create_misstatement(pid, MisstatementCreate(
        year=2024, misstatement_description="上年错报2",
        misstatement_amount=Decimal("3000"),
        misstatement_type=MisstatementType.judgmental,
    ))
    await db_session.flush()

    # 结转到本年
    count = await svc.carry_forward(pid, pid, 2024, 2025, TEST_USER.id)
    await db_session.flush()

    assert count == 2
    items = await svc.list_misstatements(pid, 2025)
    carried = [i for i in items if i.is_carried_forward]
    assert len(carried) == 2
    assert all(i.prior_year_id is not None for i in carried)


# ===== API Tests =====

@pytest.mark.asyncio
async def test_api_create_misstatement(client: AsyncClient, seeded_db):
    """POST 创建错报"""
    pid = seeded_db["pid"]
    resp = await client.post(f"/api/projects/{pid}/misstatements", json={
        "year": 2025,
        "misstatement_description": "API测试错报",
        "misstatement_amount": "12000",
        "misstatement_type": "factual",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["misstatement_description"] == "API测试错报"
    assert Decimal(str(body["misstatement_amount"])) == Decimal("12000")


@pytest.mark.asyncio
async def test_api_list_misstatements(client: AsyncClient, seeded_db):
    """GET 列表"""
    pid = seeded_db["pid"]
    await client.post(f"/api/projects/{pid}/misstatements", json={
        "year": 2025, "misstatement_description": "测试",
        "misstatement_amount": "1000", "misstatement_type": "factual",
    })
    resp = await client.get(f"/api/projects/{pid}/misstatements?year=2025")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_api_from_aje(client: AsyncClient, seeded_db):
    """POST from-aje 从AJE创建"""
    pid = seeded_db["pid"]
    group_id = seeded_db["group_id"]
    resp = await client.post(
        f"/api/projects/{pid}/misstatements/from-aje/{group_id}?year=2025"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(str(body["misstatement_amount"])) == Decimal("5000")


@pytest.mark.asyncio
async def test_api_update_misstatement(client: AsyncClient, seeded_db):
    """PUT 更新"""
    pid = seeded_db["pid"]
    create_resp = await client.post(f"/api/projects/{pid}/misstatements", json={
        "year": 2025, "misstatement_description": "原始",
        "misstatement_amount": "1000", "misstatement_type": "factual",
    })
    ms_id = create_resp.json()["id"]

    resp = await client.put(f"/api/projects/{pid}/misstatements/{ms_id}", json={
        "misstatement_description": "修改后",
        "management_reason": "客户理由",
    })
    assert resp.status_code == 200
    assert resp.json()["misstatement_description"] == "修改后"


@pytest.mark.asyncio
async def test_api_delete_misstatement(client: AsyncClient, seeded_db):
    """DELETE 软删除"""
    pid = seeded_db["pid"]
    create_resp = await client.post(f"/api/projects/{pid}/misstatements", json={
        "year": 2025, "misstatement_description": "待删除",
        "misstatement_amount": "500", "misstatement_type": "judgmental",
    })
    ms_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/projects/{pid}/misstatements/{ms_id}")
    assert resp.status_code == 200

    list_resp = await client.get(f"/api/projects/{pid}/misstatements?year=2025")
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_api_summary(client: AsyncClient, seeded_db):
    """GET summary"""
    pid = seeded_db["pid"]
    await client.post(f"/api/projects/{pid}/misstatements", json={
        "year": 2025, "misstatement_description": "错报",
        "misstatement_amount": "10000", "misstatement_type": "factual",
    })
    resp = await client.get(f"/api/projects/{pid}/misstatements/summary?year=2025")
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(str(body["cumulative_amount"])) == Decimal("10000")
    assert Decimal(str(body["overall_materiality"])) == Decimal("50000")
    assert body["exceeds_materiality"] is False
