"""Tests for ReportEngine._fill_equity_matrix (权益变动表二维矩阵填充).

验证：权益变动表「上年年末余额」(EQ-001) 行的各权益构成列，由资产负债表
对应权益科目的上期（prior）审定值填充，写入 source_accounts.eq_matrix 契约。

边界（实现刻意约束，避免编造审计数字）：
- 余额行 EQ-001 写入 current_year / prior_year；无底稿时变动明细行（如 EQ-002）不填。
- 仅匹配负债权益侧科目，排除资产侧同名行（其他权益工具投资/永续债投资）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import MetaData, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.report_engine import ReportEngine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_TEST_TABLES = [Project.__table__, FinancialReport.__table__]


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().drop_all(sync_conn, tables=_TEST_TABLES)
        )


@pytest_asyncio.fixture
async def project(db_session: AsyncSession):
    p = Project(
        id=uuid.uuid4(),
        name="致同测试有限公司",
        client_name="致同测试有限公司",
        template_type="soe",
        report_scope="consolidated",
    )
    db_session.add(p)
    await db_session.flush()
    return p


def _bs(project_id, code, name, current, prior, year=2024):
    now = datetime.now(timezone.utc)
    return FinancialReport(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        report_type=FinancialReportType.balance_sheet,
        row_code=code,
        row_name=name,
        current_period_amount=Decimal(str(current)),
        prior_period_amount=Decimal(str(prior)),
        generated_at=now,
    )


def _eq(project_id, code, name, source_accounts=None):
    now = datetime.now(timezone.utc)
    return FinancialReport(
        id=uuid.uuid4(),
        project_id=project_id,
        year=2024,
        report_type=FinancialReportType.equity_statement,
        row_code=code,
        row_name=name,
        source_accounts=source_accounts,
        generated_at=now,
    )


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession, project: Project):
    """BS 权益行（含资产侧同名干扰行）+ EQ-001/EQ-002 行；含 2023 BS 供 prior_year。"""
    rows = [
        _bs(project.id, "BS-034", "其他权益工具投资", 11111, 22222),
        _bs(project.id, "BS-088", "永续债", 33333, 44444),
        _bs(project.id, "BS-101", "所有者权益：", 0, 0),
        _bs(project.id, "BS-102", "实收资本", 5000000, 4000000),
        _bs(project.id, "BS-110", "其他权益工具", 70000, 60000),
        _bs(project.id, "BS-112", "永续债", 50000, 40000),
        _bs(project.id, "BS-113", "资本公积", 800000, 700000.5),
        _bs(project.id, "BS-114", "减：库存股", -10000, -5000),
        _bs(project.id, "BS-115", "其他综合收益", 12000, 9000),
        _bs(project.id, "BS-117", "专项储备", 3000, 2000),
        _bs(project.id, "BS-118", "盈余公积", 600000, 500000),
        _bs(project.id, "BS-124", "△一般风险准备", 1000, 800),
        _bs(project.id, "BS-125", "未分配利润", 2000000, 1500000),
        _bs(project.id, "BS-126", "归属于母公司所有者权益合计", 9400000, 7900000),
        _bs(project.id, "BS-127", "*少数股东权益", 90000, 80000),
        _bs(project.id, "BS-128", "所有者权益合计", 9500000, 8000000),
        # 再上一年 BS（供 prior_year 块）
        _bs(project.id, "BS-101", "所有者权益：", 0, 0, year=2023),
        _bs(project.id, "BS-102", "实收资本", 4000000, 3500000, year=2023),
        _bs(project.id, "BS-113", "资本公积", 700000, 600000, year=2023),
        _eq(project.id, "EQ-001", "一、上年年末余额"),
        _eq(project.id, "EQ-002", "加：会计政策变更"),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.flush()
    return project


@pytest.mark.asyncio
async def test_fill_equity_matrix_basic(db_session: AsyncSession, seeded: Project):
    engine = ReportEngine(db_session)
    now = datetime.now(timezone.utc)
    await engine._fill_equity_matrix(seeded.id, 2024, "soe_consolidated", now)

    res = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == seeded.id,
            FinancialReport.report_type == FinancialReportType.equity_statement,
            FinancialReport.row_code == "EQ-001",
        )
    )
    eq1 = res.scalar_one()
    matrix = eq1.source_accounts["eq_matrix"]["current_year"]

    assert matrix["share_capital"] == pytest.approx(4000000)
    assert matrix["capital_reserve"] == pytest.approx(700000.5)
    assert matrix["treasury_stock"] == pytest.approx(-5000)
    assert matrix["other_comprehensive_income"] == pytest.approx(9000)
    assert matrix["special_reserve"] == pytest.approx(2000)
    assert matrix["surplus_reserve"] == pytest.approx(500000)
    assert matrix["general_risk_reserve"] == pytest.approx(800)
    assert matrix["retained_earnings"] == pytest.approx(1500000)
    assert matrix["minority_interest"] == pytest.approx(80000)
    assert matrix["total_equity"] == pytest.approx(8000000)


@pytest.mark.asyncio
async def test_fill_equity_matrix_prior_year_block(db_session: AsyncSession, seeded: Project):
    """EQ-001 同时写入 prior_year（来自 year-1 BS 上期）。"""
    engine = ReportEngine(db_session)
    now = datetime.now(timezone.utc)
    await engine._fill_equity_matrix(seeded.id, 2024, "soe_consolidated", now)

    res = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == seeded.id,
            FinancialReport.row_code == "EQ-001",
        )
    )
    py = res.scalar_one().source_accounts["eq_matrix"]["prior_year"]
    assert py["share_capital"] == pytest.approx(3500000)
    assert py["capital_reserve"] == pytest.approx(600000)


@pytest.mark.asyncio
async def test_fill_equity_matrix_total_equity_exact_match(db_session: AsyncSession, seeded: Project):
    engine = ReportEngine(db_session)
    now = datetime.now(timezone.utc)
    await engine._fill_equity_matrix(seeded.id, 2024, "soe_consolidated", now)

    res = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == seeded.id,
            FinancialReport.row_code == "EQ-001",
        )
    )
    matrix = res.scalar_one().source_accounts["eq_matrix"]["current_year"]
    assert matrix["total_equity"] == pytest.approx(8000000)


@pytest.mark.asyncio
async def test_fill_equity_matrix_excludes_asset_side(db_session: AsyncSession, seeded: Project):
    engine = ReportEngine(db_session)
    now = datetime.now(timezone.utc)
    await engine._fill_equity_matrix(seeded.id, 2024, "soe_consolidated", now)

    res = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == seeded.id,
            FinancialReport.row_code == "EQ-001",
        )
    )
    matrix = res.scalar_one().source_accounts["eq_matrix"]["current_year"]
    assert matrix["other_equity_instrument"] == pytest.approx(60000)
    assert matrix["perpetual_bond"] == pytest.approx(40000)


@pytest.mark.asyncio
async def test_fill_equity_matrix_does_not_fill_eq002_without_wp(
    db_session: AsyncSession, seeded: Project,
):
    """无底稿时 EQ-002 等变动行不自动填充（仅 EQ-001 余额行）。"""
    engine = ReportEngine(db_session)
    now = datetime.now(timezone.utc)
    await engine._fill_equity_matrix(seeded.id, 2024, "soe_consolidated", now)

    res = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == seeded.id,
            FinancialReport.row_code == "EQ-002",
        )
    )
    eq2 = res.scalar_one()
    assert eq2.source_accounts is None


@pytest.mark.asyncio
async def test_fill_equity_matrix_preserves_existing_source_accounts(
    db_session: AsyncSession, project: Project,
):
    db_session.add(_bs(project.id, "BS-102", "实收资本", 5000000, 4000000))
    db_session.add(
        _eq(project.id, "EQ-001", "一、上年年末余额", source_accounts={"existing": ["4001"]})
    )
    await db_session.flush()

    engine = ReportEngine(db_session)
    now = datetime.now(timezone.utc)
    await engine._fill_equity_matrix(project.id, 2024, "soe_consolidated", now)

    res = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == project.id,
            FinancialReport.row_code == "EQ-001",
        )
    )
    eq1 = res.scalar_one()
    assert eq1.source_accounts["existing"] == ["4001"]
    assert eq1.source_accounts["eq_matrix"]["current_year"]["share_capital"] == pytest.approx(4000000)


@pytest.mark.asyncio
async def test_fill_equity_matrix_no_bs_rows_noop(db_session: AsyncSession, project: Project):
    db_session.add(_eq(project.id, "EQ-001", "一、上年年末余额"))
    await db_session.flush()

    engine = ReportEngine(db_session)
    now = datetime.now(timezone.utc)
    await engine._fill_equity_matrix(project.id, 2024, "soe_consolidated", now)

    res = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == project.id,
            FinancialReport.row_code == "EQ-001",
        )
    )
    eq1 = res.scalar_one()
    assert eq1.source_accounts is None
