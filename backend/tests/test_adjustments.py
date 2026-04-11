"""审计调整分录管理测试

Validates: Requirements 7.1-7.20
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
    AdjustmentEntry,
    AdjustmentType,
    ReportLineMapping,
    ReportLineMappingType,
    ReportType,
    ReviewStatus,
    TrialBalance,
)
from app.models.audit_platform_schemas import (
    AdjustmentCreate,
    AdjustmentLineItem,
    AdjustmentUpdate,
    ReviewStatusChange,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.adjustment_service import AdjustmentService
from app.routers.adjustments import router

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
    """创建调整分录测试数据"""
    project = Project(
        id=uuid.uuid4(),
        name="调整分录测试_2025",
        client_name="调整分录测试",
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
            project_id=pid, account_code="6001", account_name="主营业务收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
    ])

    # 报表行次映射（已确认）
    db_session.add_all([
        ReportLineMapping(
            project_id=pid, standard_account_code="1001",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-001", report_line_name="货币资金",
            report_line_level=1,
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=True,
        ),
        ReportLineMapping(
            project_id=pid, standard_account_code="1002",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-001", report_line_name="货币资金",
            report_line_level=1,
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=True,
        ),
        ReportLineMapping(
            project_id=pid, standard_account_code="6001",
            report_type=ReportType.income_statement,
            report_line_code="IS-001", report_line_name="营业收入",
            report_line_level=1,
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=True,
        ),
    ])

    # 试算表数据（用于 wp-summary 测试）
    db_session.add_all([
        TrialBalance(
            project_id=pid, year=2025, company_code="001",
            standard_account_code="1001", account_name="库存现金",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("12000"),
            audited_amount=Decimal("12000"),
        ),
        TrialBalance(
            project_id=pid, year=2025, company_code="001",
            standard_account_code="6001", account_name="主营业务收入",
            account_category=AccountCategory.revenue,
            unadjusted_amount=Decimal("100000"),
            audited_amount=Decimal("100000"),
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


# ===== 13.1 create_entry =====

@pytest.mark.asyncio
async def test_create_entry_success(db_session: AsyncSession, seeded_db):
    """创建调整分录：借贷平衡，自动编号 AJE-001"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    data = AdjustmentCreate(
        adjustment_type=AdjustmentType.aje,
        year=2025,
        description="测试调整",
        line_items=[
            AdjustmentLineItem(
                standard_account_code="1001", account_name="库存现金",
                debit_amount=Decimal("500"), credit_amount=Decimal("0"),
            ),
            AdjustmentLineItem(
                standard_account_code="6001", account_name="主营业务收入",
                debit_amount=Decimal("0"), credit_amount=Decimal("500"),
            ),
        ],
    )
    result = await svc.create_entry(pid, data, TEST_USER.id)
    await db_session.commit()

    assert result.adjustment_no == "AJE-001"
    assert result.total_debit == Decimal("500")
    assert result.total_credit == Decimal("500")
    assert result.review_status == ReviewStatus.draft
    assert len(result.line_items) == 2


@pytest.mark.asyncio
async def test_create_entry_rje_numbering(db_session: AsyncSession, seeded_db):
    """RJE 编号独立：RJE-001"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    data = AdjustmentCreate(
        adjustment_type=AdjustmentType.rje,
        year=2025,
        line_items=[
            AdjustmentLineItem(
                standard_account_code="1001", debit_amount=Decimal("100"),
            ),
            AdjustmentLineItem(
                standard_account_code="1002", credit_amount=Decimal("100"),
            ),
        ],
    )
    result = await svc.create_entry(pid, data, TEST_USER.id)
    await db_session.commit()
    assert result.adjustment_no == "RJE-001"


@pytest.mark.asyncio
async def test_create_entry_sequential_numbering(db_session: AsyncSession, seeded_db):
    """连续创建编号递增"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    for i in range(3):
        data = AdjustmentCreate(
            adjustment_type=AdjustmentType.aje,
            year=2025,
            line_items=[
                AdjustmentLineItem(
                    standard_account_code="1001",
                    debit_amount=Decimal("100"),
                ),
                AdjustmentLineItem(
                    standard_account_code="6001",
                    credit_amount=Decimal("100"),
                ),
            ],
        )
        result = await svc.create_entry(pid, data, TEST_USER.id)
        await db_session.flush()
        assert result.adjustment_no == f"AJE-{i + 1:03d}"
    await db_session.commit()


