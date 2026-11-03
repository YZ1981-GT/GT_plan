"""鉴证报告接口（真发请求；spec citar-assurance-report-menus R6）。

只替换 ``get_current_user`` 与 ``get_db``（SQLite 内存库）；鉴权、service、计算模型全部真实执行。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest
import pytest_asyncio
from docx import Document
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory, AccountChart, AccountMapping, Adjustment, AdjustmentEntry, TbBalance, TbLedger, TrialBalance,
)
from app.models.base import Base, PermissionLevel  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, User, UserRole  # noqa: E402
from app.models.report_models import FinancialReport  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402
from app.models.tax_workpaper_models import TaxWorkpaperInput  # noqa: E402
from app.routers.tax_assurance import router  # noqa: E402
from app.routers.tax_workpapers import router as workpaper_router  # noqa: E402

P = uuid.UUID("00000000-0000-0000-0000-00000000b101")
EDITOR = uuid.UUID("00000000-0000-0000-0000-00000000b001")
READER = uuid.UUID("00000000-0000-0000-0000-00000000b002")
OUTSIDER = uuid.UUID("00000000-0000-0000-0000-00000000b003")
YEAR = 2025
URL = f"/api/projects/{P}/tax-assurance"


class _Actor:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.auditor) -> None:
        self.id = uid
        self.role = role
        self.username = f"u-{uid.hex[-4:]}"
        self.is_active = True


# 编制人用合伙人身份：循环范围不限（受限成员按循环过滤科目，另有用例）
ACTORS = {"editor": _Actor(EDITOR, UserRole.partner), "reader": _Actor(READER), "outsider": _Actor(OUTSIDER)}
_TABLES = [User.__table__, Project.__table__, ProjectUser.__table__, TbBalance.__table__, TbLedger.__table__, AccountMapping.__table__,
           TaxWorkpaperInput.__table__, TrialBalance.__table__, AccountChart.__table__, Adjustment.__table__,
           AdjustmentEntry.__table__, FinancialReport.__table__, StaffMember.__table__, ProjectAssignment.__table__]

#: 标准科目 → (类别, 审定数自然正数, 期初自然正数)
TB = {
    "1002": (AccountCategory.asset, 500, 400),
    "1122": (AccountCategory.asset, 300, 200),
    "2202": (AccountCategory.liability, 200, 100),
    "3001": (AccountCategory.equity, 500, 500),
    "3201": (AccountCategory.equity, 100, 0),
    "6001": (AccountCategory.revenue, 1000, 0),
    "6401": (AccountCategory.expense, 900, 0),
}


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(Project(id=P, name="项目P", client_name="甲公司", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=EDITOR))
        await s.flush()
        s.add(ProjectUser(project_id=P, user_id=EDITOR, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
        s.add(ProjectUser(project_id=P, user_id=READER, role=ProjectUserRole.auditor, permission_level=PermissionLevel.readonly))
        for code, (cat, audited, opening) in TB.items():
            s.add(TrialBalance(project_id=P, year=YEAR, company_code="001", standard_account_code=code,
                               account_category=cat, audited_amount=Decimal(audited), unadjusted_amount=Decimal(audited),
                               opening_balance=Decimal(opening)))
        # 1-12 企业基础信息表第 107 项：300 企业会计制度（申报表 A000000!F6 取自这里）
        s.add(TaxWorkpaperInput(project_id=P, year=YEAR, sheet_code="1-12", inputs={"1-12": {"F6": 300}}, version=1))
        await s.commit()

    current = {"actor": ACTORS["editor"]}
    app = FastAPI()
    app.include_router(router)
    app.include_router(workpaper_router)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "as": lambda k: current.update(actor=ACTORS[k])}
    await engine.dispose()


Y = {"year": YEAR}


def _n(v: dict | None) -> Decimal | None:
    """接口金额 {n: "500.00"} / {n: "500"} → 数值（只比数值，不比小数位写法）。"""
    return Decimal(v["n"]) if v and "n" in v else None


@pytest.mark.asyncio
async def test_tax_return_sheet_and_forms_mark(env):
    c = env["client"]
    r = await c.get(f"{URL}/tax-return/sheets/A000000", params=Y)
    assert r.status_code == 200, r.text
    assert r.json()["parts"][0]["values"]["F6"] == {"n": "300"}  # 取自底稿 1-12
    cover = await c.get(f"{URL}/tax-return/sheets/TR-COVER", params=Y)
    assert cover.json()["parts"][0]["values"]["A6"] == {"s": "税款所属期间：2025年1月1日至2025年12月31日"}
    saved = await c.put(f"{URL}/tax-return/sheets/TR-FORMS", params=Y,
                        json={"version": 0, "inputs": {"表单": {"C7": "□"}}})
    assert saved.status_code == 200, saved.text
    assert saved.json()["parts"][0]["values"]["C7"] == {"s": "□"}
    # 公式格不能填
    bad = await c.put(f"{URL}/tax-return/sheets/A000000", params=Y, json={"version": 0, "inputs": {"A000000": {"F6": 100}}})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_domains_are_separate(env):
    c = env["client"]
    assert (await c.get(f"{URL}/tax-return/sheets/2-02", params=Y)).status_code == 404
    assert (await c.get(f"{URL}/tax-return/sheets/RN-RULES", params=Y)).status_code == 404
    assert (await c.get(f"/api/projects/{P}/tax-workpapers/sheets/A100000", params=Y)).status_code == 404
    assert (await c.put(f"/api/projects/{P}/tax-workpapers/sheets/RN-RULES", params=Y,
                        json={"version": 0, "inputs": {}})).status_code == 404


@pytest.mark.asyncio
async def test_tax_return_export_hides_unfiled(env):
    c = env["client"]
    await c.put(f"{URL}/tax-return/sheets/TR-FORMS", params=Y, json={"version": 0, "inputs": {"表单": {"C7": "□"}}})
    r = await c.get(f"{URL}/tax-return/export", params=Y)
    assert r.status_code == 200, r.text
    book = openpyxl.load_workbook(BytesIO(r.content))
    assert book["A101020"].sheet_state == "hidden"
    assert book["A100000"].sheet_state == "visible"
    assert book["表单"]["C7"].value == "□"
    assert book["申报表封面"]["D11"].value == "甲公司"
    assert not any(isinstance(cell.value, str) and cell.value.startswith("=") for ws in book for row in ws.iter_rows() for cell in row)


@pytest.mark.asyncio
async def test_report_body_and_date(env):
    c = env["client"]
    r = await c.get(f"{URL}/report-body", params=Y)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cover"]["client"] == "甲公司"
    assert body["cover"]["period"] == "2025年度"
    assert len(body["lines"]) == 25
    assert body["lines"][11]["amount_text"] == "25%"
    assert body["report_date_text"] == "日期：2026年  月  日"
    saved = await c.put(f"{URL}/report-body", params=Y, json={"version": 0, "report_date": "2026-04-30"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["report_date_text"] == "日期：2026年4月30日"
    stale = await c.put(f"{URL}/report-body", params=Y, json={"version": 0, "report_date": "2026-05-01"})
    assert stale.status_code == 409
    bad = await c.put(f"{URL}/report-body", params=Y, json={"version": 1, "report_date": "2026-13-01"})
    assert bad.status_code == 422
    doc = await c.get(f"{URL}/report-body/export", params=Y)
    assert doc.status_code == 200
    text = "\n".join(p.text for p in Document(BytesIO(doc.content)).paragraphs)
    assert "甲公司" in text and "2026年4月30日" in text and "{{" not in text


@pytest.mark.asyncio
async def test_review_notes_and_export(env):
    c = env["client"]
    r = await c.get(f"{URL}/review-notes", params=Y)
    assert r.status_code == 200, r.text
    paras = [p["text"] for p in r.json()["paragraphs"]]
    assert "企业所得税年度纳税申报审核报告说明" in paras
    assert "被审核单位名称：甲公司；" in paras
    assert any(p.startswith("一、") for p in paras)
    doc = await c.get(f"{URL}/review-notes/export", params=Y)
    assert doc.status_code == 200
    d = Document(BytesIO(doc.content))
    assert len(d.paragraphs) == len(paras)
    header = "".join(p.text for p in d.sections[0].header.paragraphs)
    assert "甲公司" in header and "{{" not in header


@pytest.mark.asyncio
async def test_financial_statements_enterprise_system(env):
    c = env["client"]
    r = await c.get(f"{URL}/financial-statements", params=Y)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["format"] == "enterprise_system" and data["standard_code"] == "300"
    bs = {row["r"]: row for row in data["statements"][0]["rows"]}
    assert _n(bs[7]["current"]) == 500 and _n(bs[7]["prior"]) == 400
    assert _n(bs[47]["current"]) == 800
    pl = {row["r"]: row for row in data["statements"][2]["rows"]}
    assert _n(pl[6]["current"]) == 1000 and _n(pl[25]["current"]) == 100
    assert pl[6]["prior"] is None
    assert any("上期金额为空" in n for n in data["notices"])
    assert all(chk["ok"] for chk in data["checks"])
    x = await c.get(f"{URL}/financial-statements/export", params=Y)
    assert x.status_code == 200
    book = openpyxl.load_workbook(BytesIO(x.content))
    assert book.sheetnames[:3] == ["资产负债表", "资产负债表（续）", "利润表"]


@pytest.mark.asyncio
async def test_financial_statements_scoped_member_is_told(env):
    """受限成员（未分配循环）只看到自己循环的科目：报表为空并提示，不当作全量数。"""
    env["as"]("reader")
    data = (await env["client"].get(f"{URL}/financial-statements", params=Y)).json()
    assert any("分配给你的审计循环" in n for n in data["notices"])
    bs = {row["r"]: row for row in data["statements"][0]["rows"]}
    assert _n(bs[7]["current"]) == 0


@pytest.mark.asyncio
async def test_financial_statements_cas_when_code_1xx(env):
    c = env["client"]
    await c.put(f"/api/projects/{P}/tax-workpapers/sheets/1-12", params=Y,
                json={"version": 1, "inputs": {"1-12": {"F6": 110}}})
    data = (await c.get(f"{URL}/financial-statements", params=Y)).json()
    assert data["format"] == "cas"
    assert any("审定报表" in n for n in data["notices"])


@pytest.mark.asyncio
async def test_authorization(env):
    c = env["client"]
    env["as"]("reader")
    for path in ("report-body", "review-notes", "financial-statements", "tax-return/sheets/A100000"):
        assert (await c.get(f"{URL}/{path}", params=Y)).status_code == 200, path
    assert (await c.put(f"{URL}/report-body", params=Y, json={"version": 0, "report_date": None})).status_code == 403
    assert (await c.put(f"{URL}/tax-return/sheets/TR-FORMS", params=Y, json={"version": 0, "inputs": {}})).status_code == 403
    env["as"]("outsider")
    for path in ("report-body", "review-notes", "financial-statements", "tax-return/sheets/A100000",
                 "tax-return/export", "report-body/export", "review-notes/export", "financial-statements/export"):
        assert (await c.get(f"{URL}/{path}", params=Y)).status_code == 403, path
