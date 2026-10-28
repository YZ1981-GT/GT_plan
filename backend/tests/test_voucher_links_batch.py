"""一张凭证挂多张底稿与已挂标识（spec voucher-identity-writeback-and-audit-phase 任务 14，需求 5，design §5）

SQLite 真 ORM 行 + 端点级请求（只挂 voucher_links 路由；覆盖内层 get_db / get_current_user，让真实的项目成员判定跑）：

- 批量挂凭：一张凭证 × 两张底稿各一行；再挂逐条 existed、原行不动；凭证对应多张 / 账套里没有 / 底稿不在本项目
  （别的项目的、已删的、不存在的）逐条失败、其余照挂；数据库拒绝的那一条只回滚它自己（保存点）；
- 阶段取项目当前阶段：已挂的行再挂不改阶段（单张端点同样），软删后复活按本次；请求体带阶段 / 多余字段 422；
- 上限：「凭证 × 底稿」超过 500 个组合 422、一条不写；已挂查询超过 500 个键 422；
- 已挂查询：手工与引擎登记按凭证键合并（同一底稿多个抽凭批次合成一条带条数），旧登记没记凭证字 / 主体的标
  legacy，没记日期的不显示，软删的不显示，别的项目的底稿不透出编码；
- 权限表驱动：批量挂凭要编辑权限（只读成员、非成员 403），查询要项目成员（非成员 403）。
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
from app.models.workpaper_models import SampledVoucher, WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.voucher_identity import VoucherKey

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

REAL = json.loads((Path(__file__).parent / "fixtures" / "voucher_real_ledger_vectors.json").read_text(encoding="utf-8"))["vouchers"]
FY, ZZ = REAL["fy0003_same_day_same_no"], REAL["zz0003_same_day_same_no"]
COMPANY = FY[0]["company_code"]
YEAR = 2025
EDITOR, READER, STRANGER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PROJECT, OTHER_PROJECT = uuid.uuid4(), uuid.uuid4()
WP_A, WP_B, WP_DELETED, WP_OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _key(vtype: str, vdate: str = "2025-01-07", no: str = "0003") -> str:
    return VoucherKey.of(year=YEAR, company_code=COMPANY, voucher_date=vdate, voucher_type=vtype, voucher_no=no).to_str()


FY_KEY, ZZ_KEY = _key("FY"), _key("ZZ")


def _amount(v):
    return Decimal(v) if v not in (None, "") else None


def _line(x: dict) -> TbLedger:
    return TbLedger(
        project_id=PROJECT, year=YEAR, company_code=x["company_code"],
        voucher_date=date.fromisoformat(x["voucher_date"]), voucher_type=x["voucher_type"],
        voucher_no=x["voucher_no"], account_code=x["account_code"], account_name=x.get("account_name"),
        debit_amount=_amount(x["debit_amount"]), credit_amount=_amount(x["credit_amount"]), summary=x.get("summary"),
    )


def _workpaper(session, wp_id, project_id, code, *, deleted=False):
    idx = WpIndex(id=uuid.uuid4(), project_id=project_id, wp_code=code, wp_name=f"{code} 底稿", status=WpStatus.not_started)
    session.add(idx)
    session.add(WorkingPaper(id=wp_id, project_id=project_id, wp_index_id=idx.id, file_path=f"{code}.xlsx",
                             source_type=WpSourceType.template, file_version=1, is_deleted=deleted))


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for uid, name in ((EDITOR, "editor"), (READER, "reader"), (STRANGER, "stranger")):
            session.add(User(id=uid, username=name, email=f"{name}@test.com", hashed_password="x", role="member"))
        for pid, name in ((PROJECT, "批量挂凭测试"), (OTHER_PROJECT, "别的项目")):
            session.add(Project(id=pid, name=name, client_name="测试", project_type=ProjectType.annual,
                                status=ProjectStatus.execution, created_by=EDITOR))
        session.add(ProjectUser(project_id=PROJECT, user_id=EDITOR, role="auditor", permission_level="edit",
                                is_deleted=False))
        session.add(ProjectUser(project_id=PROJECT, user_id=READER, role="auditor", permission_level="readonly",
                                is_deleted=False))
        _workpaper(session, WP_A, PROJECT, "J1-2")
        _workpaper(session, WP_B, PROJECT, "E1-23")
        _workpaper(session, WP_DELETED, PROJECT, "D2-5", deleted=True)
        _workpaper(session, WP_OTHER, OTHER_PROJECT, "F3-7")
        session.add_all([_line(x) for x in FY + ZZ])
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import voucher_links

    app = FastAPI()
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


def _voucher(vtype: str | None = "FY", **over) -> dict:
    return {"voucher_no": "0003", "voucher_date": "2025-01-07", "voucher_type": vtype, **over}


async def _batch(client, vouchers, wps, **extra):
    return await client.post(_url("sample-vouchers/batch"), json={
        "year": YEAR, "vouchers": vouchers, "working_paper_ids": [str(w) for w in wps], **extra})


async def _query(client, keys):
    return await client.post(_url("voucher-links/query"), json={"year": YEAR, "keys": keys})


async def _rows(db) -> list[SampledVoucher]:
    db.expire_all()
    return list((await db.execute(sa.select(SampledVoucher).order_by(SampledVoucher.voucher_type,
                                                                    SampledVoucher.working_paper_id))).scalars())


async def _set_phase(db, phase: str) -> None:
    await db.execute(sa.update(Project).where(Project.id == PROJECT).values(current_audit_phase=phase))
    await db.commit()


def _by_pair(body) -> dict:
    return {(r["voucher_type"], r["working_paper_id"]): r for r in body["results"]}


async def test_one_voucher_two_workpapers_then_existed(client, db):
    first = await _batch(client, [_voucher("FY", account_code="2211")], [WP_A, WP_B], note="多科目凭证")
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["created"], body["existed"], body["failed"], body["phase"]) == (2, 0, 0, "final")
    assert {r["wp_code"] for r in body["results"]} == {"J1-2", "E1-23"}
    assert {r["voucher_key"] for r in body["results"]} == {FY_KEY}
    rows = await _rows(db)
    assert sorted((str(r.working_paper_id), r.voucher_type, r.company_code, r.phase, r.account_code, r.note)
                  for r in rows) == sorted([(str(WP_A), "FY", COMPANY, "final", "2211", "多科目凭证"),
                                            (str(WP_B), "FY", COMPANY, "final", "2211", "多科目凭证")])

    again = (await _batch(client, [_voucher("FY", account_code="1002")], [WP_A, WP_B], note="再挂")).json()
    assert (again["created"], again["existed"]) == (0, 2)
    assert {r["id"] for r in again["results"]} == {str(r.id) for r in rows}
    assert {(r.account_code, r.note) for r in await _rows(db)} == {("2211", "多科目凭证")}  # 已挂：原行不动


async def test_per_item_failures_do_not_block_the_rest(client, db):
    resp = await _batch(client, [
        _voucher("FY"),
        _voucher(None),  # 只给日期 + 号：FY 与 ZZ 两张
        _voucher("FY", voucher_no="9999"),
    ], [WP_A, WP_OTHER, WP_DELETED, uuid.uuid4()])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["created"], body["existed"], body["failed"]) == (1, 0, 11)
    by_status = {}
    for r in body["results"]:
        by_status.setdefault((r["voucher_no"], r.get("error_code") or r["status"]), []).append(r)
    assert [r["working_paper_id"] for r in by_status[("0003", "created")]] == [str(WP_A)]
    assert len(by_status[("0003", "WP_NOT_IN_PROJECT")]) == 3  # 别的项目的、已删的、不存在的
    assert all(r["wp_code"] is None for r in by_status[("0003", "WP_NOT_IN_PROJECT")])  # 不透出别的项目底稿编码
    ambiguous = by_status[("0003", "VOUCHER_KEY_AMBIGUOUS")]
    assert len(ambiguous) == 4 and "2025-01-07 FY-0003" in ambiguous[0]["reason"]
    assert [c["voucher_type"] for c in ambiguous[0]["candidates"]] == ["FY", "ZZ"]
    assert len(by_status[("9999", "VOUCHER_NOT_FOUND")]) == 4
    assert [(str(r.working_paper_id), r.voucher_type) for r in await _rows(db)] == [(str(WP_A), "FY")]


async def test_company_code_tells_two_companies_apart(client, db):
    """一套账两个主体同日同号同凭证字：不带主体这一条失败列候选（不猜），带主体只挂那一家的凭证。"""
    other = "C2-第二主体"
    db.add_all([_line({**x, "company_code": other}) for x in FY])
    await db.commit()
    body = (await _batch(client, [_voucher("FY")], [WP_A])).json()
    (failed,) = body["results"]
    assert failed["error_code"] == "VOUCHER_KEY_AMBIGUOUS"
    assert sorted(c["company_code"] for c in failed["candidates"]) == sorted([COMPANY, other])
    body = (await _batch(client, [_voucher("FY", company_code=other)], [WP_A])).json()
    assert body["created"] == 1 and body["results"][0]["voucher_key"] == VoucherKey.of(
        year=YEAR, company_code=other, voucher_date="2025-01-07", voucher_type="FY", voucher_no="0003").to_str()
    assert [(r.voucher_type, r.company_code) for r in await _rows(db)] == [("FY", other)]


async def test_database_rejection_rolls_back_only_that_pair(client, db):
    """单条被数据库拒绝（触发器模拟）：只回滚这一条，同批其余照常写入（逐条保存点）。"""
    await db.execute(sa.text(
        "CREATE TRIGGER t14_boom BEFORE INSERT ON sampled_vouchers WHEN NEW.account_code = 'BOOM' "
        "BEGIN SELECT RAISE(ABORT, 'boom'); END"))
    await db.commit()
    resp = await _batch(client, [_voucher("FY", account_code="BOOM"), _voucher("ZZ", account_code="1002")],
                        [WP_A, WP_B])
    assert resp.status_code == 200, resp.text
    pairs = _by_pair(resp.json())
    assert {k: v["status"] for k, v in pairs.items()} == {
        ("FY", str(WP_A)): "failed", ("FY", str(WP_B)): "failed",
        ("ZZ", str(WP_A)): "created", ("ZZ", str(WP_B)): "created"}
    assert pairs[("FY", str(WP_A))]["error_code"] == "ATTACH_WRITE_FAILED"
    assert sorted((r.voucher_type, str(r.working_paper_id)) for r in await _rows(db)) == sorted(
        [("ZZ", str(WP_A)), ("ZZ", str(WP_B))])


async def test_existed_keeps_phase_and_revived_takes_current_phase(client, db):
    await _set_phase(db, "preliminary")
    created = (await _batch(client, [_voucher("FY")], [WP_A])).json()["results"][0]
    assert (created["status"], created["phase"]) == ("created", "preliminary")
    await _set_phase(db, "final")
    existed = (await _batch(client, [_voucher("FY")], [WP_A])).json()["results"][0]
    assert (existed["status"], existed["phase"], existed["id"]) == ("existed", "preliminary", created["id"])
    # 单张端点再挂同样不改已挂行的阶段（年审重挂预审挂过的凭证）
    single = (await client.post(_url("sample-voucher"), json={"year": YEAR, **_voucher("FY"),
                                                               "working_paper_id": str(WP_A)})).json()
    assert (single["status"], single["phase"]) == ("updated", "preliminary")
    assert (await client.delete(_url(f"sampled-vouchers/{created['id']}"))).status_code == 200
    revived = (await _batch(client, [_voucher("FY")], [WP_A])).json()["results"][0]
    assert (revived["status"], revived["phase"], revived["id"]) == ("created", "final", created["id"])
    (row,) = await _rows(db)
    assert (row.is_deleted, row.phase) == (False, "final")


async def test_phase_in_body_extra_fields_and_empty_lists_are_422(client, db):
    assert (await _batch(client, [_voucher("FY")], [WP_A], phase="final")).status_code == 422
    assert (await _batch(client, [{**_voucher("FY"), "phase": "final"}], [WP_A])).status_code == 422
    assert (await _batch(client, [], [WP_A])).status_code == 422
    assert (await _batch(client, [_voucher("FY")], [])).status_code == 422
    assert await _rows(db) == []


async def test_more_than_500_pairs_is_422_and_writes_nothing(client, db):
    vouchers = [_voucher("FY")] * 26
    resp = await _batch(client, vouchers, [WP_A] + [uuid.uuid4() for _ in range(19)])  # 26 × 20 = 520
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "ATTACH_BATCH_TOO_LARGE"
    assert await _rows(db) == []
    ok = await _batch(client, [_voucher("FY")] * 25, [WP_A] + [uuid.uuid4() for _ in range(19)])  # 正好 500
    assert ok.status_code == 200 and ok.json()["created"] == 1 and ok.json()["existed"] == 24


@pytest.mark.parametrize("user, endpoint, expected", [
    (EDITOR, "batch", 200), (READER, "batch", 403), (STRANGER, "batch", 403),
    (EDITOR, "query", 200), (READER, "query", 200), (STRANGER, "query", 403),
])
async def test_permissions_table(client, db, user, endpoint, expected):
    client.as_user(user)
    resp = await (_batch(client, [_voucher("FY")], [WP_A]) if endpoint == "batch" else _query(client, [FY_KEY]))
    assert resp.status_code == expected, resp.text
    if endpoint == "batch" and expected != 200:
        assert await _rows(db) == []


async def test_links_merge_manual_and_engine_rows_by_voucher_key(client, db):
    d = date(2025, 1, 7)
    common = {"project_id": PROJECT, "year": YEAR, "voucher_no": "0003", "voucher_date": d}
    b1, b2 = uuid.uuid4(), uuid.uuid4()
    db.add_all([
        SampledVoucher(**common, company_code=COMPANY, voucher_type="FY", working_paper_id=WP_A, phase="final"),
        SampledVoucher(**common, company_code=COMPANY, voucher_type="FY", working_paper_id=WP_A, phase="preliminary",
                       batch_id=b1),
        SampledVoucher(**common, company_code=COMPANY, voucher_type="FY", working_paper_id=WP_A, phase="preliminary",
                       batch_id=b2),
        SampledVoucher(**common, company_code=COMPANY, voucher_type="ZZ", working_paper_id=WP_B, phase="final",
                       batch_id=b1),
        # 旧登记（V210 前）没记凭证字与主体：同日同号的两张都显示它，标 legacy
        SampledVoucher(**common, working_paper_id=WP_B),
        # 只有凭证号的旧登记：说不清是全年哪一张，不显示
        SampledVoucher(project_id=PROJECT, year=YEAR, voucher_no="0003", working_paper_id=WP_A, batch_id=b2),
        # 软删的不显示；挂到别的项目底稿 id 上的不透出编码
        SampledVoucher(**common, company_code=COMPANY, voucher_type="FY", working_paper_id=WP_B, is_deleted=True),
        SampledVoucher(**common, company_code=COMPANY, voucher_type="ZZ", working_paper_id=WP_OTHER, phase="final"),
        # 别的主体的同日同号同字凭证不算本凭证
        SampledVoucher(**common, company_code="OTHER", voucher_type="FY", working_paper_id=WP_B, phase="final"),
    ])
    await db.commit()
    resp = await _query(client, [FY_KEY, ZZ_KEY, _key("FY", vdate="2025-02-07"), "坏键", _key("FY")[:-2]])
    assert resp.status_code == 200, resp.text
    links = resp.json()["links"]
    assert set(links) == {FY_KEY, ZZ_KEY}

    def brief(e):
        return (e["wp_code"], e["source"], e["phase"], e["count"], e["legacy"], e["wp_missing"])

    assert [brief(e) for e in links[FY_KEY]] == [
        ("E1-23", "manual", None, 1, True, False),
        ("J1-2", "manual", "final", 1, False, False),
        ("J1-2", "sampling_engine", "preliminary", 2, False, False),
    ]
    assert [brief(e) for e in links[ZZ_KEY]] == [
        ("E1-23", "manual", None, 1, True, False),
        ("E1-23", "sampling_engine", "final", 1, False, False),
        (None, "manual", "final", 1, False, True),
    ]
    assert links[FY_KEY][1]["working_paper_id"] == str(WP_A) and links[FY_KEY][1]["wp_name"] == "J1-2 底稿"


async def test_query_key_cap_other_year_and_empty(client, db):
    assert (await _query(client, [])).json() == {"links": {}}
    over = await _query(client, [_key("FY", no=f"{i:04d}") for i in range(501)])
    assert over.status_code == 422 and over.json()["detail"]["error_code"] == "TOO_MANY_VOUCHER_KEYS"
    assert (await _query(client, [_key("FY", no=f"{i:04d}") for i in range(500)])).status_code == 200
    other_year = VoucherKey.of(year=2024, company_code=COMPANY, voucher_date="2024-01-07", voucher_type="FY",
                               voucher_no="0003").to_str()
    await _batch(client, [_voucher("FY")], [WP_A])
    assert set((await _query(client, [other_year, FY_KEY])).json()["links"]) == {FY_KEY}


async def test_ledger_detail_rows_carry_their_voucher_key(db):
    """明细层 / 辅助明细层的行带主体与凭证字：前端按行还原凭证键查已挂标识（少一列就对不上已挂记录）。"""
    from app.models.audit_platform_models import TbAuxLedger
    from app.services.ledger_penetration_service import LedgerPenetrationService

    zz = ZZ[0]
    db.add(TbAuxLedger(project_id=PROJECT, year=YEAR, company_code=zz["company_code"],
                       voucher_date=date.fromisoformat(zz["voucher_date"]), voucher_no=zz["voucher_no"],
                       voucher_type=zz["voucher_type"], account_code=zz["account_code"], aux_type="客户", aux_code="C1",
                       debit_amount=_amount(zz["debit_amount"]), credit_amount=_amount(zz["credit_amount"])))
    await db.commit()
    svc = LedgerPenetrationService(db)
    fy_code = FY[0]["account_code"]
    pages = [
        (await svc.get_ledger_entries_cursor(PROJECT, YEAR, fy_code, limit=100))["items"],
        (await svc.get_ledger_entries(PROJECT, YEAR, fy_code))["items"],
    ]
    for items in pages:
        assert items and {VoucherKey.from_row(r, year=YEAR).to_str() for r in items} == {FY_KEY}
    aux_pages = [
        (await svc.get_aux_ledger_entries_cursor(PROJECT, YEAR, zz["account_code"], limit=100))["items"],
        (await svc.get_aux_ledger_entries(PROJECT, YEAR, zz["account_code"]))["items"],
    ]
    for items in aux_pages:
        assert items and {VoucherKey.from_row(r, year=YEAR).to_str() for r in items} == {ZZ_KEY}


def test_new_routes_registered_once_in_the_real_app():
    from app.main import app

    want = {
        ("POST", "/api/projects/{project_id}/ledger/sample-vouchers/batch"),
        ("POST", "/api/projects/{project_id}/ledger/voucher-links/query"),
    }
    seen = [(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods if (m, r.path) in want]
    assert sorted(seen) == sorted(want)
    assert {r.endpoint.__module__ for r in app.routes if getattr(r, "path", "") in {p for _, p in want}} == {
        "app.routers.voucher_links"}
