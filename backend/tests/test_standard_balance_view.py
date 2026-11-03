"""标准科目余额视图（GET /trial-balance/standard-view）：取数口径 + 端点鉴权。

口径要点（见 standard_balance_view_service 模块说明）：
- 本期借贷 = tb_balance 叶子经映射汇总（多对一相加）
- 借贷方审计调整只计已批准、非底稿来源，且借贷分别汇总不轧差
- 金额借正贷负：贷方科目的期初 / 期末为负
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
import sqlalchemy as sa

from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    MappingType,
    ReviewStatus,
    TbBalance,
    TrialBalance,
)
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.routers.trial_balance import router as tb_router
from app.services.standard_balance_view_service import build_standard_balance_view
from app.services.trial_balance_service import TrialBalanceService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_UID = uuid.uuid4()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


async def _add_adj(db, pid, *, code, debit, credit, status=ReviewStatus.approved, origin="manual"):
    adj_id, grp = uuid.uuid4(), uuid.uuid4()
    db.add(Adjustment(
        id=adj_id, project_id=pid, year=2025, company_code="001",
        adjustment_no=f"AJE-{uuid.uuid4().hex[:6]}", adjustment_type=AdjustmentType.aje,
        account_code=code, account_name=code, debit_amount=debit, credit_amount=credit,
        entry_group_id=grp, review_status=status, origin=origin,
        is_deleted=False, created_by=_UID,
    ))
    db.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
        standard_account_code=code, account_name=code,
        debit_amount=debit, credit_amount=credit, is_deleted=False,
    ))
    await db.flush()


@pytest_asyncio.fixture
async def pid(db: AsyncSession):
    project = Project(
        id=uuid.uuid4(), name="标准科目视图_2025", client_name="视图测试",
        project_type=ProjectType.annual, status=ProjectStatus.planning, created_by=_UID,
    )
    db.add(project)
    await db.flush()
    p = project.id
    for orig, std in (("C1002", "1002"), ("C1003", "1002"), ("C2202", "2202"), ("C6001", "6001")):
        db.add(AccountMapping(
            project_id=p, original_account_code=orig, original_account_name=orig,
            standard_account_code=std, mapping_type=MappingType.manual, created_by=_UID,
        ))

    def bal(code, opening, closing, dr, cr, direction=None):
        return TbBalance(
            project_id=p, year=2025, company_code="001", account_code=code, account_name=code,
            opening_balance=Decimal(opening), closing_balance=Decimal(closing),
            debit_amount=Decimal(dr), credit_amount=Decimal(cr),
            opening_direction=direction, closing_direction=direction,
        )

    db.add_all([
        bal("C1002", "30000", "35000", "10000", "5000"),
        bal("C1003", "20000", "22000", "5000", "3000"),
        bal("C2202", "6000", "8000", "0", "2000", "credit"),
        bal("C6001", "0", "100000", "0", "100000", "credit"),
    ])
    await db.flush()
    await TrialBalanceService(db).recalc_unadjusted(p, 2025)
    await _add_adj(db, p, code="1002", debit=Decimal("500"), credit=Decimal("0"))
    await _add_adj(db, p, code="6001", debit=Decimal("0"), credit=Decimal("500"))
    # 不计入：草稿、底稿来源
    await _add_adj(db, p, code="1002", debit=Decimal("999"), credit=Decimal("0"), status=ReviewStatus.draft)
    await _add_adj(db, p, code="1002", debit=Decimal("777"), credit=Decimal("0"), origin="workpaper")
    await db.commit()
    return p


def _row(rows, code):
    return next(r for r in rows if r["standard_account_code"] == code)


@pytest.mark.asyncio
async def test_period_amounts_and_adjustments(db, pid):
    rows = await build_standard_balance_view(db, pid, 2025)
    cash = _row(rows, "1002")
    # 多对一：两个客户科目相加
    assert Decimal(cash["period_debit"]) == Decimal("15000")
    assert Decimal(cash["period_credit"]) == Decimal("8000")
    assert Decimal(cash["opening_balance"]) == Decimal("50000")
    assert Decimal(cash["closing_balance"]) == Decimal("57000")
    # 只计已批准、非底稿来源（草稿 999、底稿 777 不进）
    assert Decimal(cash["adjustment_debit"]) == Decimal("500")
    assert Decimal(cash["adjustment_credit"]) == Decimal("0")
    assert Decimal(cash["adjusted_closing_balance"]) == Decimal("57500")


@pytest.mark.asyncio
async def test_name_comes_from_standard_chart(db, pid):
    """试算表行名可能是客户科目名（真库 1122 显示「\\银行存款」），视图显示标准科目名。"""
    db.add(AccountChart(
        project_id=pid, account_code="2202", account_name="应付账款",
        direction=AccountDirection.credit, level=1,
        category=AccountCategory.liability, source=AccountSource.standard,
    ))
    tb = (await db.execute(
        sa.select(TrialBalance).where(TrialBalance.project_id == pid, TrialBalance.standard_account_code == "2202")
    )).scalar_one()
    tb.account_name = "\\应付账款_客户名"
    await db.commit()
    rows = await build_standard_balance_view(db, pid, 2025)
    assert _row(rows, "2202")["account_name"] == "应付账款"


@pytest.mark.asyncio
async def test_credit_accounts_are_negative(db, pid):
    rows = await build_standard_balance_view(db, pid, 2025)
    payable = _row(rows, "2202")
    assert payable["direction"] == "credit"
    assert Decimal(payable["opening_balance"]) == Decimal("-6000")
    assert Decimal(payable["closing_balance"]) == Decimal("-8000")
    revenue = _row(rows, "6001")
    assert Decimal(revenue["adjustment_credit"]) == Decimal("500")
    assert Decimal(revenue["adjusted_closing_balance"]) == Decimal("-100500")


def _app(db, user=None) -> FastAPI:
    app = FastAPI()
    app.include_router(tb_router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.mark.asyncio
async def test_endpoint_returns_rows_for_admin(db, pid):
    admin = User(id=uuid.uuid4(), username="admin_v", email="a@v.t", hashed_password="x", role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=_app(db, admin)), base_url="http://t") as c:
        r = await c.get(f"/api/projects/{pid}/trial-balance/standard-view", params={"year": 2025})
    assert r.status_code == 200
    assert {row["standard_account_code"] for row in r.json()} >= {"1002", "2202", "6001"}


@pytest.mark.asyncio
async def test_endpoint_requires_login(db, pid):
    async with AsyncClient(transport=ASGITransport(app=_app(db)), base_url="http://t") as c:
        r = await c.get(f"/api/projects/{pid}/trial-balance/standard-view", params={"year": 2025})
    assert r.status_code == 401
