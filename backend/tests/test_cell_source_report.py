"""审定报表单元格来源（spec citar-cell-source-hover R5，design §6）。

判据：内存重算值 = 报表生成写库的值；线性公式逐项（TB 拆到各标准科目、ROW / SUM_ROW 拆到行）之和 = 格值；
手工值带自动值与修改人；库里值与重算不符 ⇒ 过期；非线性公式不做合计核对；未审口径不读手工值；项目只读鉴权。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal as D

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import AccountMapping, MappingType, TbBalance  # noqa: E402
from app.models.base import Base, PermissionLevel  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, User, UserRole  # noqa: E402
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig  # noqa: E402
from app.routers.cell_sources import router as src_router  # noqa: E402
from app.services.cell_source.report import linear_leaves, report_sources  # noqa: E402
from app.services.formula_engine import parse_to_ast  # noqa: E402
from app.services.report_engine import ReportEngine  # noqa: E402
from app.services.report_manual_values import save_manual  # noqa: E402

PID = uuid.UUID("00000000-0000-0000-0000-00000000c601")
EDITOR = uuid.UUID("00000000-0000-0000-0000-00000000c602")
OUTSIDER = uuid.UUID("00000000-0000-0000-0000-00000000c603")
STD = "cell_source_report_test"
YEAR = 2025
BS, IS = FinancialReportType.balance_sheet, FinancialReportType.income_statement

# 1002 银行存款下挂两个末级（工行 / 建行）：试算表只取末级，TB('1002') 按前缀并入两个子级
BALANCES = [("1002", "银行存款", D(500), D(400)), ("100201", "工行", D(50), D(40)), ("100202", "建行", D(450), D(360)),
            ("1122", "应收账款", D(300), D(200)), ("1231", "坏账准备", D(-30), D(-20))]
ROWS = [
    (BS, "BS-001", 1, "货币资金", "TB('1002','期末余额')", False),
    (BS, "BS-002", 2, "应收账款", "TB('1122','期末余额') + TB('1231','期末余额')", False),
    (BS, "BS-003", 3, "资产总计", "SUM_ROW('BS-001','BS-002')", True),
    (BS, "BS-004", 4, "两倍货币资金", "ROW('BS-001') * 2", False),
    (BS, "BS-005", 5, "取大", "MAX(ROW('BS-001'), ROW('BS-002'))", False),
]


@pytest_asyncio.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(User(id=EDITOR, username="报表编制人", email="r@t.local", hashed_password="x", role=UserRole.auditor))
        s.add(Project(id=PID, name="报表来源_2025", client_name="报表来源", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=EDITOR))
        await s.flush()
        s.add(ProjectUser(project_id=PID, user_id=EDITOR, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
        for code, name, closing, opening in BALANCES:
            s.add(TbBalance(project_id=PID, year=YEAR, company_code="001", account_code=code, account_name=name,
                            opening_balance=opening, opening_direction="debit", closing_balance=closing,
                            closing_direction="debit", debit_amount=D(0), credit_amount=D(0)))
            s.add(AccountMapping(project_id=PID, original_account_code=code, standard_account_code=code,
                                 mapping_type=MappingType.auto_exact, created_by=EDITOR))
        for rt, code, num, name, formula, total in ROWS:
            s.add(ReportConfig(report_type=rt, row_code=code, row_number=num, row_name=name, indent_level=0,
                               formula=formula, applicable_standard=STD, is_total_row=total))
        await s.flush()
        await ReportEngine(s).generate_all_reports(PID, YEAR, STD)
        await s.commit()
    yield maker
    await engine.dispose()


@pytest.fixture(autouse=True)
def _standard(monkeypatch):
    from app.services.report_config_service import ReportConfigService

    async def _std(db, project_id):
        return STD

    monkeypatch.setattr(ReportConfigService, "resolve_applicable_standard", staticmethod(_std))


def _sum(s):
    return sum((D(i["amount"]) * D(i["sign"]) for i in s["items"] if i["amount"] is not None), D(0))


@pytest.mark.asyncio
async def test_sources_match_generated_report(factory):
    async with factory() as s:
        cells = (await report_sources(s, PID, YEAR, BS))["cells"]
        stored = {r.row_code: r for r in (await s.execute(sa.select(FinancialReport).where(
            FinancialReport.project_id == PID, FinancialReport.report_type == BS))).scalars()}
    for code in ("BS-001", "BS-002", "BS-003", "BS-004"):
        for col, field in (("current", "current_period_amount"), ("prior", "prior_period_amount")):
            src = cells[f"{code}:{col}"]
            assert src["issue"] is None, (code, col, src["issue"])
            assert D(src["value"]) == getattr(stored[code], field), (code, col)
            assert src["linear"] and src["diff"] is None and _sum(src) == D(src["value"]), (code, col, src)


@pytest.mark.asyncio
async def test_tb_split_by_prefix_and_sum_row(factory):
    async with factory() as s:
        cells = (await report_sources(s, PID, YEAR, BS))["cells"]
    bs1 = cells["BS-001:current"]
    # 试算表只按末级建行：1002 本身没有行，TB('1002') 按前缀取到两个子级
    assert [(i["label"], i["amount"]) for i in bs1["items"]] == [("100201 工行", "50"), ("100202 建行", "450")]
    assert bs1["value"] == "500" and bs1["total"] == "500"
    assert bs1["items"][0]["detail"] == "期末余额（审定口径）"
    assert bs1["items"][0]["link"] == {"page": "trial_balance", "code": "100201"}
    total = cells["BS-003:current"]
    assert [i["label"] for i in total["items"]] == ["BS-001 货币资金", "BS-002 应收账款"]
    assert total["items"][0]["link"] == {"page": "reports", "report_type": "balance_sheet", "code": "BS-001"}
    double = cells["BS-004:current"]
    assert double["items"][0]["sign"] == "2" and double["value"] == "1000"
    assert cells["BS-001:prior"]["title"].startswith("期初余额：本年试算表期初数")
    assert _sum(cells["BS-001:prior"]) == D(400)


@pytest.mark.asyncio
async def test_nonlinear_formula_lists_refs_only(factory):
    async with factory() as s:
        cell = (await report_sources(s, PID, YEAR, BS))["cells"]["BS-005:current"]
    assert cell["linear"] is False and cell["total"] is None
    assert {i["label"] for i in cell["items"]} == {"BS-001 货币资金", "BS-002 应收账款"}


@pytest.mark.asyncio
async def test_zero_accounts_are_summarised(factory):
    """前缀并入的下级里金额为 0 的不逐个列，汇成一行（真库 BS-002 货币资金下挂十个科目只一个有数）。"""
    async with factory() as s:
        for code, name, opening, closing in (("112201", "甲客户", D(0), D(0)), ("112202", "乙客户", D(200), D(300))):
            s.add(TbBalance(project_id=PID, year=YEAR, company_code="001", account_code=code, account_name=name,
                            opening_balance=opening, opening_direction="debit", closing_balance=closing,
                            closing_direction="debit", debit_amount=D(0), credit_amount=D(0)))
            s.add(AccountMapping(project_id=PID, original_account_code=code, standard_account_code=code,
                                 mapping_type=MappingType.auto_exact, created_by=EDITOR))
        await s.flush()
        from app.services.trial_balance_service import TrialBalanceService
        await TrialBalanceService(s).full_recalc(PID, YEAR)
        cell = (await report_sources(s, PID, YEAR, BS))["cells"]["BS-002:current"]
    labels = [i["label"] for i in cell["items"]]
    assert any(lab.startswith("112202") for lab in labels) and not any(lab.startswith("112201") for lab in labels), labels
    assert any(lab.startswith("另有") and "金额为 0" in lab for lab in labels), labels
    assert cell["diff"] is None


@pytest.mark.asyncio
async def test_manual_value_and_stale(factory):
    async with factory() as s:
        await save_manual(s, PID, YEAR, [
            {"report_type": "balance_sheet", "row_code": "BS-001", "column": "current", "value": "600"}], EDITOR)
        await ReportEngine(s).generate_all_reports(PID, YEAR, STD)
        await s.commit()
        cells = (await report_sources(s, PID, YEAR, BS))["cells"]
        bs1 = cells["BS-001:current"]
        assert bs1["kind"] == "manual" and bs1["manual"]["value"] == "600" and bs1["manual"]["auto"] == "500"
        assert bs1["manual"]["by_name"] == "报表编制人"
        assert bs1["value"] == "500" and bs1["diff"] is None and bs1["issue"] is None
        assert cells["BS-003:current"]["value"] == "870"  # 合计按手工值：600 + 270
        # 未审口径不读手工值
        un = (await report_sources(s, PID, YEAR, BS, "unadjusted"))["cells"]
        assert un["BS-001:current"]["kind"] == "formula" and un["BS-001:current"]["manual"] is None
        # 库里的值改掉（试算表变了没重新生成）⇒ 过期
        await s.execute(sa.update(TbBalance).where(TbBalance.account_code == "1122").values(closing_balance=D(999)))
        from app.services.trial_balance_service import TrialBalanceService
        await TrialBalanceService(s).full_recalc(PID, YEAR)
        cells = (await report_sources(s, PID, YEAR, BS))["cells"]
        assert "已过期" in (cells["BS-002:current"]["issue"] or "")
        assert cells["BS-001:current"]["issue"] is None


@pytest.mark.parametrize("formula,expect", [
    ("TB('1001','期末余额') - TB('1231','期末余额')", [("TB", "1001", "期末余额", 1), ("TB", "1231", "期末余额", -1)]),
    ("-(ROW('A') + ROW('B')) / 2", [("ROW", "A", None, D("-0.5")), ("ROW", "B", None, D("-0.5"))]),
    ("SUM_TB('6001~6099','期末余额') + PL_UNCLOSED()", [("SUM_TB", "6001~6099", "期末余额", 1), ("PL_UNCLOSED", None, None, 1)]),
])
def test_linear_leaves(formula, expect):
    got = [((leaf + (None, None))[:3], c) for leaf, c in linear_leaves(parse_to_ast(formula))]
    assert got == [((a, b, c), D(k)) for a, b, c, k in expect]


@pytest.mark.parametrize("formula", ["IF(ROW('A')>0, ROW('A'), 0)", "ROW('A') * ROW('B')", "ABS(ROW('A'))"])
def test_nonlinear_rejected(formula):
    assert linear_leaves(parse_to_ast(formula)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,role,status", [(EDITOR, UserRole.auditor, 200), (OUTSIDER, UserRole.auditor, 403),
                                              (uuid.uuid4(), UserRole.admin, 200)])
async def test_endpoint_requires_project_access(factory, uid, role, status):
    class _U:
        id, username, is_active = uid, "u", True

    _U.role = role
    app = FastAPI()
    app.include_router(src_router)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: _U()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/projects/{PID}/cell-sources/report/balance_sheet", params={"year": YEAR})
        assert r.status_code == status, r.text
        if status == 200:
            assert "BS-001:current" in r.json()["cells"]
            bad = await c.get(f"/api/projects/{PID}/cell-sources/report/cash_flow_statement", params={"year": YEAR})
            assert bad.status_code == 422
