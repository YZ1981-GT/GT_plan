"""四表联动穿透查询测试

Validates: Requirements 5.1-5.9
"""

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
from app.models.base import Base, UserRole
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.routers.drilldown import router

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
    """创建穿透查询测试数据并返回 project_id"""
    project = Project(
        id=uuid.uuid4(),
        name="穿透测试公司_2025",
        client_name="穿透测试公司",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=TEST_USER.id,
    )
    db_session.add(project)
    await db_session.flush()
    pid = project.id

    # 客户科目表
    db_session.add_all([
        AccountChart(
            project_id=pid, account_code="1001", account_name="库存现金",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.client,
        ),
        AccountChart(
            project_id=pid, account_code="1002", account_name="银行存款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.client,
        ),
        AccountChart(
            project_id=pid, account_code="6001", account_name="主营业务收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.client,
        ),
    ])

    # 余额表
    db_session.add_all([
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="1001", account_name="库存现金",
            opening_balance=Decimal("10000"), debit_amount=Decimal("5000"),
            credit_amount=Decimal("3000"), closing_balance=Decimal("12000"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="1002", account_name="银行存款",
            opening_balance=Decimal("50000"), debit_amount=Decimal("20000"),
            credit_amount=Decimal("15000"), closing_balance=Decimal("55000"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="6001", account_name="主营业务收入",
            opening_balance=Decimal("0"), debit_amount=Decimal("0"),
            credit_amount=Decimal("100000"), closing_balance=Decimal("100000"),
        ),
    ])

    # 序时账
    db_session.add_all([
        TbLedger(
            project_id=pid, year=2025, company_code="001",
            voucher_date=date(2025, 1, 15), voucher_no="记-001",
            account_code="1001", account_name="库存现金",
            debit_amount=Decimal("3000"), credit_amount=Decimal("0"),
            counterpart_account="6001", summary="销售收款", preparer="张三",
        ),
        TbLedger(
            project_id=pid, year=2025, company_code="001",
            voucher_date=date(2025, 2, 10), voucher_no="记-002",
            account_code="1001", account_name="库存现金",
            debit_amount=Decimal("2000"), credit_amount=Decimal("0"),
            counterpart_account="1002", summary="银行提现", preparer="李四",
        ),
        TbLedger(
            project_id=pid, year=2025, company_code="001",
            voucher_date=date(2025, 3, 5), voucher_no="记-003",
            account_code="1001", account_name="库存现金",
            debit_amount=Decimal("0"), credit_amount=Decimal("3000"),
            counterpart_account="1002", summary="存入银行", preparer="张三",
        ),
    ])

    # 辅助余额表（银行存款有辅助核算）
    db_session.add_all([
        TbAuxBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="1002", aux_type="bank", aux_code="B001",
            aux_name="工商银行",
            opening_balance=Decimal("30000"), debit_amount=Decimal("10000"),
            credit_amount=Decimal("8000"), closing_balance=Decimal("32000"),
        ),
        TbAuxBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="1002", aux_type="bank", aux_code="B002",
            aux_name="建设银行",
            opening_balance=Decimal("20000"), debit_amount=Decimal("10000"),
            credit_amount=Decimal("7000"), closing_balance=Decimal("23000"),
        ),
    ])

    # 辅助明细账
    db_session.add_all([
        TbAuxLedger(
            project_id=pid, year=2025, company_code="001",
            voucher_date=date(2025, 1, 20), voucher_no="记-004",
            account_code="1002", aux_type="bank", aux_code="B001",
            aux_name="工商银行",
            debit_amount=Decimal("5000"), credit_amount=Decimal("0"),
            summary="客户回款",
        ),
        TbAuxLedger(
            project_id=pid, year=2025, company_code="001",
            voucher_date=date(2025, 2, 15), voucher_no="记-005",
            account_code="1002", aux_type="bank", aux_code="B002",
            aux_name="建设银行",
            debit_amount=Decimal("0"), credit_amount=Decimal("3000"),
            summary="支付货款",
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


# ===== 余额表查询 =====

@pytest.mark.asyncio
async def test_balance_list_basic(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(f"/api/projects/{pid}/drilldown/balance?year=2025")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


@pytest.mark.asyncio
async def test_balance_filter_category(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/drilldown/balance?year=2025&category=asset"
    )
    body = resp.json()
    assert body["total"] == 2
    codes = {i["account_code"] for i in body["items"]}
    assert codes == {"1001", "1002"}


@pytest.mark.asyncio
async def test_balance_filter_keyword(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/drilldown/balance?year=2025&keyword=银行"
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["account_code"] == "1002"


@pytest.mark.asyncio
async def test_balance_has_aux_flag(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(f"/api/projects/{pid}/drilldown/balance?year=2025")
    items = {i["account_code"]: i for i in resp.json()["items"]}
    assert items["1002"]["has_aux"] is True
    assert items["1001"]["has_aux"] is False


@pytest.mark.asyncio
async def test_balance_pagination(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/drilldown/balance?year=2025&page=1&page_size=2"
    )
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    resp2 = await client.get(
        f"/api/projects/{pid}/drilldown/balance?year=2025&page=2&page_size=2"
    )
    assert len(resp2.json()["items"]) == 1


# ===== 序时账穿透 =====

@pytest.mark.asyncio
async def test_ledger_drilldown(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(f"/api/projects/{pid}/drilldown/ledger/1001?year=2025")
    body = resp.json()
    assert body["total"] == 3


@pytest.mark.asyncio
async def test_ledger_filter_date_range(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/drilldown/ledger/1001?year=2025"
        "&date_from=2025-02-01&date_to=2025-02-28"
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["voucher_no"] == "记-002"


@pytest.mark.asyncio
async def test_ledger_filter_summary(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/drilldown/ledger/1001?year=2025&summary_keyword=银行"
    )
    body = resp.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_ledger_filter_counterpart(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/drilldown/ledger/1001?year=2025&counterpart_account=6001"
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["summary"] == "销售收款"


# ===== 辅助余额表穿透 =====

@pytest.mark.asyncio
async def test_aux_balance_drilldown(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(f"/api/projects/{pid}/drilldown/aux-balance/1002?year=2025")
    body = resp.json()
    assert len(body) == 2
    codes = {i["aux_code"] for i in body}
    assert codes == {"B001", "B002"}


# ===== 辅助明细账穿透 =====

@pytest.mark.asyncio
async def test_aux_ledger_drilldown(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(f"/api/projects/{pid}/drilldown/aux-ledger/1002?year=2025")
    body = resp.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_aux_ledger_filter_by_aux(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(
        f"/api/projects/{pid}/drilldown/aux-ledger/1002?year=2025"
        "&aux_type=bank&aux_code=B001"
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["aux_name"] == "工商银行"


@pytest.mark.asyncio
async def test_empty_drilldown(client: AsyncClient, seeded_db):
    pid = seeded_db
    resp = await client.get(f"/api/projects/{pid}/drilldown/ledger/9999?year=2025")
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