@pytest.mark.asyncio
async def test_create_entry_imbalanced(db_session: AsyncSession, seeded_db):
    """借贷不平衡拒绝"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    data = AdjustmentCreate(
        adjustment_type=AdjustmentType.aje,
        year=2025,
        line_items=[
            AdjustmentLineItem(
                standard_account_code="1001",
                debit_amount=Decimal("500"),
            ),
            AdjustmentLineItem(
                standard_account_code="6001",
                credit_amount=Decimal("300"),
            ),
        ],
    )
    with pytest.raises(ValueError, match="借贷不平衡"):
        await svc.create_entry(pid, data, TEST_USER.id)


@pytest.mark.asyncio
async def test_create_entry_invalid_account(db_session: AsyncSession, seeded_db):
    """科目不存在拒绝"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    data = AdjustmentCreate(
        adjustment_type=AdjustmentType.aje,
        year=2025,
        line_items=[
            AdjustmentLineItem(
                standard_account_code="9999",
                debit_amount=Decimal("100"),
            ),
            AdjustmentLineItem(
                standard_account_code="1001",
                credit_amount=Decimal("100"),
            ),
        ],
    )
    with pytest.raises(ValueError, match="科目编码不存在"):
        await svc.create_entry(pid, data, TEST_USER.id)


# ===== 13.2 update_entry / delete_entry =====

@pytest.mark.asyncio
async def test_update_entry_description(db_session: AsyncSession, seeded_db):
    """修改描述"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    create_data = AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        description="原始描述",
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    )
    created = await svc.create_entry(pid, create_data, TEST_USER.id)
    await db_session.flush()

    update_data = AdjustmentUpdate(description="修改后描述")
    updated = await svc.update_entry(pid, created.entry_group_id, update_data, TEST_USER.id)
    assert updated.description == "修改后描述"


@pytest.mark.asyncio
async def test_update_entry_line_items(db_session: AsyncSession, seeded_db):
    """修改行项"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    create_data = AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    )
    created = await svc.create_entry(pid, create_data, TEST_USER.id)
    await db_session.flush()

    update_data = AdjustmentUpdate(
        line_items=[
            AdjustmentLineItem(standard_account_code="1002", debit_amount=Decimal("200")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("200")),
        ],
    )
    updated = await svc.update_entry(pid, created.entry_group_id, update_data, TEST_USER.id)
    assert updated.total_debit == Decimal("200")
    assert updated.line_items[0].standard_account_code == "1002"


@pytest.mark.asyncio
async def test_update_approved_rejected(db_session: AsyncSession, seeded_db):
    """approved 状态不可修改"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    create_data = AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    )
    created = await svc.create_entry(pid, create_data, TEST_USER.id)
    await db_session.flush()

    # 提交复核 → 批准
    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.pending_review), TEST_USER.id,
    )
    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.approved), TEST_USER.id,
    )
    await db_session.flush()

    with pytest.raises(ValueError, match="不允许修改"):
        await svc.update_entry(
            pid, created.entry_group_id,
            AdjustmentUpdate(description="尝试修改"), TEST_USER.id,
        )


@pytest.mark.asyncio
async def test_delete_entry(db_session: AsyncSession, seeded_db):
    """软删除"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    create_data = AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    )
    created = await svc.create_entry(pid, create_data, TEST_USER.id)
    await db_session.flush()

    await svc.delete_entry(pid, created.entry_group_id)
    await db_session.flush()

    # 验证已删除
    rows = await svc._get_group_rows(pid, created.entry_group_id)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_delete_approved_rejected(db_session: AsyncSession, seeded_db):
    """approved 状态不可删除"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    create_data = AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    )
    created = await svc.create_entry(pid, create_data, TEST_USER.id)
    await db_session.flush()

    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.pending_review), TEST_USER.id,
    )
    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.approved), TEST_USER.id,
    )
    await db_session.flush()

    with pytest.raises(ValueError, match="不允许删除"):
        await svc.delete_entry(pid, created.entry_group_id)


# ===== 13.3 change_review_status =====

@pytest.mark.asyncio
async def test_review_status_draft_to_pending(db_session: AsyncSession, seeded_db):
    """draft → pending_review"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    created = await svc.create_entry(pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    ), TEST_USER.id)
    await db_session.flush()

    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.pending_review), TEST_USER.id,
    )
    await db_session.flush()

    rows = await svc._get_group_rows(pid, created.entry_group_id)
    assert rows[0].review_status == ReviewStatus.pending_review


