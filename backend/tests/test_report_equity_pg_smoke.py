"""P2-11: 权益 eq_matrix JSONB 真 PG 冒烟测试.

CI 连 PostgreSQL 时验证 source_accounts.eq_matrix 读写与 enrich 不报错。
SQLite 环境自动 skip（conftest pytest_collection_modifyitems）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.report_engine import ReportEngine


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_pg_eq_matrix_jsonb_roundtrip(db_session):
    """JSONB 契约：写入 nested eq_matrix 后原样读出。"""
    project = Project(
        id=uuid.uuid4(),
        name="PG权益冒烟",
        client_name="PG权益冒烟",
        template_type="soe",
        report_scope="standalone",
    )
    db_session.add(project)
    now = datetime.now(timezone.utc)
    matrix = {
        "eq_matrix": {
            "current_year": {"share_capital": 100.0, "total_equity": 500.0},
            "prior_year": {"share_capital": 90.0},
        }
    }
    row = FinancialReport(
        id=uuid.uuid4(),
        project_id=project.id,
        year=2024,
        report_type=FinancialReportType.equity_statement,
        row_code="EQ-001",
        row_name="一、上年年末余额",
        source_accounts=matrix,
        generated_at=now,
    )
    db_session.add(row)
    await db_session.flush()
    await db_session.commit()

    res = await db_session.execute(
        select(FinancialReport).where(FinancialReport.id == row.id)
    )
    loaded = res.scalar_one()
    assert loaded.source_accounts["eq_matrix"]["current_year"]["share_capital"] == 100.0
    assert loaded.source_accounts["eq_matrix"]["prior_year"]["share_capital"] == 90.0


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_pg_enrich_equity_statement_rows_smoke(db_session):
    """enrich 在真 PG 上可对 EQ 行执行（无 BS 时不报错）。"""
    project = Project(
        id=uuid.uuid4(),
        name="PG enrich冒烟",
        client_name="PG enrich冒烟",
        template_type="soe",
        report_scope="standalone",
    )
    db_session.add(project)
    now = datetime.now(timezone.utc)
    db_session.add(
        FinancialReport(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            report_type=FinancialReportType.income_statement,
            row_code="IS-024",
            row_name="净利润",
            current_period_amount=Decimal("12345"),
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
    eq_rows = [
        {"row_code": "EQ-007", "row_name": "综合收益总额", "source_accounts": None},
    ]
    enriched = await engine.enrich_equity_statement_rows(project.id, 2024, eq_rows)
    cy = enriched[0]["source_accounts"]["eq_matrix"]["current_year"]
    assert cy["retained_earnings"] == pytest.approx(12345.0)
