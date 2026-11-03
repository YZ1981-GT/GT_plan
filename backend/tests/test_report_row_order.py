"""报表行求值顺序：被 ROW / SUM_ROW 引用的行先算（report_row_order）。

真库：国企利润表「一、营业总收入 = ROW('IS-002')+…+ROW('IS-006')」排在「其中：营业收入」之前，
按行号求值时读到空缓存 ⇒ 营业收入 38,599,110.27、营业总收入 0（重庆医药集团四川医药 2025）。
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import FinancialReportType
from app.services.report_engine import ReportEngine
from app.services.report_row_order import evaluation_order

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


def _cfg(code, n, formula=None, name=None):
    return SimpleNamespace(row_code=code, row_number=n, formula=formula, row_name=name or code,
                           indent_level=0, is_total_row=False)


def _codes(rows):
    return [r.row_code for r in rows]


# ── 纯函数 ───────────────────────────────────────────────────────────────────


def test_no_forward_refs_keeps_row_number_order():
    rows = [_cfg("B", 2, "ROW('A')"), _cfg("A", 1, "TB('1001','期末余额')"), _cfg("C", 3, "ROW('A')+ROW('B')")]
    assert _codes(evaluation_order(rows)) == ["A", "B", "C"]


def test_total_before_details_is_evaluated_after_them():
    rows = [_cfg("IS-001", 1, "ROW('IS-002') + ROW('IS-003')"), _cfg("IS-002", 2, "TB('6001','本期发生额')"),
            _cfg("IS-003", 3), _cfg("IS-004", 4, "ROW('IS-001')")]
    assert _codes(evaluation_order(rows)) == ["IS-002", "IS-003", "IS-001", "IS-004"]


def test_sum_row_range_counts_as_dependency():
    rows = [_cfg("BS-001", 1, "SUM_ROW('BS-002','BS-004')"), _cfg("BS-002", 2), _cfg("BS-003", 3),
            _cfg("BS-004", 4), _cfg("BS-005", 5)]
    order = _codes(evaluation_order(rows))
    assert order.index("BS-001") > max(order.index(c) for c in ("BS-002", "BS-003", "BS-004"))
    assert order[-1] == "BS-005"


def test_cycle_does_not_raise_or_drop_rows():
    rows = [_cfg("A", 1, "ROW('B')"), _cfg("B", 2, "ROW('A')"), _cfg("C", 3)]
    assert sorted(_codes(evaluation_order(rows))) == ["A", "B", "C"]


def test_unknown_and_self_refs_are_ignored():
    rows = [_cfg("A", 1, "ROW('A') + ROW('ZZ-999')"), _cfg("B", 2)]
    assert _codes(evaluation_order(rows)) == ["A", "B"]


# ── 未审报表（真实求值路径）────────────────────────────────────────────────

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_PID = uuid.uuid4()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        s.add(Project(id=_PID, name="求值顺序_2025", client_name="求值顺序", project_type=ProjectType.annual,
                      status=ProjectStatus.planning, created_by=uuid.uuid4()))
        await s.flush()
        for code, cat, amt in (("6001", AccountCategory.revenue, "38594884.94"),
                               ("6051", AccountCategory.revenue, "4225.33"),
                               ("6401", AccountCategory.expense, "10324471.50")):
            s.add(TrialBalance(project_id=_PID, year=2025, company_code="001", standard_account_code=code,
                               account_name=code, account_category=cat, unadjusted_amount=Decimal(amt),
                               audited_amount=Decimal(amt), opening_balance=Decimal("0")))
        await s.commit()
        yield s


_SOE_IS = [
    _cfg("IS-001", 1, "ROW('IS-002') + ROW('IS-003')", "一、营业总收入"),
    _cfg("IS-002", 2, "TB('6001','本期发生额')+TB('6051','本期发生额')", "其中：营业收入"),
    _cfg("IS-003", 3, None, "△利息收入"),
    _cfg("IS-007", 7, "ROW('IS-008')", "二、营业总成本"),
    _cfg("IS-008", 8, "TB('6401','本期发生额')", "其中：营业成本"),
    _cfg("IS-020", 20, "ROW('IS-001') - ROW('IS-007')", "利润"),
]


@pytest.mark.asyncio
async def test_unadjusted_income_statement_totals_before_details(db):
    rows = await ReportEngine(db)._compute_unadjusted_report_rows(
        _PID, 2025, FinancialReportType.income_statement, _SOE_IS, {},
    )
    got = {r["row_code"]: Decimal(r["current_period_amount"]) for r in rows}
    assert got["IS-002"] == Decimal("38599110.27")
    assert got["IS-001"] == Decimal("38599110.27")
    assert got["IS-007"] == Decimal("10324471.50")
    assert got["IS-020"] == Decimal("28274638.77")
    # 输出仍按行号排（前端按列表顺序展示）
    assert [r["row_code"] for r in rows] == ["IS-001", "IS-002", "IS-003", "IS-007", "IS-008", "IS-020"]
