"""税审底稿 / 汇算申报表单元格来源（spec citar-cell-source-hover R3，design §4）。

真发请求：只替换 ``get_current_user`` 与 ``get_db``（SQLite 内存库）；鉴权、取数、公式求值、来源组装全部真实执行。
核心判据：取数格各科目金额之和 = 格值、线性公式各引用格 × 系数之和 = 格值。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory, AccountChart, AccountDirection, AccountMapping, AccountSource, Adjustment, AdjustmentEntry,
    AdjustmentType, ReviewStatus, TbBalance, TbLedger,
)
from app.models.base import Base, PermissionLevel  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, User, UserRole  # noqa: E402
from app.models.tax_workpaper_models import TaxWorkpaperInput  # noqa: E402
from app.routers.cell_sources import router as sources_router  # noqa: E402
from app.routers.tax_workpapers import router as sheets_router  # noqa: E402
from app.services.cell_source.tax_sheet import linear_terms  # noqa: E402
from app.services.tax_formula_engine import parse_formula  # noqa: E402

P = uuid.UUID("00000000-0000-0000-0000-00000000c501")
EDITOR = uuid.UUID("00000000-0000-0000-0000-00000000c001")
OUTSIDER = uuid.UUID("00000000-0000-0000-0000-00000000c003")
YEAR = 2025
SRC = f"/api/projects/{P}/cell-sources/tax-sheet"
SHEETS = f"/api/projects/{P}/tax-workpapers/sheets"


class _Actor:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.auditor) -> None:
        self.id = uid
        self.role = role
        self.username = f"u-{uid.hex[-4:]}"
        self.is_active = True


ACTORS = {"editor": _Actor(EDITOR), "outsider": _Actor(OUTSIDER), "admin": _Actor(uuid.uuid4(), UserRole.admin)}
_TABLES = [User.__table__, Project.__table__, ProjectUser.__table__, TbBalance.__table__, TbLedger.__table__,
           AccountMapping.__table__, AccountChart.__table__, TaxWorkpaperInput.__table__, Adjustment.__table__,
           AdjustmentEntry.__table__]


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(User(id=EDITOR, username="编制人甲", email="e@t.local", hashed_password="x", role=UserRole.auditor))
        s.add(Project(id=P, name="项目P", client_name="甲公司", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=EDITOR))
        await s.flush()
        s.add(ProjectUser(project_id=P, user_id=EDITOR, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
        # 其他业务收入：出租固定资产收入 1,000 / 租金 200（租金下再挂一个三级科目）
        for code, name, cr in (("6051", "其他业务收入", 1200), ("605101", "出租固定资产收入", 1000), ("605102", "租金", 200),
                               ("60510201", "某甲", 200)):
            s.add(TbBalance(project_id=P, year=YEAR, company_code="001", account_code=code, account_name=name,
                            credit_amount=cr, debit_amount=cr))
        s.add(AccountMapping(project_id=P, original_account_code="6051", standard_account_code="6051", mapping_type="manual"))
        s.add(AccountChart(project_id=P, account_code="6051", account_name="其他业务收入", direction=AccountDirection.credit,
                           level=1, category=AccountCategory.revenue, source=AccountSource.standard))
        # 已批准调整分录（贷其他业务收入 300）：税审取数不含，来源里列出「未计入」；草稿不列
        for no, status in (("AJE-1", ReviewStatus.approved), ("AJE-2", ReviewStatus.draft)):
            gid = uuid.uuid4()
            adj = Adjustment(project_id=P, year=YEAR, company_code="001", adjustment_no=no, adjustment_type=AdjustmentType.aje,
                             description=f"{no} 补确认租金", account_code="6051", entry_group_id=gid, review_status=status,
                             created_by=EDITOR)
            s.add(adj)
            await s.flush()
            s.add(AdjustmentEntry(adjustment_id=adj.id, entry_group_id=gid, line_no=1, standard_account_code="6051",
                                  debit_amount=0, credit_amount=300))
        await s.commit()

    current = {"actor": ACTORS["editor"]}
    app = FastAPI()
    app.include_router(sources_router)
    app.include_router(sheets_router)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "as": lambda k: current.update(actor=ACTORS[k])}
    await engine.dispose()


def _sum(src: dict) -> Decimal:
    return sum((Decimal(i["amount"]) * Decimal(i["sign"]) for i in src["items"] if i["amount"] is not None), Decimal(0))


async def _cells(env, code: str = "2-02", **params) -> dict:
    r = await env["client"].get(f"{SRC}/{code}", params={"year": YEAR, **params})
    assert r.status_code == 200, r.text
    return r.json()["cells"]


@pytest.mark.asyncio
async def test_rule_cell_lists_accounts_summing_to_value(env):
    d10 = (await _cells(env))["2-02!D10"]
    assert d10["kind"] == "rule" and d10["value"] == "1000"
    assert d10["title"].startswith("科目余额表（导入数，不含审计调整）· 本期贷方发生额")
    accounts = [i for i in d10["items"] if i["sign"] != "0"]
    assert [i["label"] for i in accounts] == ["605101 出租固定资产收入"]
    assert accounts[0]["detail"] == "映射到 6051 其他业务收入"
    assert accounts[0]["link"] == {"page": "balance", "code": "605101"}
    assert d10["linear"] and d10["total"] == "1000" and d10["diff"] is None
    assert "出租固定资产收入" in d10["rule_text"]


@pytest.mark.asyncio
async def test_approved_adjustment_listed_but_not_counted(env):
    """已批准调整（AJE-1）列出、系数 0、不进合计；草稿（AJE-2）不列。"""
    d10 = (await _cells(env))["2-02!D10"]
    adj = [i for i in d10["items"] if i["sign"] == "0"]
    assert [i["label"] for i in adj] == ["调整分录 AJE-1"]
    assert adj[0]["amount"] == "-300" and adj[0]["link"]["page"] == "adjustments"
    assert any("未计入本格" in n for n in d10["notes"])
    assert d10["total"] == "1000"


@pytest.mark.asyncio
async def test_every_linear_cell_reconciles(env):
    """全表：线性的格（取数 / 公式）构成之和都等于格值，没有一格对不上。"""
    cells = await _cells(env)
    linear = {k: s for k, s in cells.items() if s["linear"]}
    assert len(linear) >= 5
    for k, s in linear.items():
        assert s["diff"] is None, (k, s)
        value = Decimal(s["value"]) if s["value"] not in (None, "") else Decimal(0)
        assert abs(_sum(s) - value) < Decimal("0.005"), k


@pytest.mark.asyncio
async def test_formula_cell_lists_referenced_cells(env):
    g10 = (await _cells(env))["2-02!G10"]
    assert g10["kind"] == "formula" and g10["title"] == "公式计算：=D10+F10-E10"
    by_ref = {i["link"]["ref"]: i for i in g10["items"]}
    assert set(by_ref) == {"D10"} | ({"E10", "F10"} & set(by_ref))  # 空格不列
    assert by_ref["D10"]["sign"] == "1" and by_ref["D10"]["amount"] == "1000"
    assert by_ref["D10"]["link"] == {"page": "workpaper", "code": "2-02", "sheet": "2-02", "ref": "D10"}
    assert g10["total"] == "1000" and g10["diff"] is None


@pytest.mark.asyncio
async def test_manual_value_keeps_auto_breakdown_and_saver(env):
    c = env["client"]
    r = await c.put(SHEETS + "/2-02", params={"year": YEAR}, json={"version": 0, "inputs": {"2-02": {"D10": 1500}}})
    assert r.status_code == 200, r.text
    cells = await _cells(env)
    d10 = cells["2-02!D10"]
    assert d10["kind"] == "manual"
    assert d10["manual"]["value"] == "1500" and d10["manual"]["auto"] == "1000"
    assert d10["manual"]["by_name"] == "编制人甲" and d10["manual"]["at"]
    assert d10["value"] == "1000" and d10["diff"] is None  # 构成仍按原取数值核对
    # 下游公式按手工值算
    assert cells["2-02!G10"]["value"] == "1500" and cells["2-02!G10"]["diff"] is None


@pytest.mark.asyncio
async def test_tax_return_domain_and_404(env):
    r = await env["client"].get(f"{SRC}/2-02", params={"year": YEAR, "domain": "tax_return"})
    assert r.status_code == 404
    r = await env["client"].get(f"{SRC}/A100000", params={"year": YEAR, "domain": "tax_return"})
    assert r.status_code == 200, r.text
    d3 = r.json()["cells"]["A100000!D3"]
    assert d3["kind"] == "formula" and d3["linear"]
    assert all(i["link"]["page"] == "tax_return" for i in d3["items"])
    # 行名取左侧最近的项目名，不取行次数字、也不取更靠左的合并类别列
    labels = {i["link"]["ref"] if i["link"]["sheet"] == "A101010" else None: i["label"] for i in d3["items"]}
    assert labels["C3"].startswith("A101010 C3 一、营业收入"), labels["C3"]


@pytest.mark.asyncio
@pytest.mark.parametrize("who,status", [("editor", 200), ("admin", 200), ("outsider", 403)])
async def test_project_readonly_required(env, who, status):
    env["as"](who)
    r = await env["client"].get(f"{SRC}/2-02", params={"year": YEAR})
    assert r.status_code == status


@pytest.mark.parametrize("formula,expect", [
    ("=A1+B1-C1", {"A1": 1, "B1": 1, "C1": -1}),
    ("=SUM(A1:A2)*2", {"A1": 2, "A2": 2}),
    ("=-(A1-B1)/4", {"A1": Decimal("-0.25"), "B1": Decimal("0.25")}),
    ("=A1+A1", {"A1": 2}),
])
def test_linear_terms_coefficients(formula, expect):
    terms, const = linear_terms(parse_formula(formula, "S"))
    flat: dict[str, Decimal] = {}
    for (_, _, r1, c1, r2, c2), coef in terms.items():
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                key = f"{chr(64 + c)}{r}"
                flat[key] = flat.get(key, Decimal(0)) + coef
    assert flat == {k: Decimal(v) for k, v in expect.items()} and const == 0


@pytest.mark.parametrize("formula", ["=IF(A1>0,A1,0)", "=MIN(A1,B1)", "=A1*B1", "=ROUND(A1,2)", "=A1/B1"])
def test_nonlinear_formulas_rejected(formula):
    assert linear_terms(parse_formula(formula, "S")) is None


def test_cancelled_reference_has_zero_coefficient():
    """区域里含、又单独减掉的格（2-05 G18 =SUM(G8:G17)-G9 这类）系数为 0：来源里不列为构成项，改写说明。"""
    terms, _ = linear_terms(parse_formula("=SUM(A1:A3)-A2", "S"))
    flat: dict[int, Decimal] = {}
    for (_, _, r1, _, r2, _), coef in terms.items():
        for r in range(r1, r2 + 1):
            flat[r] = flat.get(r, Decimal(0)) + coef
    assert flat == {1: 1, 2: 0, 3: 1}