@pytest.mark.asyncio
async def test_review_status_pending_to_approved(db_session: AsyncSession, seeded_db):
    """pending_review → approved（记录 reviewer_id + reviewed_at）"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    created = await svc.create_entry(pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    ), TEST_USER.id)
    await db_session.flush()

    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.pending_review), TEST_USER.id,
    )
    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.approved), TEST_USER.id,
    )
    await db_session.flush()

    rows = await svc._get_group_rows(pid, created.entry_group_id)
    assert rows[0].review_status == ReviewStatus.approved
    assert rows[0].reviewer_id == TEST_USER.id
    assert rows[0].reviewed_at is not None


@pytest.mark.asyncio
async def test_review_status_pending_to_rejected(db_session: AsyncSession, seeded_db):
    """pending_review → rejected（需填 reason）"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    created = await svc.create_entry(pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    ), TEST_USER.id)
    await db_session.flush()

    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.pending_review), TEST_USER.id,
    )

    # 无 reason 应拒绝
    with pytest.raises(ValueError, match="必须填写原因"):
        await svc.change_review_status(
            pid, created.entry_group_id,
            ReviewStatusChange(status=ReviewStatus.rejected), TEST_USER.id,
        )

    # 有 reason 应成功
    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.rejected, reason="金额有误"),
        TEST_USER.id,
    )
    await db_session.flush()

    rows = await svc._get_group_rows(pid, created.entry_group_id)
    assert rows[0].review_status == ReviewStatus.rejected
    assert rows[0].rejection_reason == "金额有误"


