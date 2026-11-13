"""挂凭写入的归属与底稿级写门（spec voucher-workflow-linkage-lineage-closure R1，承接 voucher-runtime-integrity R1）

SQLite 真 ORM 行 + 端点级请求（只挂 voucher_links 路由；覆盖 get_db / get_current_user，项目成员判定照常跑）。
底稿级门 ``try_gate_wp`` 在路由模块下一层换成按表放行的替身，并记下每次调用的动作：

- 单笔挂凭必须指定底稿（422 WP_REQUIRED）；底稿不在本项目 / 已删除 422；不可写 403 WP_NOT_WRITABLE，一行不写；
- 抽样记录不在本项目 / 已删除 422；
- 批量挂凭逐张判写：可写的照挂，不可写的逐条 WP_NOT_WRITABLE 且不回编码，不在本项目的 WP_NOT_IN_PROJECT；
- 取消挂凭：底稿不可写 403、记录保留；没有底稿的旧记录只要项目级编辑权限；
- 按底稿取清单：底稿读门拒绝 404；
- 写门用「保存凭证检查表」动作，读门用「读取凭证检查表」动作。
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TbLedger
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.workpaper_models import (
    SampledVoucher, SamplingRecord, WorkingPaper, WpIndex, WpSourceType, WpStatus,
)
from app.routers import voucher_links

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
pytestmark = pytest.mark.asyncio

EDITOR = uuid.uuid4()
PROJECT_A, PROJECT_B = uuid.uuid4(), uuid.uuid4()
WP_A, WP_LOCKED, WP_GONE, WP_B = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
SR_A, SR_GONE, SR_B = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
YEAR, COMPANY = 2025, "测试主体"
#: 当前用户能写的底稿（替身门按它放行写动作）；读动作对 WP_A 放行
WRITABLE = {WP_A}
READABLE = {WP_A}


def _wp(session, wp_id, project_id, code, *, deleted=False):
    idx = WpIndex(id=uuid.uuid4(), project_id=project_id, wp_code=code, wp_name=f"{code} 底稿",
                  audit_cycle=code[0], status=WpStatus.not_started)
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
        session.add(User(id=EDITOR, username="editor", email="e@test.com", hashed_password="x", role="auditor"))
        for pid in (PROJECT_A, PROJECT_B):
            session.add(Project(id=pid, name=f"挂凭门 {pid.hex[:4]}", client_name="测试", created_by=EDITOR,
                                project_type=ProjectType.annual, status=ProjectStatus.execution))
            session.add(ProjectUser(project_id=pid, user_id=EDITOR, role="auditor", permission_level="edit",
                                    is_deleted=False))
        _wp(session, WP_A, PROJECT_A, "E1")
        _wp(session, WP_LOCKED, PROJECT_A, "D2")
        _wp(session, WP_GONE, PROJECT_A, "J1", deleted=True)
        _wp(session, WP_B, PROJECT_B, "F3")
        for sr_id, pid, deleted in ((SR_A, PROJECT_A, False), (SR_GONE, PROJECT_A, True), (SR_B, PROJECT_B, False)):
            session.add(SamplingRecord(id=sr_id, project_id=pid, sampling_purpose="测试", population_description="测试",
                                       sample_size=1, is_deleted=deleted))
        session.add(TbLedger(project_id=PROJECT_A, year=YEAR, company_code=COMPANY, voucher_date=date(2025, 3, 5),
                             voucher_type="记", voucher_no="0007", account_code="1002",
                             debit_amount=Decimal("100.00"), credit_amount=None))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.fixture
def gate_calls(monkeypatch):
    calls: list[tuple] = []

    async def _gate(_db, _user, *, entrypoint, action, method, wp_id, entry_family=None, **_kw):
        calls.append((entrypoint, action, method, entry_family, wp_id))
        allowed = WRITABLE if action == "save_checklist" else READABLE
        return object() if wp_id in allowed else None

    monkeypatch.setattr(voucher_links, "try_gate_wp", _gate)

    async def _all(_db, _user, wp_ids):
        return set(wp_ids)

    monkeypatch.setattr(voucher_links, "_visible_wp_ids", _all)
    return calls


@pytest_asyncio.fixture
async def client(db, gate_calls):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user

    app = FastAPI()
    app.include_router(voucher_links.router)

    async def _db():
        yield db

    async def _user():
        return (await db.execute(sa.select(User).where(User.id == EDITOR))).scalar_one()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _url(path: str, pid=PROJECT_A) -> str:
    return f"/api/projects/{pid}/ledger/{path}"


def _body(**over) -> dict:
    return {"year": YEAR, "voucher_no": "0007", "voucher_date": "2025-03-05", "voucher_type": "记", **over}


async def _live(db) -> list[SampledVoucher]:
    db.expire_all()
    return list((await db.execute(sa.select(SampledVoucher).where(SampledVoucher.is_deleted == sa.false()))).scalars())


# ── 单笔挂凭 ─────────────────────────────────────────────────────────


async def test_writable_wp_attaches_and_gate_uses_save_checklist(client, db, gate_calls):
    resp = await client.post(_url("sample-voucher"), json=_body(working_paper_id=str(WP_A)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "created"
    assert [(r.working_paper_id, r.voucher_type) for r in await _live(db)] == [(WP_A, "记")]
    assert gate_calls == [("workpaper.checklist_save", "save_checklist", "PUT", "checklist", WP_A)]


async def test_missing_wp_is_422_and_writes_nothing(client, db, gate_calls):
    resp = await client.post(_url("sample-voucher"), json=_body())
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "WP_REQUIRED"
    assert await _live(db) == [] and gate_calls == []


@pytest.mark.parametrize("wp_id", [WP_B, WP_GONE, uuid.uuid4()], ids=["其他项目", "已删除", "不存在"])
async def test_wp_not_in_project_is_422(client, db, wp_id):
    resp = await client.post(_url("sample-voucher"), json=_body(working_paper_id=str(wp_id)))
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "WP_NOT_IN_PROJECT"
    assert await _live(db) == []


async def test_not_writable_wp_is_403_and_writes_nothing(client, db):
    resp = await client.post(_url("sample-voucher"), json=_body(working_paper_id=str(WP_LOCKED)))
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "WP_NOT_WRITABLE"
    assert "编制人" in resp.json()["detail"]["message"]
    assert await _live(db) == []


@pytest.mark.parametrize("sr_id", [SR_B, SR_GONE], ids=["其他项目", "已删除"])
async def test_sampling_record_not_in_project_is_422(client, db, sr_id):
    resp = await client.post(_url("sample-voucher"), json=_body(working_paper_id=str(WP_A), sampling_record_id=str(sr_id)))
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "SAMPLING_RECORD_NOT_IN_PROJECT"
    assert await _live(db) == []


async def test_own_sampling_record_is_accepted(client, db):
    resp = await client.post(_url("sample-voucher"), json=_body(working_paper_id=str(WP_A), sampling_record_id=str(SR_A)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["sampling_record_id"] == str(SR_A)


# ── 批量挂凭 ─────────────────────────────────────────────────────────


async def test_batch_gates_each_workpaper(client, db):
    resp = await client.post(_url("sample-vouchers/batch"), json={
        "year": YEAR, "working_paper_ids": [str(WP_A), str(WP_LOCKED), str(WP_B)],
        "vouchers": [{"voucher_no": "0007", "voucher_date": "2025-03-05", "voucher_type": "记"}],
    })
    assert resp.status_code == 200, resp.text
    by_wp = {r["working_paper_id"]: r for r in resp.json()["results"]}
    assert by_wp[str(WP_A)]["status"] == "created" and by_wp[str(WP_A)]["wp_code"] == "E1"
    locked = by_wp[str(WP_LOCKED)]
    assert (locked["status"], locked["error_code"], locked["wp_code"]) == ("failed", "WP_NOT_WRITABLE", None)
    assert (by_wp[str(WP_B)]["status"], by_wp[str(WP_B)]["error_code"]) == ("failed", "WP_NOT_IN_PROJECT")
    assert [r.working_paper_id for r in await _live(db)] == [WP_A]


# ── 取消挂凭 ─────────────────────────────────────────────────────────


async def _manual_row(db, wp_id) -> uuid.UUID:
    row = SampledVoucher(id=uuid.uuid4(), project_id=PROJECT_A, year=YEAR, voucher_no="0007",
                         voucher_date=date(2025, 3, 5), company_code=COMPANY, voucher_type="记",
                         working_paper_id=wp_id, sampled_by=EDITOR)
    db.add(row)
    await db.commit()
    return row.id


async def test_delete_on_not_writable_wp_is_403_and_keeps_row(client, db):
    rid = await _manual_row(db, WP_LOCKED)
    resp = await client.delete(_url(f"sampled-vouchers/{rid}"))
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "WP_NOT_WRITABLE"
    assert [r.id for r in await _live(db)] == [rid]


async def test_delete_on_writable_wp_and_orphan_row(client, db, gate_calls):
    own = await _manual_row(db, WP_A)
    orphan = await _manual_row(db, None)
    assert (await client.delete(_url(f"sampled-vouchers/{own}"))).status_code == 200
    gate_calls.clear()
    assert (await client.delete(_url(f"sampled-vouchers/{orphan}"))).status_code == 200
    assert gate_calls == [], "没有底稿的旧记录只校项目级权限"
    assert await _live(db) == []


# ── 按底稿取清单 ─────────────────────────────────────────────────────


async def test_list_by_unreadable_wp_is_404(client, db, gate_calls):
    await _manual_row(db, WP_LOCKED)
    resp = await client.get(_url("sampled-vouchers"), params={"year": YEAR, "working_paper_id": str(WP_LOCKED)})
    assert resp.status_code == 404
    assert gate_calls[-1][:4] == ("workpaper.checklist_read", "read_checklist", "GET", "checklist")


async def test_list_by_readable_wp(client, db):
    rid = await _manual_row(db, WP_A)
    resp = await client.get(_url("sampled-vouchers"), params={"year": YEAR, "working_paper_id": str(WP_A)})
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()["items"]] == [str(rid)]
