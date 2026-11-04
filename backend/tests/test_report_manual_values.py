"""审定报表手工值（spec citar-table-manual-edit R6）：重新生成保留手工值、合计按手工值算、恢复、增量重算不覆盖、接口校验。

报表：货币资金 = TB(1002)、应收账款 = TB(1122)、资产总计 = 两行之和；期初 400 / 200。
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
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, UserRole  # noqa: E402
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig  # noqa: E402
from app.routers import reports as reports_router  # noqa: E402
from app.services.report_engine import ReportEngine  # noqa: E402
from app.services.report_manual_values import save_manual  # noqa: E402

PID = uuid.UUID("00000000-0000-0000-0000-00000000c101")
EDITOR = uuid.UUID("00000000-0000-0000-0000-00000000c001")
READER = uuid.UUID("00000000-0000-0000-0000-00000000c002")
STD = "manual_values_test"
YEAR = 2025
BS = FinancialReportType.balance_sheet

BALANCES = [("1002", "银行存款", D(500), D(400)), ("1122", "应收账款", D(300), D(200))]
ROWS = [
    ("BS-001", 1, "货币资金", "TB('1002','期末余额')", False),
    ("BS-002", 2, "应收账款", "TB('1122','期末余额')", False),
    ("BS-003", 3, "资产总计", "ROW('BS-001') + ROW('BS-002')", True),
]


class _Actor:
    def __init__(self, uid: uuid.UUID) -> None:
        self.id = uid
        self.role = UserRole.auditor
        self.username = f"u-{uid.hex[-4:]}"
        self.is_active = True


@pytest_asyncio.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(Project(id=PID, name="手工值_2025", client_name="手工值", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=EDITOR))
        await s.flush()
        s.add(ProjectUser(project_id=PID, user_id=EDITOR, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
        s.add(ProjectUser(project_id=PID, user_id=READER, role=ProjectUserRole.auditor, permission_level=PermissionLevel.readonly))
        for code, name, closing, opening in BALANCES:
            s.add(TbBalance(project_id=PID, year=YEAR, company_code="001", account_code=code, account_name=name,
                            opening_balance=opening, opening_direction="debit", closing_balance=closing,
                            closing_direction="debit", debit_amount=D(0), credit_amount=D(0)))
            s.add(AccountMapping(project_id=PID, original_account_code=code, standard_account_code=code,
                                 mapping_type=MappingType.auto_exact, created_by=EDITOR))
        for code, num, name, formula, total in ROWS:
            s.add(ReportConfig(report_type=BS, row_code=code, row_number=num, row_name=name, indent_level=0,
                               formula=formula, applicable_standard=STD, is_total_row=total))
        await s.flush()
        await ReportEngine(s).generate_all_reports(PID, YEAR, STD)
        await s.commit()
    yield maker
    await engine.dispose()


async def _rows(s: AsyncSession) -> dict[str, FinancialReport]:
    rows = (await s.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == PID, FinancialReport.report_type == BS)
        .execution_options(populate_existing=True))).scalars()
    return {r.row_code: r for r in rows}


@pytest.mark.asyncio
async def test_manual_values_survive_regeneration_and_drive_totals(factory):
    async with factory() as s:
        before = await _rows(s)
        assert before["BS-003"].current_period_amount == D(800)
        assert before["BS-003"].prior_period_amount == D(600)
        await save_manual(s, PID, YEAR, [
            {"report_type": "balance_sheet", "row_code": "BS-001", "column": "current", "value": "550.5"},
            {"report_type": "balance_sheet", "row_code": "BS-002", "column": "prior", "value": 250},
        ], EDITOR)
        await ReportEngine(s).generate_all_reports(PID, YEAR, STD)
        rows = await _rows(s)
        assert rows["BS-001"].current_period_amount == D("550.50")
        assert rows["BS-001"].manual_amounts["current"] == {"value": "550.50", "auto": "500.00"}
        assert rows["BS-003"].current_period_amount == D("850.50")   # 合计按手工值
        assert rows["BS-002"].prior_period_amount == D(250)
        assert rows["BS-003"].prior_period_amount == D(650)          # 上期合计按手工值
        assert rows["BS-001"].manual_amounts["by"] == str(EDITOR)

        # 数据变化后重新生成：手工值不动、auto 刷新
        tb = (await s.execute(sa.select(TbBalance).where(TbBalance.account_code == "1002"))).scalar_one()
        tb.closing_balance = D(700)
        await s.flush()
        await ReportEngine(s).generate_all_reports(PID, YEAR, STD)
        rows = await _rows(s)
        assert rows["BS-001"].current_period_amount == D("550.50")
        assert D(rows["BS-001"].manual_amounts["current"]["auto"]) == D(700)

        # 恢复：回到自动值、标记去掉
        await save_manual(s, PID, YEAR, [
            {"report_type": "balance_sheet", "row_code": "BS-001", "column": "current", "restore": True},
            {"report_type": "balance_sheet", "row_code": "BS-002", "column": "prior", "restore": True},
        ], EDITOR)
        await ReportEngine(s).generate_all_reports(PID, YEAR, STD)
        rows = await _rows(s)
        assert rows["BS-001"].current_period_amount == D(700) and rows["BS-001"].manual_amounts is None
        # 库里必须是 SQL NULL（JSON null 会让 IS NOT NULL 恒真，页面按「有手工值」处理）
        stored = (await s.execute(sa.select(sa.func.count()).select_from(FinancialReport).where(
            FinancialReport.project_id == PID, FinancialReport.manual_amounts.is_not(None)))).scalar()
        assert stored == 0
        assert rows["BS-003"].current_period_amount == D(1000) and rows["BS-003"].prior_period_amount == D(600)


@pytest.mark.asyncio
async def test_incremental_and_stale_recalc_keep_manual_value(factory):
    async with factory() as s:
        await save_manual(s, PID, YEAR, [
            {"report_type": "balance_sheet", "row_code": "BS-001", "column": "current", "value": 1},
        ], EDITOR)
        engine = ReportEngine(s)
        await engine.regenerate_affected(PID, YEAR, ["1002"], STD)
        rows = await _rows(s)
        assert rows["BS-001"].current_period_amount == D(1)
        assert rows["BS-003"].current_period_amount == D(301)
        for r in rows.values():
            r.is_stale = True
        await s.flush()
        await engine.recalculate_stale_rows(PID, YEAR, STD)
        rows = await _rows(s)
        assert rows["BS-001"].current_period_amount == D(1)
        assert rows["BS-003"].current_period_amount == D(301)


@pytest.mark.asyncio
async def test_manual_clear_is_blank_not_zero_and_totals_treat_as_zero(factory):
    async with factory() as s:
        await save_manual(s, PID, YEAR, [
            {"report_type": "balance_sheet", "row_code": "BS-002", "column": "current", "value": None},
        ], EDITOR)
        await ReportEngine(s).generate_all_reports(PID, YEAR, STD)
        rows = await _rows(s)
        assert rows["BS-002"].current_period_amount is None
        assert rows["BS-002"].manual_amounts["current"]["value"] is None
        assert rows["BS-003"].current_period_amount == D(500)


@pytest_asyncio.fixture
async def client(factory, monkeypatch) -> AsyncGenerator[dict, None]:
    current = {"actor": _Actor(EDITOR)}
    app = FastAPI()
    app.include_router(reports_router.router)

    async def _std(_db, _pid):
        return STD

    monkeypatch.setattr(reports_router, "_resolve_applicable_standard", _std)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield {"c": c, "as": lambda uid: current.update(actor=_Actor(uid)),
               "use": lambda actor: current.update(actor=actor)}


URL = f"/api/reports/{PID}/{YEAR}/manual"


@pytest.mark.asyncio
async def test_manual_endpoint_saves_regenerates_and_validates(client, factory):
    c = client["c"]
    r = await c.put(URL, json={"items": [{"report_type": "balance_sheet", "row_code": "BS-001", "column": "current", "value": 900}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"changed": 1}
    got = await c.get(f"/api/reports/{PID}/{YEAR}/balance_sheet")
    rows = {row["row_code"]: row for row in got.json()}
    assert D(str(rows["BS-001"]["current_period_amount"])) == D(900)
    assert D(str(rows["BS-003"]["current_period_amount"])) == D(1200)
    assert rows["BS-001"]["manual_amounts"]["current"]["auto"] == "500.00"

    missing = await c.put(URL, json={"items": [{"report_type": "income_statement", "row_code": "IS-001", "column": "current", "value": 1}]})
    assert missing.status_code == 409
    for bad in ({"report_type": "x", "row_code": "BS-001", "column": "current", "value": 1},
                {"report_type": "balance_sheet", "row_code": "BS-001", "column": "total", "value": 1},
                {"report_type": "balance_sheet", "row_code": "BS-001", "column": "current", "value": "abc"}):
        assert (await c.put(URL, json={"items": [bad]})).status_code == 422, bad

    client["as"](READER)
    assert (await c.put(URL, json={"items": []})).status_code == 403


@pytest.mark.asyncio
async def test_manual_endpoint_requires_allow_manual_edit(client):
    """账号未开通「允许修改」：审定报表手工值 403、报表不动（spec citar-manual-edit-permission R2）。"""
    c = client["c"]
    locked = _Actor(EDITOR)
    locked.allow_manual_edit = False
    client["use"](locked)
    r = await c.put(URL, json={"items": [{"report_type": "balance_sheet", "row_code": "BS-001", "column": "current", "value": 900}]})
    assert r.status_code == 403 and "允许修改" in r.text
    rows = {row["row_code"]: row for row in (await c.get(f"/api/reports/{PID}/{YEAR}/balance_sheet")).json()}
    assert D(str(rows["BS-001"]["current_period_amount"])) == D(500)
    assert not rows["BS-001"].get("manual_amounts")
