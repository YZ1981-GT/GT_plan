"""鉴证报告接口（真发请求；spec citar-assurance-report-menus R6）。

只替换 ``get_current_user`` 与 ``get_db``（SQLite 内存库）；鉴权、service、计算模型全部真实执行。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date
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
    AccountCategory, AccountChart, AccountMapping, Adjustment, AdjustmentEntry, MappingType, TbBalance, TbLedger, TrialBalance,
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
        yield {"client": client, "as": lambda k: current.update(actor=ACTORS[k]),
               "use": lambda actor: current.update(actor=actor), "db": factory}
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
    # 公式格可手工修改：手工值盖过取自底稿的值，带原公式值（spec citar-table-manual-edit R1）
    over = await c.put(f"{URL}/tax-return/sheets/A000000", params=Y, json={"version": 0, "inputs": {"A000000": {"F6": 100}}})
    assert over.status_code == 200, over.text
    assert over.json()["parts"][0]["values"]["F6"] == {"n": "100"}
    assert over.json()["parts"][0]["cells"]["F6"] == {"origin": "input", "auto": {"n": "300"}}


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
async def test_report_body_amounts_manual_and_restore(env):
    """摘录表金额可改：写底稿 1-01 的手工值、带原值、Word 用改后金额；不提交的行恢复（spec citar-table-manual-edit R9）。"""
    c = env["client"]
    # 1-01 已有一个别的手工值，保存金额不能把它冲掉
    pre = await c.put(f"/api/projects/{P}/tax-workpapers/sheets/1-01", params=Y,
                      json={"version": 0, "inputs": {"1-01报告正文": {"A4": "某税务局："}}})
    assert pre.status_code == 200, pre.text
    body = (await c.get(f"{URL}/report-body", params=Y)).json()
    assert body["amounts_version"] == 1
    line17 = body["lines"][0]
    assert line17["row"] == 17 and line17["manual"] is False
    auto17 = line17["amount"]

    saved = await c.put(f"{URL}/report-body/amounts", params=Y,
                        json={"version": 1, "values": {"17": 123456.78, "28": 0.2}})
    assert saved.status_code == 200, saved.text
    lines = {ln["row"]: ln for ln in saved.json()["lines"]}
    assert _n(lines[17]["amount"]) == Decimal("123456.78") and lines[17]["manual"] is True
    assert lines[17]["auto"] == auto17
    assert lines[28]["amount_text"] == "20%" and _n(lines[28]["auto"]) == Decimal("0.25")
    assert saved.json()["addressee"] == "某税务局："
    doc = Document(BytesIO((await c.get(f"{URL}/report-body/export", params=Y)).content))
    texts = [p.text for p in doc.paragraphs] + [cell.text for t in doc.tables for row in t.rows for cell in row.cells]
    assert any("123,456.78" in t for t in texts)

    # 税审底稿 1-01 同一处
    sheet = (await c.get(f"/api/projects/{P}/tax-workpapers/sheets/1-01", params=Y)).json()
    part = next(p for p in sheet["parts"] if p["source"] == "1-01报告正文")
    assert part["cells"]["F17"]["origin"] == "input" and part["values"]["A4"] == {"s": "某税务局："}

    restored = await c.put(f"{URL}/report-body/amounts", params=Y, json={"version": 2, "values": {"28": 0.2}})
    lines = {ln["row"]: ln for ln in restored.json()["lines"]}
    assert lines[17]["manual"] is False and lines[17]["amount"] == auto17
    assert lines[28]["manual"] is True

    assert (await c.put(f"{URL}/report-body/amounts", params=Y, json={"version": 2, "values": {}})).status_code == 409
    for bad in ({"16": 1}, {"17": "abc"}, {"17": True}):
        r = await c.put(f"{URL}/report-body/amounts", params=Y, json={"version": 3, "values": bad})
        assert r.status_code == 422, bad


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
async def test_review_notes_edit_delete_restore(env):
    """段落可改 / 删 / 恢复，Word 用改后的段落（spec citar-table-manual-edit R8）。"""
    c = env["client"]
    first = (await c.get(f"{URL}/review-notes", params=Y)).json()
    assert first["version"] == 0 and first["edits"] == {} and first["deleted"] == []
    target = next(p for p in first["paragraphs"] if p["body"].startswith("被审核单位名称"))
    drop = next(p for p in first["paragraphs"] if p["key"] != target["key"] and p["level"] is None and p["body"] != target["body"])
    edits = {
        target["key"]: {"text": "被审核单位名称：甲公司（全称）；", "auto": target["auto_body"]},
        drop["key"]: {"text": None, "auto": drop["auto_body"]},
    }
    saved = await c.put(f"{URL}/review-notes", params=Y, json={"version": 0, "edits": edits})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["version"] == 1
    texts = [p["text"] for p in body["paragraphs"]]
    assert any(t.endswith("被审核单位名称：甲公司（全称）；") for t in texts)
    assert drop["key"] not in {p["key"] for p in body["paragraphs"]}
    assert [d["key"] for d in body["deleted"]] == [drop["key"]]
    doc = Document(BytesIO((await c.get(f"{URL}/review-notes/export", params=Y)).content))
    assert any("甲公司（全称）" in p.text for p in doc.paragraphs)
    assert len(doc.paragraphs) == len(texts)

    restored = await c.put(f"{URL}/review-notes", params=Y, json={"version": 1, "edits": {}})
    assert [p["text"] for p in restored.json()["paragraphs"]] == [p["text"] for p in first["paragraphs"]]
    assert (await c.put(f"{URL}/review-notes", params=Y, json={"version": 1, "edits": {}})).status_code == 409
    for bad in ({"x1": {"text": "a"}}, {"r5": {"text": "  "}}, {"r5": {"text": 1}}):
        assert (await c.put(f"{URL}/review-notes", params=Y, json={"version": 2, "edits": bad})).status_code == 422, bad
    env["as"]("reader")
    assert (await c.put(f"{URL}/review-notes", params=Y, json={"version": 2, "edits": {}})).status_code == 403


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
    # 点「其他问题」定位：上期为空的提示指向利润表上期金额整列
    prior_notice = next(n for n in data["notices"] if "上期金额为空" in n)
    assert data["notice_targets"][prior_notice] == [{"statement": "income_statement", "r": None, "column": "prior"}]
    # 源头：去数据导入导上年账套（spec citar-fs-issue-source-locate R3）
    assert [s["page"] for s in data["notice_sources"][prior_notice]] == ["ledger_import"]
    assert all(chk["ok"] for chk in data["checks"])
    assert not any("sources" in chk for chk in data["checks"])
    keys = {s["key"]: {row["r"] for row in s["rows"]} for s in data["statements"]}
    for chk in data["checks"]:
        # 平衡校验指向「资产总计」「负债和所有者权益总计」两格，且两行都在返回的表里
        assert [(t["statement"], t["r"]) for t in chk["targets"]] == [("balance_sheet", 47), ("balance_sheet_liabilities", 46)]
        assert all(t["r"] in keys[t["statement"]] for t in chk["targets"])
        assert {t["column"] for t in chk["targets"]} == {"current" if chk["label"].startswith("期末") else "prior"}
    for stmt_key, r in (("balance_sheet", 47), ("balance_sheet_liabilities", 46)):
        row = next(x for x in next(s for s in data["statements"] if s["key"] == stmt_key)["rows"] if x["r"] == r)
        assert row["label"] in ("资产总计", "负债和所有者权益总计")
    x = await c.get(f"{URL}/financial-statements/export", params=Y)
    assert x.status_code == 200
    book = openpyxl.load_workbook(BytesIO(x.content))
    assert book.sheetnames[:3] == ["资产负债表", "资产负债表（续）", "利润表"]


@pytest.mark.asyncio
async def test_financial_statements_manual_values(env):
    """企业会计制度格式手工值：合计、平衡校验、导出都按手工值；带原值；整份替换即恢复（spec citar-table-manual-edit R7）。"""
    c = env["client"]
    first = (await c.get(f"{URL}/financial-statements", params=Y)).json()
    assert first["version"] == 0 and first["statements"][0]["source"] == "fs"
    saved = await c.put(f"{URL}/financial-statements", params=Y,
                        json={"version": 0, "values": {"balance_sheet": {"7": {"current": 600}}}})
    assert saved.status_code == 200, saved.text
    data = saved.json()
    bs = {row["r"]: row for row in data["statements"][0]["rows"]}
    assert _n(bs[7]["current"]) == 600 and _n(bs[7]["manual"]["current"]["auto"]) == 500
    assert bs[7]["manual"].get("prior") is None
    assert _n(bs[47]["current"]) == 900 and bs[47]["manual"] is None
    check = next(chk for chk in data["checks"] if chk["label"].startswith("期末"))
    assert check["ok"] is False and _n(check["difference"]) == 100
    # 差额来源：本页手工修改的那一格（spec citar-fs-issue-source-locate R1）
    assert [s["kind"] for s in check["sources"]] == ["manual"]
    assert _n(check["sources"][0]["amount"]) == 100
    cell = check["sources"][0]["rows"][0]
    assert (cell["statement"], cell["r"], cell["column"], _n(cell["amount"])) == ("balance_sheet", 7, "current", 100)
    book = openpyxl.load_workbook(BytesIO((await c.get(f"{URL}/financial-statements/export", params=Y)).content))
    assert 600 in [cell.value for row in book["资产负债表"].iter_rows() for cell in row]

    heading = next(r["r"] for r in first["statements"][0]["rows"] if r["heading"])
    for bad in ({"balance_sheet": {str(heading): {"current": 1}}}, {"nope": {}},
                {"balance_sheet": {"7": {"total": 1}}}, {"balance_sheet": {"7": {"current": "x"}}}):
        assert (await c.put(f"{URL}/financial-statements", params=Y, json={"version": 1, "values": bad})).status_code == 422, bad
    restored = (await c.put(f"{URL}/financial-statements", params=Y, json={"version": 1, "values": {}})).json()
    bs = {row["r"]: row for row in restored["statements"][0]["rows"]}
    assert _n(bs[7]["current"]) == 500 and bs[7]["manual"] is None
    env["as"]("reader")
    assert (await c.put(f"{URL}/financial-statements", params=Y, json={"version": 2, "values": {}})).status_code == 403


#: 客户末级科目 → (标准科目或 None, 期初, 借, 贷, 期末)，金额借正贷负；与 TB 试算表一致，另加两处不平：
#: 5801 余额表借方 −50 而序时账没有分录（→ 6901 未结转损益）；1221 / 2241 一对其中 1221 未映射（期末 30）
LEAVES = {
    "1002": ("1002", 400, 1100, 1000, 500), "1122": ("1122", 200, 300, 200, 300),
    "2202": ("2202", -100, 100, 200, -200), "3001": ("3001", -500, 0, 0, -500),
    "3201": ("3201", 0, 0, 100, -100), "6001": ("6001", 0, 1000, 1000, 0), "6401": ("6401", 0, 900, 900, 0),
    "5801": ("6901", 0, -50, 0, -50), "1221": (None, 0, 30, 0, 30), "2241": ("2241", 0, 0, 30, -30),
}
#: 序时账逐科目 (借, 贷)：除 5801 外与余额表一致，借贷合计相等
LEDGER = {"1002": (1100, 1000), "1122": (300, 200), "2202": (100, 200), "3201": (0, 100),
          "6001": (1000, 1000), "6401": (900, 900), "1221": (30, 0), "2241": (0, 30)}


async def _seed_ledger(env, *, ledger: bool = True) -> None:
    def signed(v: int) -> tuple[Decimal, str]:
        return Decimal(abs(v)), "credit" if v < 0 else "debit"

    async with env["db"]() as s:
        for code, (std, op, dr, cr, cl) in LEAVES.items():
            op_amt, op_dir = signed(op)
            cl_amt, cl_dir = signed(cl)
            s.add(TbBalance(project_id=P, year=YEAR, company_code="001", account_code=code, account_name=f"科目{code}",
                            opening_balance=op_amt, opening_direction=op_dir, debit_amount=Decimal(dr),
                            credit_amount=Decimal(cr), closing_balance=cl_amt, closing_direction=cl_dir))
            if std:
                s.add(AccountMapping(project_id=P, original_account_code=code, original_account_name=f"科目{code}",
                                     standard_account_code=std, mapping_type=MappingType.manual))
        if ledger:
            for i, (code, (dr, cr)) in enumerate(LEDGER.items()):
                s.add(TbLedger(project_id=P, year=YEAR, company_code="001", voucher_date=date(YEAR, 6, 30),
                               voucher_no=f"记-{i}", account_code=code, debit_amount=Decimal(dr), credit_amount=Decimal(cr)))
        await s.commit()


@pytest.mark.asyncio
async def test_financial_statements_unbalanced_sources(env):
    """期末不平拆到源头行：余额表与序时账不一致 5801、未映射 1221，两项之和 = 差额（spec citar-fs-issue-source-locate R1）。"""
    await _seed_ledger(env)
    data = (await env["client"].get(f"{URL}/financial-statements", params=Y)).json()
    check = next(c for c in data["checks"] if c["column"] == "current")
    assert check["ok"] is False and _n(check["difference"]) == -80
    sources = {s["kind"]: s for s in check["sources"]}
    assert set(sources) == {"ledger_mismatch", "unmapped"}
    assert sum(_n(s["amount"]) for s in check["sources"]) == _n(check["difference"])
    mism = sources["ledger_mismatch"]
    assert mism["page"] == "balance" and _n(mism["amount"]) == -50
    assert [(r["code"], _n(r["amount"]), r["journal"]) for r in mism["rows"]] == [("5801", -50, True)]
    assert "序时账 借 0.00 贷 0.00" in mism["rows"][0]["note"]
    un = sources["unmapped"]
    assert un["page"] == "mapping" and [(r["code"], _n(r["amount"])) for r in un["rows"]] == [("1221", -30)]
    # 上年年末平衡：不拆
    assert next(c for c in data["checks"] if c["column"] == "prior")["ok"] is True
    # 导出不受影响；受限成员不拆来源
    assert (await env["client"].get(f"{URL}/financial-statements/export", params=Y)).status_code == 200
    env["as"]("reader")
    scoped = (await env["client"].get(f"{URL}/financial-statements", params=Y)).json()
    assert not any(c.get("sources") for c in scoped["checks"])


@pytest.mark.asyncio
async def test_financial_statements_unbalanced_without_ledger(env):
    """没有序时账：本期借贷不平只能指到科目余额表页，金额仍对得上。"""
    await _seed_ledger(env, ledger=False)
    data = (await env["client"].get(f"{URL}/financial-statements", params=Y)).json()
    check = next(c for c in data["checks"] if c["column"] == "current")
    sources = {s["kind"]: s for s in check["sources"]}
    assert set(sources) == {"balance_movement", "unmapped"}
    assert sources["balance_movement"]["page"] == "balance" and sources["balance_movement"]["rows"] == []
    assert _n(sources["balance_movement"]["amount"]) == -50
    assert "借方合计 3,380.00、贷方合计 3,430.00" in sources["balance_movement"]["title"]
    assert sum(_n(s["amount"]) for s in check["sources"]) == _n(check["difference"])


def test_fs_balance_coefficients():
    """每个标准科目 1 元对差额的影响：资产负债类 1，损益类 0（经未结转损益进未分配利润，系数 1）。"""
    from app.services.tax_assurance import fs_balance_sources as fbs

    for code in ("1002", "1122", "1602", "2202", "2241", "3001", "3201"):
        assert fbs.coefficient(code) == 1, code
    assert fbs.coefficient("6001") == 0 and fbs.coefficient("6901") == 0
    assert fbs.coefficient("9999") == 0  # 不在任何项目
    assert fbs.pl_close_coefficient() == 1


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
    # 未生成报表的提示：指向每张未生成的表（整张表，不定位到行列）
    missing = next(n for n in data["notices"] if "尚未生成" in n)
    targets = data["notice_targets"][missing]
    assert targets and all(t["r"] is None and t["column"] is None for t in targets)
    assert {t["statement"] for t in targets} <= {s["key"] for s in data["statements"]}


@pytest.mark.asyncio
async def test_authorization(env):
    c = env["client"]
    env["as"]("reader")
    for path in ("report-body", "review-notes", "financial-statements", "tax-return/sheets/A100000"):
        assert (await c.get(f"{URL}/{path}", params=Y)).status_code == 200, path
    assert (await c.put(f"{URL}/report-body", params=Y, json={"version": 0, "report_date": None})).status_code == 403
    assert (await c.put(f"{URL}/report-body/amounts", params=Y, json={"version": 0, "values": {}})).status_code == 403
    assert (await c.put(f"{URL}/tax-return/sheets/TR-FORMS", params=Y, json={"version": 0, "inputs": {}})).status_code == 403
    env["as"]("outsider")
    for path in ("report-body", "review-notes", "financial-statements", "tax-return/sheets/A100000",
                 "tax-return/export", "report-body/export", "review-notes/export", "financial-statements/export"):
        assert (await c.get(f"{URL}/{path}", params=Y)).status_code == 403, path


@pytest.mark.asyncio
async def test_account_without_manual_edit(env):
    """账号未开通「允许修改」（spec citar-manual-edit-permission R2，2026-11-04 改为整表只读）：
    摘录表金额、审核说明、单体报表手工值、申报表格子、是否填报、报告日期一律 403；查看与导出照常。"""
    c = env["client"]
    locked = _Actor(EDITOR, UserRole.partner)
    locked.allow_manual_edit = False
    env["use"](locked)
    denied = [
        ("report-body/amounts", {"version": 0, "values": {"17": 1}}),
        ("review-notes", {"version": 0, "edits": {}}),
        ("financial-statements", {"version": 0, "values": {}}),
        ("tax-return/sheets/A000000", {"version": 0, "inputs": {"A000000": {"F6": 100}}}),
        ("tax-return/sheets/TR-FORMS", {"version": 0, "inputs": {"表单": {"C7": "□"}}}),
        ("report-body", {"version": 0, "report_date": "2026-03-01"}),
    ]
    for path, body in denied:
        r = await c.put(f"{URL}/{path}", params=Y, json=body)
        assert r.status_code == 403 and "允许修改" in r.text, (path, r.text)
    assert (await c.get(f"{URL}/report-body", params=Y)).json()["report_date"] in (None, "")
    for path in ("report-body", "review-notes", "financial-statements", "tax-return/export", "tax-return/sheets/TR-FORMS"):
        assert (await c.get(f"{URL}/{path}", params=Y)).status_code == 200, path
