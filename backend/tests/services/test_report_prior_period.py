"""报表上期 / 期初金额来源（spec deliverable-trio-generation-accuracy §1.3）。

真实库项目按年度建立、同项目没有上年试算表 ⇒ 旧口径（同项目 year-1 重算）上期恒 0。
- 时点报表（资产负债表）：本年试算表期初数；本年没有任何期初数 ⇒ None（留空，不写 0）；
- 期间报表（利润表等）：上年项目报表行（同码同名 → 唯一同名）→ 上年项目试算表 → None。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.report_prior_period import PriorPeriodResolver

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

IS = FinancialReportType.income_statement
BS = FinancialReportType.balance_sheet


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Project.__table__, TrialBalance.__table__, FinancialReport.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: MetaData().create_all(c, tables=tables))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


def _cfg(code: str, name: str, formula: str | None = None):
    return SimpleNamespace(row_code=code, row_name=name, formula=formula)


def _tb(pid, year, code, closing, opening=None):
    return TrialBalance(
        project_id=pid, year=year, company_code="001", standard_account_code=code, account_name=code,
        account_category=AccountCategory.asset, unadjusted_amount=Decimal(closing), audited_amount=Decimal(closing),
        opening_balance=None if opening is None else Decimal(opening),
    )


async def _projects(db, *, with_prior: bool):
    cur, prior = uuid.uuid4(), uuid.uuid4()
    db.add(Project(id=cur, name="甲_2025", client_name="甲公司", company_code="C1", audit_year=2025,
                   report_scope="standalone"))
    if with_prior:
        db.add(Project(id=prior, name="甲_2024", client_name="甲公司", company_code="C1", audit_year=2024,
                       report_scope="standalone"))
    await db.flush()
    return cur, prior


@pytest.mark.asyncio
async def test_balance_sheet_prior_is_current_year_opening_or_blank(db):
    cur, _ = await _projects(db, with_prior=False)
    resolver = PriorPeriodResolver(db, cur, 2025)
    assert await resolver.prior_amount(BS, _cfg("BS-002", "货币资金", "TB('1002','期末余额')")) is None  # 无期初数

    db.add_all([_tb(cur, 2025, "1002", 100, 80), _tb(cur, 2025, "1001", 5, 2)])
    await db.flush()
    resolver = PriorPeriodResolver(db, cur, 2025)
    value = await resolver.prior_amount(
        BS, _cfg("BS-002", "货币资金", "TB('1001','期末余额') + TB('1002', '期末余额')"),
    )
    assert value == Decimal("82")


@pytest.mark.asyncio
async def test_income_statement_prior_from_prior_year_project_report(db):
    cur, prior = await _projects(db, with_prior=True)
    now = datetime.now(timezone.utc)
    db.add_all([
        FinancialReport(id=uuid.uuid4(), project_id=prior, year=2024, report_type=IS, row_code="IS-001",
                        row_name="营业收入", current_period_amount=Decimal("900"), generated_at=now),
        # 上年报表用另一套编号：编码不同、行名唯一 ⇒ 按行名取
        FinancialReport(id=uuid.uuid4(), project_id=prior, year=2024, report_type=IS, row_code="IS-050",
                        row_name="五、净利润（净亏损以“－”号填列）", current_period_amount=Decimal("30"),
                        generated_at=now),
        # 同码不同名：不按编码硬取
        FinancialReport(id=uuid.uuid4(), project_id=prior, year=2024, report_type=IS, row_code="IS-007",
                        row_name="资产减值损失", current_period_amount=Decimal("7"), generated_at=now),
    ])
    await db.flush()
    resolver = PriorPeriodResolver(db, cur, 2025)
    assert await resolver.prior_amount(IS, _cfg("IS-001", "营业收入")) == Decimal("900")
    assert await resolver.prior_amount(IS, _cfg("IS-024", "四、净利润")) == Decimal("30")
    assert await resolver.prior_amount(IS, _cfg("IS-007", "财务费用")) is None


@pytest.mark.asyncio
async def test_income_statement_prior_falls_back_to_prior_project_tb_then_blank(db):
    cur, prior = await _projects(db, with_prior=True)
    resolver = PriorPeriodResolver(db, cur, 2025)
    assert await resolver.prior_amount(IS, _cfg("IS-001", "营业收入", "TB('6001','期末余额')")) is None

    db.add(_tb(prior, 2024, "6001", 777))
    await db.flush()
    resolver = PriorPeriodResolver(db, cur, 2025)
    assert await resolver.prior_amount(IS, _cfg("IS-001", "营业收入", "TB('6001','期末余额')")) == Decimal("777")
