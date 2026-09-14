"""未审权益变动表 eq_matrix 取数链路测试.

验证：
- generate_unadjusted_report(equity_statement) 从四表未审 BS 上期构建 eq_matrix
- get_unadjusted_export_data 供 Excel 未审导出
- enrich_equity_statement_rows 供交付成果审定导出内存回填
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpFileStatus
from app.services.report_engine import (
    ReportEngine,
    _build_eq_col_values_from_bs_rows,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()

_TEST_TABLES = [
    Project.__table__,
    TrialBalance.__table__,
    ReportConfig.__table__,
    FinancialReport.__table__,
    WpIndex.__table__,
    WorkingPaper.__table__,
]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().drop_all(sync_conn, tables=_TEST_TABLES)
        )


@pytest_asyncio.fixture
async def equity_seed(db_session: AsyncSession):
    project = Project(
        id=FAKE_PROJECT_ID,
        name="未审权益测试",
        client_name="未审权益测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
        template_type="soe",
        report_scope="standalone",
    )
    db_session.add(project)
    await db_session.flush()

    tb_rows = [
        ("4001", "实收资本", AccountCategory.equity, Decimal("5000000"), Decimal("4800000"), Decimal("4000000")),
        ("4002", "资本公积", AccountCategory.equity, Decimal("800000"), Decimal("750000"), Decimal("700000")),
        ("4104", "未分配利润", AccountCategory.equity, Decimal("2000000"), Decimal("1900000"), Decimal("1500000")),
    ]
    for year in (2023, 2024):
        for code, name, cat, audited, unadjusted, opening in tb_rows:
            # 2023 年期末 = 2024 年「上年年末余额」口径
            yr_audited = opening if year == 2023 else audited
            yr_unadjusted = opening if year == 2023 else unadjusted
            db_session.add(
                TrialBalance(
                    project_id=FAKE_PROJECT_ID,
                    year=year,
                    company_code="default",
                    standard_account_code=code,
                    account_name=name,
                    account_category=cat,
                    audited_amount=yr_audited,
                    unadjusted_amount=yr_unadjusted,
                    opening_balance=opening,
                )
            )

    bs_configs = [
        ("BS-101", "所有者权益：", None, 101, 0, False),
        ("BS-102", "实收资本", "TB('4001','期末余额')", 102, 0, False),
        ("BS-113", "资本公积", "TB('4002','期末余额')", 113, 0, False),
        ("BS-125", "未分配利润", "TB('4104','期末余额')", 125, 0, False),
        ("BS-128", "所有者权益合计", "ROW('BS-102')+ROW('BS-113')+ROW('BS-125')", 128, 0, True),
    ]
    for row_code, row_name, formula, row_num, indent, is_total in bs_configs:
        db_session.add(
            ReportConfig(
                applicable_standard="soe_standalone",
                report_type=FinancialReportType.balance_sheet,
                row_code=row_code,
                row_name=row_name,
                formula=formula,
                row_number=row_num,
                indent_level=indent,
                is_total_row=is_total,
            )
        )

    eq_configs = [
        ("EQ-001", "一、上年年末余额", None, 1, 0, False),
        ("EQ-007", "（一）综合收益总额", None, 7, 0, True),
        ("EQ-017", "1.提取盈余公积", None, 17, 1, False),
        ("EQ-024", "3.对所有者（或股东）的分配", None, 24, 1, False),
    ]
    for row_code, row_name, formula, row_num, indent, is_total in eq_configs:
        db_session.add(
            ReportConfig(
                applicable_standard="soe_standalone",
                report_type=FinancialReportType.equity_statement,
                row_code=row_code,
                row_name=row_name,
                formula=formula,
                row_number=row_num,
                indent_level=indent,
                is_total_row=is_total,
            )
        )

    await db_session.flush()
    return db_session


def test_build_eq_col_values_from_bs_dict_rows():
    bs_rows = [
        {"row_code": "BS-101", "row_name": "所有者权益：", "prior_period_amount": "0"},
        {"row_code": "BS-102", "row_name": "实收资本", "prior_period_amount": "4000000"},
        {"row_code": "BS-113", "row_name": "资本公积", "prior_period_amount": "700000.5"},
        {"row_code": "BS-125", "row_name": "未分配利润", "prior_period_amount": "1500000"},
    ]
    cols = _build_eq_col_values_from_bs_rows(bs_rows, "prior_period_amount")
    assert cols["share_capital"] == pytest.approx(4000000)
    assert cols["capital_reserve"] == pytest.approx(700000.5)
    assert cols["retained_earnings"] == pytest.approx(1500000)


@pytest.mark.asyncio
async def test_generate_unadjusted_equity_has_eq_matrix(db_session: AsyncSession, equity_seed):
    engine = ReportEngine(db_session)
    rows = await engine.generate_unadjusted_report(
        FAKE_PROJECT_ID, 2024, FinancialReportType.equity_statement,
    )
    eq001 = next(r for r in rows if r["row_code"] == "EQ-001")
    matrix = eq001["source_accounts"]["eq_matrix"]["current_year"]
    # 未审 BS 上期：实收资本 opening 4000000（year-1 未审期末）
    assert matrix["share_capital"] == pytest.approx(4000000)
    assert matrix["capital_reserve"] == pytest.approx(700000)
    assert matrix["retained_earnings"] == pytest.approx(1500000)


@pytest.mark.asyncio
async def test_get_unadjusted_export_data_equity(db_session: AsyncSession, equity_seed):
    engine = ReportEngine(db_session)
    data = await engine.get_unadjusted_export_data(
        FAKE_PROJECT_ID,
        2024,
        ["equity_statement"],
    )
    eq_rows = data["equity_statement"]
    eq001 = next(r for r in eq_rows if r["row_code"] == "EQ-001")
    assert "eq_matrix" in eq001["source_accounts"]
    assert eq001["source_accounts"]["eq_matrix"]["current_year"]["share_capital"] == pytest.approx(4000000)


@pytest.mark.asyncio
async def test_workpaper_overlay_on_unadjusted_equity(db_session: AsyncSession, equity_seed):
    wp_index = WpIndex(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        wp_code="M1",
        wp_name="所有者权益",
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        wp_index_id=wp_index.id,
        file_path="M1/test.xlsx",
        source_type=WpSourceType.imported,
        status=WpFileStatus.draft,
        parsed_data={
            "equity_movement": {
                "M1-1": {
                    "method": "equity_movement_calculation",
                    "applied_at": "2026-06-12T10:00:00+00:00",
                    "data": {
                        "opening_balances": {
                            "paid_in_capital": "4100000",
                            "capital_reserve": "710000",
                            "surplus_reserve": "0",
                            "retained_earnings": "1600000",
                            "oci": "0",
                            "other_equity_instruments": "0",
                        },
                        "movement_summary": {
                            "retained_earnings_change": "300000",
                            "oci_change": "12000",
                        },
                    },
                }
            }
        },
        last_parsed_at=datetime.now(timezone.utc),
    )
    db_session.add(wp)
    await db_session.flush()

    engine = ReportEngine(db_session)
    rows = await engine.generate_unadjusted_report(
        FAKE_PROJECT_ID, 2024, FinancialReportType.equity_statement,
    )
    eq001 = next(r for r in rows if r["row_code"] == "EQ-001")
    cy = eq001["source_accounts"]["eq_matrix"]["current_year"]
    assert cy["share_capital"] == pytest.approx(4100000)
    eq007 = next(r for r in rows if r["row_code"] == "EQ-007")
    mv = eq007["source_accounts"]["eq_matrix"]["current_year"]
    assert mv["retained_earnings"] == pytest.approx(300000)
    assert mv["other_comprehensive_income"] == pytest.approx(12000)


@pytest.mark.asyncio
async def test_enrich_equity_statement_rows_in_memory(db_session: AsyncSession, equity_seed):
    now = datetime.now(timezone.utc)
    for year, code, name, current, prior in [
        (2023, "BS-101", "所有者权益：", 0, 0),
        (2023, "BS-102", "实收资本", 4000000, 3500000),
        (2023, "BS-113", "资本公积", 700000, 650000),
        (2024, "BS-101", "所有者权益：", 0, 0),
        (2024, "BS-102", "实收资本", 5000000, 4000000),
        (2024, "BS-113", "资本公积", 800000, 700000),
        (2024, "BS-125", "未分配利润", 2000000, 1500000),
    ]:
        db_session.add(
            FinancialReport(
                id=uuid.uuid4(),
                project_id=FAKE_PROJECT_ID,
                year=year,
                report_type=FinancialReportType.balance_sheet,
                row_code=code,
                row_name=name,
                current_period_amount=Decimal(str(current)),
                prior_period_amount=Decimal(str(prior)),
                generated_at=now,
            )
        )
    eq_rows = [{
        "row_code": "EQ-001",
        "row_name": "一、上年年末余额",
        "source_accounts": None,
    }]
    await db_session.flush()

    engine = ReportEngine(db_session)
    enriched = await engine.enrich_equity_statement_rows(FAKE_PROJECT_ID, 2024, eq_rows)

    cy = enriched[0]["source_accounts"]["eq_matrix"]["current_year"]
    py = enriched[0]["source_accounts"]["eq_matrix"]["prior_year"]
    assert cy["share_capital"] == pytest.approx(4000000)
    assert cy["capital_reserve"] == pytest.approx(700000)
    assert py["share_capital"] == pytest.approx(3500000)
    assert py["capital_reserve"] == pytest.approx(650000)


@pytest.mark.asyncio
async def test_wp_movement_maps_to_multiple_eq_rows(db_session: AsyncSession, equity_seed):
    wp_index = WpIndex(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        wp_code="M1",
        wp_name="所有者权益",
    )
    db_session.add(wp_index)
    await db_session.flush()
    db_session.add(
        WorkingPaper(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            wp_index_id=wp_index.id,
            file_path="M1/test.xlsx",
            source_type=WpSourceType.imported,
            status=WpFileStatus.draft,
            parsed_data={
                "equity_movement": {
                    "M1-1": {
                        "applied_at": "2026-06-12T12:00:00+00:00",
                        "data": {
                            "opening_balances": {"paid_in_capital": "4000000"},
                            "net_profit": "500000",
                            "dividends": "100000",
                            "surplus_reserve": "50000",
                            "movement_summary": {"oci_change": "8000"},
                        },
                    }
                }
            },
            last_parsed_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()

    engine = ReportEngine(db_session)
    rows = await engine.generate_unadjusted_report(
        FAKE_PROJECT_ID, 2024, FinancialReportType.equity_statement,
    )
    by_code = {r["row_code"]: r for r in rows}
    assert by_code["EQ-007"]["source_accounts"]["eq_matrix"]["current_year"]["retained_earnings"] == pytest.approx(500000)
    assert by_code["EQ-024"]["source_accounts"]["eq_matrix"]["current_year"]["retained_earnings"] == pytest.approx(-100000)
    assert by_code["EQ-017"]["source_accounts"]["eq_matrix"]["current_year"]["surplus_reserve"] == pytest.approx(50000)
