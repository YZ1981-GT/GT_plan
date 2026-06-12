"""P3: 权益变动表架构收尾 — 双路径合并、未审交付、多标准行次解析."""
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
from app.services.report_engine import (
    ReportEngine,
    resolve_eq_semantic_row_codes,
)

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


def _listed_eq_rows() -> list[dict]:
    """上市合并版行次：综合收益=EQ-008，分配=EQ-017（非国企 EQ-007/024）。"""
    names = [
        ("EQ-001", "一、上年年末余额"),
        ("EQ-007", "三、本年增减变动金额（减少以“-”号填列）"),
        ("EQ-008", "（一）综合收益总额"),
        ("EQ-015", "1．提取盈余公积"),
        ("EQ-017", "3．对股东（或所有者）的分配"),
    ]
    return [{"row_code": c, "row_name": n} for c, n in names]


def test_resolve_eq_semantic_row_codes_listed_offset():
    sem = resolve_eq_semantic_row_codes(_listed_eq_rows())
    assert sem["prior_year_end"] == "EQ-001"
    assert sem["comprehensive_income"] == "EQ-008"
    assert sem["surplus_extract"] == "EQ-015"
    assert sem["dividend"] == "EQ-017"


@pytest.mark.asyncio
async def test_enrich_preserves_manual_edit_over_bs(db_session: AsyncSession):
    """enrich 合并：手工编辑优先，BS 仅填补空缺列。"""
    project = Project(
        id=uuid.uuid4(),
        name="P3手工优先",
        client_name="P3手工优先",
        template_type="soe",
        report_scope="standalone",
    )
    db_session.add(project)
    now = datetime.now(timezone.utc)
    for code, name, cur, prior in [
        ("BS-101", "所有者权益：", 0, 0),
        ("BS-102", "实收资本", 5000000, 4000000),
        ("BS-113", "资本公积", 800000, 700000),
        ("BS-125", "未分配利润", 2000000, 1500000),
        ("BS-128", "所有者权益合计", 7800000, 6200000),
    ]:
        db_session.add(
            FinancialReport(
                id=uuid.uuid4(),
                project_id=project.id,
                year=2024,
                report_type=FinancialReportType.balance_sheet,
                row_code=code,
                row_name=name,
                current_period_amount=Decimal(str(cur)),
                prior_period_amount=Decimal(str(prior)),
                generated_at=now,
            )
        )
    db_session.add(
        FinancialReport(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            report_type=FinancialReportType.equity_statement,
            row_code="EQ-001",
            row_name="一、上年年末余额",
            source_accounts={
                "eq_matrix": {
                    "current_year": {"share_capital": 9999999.0},
                }
            },
            generated_at=now,
        )
    )
    await db_session.flush()

    engine = ReportEngine(db_session)
    eq_rows = [
        {
            "row_code": "EQ-001",
            "row_name": "一、上年年末余额",
            "source_accounts": {
                "eq_matrix": {"current_year": {"share_capital": 9999999.0}}
            },
        }
    ]
    enriched = await engine.enrich_equity_statement_rows(project.id, 2024, eq_rows)
    cy = enriched[0]["source_accounts"]["eq_matrix"]["current_year"]
    assert cy["share_capital"] == pytest.approx(9999999.0)
    assert cy["capital_reserve"] == pytest.approx(700000.0)


@pytest.mark.asyncio
async def test_listed_is_net_profit_targets_eq008(db_session: AsyncSession):
    """上市行次：IS 净利润写入 EQ-008 而非 EQ-007。"""
    project = Project(
        id=uuid.uuid4(),
        name="P3上市EQ",
        client_name="P3上市EQ",
        template_type="listed",
        report_scope="consolidated",
    )
    db_session.add(project)
    now = datetime.now(timezone.utc)
    for row in _listed_eq_rows():
        db_session.add(
            FinancialReport(
                id=uuid.uuid4(),
                project_id=project.id,
                year=2024,
                report_type=FinancialReportType.equity_statement,
                row_code=row["row_code"],
                row_name=row["row_name"],
                generated_at=now,
            )
        )
    db_session.add(
        FinancialReport(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            report_type=FinancialReportType.income_statement,
            row_code="IS-024",
            row_name="净利润",
            current_period_amount=Decimal("55555"),
            generated_at=now,
        )
    )
    await db_session.flush()

    engine = ReportEngine(db_session)
    res = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == project.id,
            FinancialReport.report_type == FinancialReportType.equity_statement,
        )
    )
    eq_rows = [
        {
            "row_code": r.row_code,
            "row_name": r.row_name,
            "source_accounts": r.source_accounts,
        }
        for r in res.scalars().all()
    ]
    enriched = await engine.enrich_equity_statement_rows(project.id, 2024, eq_rows)
    eq008 = next(r for r in enriched if r["row_code"] == "EQ-008")
    cy = eq008["source_accounts"]["eq_matrix"]["current_year"]
    assert cy["retained_earnings"] == pytest.approx(55555.0)
    eq007 = next(r for r in enriched if r["row_code"] == "EQ-007")
    assert eq007.get("source_accounts") is None or "eq_matrix" not in (eq007.get("source_accounts") or {})
