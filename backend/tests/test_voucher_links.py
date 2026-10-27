"""挂凭按凭证键并记阶段（spec voucher-identity-writeback-and-audit-phase 任务 6，需求 2.5）

SQLite 真 ORM 行 + 端点级请求（只挂 voucher_links 与 ledger_penetration 两个路由；覆盖内层 get_db /
get_current_user，让真实的项目成员判定跑）：

- 同日同号两种凭证字分别挂同一底稿 → 两条记录，各记凭证字 / 主体 / 阶段；回拉按记录的凭证键只取各自分录；
- 只给日期 + 号却命中两张 → 409 + 候选，不落库；只给号且唯一 → 后端补全凭证键；找不到 → 404；
- 同一凭证挂同一底稿幂等（含软删后复活）；挂两张底稿各成一行；同号别月是两张凭证；
- 手工侧不复用、不改写抽凭引擎批次行；V210 前没有凭证字的旧行不被当成本凭证改写；
- 阶段缺省年审、非法值 422；只读成员不能挂、非成员看不到。
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TbLedger
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.workpaper_models import SampledVoucher
from app.services.voucher_identity import VoucherKey

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

REAL = json.loads((Path(__file__).parent / "fixtures" / "voucher_real_ledger_vectors.json").read_text(encoding="utf-8"))["vouchers"]
FY, ZZ = REAL["fy0003_same_day_same_no"], REAL["zz0003_same_day_same_no"]
COMPANY = FY[0]["company_code"]
YEAR = 2025
EDITOR, READER, STRANGER, PROJECT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
WP_A, WP_B = uuid.uuid4(), uuid.uuid4()


def _amount(v):
    return Decimal(v) if v not in (None, "") else None


def _row(x: dict, **over) -> TbLedger:
    x = {**x, **over}
    return TbLedger(
        project_id=PROJECT, year=YEAR, company_code=x["company_code"],
        voucher_date=date.fromisoformat(x["voucher_date"]), voucher_type=x["voucher_type"],
        voucher_no=x["voucher_no"], account_code=x["account_code"], account_name=x.get("account_name"),
        debit_amount=_amount(x["debit_amount"]), credit_amount=_amount(x["credit_amount"]), summary=x.get("summary"),
    )


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for uid, name in ((EDITOR, "editor"), (READER, "reader"), (STRANGER, "stranger")):
            session.add(User(id=uid, username=name, email=f"{name}@test.com", hashed_password="x", role="member"))
        session.add(Project(id=PROJECT, name="挂凭凭证键测试", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=EDITOR))
        session.add(ProjectUser(project_id=PROJECT, user_id=EDITOR, role="auditor", permission_level="edit",
                                is_deleted=False))
        session.add(ProjectUser(project_id=PROJECT, user_id=READER, role="auditor", permission_level="readonly",
                                is_deleted=False))
        session.add_all([_row(x) for x in FY + ZZ])
        session.add_all([_row(x, voucher_date="2025-02-07") for x in ZZ[:2]])  # 同号别月（ZZ）
        session.add_all([_row(x, voucher_no="0046", voucher_type=None) for x in FY])  # 凭证字为空、号唯一
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import ledger_penetration, voucher_links

    app = FastAPI()
    app.include_router(ledger_penetration.router)
    app.include_router(voucher_links.router)
    state = {"user": EDITOR}

    class _User:
        def __init__(self, uid):
            self.id = uid

        class _Role:
            value = "member"

        role = _Role()

    async def _db():
        yield db

    async def _user():
        return _User(state["user"])

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda uid: state.update(user=uid)  # type: ignore[attr-defined]
        yield c


def _url(path: str) -> str:
    return f"/api/projects/{PROJECT}/ledger/{path}"


async def _attach(client, **body):
    return await client.post(_url("sample-voucher"), json={"year": YEAR, **body})


async def _rows(db) -> list[SampledVoucher]:
    db.expire_all()
    return list((await db.execute(sa.select(SampledVoucher).order_by(SampledVoucher.voucher_date,
                                                                    SampledVoucher.voucher_type))).scalars())


async def test_two_voucher_types_same_day_same_no_are_two_records_and_pull_back_separately(client, db):
    for vtype in ("FY", "ZZ"):
        resp = await _attach(client, voucher_no="0003", voucher_date="2025-01-07", voucher_type=vtype,
                             working_paper_id=str(WP_A), account_code="1002")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "created" and resp.json()["voucher_type"] == vtype
    rows = await _rows(db)
    assert [(r.voucher_type, r.company_code, r.phase) for r in rows] == [("FY", COMPANY, "final"), ("ZZ", COMPANY, "final")]

    listed = (await client.get(_url("sampled-vouchers"), params={"year": YEAR, "working_paper_id": str(WP_A),
                                                                  "manual_only": True})).json()["items"]
    assert sorted(i["voucher_type"] for i in listed) == ["FY", "ZZ"]
    for rec in listed:
        assert rec["voucher_key"] == VoucherKey.of(year=YEAR, company_code=COMPANY, voucher_date="2025-01-07",
                                                   voucher_type=rec["voucher_type"], voucher_no="0003").to_str()
        # 回拉：按记录里的日期 + 凭证字穿透，只拿到这一张凭证的分录
        lines = (await client.get(_url("voucher/0003"), params={
            "year": YEAR, "voucher_date": rec["voucher_date"], "voucher_type": rec["voucher_type"]})).json()
        expected = FY if rec["voucher_type"] == "FY" else ZZ
        assert len(lines) == len(expected) and {x["voucher_type"] for x in lines} == {rec["voucher_type"]}
        assert all(x["voucher_key"] == rec["voucher_key"] for x in lines)


async def test_date_and_number_hitting_two_vouchers_is_409_and_writes_nothing(client, db):
    resp = await _attach(client, voucher_no="0003", voucher_date="2025-01-07", working_paper_id=str(WP_A))
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error_code"] == "VOUCHER_KEY_AMBIGUOUS"
    assert [c["voucher_type"] for c in detail["candidates"]] == ["FY", "ZZ"]
    assert await _rows(db) == []


async def test_unique_number_is_completed_from_the_ledger(client, db):
    resp = await _attach(client, voucher_no="0046", working_paper_id=str(WP_A))
    assert resp.status_code == 200, resp.text
    (row,) = await _rows(db)
    assert (row.voucher_date, row.voucher_type, row.company_code) == (date.fromisoformat(FY[0]["voucher_date"]), "", COMPANY)


async def test_voucher_not_in_ledger_is_404(client, db):
    resp = await _attach(client, voucher_no="9999", voucher_date="2025-01-07")
    assert resp.status_code == 404 and resp.json()["detail"]["error_code"] == "VOUCHER_NOT_FOUND"
    assert await _rows(db) == []


async def test_same_voucher_same_workpaper_is_idempotent_and_revives(client, db):
    body = {"voucher_no": "0003", "voucher_date": "2025-01-07", "voucher_type": "FY", "working_paper_id": str(WP_A)}
    first = (await _attach(client, **body)).json()
    assert (await _attach(client, **body)).json()["status"] == "updated"
    assert len(await _rows(db)) == 1
    assert (await client.delete(_url(f"sampled-vouchers/{first['id']}"))).status_code == 200
    again = (await _attach(client, **body)).json()
    assert again["status"] == "updated" and again["id"] == first["id"]
    (row,) = await _rows(db)
    assert row.is_deleted is False


async def test_two_workpapers_and_other_month_are_separate_records(client, db):
    for wp in (WP_A, WP_B):
        await _attach(client, voucher_no="0003", voucher_date="2025-01-07", voucher_type="ZZ", working_paper_id=str(wp))
    await _attach(client, voucher_no="0003", voucher_date="2025-02-07", voucher_type="ZZ", working_paper_id=str(WP_A))
    rows = await _rows(db)
    assert sorted((r.voucher_date.isoformat(), str(r.working_paper_id)) for r in rows) == sorted([
        ("2025-01-07", str(WP_A)), ("2025-01-07", str(WP_B)), ("2025-02-07", str(WP_A))])


async def test_manual_side_never_touches_engine_rows(client, db):
    batch = uuid.uuid4()
    db.add(SampledVoucher(id=uuid.uuid4(), project_id=PROJECT, year=YEAR, voucher_no="0003",
                          voucher_date=date(2025, 1, 7), company_code=COMPANY, voucher_type="FY",
                          working_paper_id=WP_A, batch_id=batch, phase="preliminary", note="引擎登记"))
    await db.commit()
    resp = await _attach(client, voucher_no="0003", voucher_date="2025-01-07", voucher_type="FY",
                         working_paper_id=str(WP_A), note="手工挂")
    assert resp.json()["status"] == "created"
    engine_row = next(r for r in await _rows(db) if r.batch_id == batch)
    assert (engine_row.note, engine_row.phase) == ("引擎登记", "preliminary")
    manual = (await client.get(_url("sampled-vouchers"), params={"year": YEAR, "manual_only": True})).json()["items"]
    assert [m["source"] for m in manual] == ["manual"]


async def test_old_row_without_voucher_type_is_not_rewritten(client, db):
    """V210 前的手工行没有凭证字 / 主体：说不清是 FY 还是 ZZ，不能被当成本次凭证改写（回拉时 409 提示重新挂凭）。"""
    old_id = uuid.uuid4()
    db.add(SampledVoucher(id=old_id, project_id=PROJECT, year=YEAR, voucher_no="0003",
                          voucher_date=date(2025, 1, 7), working_paper_id=WP_A))
    await db.commit()
    resp = await _attach(client, voucher_no="0003", voucher_date="2025-01-07", voucher_type="FY",
                         working_paper_id=str(WP_A))
    assert resp.json()["status"] == "created" and resp.json()["id"] != str(old_id)
    old = next(r for r in await _rows(db) if r.id == old_id)
    assert (old.voucher_type, old.company_code) == (None, None)


async def test_phase_recorded_defaulted_and_validated(client, db):
    resp = await _attach(client, voucher_no="0003", voucher_date="2025-01-07", voucher_type="FY",
                         working_paper_id=str(WP_A), phase="preliminary")
    assert resp.json()["phase"] == "preliminary"
    bad = await _attach(client, voucher_no="0003", voucher_date="2025-01-07", voucher_type="ZZ", phase="interim")
    assert bad.status_code == 422
    assert [r.phase for r in await _rows(db)] == ["preliminary"]


async def test_readonly_member_cannot_attach_and_stranger_cannot_list(client, db):
    client.as_user(READER)
    assert (await _attach(client, voucher_no="0046")).status_code == 403
    assert (await client.get(_url("sampled-vouchers"), params={"year": YEAR})).status_code == 200
    client.as_user(STRANGER)
    assert (await client.get(_url("sampled-vouchers"), params={"year": YEAR})).status_code == 403
    assert await _rows(db) == []


def test_routes_are_registered_once_in_the_real_app():
    """URL 不变、只注册一次：挂凭三端点从 ledger_penetration 迁到 voucher_links 后，真实应用里仍各有一条。"""
    from app.main import app

    want = {
        ("POST", "/api/projects/{project_id}/ledger/sample-voucher"),
        ("GET", "/api/projects/{project_id}/ledger/sampled-vouchers"),
        ("DELETE", "/api/projects/{project_id}/ledger/sampled-vouchers/{sampled_id}"),
    }
    seen = [(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods if (m, r.path) in want]
    assert sorted(seen) == sorted(want)
    owners = {r.endpoint.__module__ for r in app.routes if getattr(r, "path", "").endswith(("sample-voucher", "sampled-vouchers"))}
    assert owners == {"app.routers.voucher_links"}
