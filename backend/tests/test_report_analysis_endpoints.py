"""报表分析端点与服务（spec citar-report-analysis 任务 2~7）。

- 6 个端点：未登录 401、非成员 403、只读成员 200（原先只校登录）
- 财务比率：按行名取数（国企单体真实行编码，旧写死的 BS-019 / PL-001 取不到）、mode 生效、
  周转率用期初期末平均、取不到时写原因
- 变动分析：上期为空时变动率为空、≥10% 标显著
- 期初核对：自动找上年项目；找不到写原因、不列假差异
- 试算全景：存在说不清来源的调整时不平衡并列出科目
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base, PermissionLevel, ProjectUserRole
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User, UserRole
from app.models.report_models import FinancialReport, FinancialReportType
from app.routers.wp_report_analysis import router
from app.services.financial_ratio_service import FinancialRatioService
from app.services.report_trend_analysis_service import build_trend_rows
from app.services.trial_balance_full_view_service import TrialBalanceFullViewService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_YEAR = 2025
_UID = uuid.uuid4()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


def _project(name: str, *, code: str | None = "91XX", audit_year: int = _YEAR) -> Project:
    return Project(
        id=uuid.uuid4(), name=name, client_name=name, company_code=code, audit_year=audit_year,
        report_scope="standalone", project_type=ProjectType.annual,
        status=ProjectStatus.execution, created_by=_UID,
    )


def _tb(pid, code, *, unadj, audited=None, opening=None, year=_YEAR, aje=Decimal("0")):
    return TrialBalance(
        id=uuid.uuid4(), project_id=pid, year=year, company_code="001",
        standard_account_code=code, account_name=f"科目{code}",
        account_category=AccountCategory.asset, unadjusted_amount=unadj,
        aje_adjustment=aje, rje_adjustment=Decimal("0"), wp_adjustment=Decimal("0"),
        audited_amount=audited, opening_balance=opening,
    )


def _fr(pid, rtype, code, name, cur, prior=None, indent=0, total=False):
    return FinancialReport(
        id=uuid.uuid4(), project_id=pid, year=_YEAR, report_type=rtype, row_code=code,
        row_name=name, current_period_amount=cur, prior_period_amount=prior,
        indent_level=indent, is_total_row=total,
    )


#: 国企单体真实行编码与行名（report_config soe_standalone）
def _soe_reports(pid) -> list[FinancialReport]:
    bs, is_ = FinancialReportType.balance_sheet, FinancialReportType.income_statement
    D = Decimal
    return [
        _fr(pid, bs, "BS-001", "流动资产：", None),
        _fr(pid, bs, "BS-008", "应收账款", D("400"), D("200"), 1),
        _fr(pid, bs, "BS-018", "存货", D("100"), D("300"), 1),
        _fr(pid, bs, "BS-019", "其中：原材料", D("40"), D("40"), 2),
        _fr(pid, bs, "BS-027", "流动资产合计", D("800"), D("820"), 0, True),
        _fr(pid, bs, "BS-053", "资产总计", D("1000"), D("1000"), 0, True),
        _fr(pid, bs, "BS-082", "流动负债合计", D("400"), D("420"), 0, True),
        _fr(pid, bs, "BS-100", "负债合计", D("600"), D("650"), 0, True),
        _fr(pid, bs, "BS-126", "归属于母公司所有者权益合计", D("390"), D("340"), 0, True),
        _fr(pid, bs, "BS-128", "所有者权益合计", D("400"), D("350"), 0, True),
        _fr(pid, is_, "IS-001", "一、营业总收入", D("2000"), None),
        _fr(pid, is_, "IS-002", "其中：营业收入", D("2000"), None, 1),
        _fr(pid, is_, "IS-008", "其中：营业成本", D("1500"), None, 1),
        _fr(pid, is_, "IS-019", "▲保单红利支出", D("0"), None, 1),
        _fr(pid, is_, "IS-046", "五、净利润（净亏损以“－”号填列）", D("75"), None),
        _fr(pid, is_, "IS-048", "1.归属于母公司所有者的净利润", D("70"), None, 1),
    ]


def _ratio(ratios, name):
    return next(r for r in ratios if r["name"] == name)


# ─── 财务比率 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ratios_locate_rows_by_name(db):
    p = _project("比率")
    db.add(p)
    db.add_all(_soe_reports(p.id))
    await db.flush()
    ratios = await FinancialRatioService(db).calculate_ratios(p.id, _YEAR, "audited")

    assert _ratio(ratios, "流动比率")["value"] == Decimal("2.00")          # 800 / 400
    assert _ratio(ratios, "流动比率")["numerator"]["row_code"] == "BS-027"
    assert _ratio(ratios, "速动比率")["value"] == Decimal("1.75")          # (800-100)/400
    assert _ratio(ratios, "资产负债率")["value"] == Decimal("60.00")
    assert _ratio(ratios, "毛利率")["value"] == Decimal("25.00")           # 500/2000
    assert _ratio(ratios, "净利率")["value"] == Decimal("3.75")            # 75/2000（不取归母 70）
    # 周转率用期初期末平均：应收 (400+200)/2=300 → 2000/300
    assert _ratio(ratios, "应收账款周转率")["value"] == Decimal("6.67")
    assert _ratio(ratios, "存货周转率")["value"] == Decimal("7.50")        # 1500/((100+300)/2)
    assert _ratio(ratios, "净资产收益率(ROE)")["value"] == Decimal("20.00")  # 75/375


@pytest.mark.asyncio
async def test_ratios_report_not_generated_gives_reason(db):
    p = _project("未生成")
    db.add(p)
    await db.flush()
    ratios = await FinancialRatioService(db).calculate_ratios(p.id, _YEAR, "audited")
    assert all(r["value"] is None for r in ratios)
    assert "审定报表未生成" in _ratio(ratios, "流动比率")["note"]


@pytest.mark.asyncio
async def test_ratios_unadjusted_mode_uses_unadjusted_report(db, monkeypatch):
    """mode=unadjusted 走未审报表路径（旧实现忽略 mode，两档结果恒同）。"""
    p = _project("未审")
    db.add(p)
    await db.flush()
    calls = []

    async def fake_unadjusted(self, project_id, year, report_type):
        calls.append(report_type.value)
        return [{"row_code": "BS-027", "row_name": "流动资产合计", "current_period_amount": "300",
                 "indent_level": 0, "is_total_row": True},
                {"row_code": "BS-082", "row_name": "流动负债合计", "current_period_amount": "100",
                 "indent_level": 0, "is_total_row": True}]

    from app.services.report_engine import ReportEngine
    monkeypatch.setattr(ReportEngine, "generate_unadjusted_report", fake_unadjusted)
    ratios = await FinancialRatioService(db).calculate_ratios(p.id, _YEAR, "unadjusted")
    assert set(calls) == {"balance_sheet", "income_statement"}
    assert _ratio(ratios, "流动比率")["value"] == Decimal("3.00")


# ─── 变动分析 ─────────────────────────────────────────────────────────────────

def test_trend_rate_and_significance():
    rows = build_trend_rows([
        {"row_code": "A", "row_name": "甲", "current_period_amount": "110", "prior_period_amount": "100"},
        {"row_code": "B", "row_name": "乙", "current_period_amount": "105", "prior_period_amount": "100"},
        {"row_code": "C", "row_name": "丙", "current_period_amount": "50", "prior_period_amount": None},
        {"row_code": "D", "row_name": "丁", "current_period_amount": "50", "prior_period_amount": "0"},
        {"row_code": "E", "row_name": "戊", "current_period_amount": "-80", "prior_period_amount": "-100"},
    ])
    by = {r["row_code"]: r for r in rows}
    assert by["A"]["change_rate"] == Decimal("10.00") and by["A"]["significant"] is True
    assert by["B"]["significant"] is False
    assert by["C"]["change"] is None and by["C"]["change_rate"] is None
    assert by["D"]["change"] == Decimal("50") and by["D"]["change_rate"] is None
    assert by["E"]["change_rate"] == Decimal("20.00")   # 分母取绝对值


# ─── 期初核对 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_opening_finds_prior_project_by_company_code(db):
    cur = _project("本年", code="91AA")
    prior = _project("上年", code="91AA", audit_year=_YEAR - 1)
    db.add_all([cur, prior])
    db.add_all([
        _tb(cur.id, "1001", unadj=Decimal("0"), opening=Decimal("100")),
        _tb(cur.id, "1002", unadj=Decimal("0"), opening=Decimal("200")),
        _tb(prior.id, "1001", unadj=Decimal("100"), audited=Decimal("100"), year=_YEAR - 1),
        _tb(prior.id, "1002", unadj=Decimal("150"), audited=Decimal("150"), year=_YEAR - 1),
    ])
    await db.flush()
    res = await TrialBalanceFullViewService(db).reconcile_opening_balance(cur.id, _YEAR)
    assert res["has_prior"] is True
    assert res["prior_project_id"] == str(prior.id)
    assert res["matched"] == 1
    assert [d["account_code"] for d in res["differences"]] == ["1002"]
    assert res["differences"][0]["difference"] == Decimal("50")


@pytest.mark.asyncio
async def test_opening_without_prior_reports_reason_not_fake_diffs(db):
    cur = _project("无上年", code="91BB")
    db.add(cur)
    db.add(_tb(cur.id, "1001", unadj=Decimal("0"), opening=Decimal("100")))
    await db.flush()
    res = await TrialBalanceFullViewService(db).reconcile_opening_balance(cur.id, _YEAR)
    assert res["has_prior"] is False
    assert res["differences"] == []
    assert res["reconciled"] is None
    assert "没有上年项目" in res["reason"]


# ─── 试算全景平衡 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_balance_flags_unexplained_adjustment(db):
    p = _project("平衡")
    db.add(p)
    db.add_all([
        _tb(p.id, "1001", unadj=Decimal("100"), aje=Decimal("10"), audited=Decimal("110")),
        _tb(p.id, "1002", unadj=Decimal("100"), audited=Decimal("130")),  # 30 说不清来源
    ])
    await db.flush()
    res = await TrialBalanceFullViewService(db).check_balance_formula(p.id, _YEAR)
    assert res["balanced"] is False
    assert [u["account_code"] for u in res["unexplained"]] == ["1002"]
    assert res["unexplained"][0]["amount"] == Decimal("30")


@pytest.mark.asyncio
async def test_balance_ok_when_components_explain_audited(db):
    p = _project("平衡2")
    db.add(p)
    db.add(_tb(p.id, "1001", unadj=Decimal("100"), aje=Decimal("10"), audited=Decimal("110")))
    await db.flush()
    res = await TrialBalanceFullViewService(db).check_balance_formula(p.id, _YEAR)
    assert res["balanced"] is True and res["unexplained"] == []


# ─── 端点鉴权 ─────────────────────────────────────────────────────────────────

_PATHS = ("full-tb", "tb-balance-check", "opening-reconcile", "bs-trend", "pl-trend", "financial-ratios")


def _app(db, user=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


async def _get(app, path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path)


@pytest_asyncio.fixture
async def proj(db):
    p = _project("鉴权")
    db.add(p)
    await db.commit()
    return p


def _user(role=UserRole.auditor) -> User:
    uid = uuid.uuid4()
    return User(id=uid, username=f"u{uid.hex[:6]}", email=f"{uid.hex[:6]}@t.t",
                hashed_password="x", role=role)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _PATHS)
async def test_requires_login(db, proj, path):
    r = await _get(_app(db), f"/api/workpapers/{proj.id}/{_YEAR}/{path}")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _PATHS)
async def test_non_member_forbidden(db, proj, path):
    stranger = _user()
    db.add(stranger)
    await db.commit()
    r = await _get(_app(db, stranger), f"/api/workpapers/{proj.id}/{_YEAR}/{path}")
    assert r.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _PATHS)
async def test_readonly_member_allowed(db, proj, path):
    member = _user()
    db.add(member)
    await db.flush()
    db.add(ProjectUser(project_id=proj.id, user_id=member.id, role=ProjectUserRole.readonly,
                       permission_level=PermissionLevel.readonly))
    await db.commit()
    r = await _get(_app(db, member), f"/api/workpapers/{proj.id}/{_YEAR}/{path}")
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_invalid_mode_rejected(db, proj):
    admin = _user(UserRole.admin)
    r = await _get(_app(db, admin), f"/api/workpapers/{proj.id}/{_YEAR}/financial-ratios?mode=foo")
    assert r.status_code == 422