@pytest.mark.asyncio
async def test_review_status_rejected_to_draft(db_session: AsyncSession, seeded_db):
    """rejected → draft"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    created = await svc.create_entry(pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    ), TEST_USER.id)
    await db_session.flush()

    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.pending_review), TEST_USER.id,
    )
    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.rejected, reason="需修改"),
        TEST_USER.id,
    )
    await svc.change_review_status(
        pid, created.entry_group_id,
        ReviewStatusChange(status=ReviewStatus.draft), TEST_USER.id,
    )
    await db_session.flush()

    rows = await svc._get_group_rows(pid, created.entry_group_id)
    assert rows[0].review_status == ReviewStatus.draft
    assert rows[0].rejection_reason is None


@pytest.mark.asyncio
async def test_review_status_illegal_transition(db_session: AsyncSession, seeded_db):
    """非法转换：draft → approved"""
    pid = seeded_db
    svc = AdjustmentService(db_session)
    created = await svc.create_entry(pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
        ],
    ), TEST_USER.id)
    await db_session.flush()

    with pytest.raises(ValueError, match="非法状态转换"):
        await svc.change_review_status(
            pid, created.entry_group_id,
            ReviewStatusChange(status=ReviewStatus.approved), TEST_USER.id,
        )


# ===== 13.4 get_summary =====

@pytest.mark.asyncio
async def test_get_summary(db_session: AsyncSession, seeded_db):
    """汇总统计"""
    pid = seeded_db
    svc = AdjustmentService(db_session)

    # 创建 2 个 AJE + 1 个 RJE
    for _ in range(2):
        await svc.create_entry(pid, AdjustmentCreate(
            adjustment_type=AdjustmentType.aje, year=2025,
            line_items=[
                AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
                AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
            ],
        ), TEST_USER.id)
        await db_session.flush()

    await svc.create_entry(pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.rje, year=2025,
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("50")),
            AdjustmentLineItem(standard_account_code="1002", credit_amount=Decimal("50")),
        ],
    ), TEST_USER.id)
    await db_session.commit()

    summary = await svc.get_summary(pid, 2025)
    assert summary.aje_count == 2
    assert summary.rje_count == 1
    assert summary.aje_total_debit == Decimal("200")
    assert summary.rje_total_debit == Decimal("50")


# ===== 13.5 API 路由测试 =====

@pytest.mark.asyncio
async def test_api_create_adjustment(client: AsyncClient, seeded_db):
    """POST 创建分录"""
    pid = seeded_db
    resp = await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje",
        "year": 2025,
        "description": "API测试",
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "200", "credit_amount": "0"},
            {"standard_account_code": "6001", "debit_amount": "0", "credit_amount": "200"},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["adjustment_no"] == "AJE-001"
    assert Decimal(str(body["total_debit"])) == Decimal("200")


@pytest.mark.asyncio
async def test_api_create_imbalanced(client: AsyncClient, seeded_db):
    """POST 借贷不平衡返回 400"""
    pid = seeded_db
    resp = await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje",
        "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "200"},
            {"standard_account_code": "6001", "credit_amount": "100"},
        ],
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_list_adjustments(client: AsyncClient, seeded_db):
    """GET 列表"""
    pid = seeded_db
    # 先创建
    await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje", "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "100"},
            {"standard_account_code": "6001", "credit_amount": "100"},
        ],
    })
    resp = await client.get(f"/api/projects/{pid}/adjustments?year=2025")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_api_list_filter_type(client: AsyncClient, seeded_db):
    """GET 列表按类型筛选"""
    pid = seeded_db
    await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje", "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "100"},
            {"standard_account_code": "6001", "credit_amount": "100"},
        ],
    })
    await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "rje", "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "50"},
            {"standard_account_code": "1002", "credit_amount": "50"},
        ],
    })

    resp = await client.get(f"/api/projects/{pid}/adjustments?year=2025&adjustment_type=aje")
    assert resp.json()["total"] == 1

    resp2 = await client.get(f"/api/projects/{pid}/adjustments?year=2025&adjustment_type=rje")
    assert resp2.json()["total"] == 1


@pytest.mark.asyncio
async def test_api_update_adjustment(client: AsyncClient, seeded_db):
    """PUT 修改分录"""
    pid = seeded_db
    create_resp = await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje", "year": 2025,
        "description": "原始",
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "100"},
            {"standard_account_code": "6001", "credit_amount": "100"},
        ],
    })
    group_id = create_resp.json()["entry_group_id"]

    resp = await client.put(f"/api/projects/{pid}/adjustments/{group_id}", json={
        "description": "修改后",
    })
    assert resp.status_code == 200
    assert resp.json()["description"] == "修改后"


@pytest.mark.asyncio
async def test_api_delete_adjustment(client: AsyncClient, seeded_db):
    """DELETE 软删除"""
    pid = seeded_db
    create_resp = await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje", "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "100"},
            {"standard_account_code": "6001", "credit_amount": "100"},
        ],
    })
    group_id = create_resp.json()["entry_group_id"]

    resp = await client.delete(f"/api/projects/{pid}/adjustments/{group_id}")
    assert resp.status_code == 200

    # 列表应为空
    list_resp = await client.get(f"/api/projects/{pid}/adjustments?year=2025")
    assert list_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_api_review_status(client: AsyncClient, seeded_db):
    """POST review 变更状态"""
    pid = seeded_db
    create_resp = await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje", "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "100"},
            {"standard_account_code": "6001", "credit_amount": "100"},
        ],
    })
    group_id = create_resp.json()["entry_group_id"]

    # draft → pending_review
    resp = await client.post(
        f"/api/projects/{pid}/adjustments/{group_id}/review",
        json={"status": "pending_review"},
    )
    assert resp.status_code == 200

    # pending_review → approved
    resp2 = await client.post(
        f"/api/projects/{pid}/adjustments/{group_id}/review",
        json={"status": "approved"},
    )
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_api_summary(client: AsyncClient, seeded_db):
    """GET summary"""
    pid = seeded_db
    await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje", "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "100"},
            {"standard_account_code": "6001", "credit_amount": "100"},
        ],
    })
    resp = await client.get(f"/api/projects/{pid}/adjustments/summary?year=2025")
    assert resp.status_code == 200
    body = resp.json()
    assert body["aje_count"] == 1


# ===== 13.7 account-dropdown =====

@pytest.mark.asyncio
async def test_api_account_dropdown_level1(client: AsyncClient, seeded_db):
    """GET account-dropdown 一级行次"""
    pid = seeded_db
    resp = await client.get(f"/api/projects/{pid}/adjustments/account-dropdown")
    assert resp.status_code == 200
    body = resp.json()
    codes = {item["code"] for item in body}
    assert "BS-001" in codes
    assert "IS-001" in codes


@pytest.mark.asyncio
async def test_api_account_dropdown_level2(client: AsyncClient, seeded_db):
    """GET account-dropdown 二级科目"""
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/adjustments/account-dropdown?report_line_code=BS-001"
    )
    assert resp.status_code == 200
    body = resp.json()
    codes = {item["code"] for item in body}
    assert "1001" in codes
    assert "1002" in codes


# ===== 13.9 / 13.10 wp-summary =====

@pytest.mark.asyncio
async def test_api_wp_summary(client: AsyncClient, seeded_db):
    """GET wp-summary"""
    pid = seeded_db
    # 先创建一笔 AJE
    await client.post(f"/api/projects/{pid}/adjustments", json={
        "adjustment_type": "aje", "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "500"},
            {"standard_account_code": "6001", "credit_amount": "500"},
        ],
    })

    resp = await client.get(
        f"/api/projects/{pid}/adjustments/wp-summary/BS-001?year=2025"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "1001" in body["accounts"]
    assert Decimal(str(body["unadjusted_amount"])) == Decimal("12000")


@pytest.mark.asyncio
async def test_api_wp_summary_empty(client: AsyncClient, seeded_db):
    """GET wp-summary 无关联科目"""
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/adjustments/wp-summary/NONEXIST?year=2025"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accounts"] == []
    assert Decimal(str(body["unadjusted_amount"])) == Decimal("0")
