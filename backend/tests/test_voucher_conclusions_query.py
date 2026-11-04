"""他稿结论查询端点（spec voucher-workflow-linkage-lineage-closure R6，design §8.3）

SQLite 真 ORM 行 + 端点级请求；检查表按凭证行索引的轻量表建。底稿可见性在路由模块下一层换成按表放行的替身。

- 按凭证键找各底稿检查行：身份行按凭证键，旧行按「号|日期」（标 legacy）；同号同日别的凭证字不算；
- 同一底稿多行合并：任一异常即异常，否则任一正常即正常，否则未判定；行数照实；
- 只列可见底稿；别的项目、已删底稿的行不出；键超过 500 个 422；非成员 403、未登录 401；
- 扫描失败照常报错（不当成「无」）；扫描截断时 truncated=true。
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.routers import voucher_links
from app.services import voucher_row_index as row_index
from app.services.voucher_identity import VoucherKey

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
pytestmark = pytest.mark.asyncio

READER, STRANGER, PROJECT, OTHER_PROJECT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
WP_D2, WP_E1, WP_HIDDEN, WP_DELETED, WP_FOREIGN = (uuid.uuid4() for _ in range(5))
YEAR, COMPANY, D = 2025, "主体", date(2025, 3, 5)
URL = f"/api/projects/{PROJECT}/ledger/voucher-conclusions/query"


def _key(no: str, vtype: str = "记") -> str:
    return VoucherKey.of(year=YEAR, company_code=COMPANY, voucher_date=D, voucher_type=vtype, voucher_no=no).to_str()


def _row(no: str, vtype: str = "记", **fields) -> dict:
    return {"voucherNo": no, "_gt": {"vk": _key(no, vtype)}, **fields}


@pytest.fixture(autouse=True)
def _gates(monkeypatch):
    async def _visible(_db, _user, wp_ids):
        return {w for w in wp_ids if w != WP_HIDDEN}

    monkeypatch.setattr(voucher_links, "_visible_wp_ids", _visible)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(row_index.CHECKLIST.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for uid, name in ((READER, "reader"), (STRANGER, "stranger")):
            session.add(User(id=uid, username=name, email=f"{name}@t.com", hashed_password="x", role="auditor"))
        for pid in (PROJECT, OTHER_PROJECT):
            session.add(Project(id=pid, name=f"他稿结论{pid.hex[:4]}", client_name="测试", project_type=ProjectType.annual,
                                status=ProjectStatus.execution, created_by=READER))
        session.add(ProjectUser(project_id=PROJECT, user_id=READER, role="auditor", permission_level="readonly",
                                is_deleted=False))
        for wp_id, code, pid, deleted in ((WP_D2, "D2", PROJECT, False), (WP_E1, "E1", PROJECT, False),
                                          (WP_HIDDEN, "J1", PROJECT, False), (WP_DELETED, "K8", PROJECT, True),
                                          (WP_FOREIGN, "F2", OTHER_PROJECT, False)):
            wi = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=f"{code} 凭证检查", audit_cycle=code[0],
                         status=WpStatus.not_started)
            session.add(wi)
            session.add(WorkingPaper(id=wp_id, project_id=pid, wp_index_id=wi.id, file_path="x.xlsx",
                                     source_type=WpSourceType.template, file_version=1, is_deleted=deleted))
        await session.flush()
        sheets = {
            # D2：0001 两行一正一异（合并为异常）；0002 只有一行未判定
            WP_D2: [_row("0001", checkResult="OK"), _row("0001", isAbnormal="是"), _row("0002", remark="待核")],
            # E1：0001 旧行（号 + 日期）判正常；0002 同号同日别的凭证字（不是这张）
            WP_E1: [{"voucherNo": "0001", "voucherDate": "2025-03-05", "checkConclusion": "相符"},
                    _row("0002", "FY", isAbnormal="是")],
            WP_HIDDEN: [_row("0001", isAbnormal="是")],
            WP_DELETED: [_row("0001", isAbnormal="是")],
            WP_FOREIGN: [_row("0001", isAbnormal="是")],
        }
        for wp_id, rows in sheets.items():
            pid = OTHER_PROJECT if wp_id == WP_FOREIGN else PROJECT
            await session.execute(sa.insert(row_index.CHECKLIST).values(
                id=uuid.uuid4(), project_id=pid, wp_id=wp_id, item_id="rows",
                remark=json.dumps(rows, ensure_ascii=False)))
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user

    app = FastAPI()
    app.include_router(voucher_links.router)
    state: dict = {"user": READER}

    async def _db():
        yield db

    async def _user():
        if state["user"] is None:
            raise HTTPException(status_code=401, detail="未登录")
        return (await db.execute(sa.select(User).where(User.id == state["user"]))).scalar_one()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda uid: state.update(user=uid)  # type: ignore[attr-defined]
        yield c


async def test_conclusions_by_key_merge_rows_and_mark_legacy(client):
    resp = await client.post(URL, json={"year": YEAR, "keys": [_key("0001"), _key("0002"), _key("0099")]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["truncated"] is False
    one = {i["wp_code"]: i for i in body["conclusions"][_key("0001")]}
    # 不可见（J1）、已删（K8）、别的项目（F2）的行都不出
    assert set(one) == {"D2", "E1"}
    assert one["D2"] == {"working_paper_id": str(WP_D2), "wp_code": "D2", "wp_name": "D2 凭证检查",
                         "verdict": "abnormal", "rows": 2, "legacy": False}
    assert one["E1"]["verdict"] == "normal" and one["E1"]["rows"] == 1 and one["E1"]["legacy"] is True
    # 0002：D2 有一行未判定；E1 那行是同号同日的 FY-0002，不是这张
    assert body["conclusions"][_key("0002")] == [
        {"working_paper_id": str(WP_D2), "wp_code": "D2", "wp_name": "D2 凭证检查", "verdict": "unknown",
         "rows": 1, "legacy": False}]
    assert _key("0099") not in body["conclusions"]


async def test_other_year_keys_ignored_and_key_limit(client):
    other_year = VoucherKey.of(year=2024, company_code=COMPANY, voucher_date=date(2024, 3, 5), voucher_type="记",
                               voucher_no="0001").to_str()
    resp = await client.post(URL, json={"year": YEAR, "keys": [other_year, "不是凭证键"]})
    assert resp.status_code == 200 and resp.json() == {"conclusions": {}, "truncated": False}
    too_many = await client.post(URL, json={"year": YEAR, "keys": [_key(f"{i:04d}") for i in range(501)]})
    assert too_many.status_code == 422
    assert too_many.json()["detail"]["error_code"] == "TOO_MANY_VOUCHER_KEYS"


@pytest.mark.parametrize(("who", "status"), [(STRANGER, 403), (None, 401)], ids=["非成员", "未登录"])
async def test_requires_project_membership(client, who, status):
    client.as_user(who)
    resp = await client.post(URL, json={"year": YEAR, "keys": [_key("0001")]})
    assert resp.status_code == status


async def test_truncated_scan_is_reported(client, monkeypatch):
    real = row_index.scan_voucher_rows

    async def _tiny_budget(db, project_id, **kw):
        return await real(db, project_id, max_dicts=1, **kw)

    monkeypatch.setattr(row_index, "scan_voucher_rows", _tiny_budget)
    resp = await client.post(URL, json={"year": YEAR, "keys": [_key("0001")]})
    assert resp.status_code == 200 and resp.json()["truncated"] is True


async def test_scan_failure_is_not_reported_as_empty(client, monkeypatch):
    async def _boom(*_a, **_kw):
        raise RuntimeError("checklist 读失败")

    monkeypatch.setattr(row_index, "scan_voucher_rows", _boom)
    with pytest.raises(RuntimeError):
        await client.post(URL, json={"year": YEAR, "keys": [_key("0001")]})


async def test_merge_verdicts_order():
    assert row_index.merge_verdicts(["normal", "abnormal", "unknown"]) == "abnormal"
    assert row_index.merge_verdicts(["unknown", "normal"]) == "normal"
    assert row_index.merge_verdicts(["unknown"]) == "unknown"
    assert row_index.merge_verdicts([]) == "unknown"
