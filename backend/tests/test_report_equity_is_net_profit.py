"""EQ-007 利润表净利润 fallback 测试."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import MetaData, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.report_engine import (
    ReportEngine,
    _apply_is_net_profit_to_eq_rows,
    _financial_report_row_to_dict,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_TEST_TABLES = [Project.__table__, FinancialReport.__table__]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    session_factory = async_sessionmaker(
        _test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
    async with _test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().drop_all(sync_conn, tables=_TEST_TABLES)
        )


def test_apply_is_net_profit_writes_eq007():
    eq_rows = [
        {"row_code": "EQ-007", "row_name": "综合收益总额", "source_accounts": None},
    ]
    is_rows = [
        {"row_code": "IS-024", "current_period_amount": "1500000"},
    ]
    _apply_is_net_profit_to_eq_rows(eq_rows, is_rows)
    matrix = eq_rows[0]["source_accounts"]["eq_matrix"]["current_year"]
    assert matrix["retained_earnings"] == pytest.approx(1500000.0)


def test_apply_is_net_profit_skips_when_wp_already_set():
    eq_rows = [
        {
            "row_code": "EQ-007",
            "source_accounts": {
                "eq_matrix": {"current_year": {"retained_earnings": 999}},
            },
        },
    ]
    is_rows = [{"row_code": "IS-024", "current_period_amount": "1500000"}]
    _apply_is_net_profit_to_eq_rows(eq_rows, is_rows)
    matrix = eq_rows[0]["source_accounts"]["eq_matrix"]["current_year"]
    assert matrix["retained_earnings"] == 999


@pytest.mark.asyncio
async def test_enrich_equity_applies_is_net_profit(db_session: AsyncSession):
    project = Project(
        id=uuid.uuid4(),
        name="IS净利润EQ测试",
        client_name="IS净利润EQ测试",
        template_type="soe",
        report_scope="standalone",
    )
    db_session.add(project)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add(
        FinancialReport(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            report_type=FinancialReportType.income_statement,
            row_code="IS-024",
            row_name="净利润",
            current_period_amount="2500000",
            generated_at=now,
        )
    )
    db_session.add(
        FinancialReport(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            report_type=FinancialReportType.equity_statement,
            row_code="EQ-007",
            row_name="综合收益总额",
            generated_at=now,
        )
    )
    await db_session.flush()

    engine = ReportEngine(db_session)
    eq_result = await db_session.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == project.id,
            FinancialReport.report_type == FinancialReportType.equity_statement,
        )
    )
    eq_rows = [_financial_report_row_to_dict(r) for r in eq_result.scalars().all()]
    enriched = await engine.enrich_equity_statement_rows(project.id, 2024, eq_rows)
    eq7 = next(r for r in enriched if r["row_code"] == "EQ-007")
    assert eq7["source_accounts"]["eq_matrix"]["current_year"]["retained_earnings"] == pytest.approx(
        2500000.0,
    )
