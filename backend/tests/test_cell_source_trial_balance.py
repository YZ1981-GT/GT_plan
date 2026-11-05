"""试算平衡表单元格来源（spec citar-cell-source-hover R4，design §5）。

判据：各列构成之和 = standard-view 同列的格值（同一条末级行 SQL、同一组已批准调整）；未批准 / 底稿来源的调整不计入；
试算表没重算时审定数如实给差额与「需重算」。
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import (
    AccountMapping, Adjustment, AdjustmentEntry, AdjustmentType, MappingType, ReviewStatus, TbBalance, TrialBalance,
)
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.routers.cell_sources import router as src_router
from app.services.cell_source.trial_balance import trial_balance_sources
from app.services.standard_balance_view_service import build_standard_balance_view
from app.services.trial_balance_service import TrialBalanceService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_UID = uuid.uuid4()
COLS = {"opening": "opening_balance", "period_debit": "period_debit", "period_credit": "period_credit",
        "adj_debit": "adjustment_debit", "adj_credit": "adjustment_credit", "adj_closing": "adjusted_closing_balance"}


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


async def _add_adj(db, pid, no, lines, status=ReviewStatus.approved, origin="manual"):
    grp = uuid.uuid4()
    for i, (code, dr, cr) in enumerate(lines, 1):
        adj_id = uuid.uuid4()
        db.add(Adjustment(id=adj_id, project_id=pid, year=2025, company_code="001", adjustment_no=no,
                          adjustment_type=AdjustmentType.aje, description=f"{no} 摘要", account_code=code,
                          debit_amount=dr, credit_amount=cr, entry_group_id=grp, review_status=status,
                          origin=origin, is_deleted=False, created_by=_UID))
        db.add(AdjustmentEntry(id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=i,
                               standard_account_code=code, account_name=code, debit_amount=dr, credit_amount=cr,
                               is_deleted=False))
    await db.flush()


@pytest_asyncio.fixture
async def pid(db: AsyncSession):
    project = Project(id=uuid.uuid4(), name="试算来源_2025", client_name="试算来源", project_type=ProjectType.annual,
                      status=ProjectStatus.planning, created_by=_UID)
    db.add(project)
    await db.flush()
    p = project.id
    for orig, std in (("C1002", "1002"), ("C1003", "1002"), ("C2202", "2202"), ("C6001", "6001")):
        db.add(AccountMapping(project_id=p, original_account_code=orig, original_account_name=orig,
                              standard_account_code=std, mapping_type=MappingType.manual, created_by=_UID))

    def bal(code, opening, closing, dr, cr, direction=None):
        return TbBalance(project_id=p, year=2025, company_code="001", account_code=code, account_name=f"客户{code}",
                         opening_balance=Decimal(opening), closing_balance=Decimal(closing), debit_amount=Decimal(dr),
                         credit_amount=Decimal(cr), opening_direction=direction, closing_direction=direction)

    db.add_all([bal("C1002", "30000", "35000", "10000", "5000"), bal("C1003", "20000", "22000", "5000", "3000"),
                bal("C2202", "6000", "8000", "0", "2000", "credit"), bal("C6001", "0", "100000", "0", "100000", "credit")])
    await db.flush()
    # 一组两行（借银行存款 / 贷应付账款）+ 草稿 + 底稿来源（后两者不计入）
    await _add_adj(db, p, "AJE-1", [("1002", Decimal("500"), Decimal("0")), ("2202", Decimal("0"), Decimal("500"))])
    await _add_adj(db, p, "AJE-2", [("1002", Decimal("999"), Decimal("0"))], status=ReviewStatus.draft)
    await _add_adj(db, p, "AJE-3", [("1002", Decimal("777"), Decimal("0"))], origin="workpaper")
    await TrialBalanceService(db).full_recalc(p, 2025)
    await db.commit()
    return p


def _sum(s):
    return sum((Decimal(i["amount"]) * Decimal(i["sign"]) for i in s["items"] if i["amount"] is not None), Decimal(0))


@pytest.mark.asyncio
async def test_every_column_reconciles_with_standard_view(db, pid):
    view = {r["standard_account_code"]: r for r in await build_standard_balance_view(db, pid, 2025)}
    cells = (await trial_balance_sources(db, pid, 2025))["cells"]
    checked = 0
    for code in ("1002", "2202", "6001"):
        for col, field in COLS.items():
            s = cells[f"{code}:{col}"]
            assert s["linear"] and s["diff"] is None, (code, col, s)
            assert Decimal(s["value"]) == Decimal(view[code][field]), (code, col)
            assert _sum(s) == Decimal(view[code][field]), (code, col)
            checked += 1
        assert cells[f"{code}:audited"]["diff"] is None and cells[f"{code}:audited"]["issue"] is None
    assert checked == 18


@pytest.mark.asyncio
async def test_period_lists_client_accounts(db, pid):
    s = (await trial_balance_sources(db, pid, 2025))["cells"]["1002:period_debit"]
    assert [(i["label"], i["amount"]) for i in s["items"]] == [("C1002 客户C1002", "10000"), ("C1003 客户C1003", "5000")]
    assert s["items"][0]["link"] == {"page": "balance", "code": "C1002"}


@pytest.mark.asyncio
async def test_adjustment_groups_and_pending_not_counted(db, pid):
    s = (await trial_balance_sources(db, pid, 2025))["cells"]["1002:adj_debit"]
    counted = [i for i in s["items"] if i["sign"] != "0"]
    pending = [i for i in s["items"] if i["sign"] == "0"]
    assert [(i["label"], i["amount"]) for i in counted] == [("调整分录 AJE-1", "500")]
    assert counted[0]["link"]["page"] == "adjustments"
    assert [(i["label"], i["amount"]) for i in pending] == [("调整分录 AJE-2", "999")]
    assert "批准后才计入" in pending[0]["detail"]
    assert all("AJE-3" not in i["label"] for i in s["items"])  # 底稿来源不列（已在底稿发布调整里）
    assert s["value"] == "500" and s["total"] == "500"


@pytest.mark.asyncio
async def test_credit_account_is_negative_and_audited_parts(db, pid):
    cells = (await trial_balance_sources(db, pid, 2025))["cells"]
    audited = cells["2202:audited"]
    assert audited["value"] == "-8500"  # 贷方 8,000 + 贷方调整 500，借正贷负
    assert {i["label"] for i in audited["items"]} >= {"未审数", "审计调整（AJE）", "重分类调整（RJE）"}
    assert _sum(audited) == Decimal("-8500")


@pytest.mark.asyncio
async def test_stale_trial_balance_is_reported(db, pid):
    """试算表没重算（审定数改过）：审定数构成仍按试算表各列加总，但与现算调整后期末不等 ⇒ 写明需重算。"""
    await db.execute(sa.update(TrialBalance).where(TrialBalance.project_id == pid, TrialBalance.standard_account_code == "1002")
                     .values(audited_amount=Decimal("1")))
    await db.commit()
    s = (await trial_balance_sources(db, pid, 2025))["cells"]["1002:audited"]
    assert s["issue"] and "需重算" in s["issue"]


@pytest.mark.asyncio
async def test_scope_codes_filter(db, pid):
    cells = (await trial_balance_sources(db, pid, 2025, scope_codes={"1002"}))["cells"]
    assert {k.split(":")[0] for k in cells} == {"1002"}


def _app(db, user):
    app = FastAPI()
    app.include_router(src_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("role,status", [(UserRole.admin, 200), (UserRole.auditor, 403)])
async def test_endpoint_requires_project_access(db, pid, role, status):
    user = User(id=uuid.uuid4(), username=f"u{role.value}", email=f"{role.value}@t.t", hashed_password="x", role=role)
    async with AsyncClient(transport=ASGITransport(app=_app(db, user)), base_url="http://t") as c:
        r = await c.get(f"/api/projects/{pid}/cell-sources/trial-balance", params={"year": 2025})
    assert r.status_code == status, r.text
    if status == 200:
        assert "1002:audited" in r.json()["cells"]
