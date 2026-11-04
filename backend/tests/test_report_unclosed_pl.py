"""spec citar-audited-balance-and-workpaper-coverage R1 / R2：审定资产负债表未分配利润含未结转损益；重导后新科目进客户科目表。

账套：SAP 式不结转损益 —— 收入 1000（贷）、成本 700（借）留在损益科目，利润分配借方 100（以前年度亏损）。
资产 1000 = 应付 300 + 实收 500 + 未分配利润（−100 + 本年利润 300）。不含未结转损益时差 300。
"""

from __future__ import annotations

import uuid
from decimal import Decimal as D

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
)
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig
from app.services.report_engine import ReportEngine, ReportFormulaParser, evaluate_formula_result

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
PID = uuid.uuid4()
UID = uuid.uuid4()
STD = "unclosed_pl_test"
YEAR = 2025

# 余额表：(编码, 名称, 期末余额借正贷负, 借方发生额, 贷方发生额)
BALANCES = [
    ("1002", "银行存款", D(1000), D(0), D(0)),
    ("2202", "应付账款", D(-300), D(0), D(0)),
    ("3001", "实收资本", D(-500), D(0), D(0)),
    ("3201", "利润分配", D(100), D(0), D(0)),
    ("6001", "主营业务收入", D(-1000), D(0), D(1000)),
    ("6401", "主营业务成本", D(700), D(700), D(0)),
]
BS = [
    ("BS-001", 1, "资产总计", "TB('1002','期末余额')"),
    ("BS-002", 2, "应付账款", "TB('2202','期末余额')"),
    ("BS-003", 3, "实收资本", "TB('3001','期末余额')"),
    ("BS-004", 4, "未分配利润", "TB('3104','期末余额')+TB('3201','期末余额')+PL_UNCLOSED()"),
    ("BS-005", 5, "负债和所有者权益总计", "ROW('BS-002') + ROW('BS-003') + ROW('BS-004')"),
]


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(ENGINE, class_=AsyncSession, expire_on_commit=False)() as session:
        session.add(Project(id=PID, name="未结转损益_2025", client_name="未结转损益", project_type=ProjectType.annual,
                            status=ProjectStatus.planning, created_by=UID))
        await session.flush()
        for code, name, closing, dr, cr in BALANCES:
            session.add(TbBalance(project_id=PID, year=YEAR, company_code="001", account_code=code, account_name=name,
                                  opening_balance=D(0), opening_direction="debit",
                                  closing_balance=abs(closing), closing_direction="credit" if closing < 0 else "debit",
                                  debit_amount=dr, credit_amount=cr))
            session.add(AccountMapping(project_id=PID, original_account_code=code, standard_account_code=code,
                                       mapping_type=MappingType.auto_exact, created_by=UID))
        for code, num, name, formula in BS:
            session.add(ReportConfig(report_type=FinancialReportType.balance_sheet, row_code=code, row_number=num,
                                     row_name=name, indent_level=0, formula=formula, applicable_standard=STD,
                                     is_total_row=False))
        await session.flush()
        yield session


async def _bs(db: AsyncSession) -> dict[str, D]:
    await ReportEngine(db).generate_all_reports(PID, YEAR, STD)
    rows = (await db.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == PID, FinancialReport.report_type == FinancialReportType.balance_sheet))).scalars()
    return {r.row_name: r.current_period_amount for r in rows}


@pytest.mark.asyncio
async def test_unclosed_pl_keeps_balance_sheet_balanced(db):
    bs = await _bs(db)
    assert bs["未分配利润"] == D(200)  # −100 + 本年利润 300
    assert bs["资产总计"] == bs["负债和所有者权益总计"] == D(1000)


@pytest.mark.asyncio
async def test_approved_pl_adjustment_flows_into_retained_earnings(db):
    """已批准调整：借销售费用 50 / 贷应付账款 50 ⇒ 应付 350、未分配利润 150，仍平衡；未审口径不含调整。"""
    group = uuid.uuid4()
    adj = Adjustment(project_id=PID, year=YEAR, company_code="001", adjustment_no="AJE-1",
                     adjustment_type=AdjustmentType.aje, account_code="6601", entry_group_id=group,
                     review_status=ReviewStatus.approved, created_by=UID)
    db.add(adj)
    await db.flush()
    for i, (code, dr, cr) in enumerate((("6601", D(50), D(0)), ("2202", D(0), D(50))), start=1):
        db.add(AdjustmentEntry(adjustment_id=adj.id, entry_group_id=group, line_no=i, standard_account_code=code,
                               debit_amount=dr, credit_amount=cr))
    await db.flush()
    bs = await _bs(db)
    assert bs["应付账款"] == D(350) and bs["未分配利润"] == D(150)
    assert bs["资产总计"] == bs["负债和所有者权益总计"]
    parser = ReportFormulaParser(db, PID, YEAR)
    parser._use_unadjusted = True
    assert await parser.resolve_pl_unclosed() == D(300)


@pytest.mark.asyncio
async def test_opening_mode_and_unsupported_resolver(db):
    parser = ReportFormulaParser(db, PID, YEAR)
    parser._use_opening = True
    assert await parser.resolve_pl_unclosed() == D(0)

    class _Consol:  # 合并 resolver 没有未结转损益口径
        async def resolve_tb(self, code, col):
            return D(0)

        async def resolve_sum(self, rng, col):
            return D(0)

    assert (await evaluate_formula_result("TB('3201','期末余额')+PL_UNCLOSED()", resolver=_Consol())).value == D(0)
    with pytest.raises(ValueError, match="PL_UNCLOSED"):
        await evaluate_formula_result("PL_UNCLOSED()", resolver=_Consol(), strict_context=True)


def test_incremental_regeneration_sees_pl_changes():
    engine = ReportEngine(None)
    formula = "TB('3104','期末余额')+TB('3201','期末余额')+PL_UNCLOSED()"
    assert engine._is_affected(formula, ["6601"])
    assert not engine._is_affected(formula, ["1002"])


def test_other_paths_raise_instead_of_zero():
    """L1 内核（底稿 / 试算等其他求值路径）不代 0：报错。"""
    from app.services.formula_engine import FormulaContext, execute

    result = execute("PL_UNCLOSED()", FormulaContext(tb_data={}))
    assert not result.ok and any("PL_UNCLOSED" in e for e in result.errors)


@pytest.mark.asyncio
async def test_reimport_new_accounts_enter_client_chart(db):
    """R2：客户科目表已有（含「.0」写法）⇒ 只补余额表里新出现的科目，不重复建。"""
    from app.services.mapping_service import _generate_client_accounts_from_balance

    db.add(AccountChart(project_id=PID, account_code="1002.0", account_name="银行存款", source=AccountSource.client,
                        category=AccountCategory.asset, direction=AccountDirection.debit, level=1))
    await db.flush()
    created = await _generate_client_accounts_from_balance(PID, db, year=YEAR)
    codes = (await db.execute(sa.select(AccountChart.account_code).where(
        AccountChart.project_id == PID, AccountChart.source == AccountSource.client))).scalars().all()
    assert created == len(BALANCES) - 1
    assert sorted(codes) == sorted(["1002.0"] + [c for c, *_ in BALANCES if c != "1002"])
    assert await _generate_client_accounts_from_balance(PID, db, year=YEAR) == 0
