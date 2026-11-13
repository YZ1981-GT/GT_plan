"""底稿待导入提示的状态端点（spec voucher-workflow-linkage-lineage-closure R3.6，design §5.6）

SQLite 真 ORM 行 + 端点级请求；检查表按凭证行索引的轻量表建。底稿读门在路由模块下一层换成按表放行的替身。

- 只算本底稿的手工挂凭（引擎登记、别的底稿、软删的不算）；已有身份行 / 旧行的不算待导入；
- V210 前的旧登记（没记主体或凭证字）按「号|日期」认；没记日期的计入 undetermined、不列；
- 检查表读不了或扫描截断 ⇒ judged=false、不列（不能断言「没导入」）；
- 底稿不可读 / 不在本项目 ⇒ 404。
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.workpaper_models import SampledVoucher, WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.routers import voucher_links
from app.services import voucher_row_index as row_index
from app.services.voucher_identity import VoucherKey

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
pytestmark = pytest.mark.asyncio

EDITOR, PROJECT = uuid.uuid4(), uuid.uuid4()
WP, WP_OTHER, WP_HIDDEN = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
YEAR, COMPANY, D = 2025, "主体", date(2025, 3, 5)


def _key(no: str, vtype: str = "记") -> str:
    return VoucherKey.of(year=YEAR, company_code=COMPANY, voucher_date=D, voucher_type=vtype, voucher_no=no).to_str()


def _reg(no: str, wp=WP, **over) -> SampledVoucher:
    base = dict(project_id=PROJECT, year=YEAR, voucher_no=no, voucher_date=D, company_code=COMPANY, voucher_type="记",
                working_paper_id=wp, phase="final", account_code="1002")
    return SampledVoucher(**{**base, **over})


@pytest.fixture(autouse=True)
def _gates(monkeypatch):
    async def _readable(_db, _user, wp_id):
        return wp_id != WP_HIDDEN

    monkeypatch.setattr(voucher_links, "_wp_readable", _readable)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(row_index.CHECKLIST.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=EDITOR, username="editor", email="e@t.com", hashed_password="x", role="auditor"))
        session.add(Project(id=PROJECT, name="待导入", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=EDITOR))
        session.add(ProjectUser(project_id=PROJECT, user_id=EDITOR, role="auditor", permission_level="readonly",
                                is_deleted=False))
        for wp_id, code in ((WP, "E1"), (WP_OTHER, "D2"), (WP_HIDDEN, "J1")):
            wi = WpIndex(id=uuid.uuid4(), project_id=PROJECT, wp_code=code, wp_name=code, audit_cycle=code[0],
                         status=WpStatus.not_started)
            session.add(wi)
            session.add(WorkingPaper(id=wp_id, project_id=PROJECT, wp_index_id=wi.id, file_path="x.xlsx",
                                     source_type=WpSourceType.template, file_version=1))
        session.add_all([
            _reg("0001"),                                    # 已导入（身份行）
            _reg("0002"),                                    # 已导入（旧行：号 + 日期）
            _reg("0003"),                                    # 待导入
            _reg("0004", company_code=None, voucher_type=None),  # 旧登记缺列：检查表有同号同日 ⇒ 已导入
            _reg("0005", company_code=None, voucher_type=None),  # 旧登记缺列：待导入（没有凭证键）
            _reg("0006", voucher_date=None),                 # 没记日期：认不出
            _reg("0007", batch_id=uuid.uuid4()),             # 引擎登记：不算
            _reg("0008", wp=WP_OTHER),                       # 别的底稿：不算
            _reg("0009", is_deleted=True),                   # 软删：不算
        ])
        await session.flush()
        payload = [
            {"voucherNo": "0001", "_gt": {"vk": _key("0001"), "src": ["attach"]}},
            {"voucherNo": "0002", "voucherDate": "2025-03-05"},
            {"voucherNo": "0004", "voucherDate": "2025-03-05", "_gt": {"vk": _key("0004", "FY")}},
            {"voucherNo": "0003", "_gt": {"vk": _key("0003", "FY")}},   # 同号同日别的凭证字：不是这张
        ]
        await session.execute(sa.insert(row_index.CHECKLIST).values(
            id=uuid.uuid4(), project_id=PROJECT, wp_id=WP, item_id="E1-rows",
            remark=json.dumps(payload, ensure_ascii=False)))
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

    async def _db():
        yield db

    async def _user():
        return (await db.execute(sa.select(User).where(User.id == EDITOR))).scalar_one()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _url(wp=WP) -> str:
    return f"/api/projects/{PROJECT}/ledger/workpapers/{wp}/attached-voucher-status"


async def test_pending_lists_only_this_workpapers_manual_rows_not_imported(client):
    resp = await client.get(_url(), params={"year": YEAR})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["attached"], body["pending_count"], body["undetermined"], body["judged"]) == (6, 2, 1, True)
    assert [(p["voucher_no"], p["voucher_key"] is not None) for p in body["pending"]] == [("0003", True), ("0005", False)]
    first = body["pending"][0]
    assert first["voucher_key"] == _key("0003") and first["label"] == "2025-03-05 记-0003" and first["account_code"] == "1002"
    assert body["pending"][1]["label"] == "2025-03-05 0005"


async def test_unreadable_or_foreign_workpaper_is_404(client):
    assert (await client.get(_url(WP_HIDDEN), params={"year": YEAR})).status_code == 404
    assert (await client.get(_url(uuid.uuid4()), params={"year": YEAR})).status_code == 404


async def test_scan_failure_or_truncation_is_not_judged(client, monkeypatch):
    async def _boom(*_a, **_k):
        raise RuntimeError("检查表读不了")

    monkeypatch.setattr(row_index, "scan_voucher_rows", _boom)
    body = (await client.get(_url(), params={"year": YEAR})).json()
    assert (body["judged"], body["pending"], body["pending_count"]) == (False, [], 0)

    async def _truncated(*_a, **_k):
        return row_index.ScanResult(hits=[], truncated=True)

    monkeypatch.setattr(row_index, "scan_voucher_rows", _truncated)
    body = (await client.get(_url(), params={"year": YEAR})).json()
    assert (body["judged"], body["pending"]) == (False, [])


async def test_no_manual_attachments_skips_scan(client, monkeypatch):
    async def _never(*_a, **_k):
        raise AssertionError("没有手工挂凭不该扫检查表")

    monkeypatch.setattr(row_index, "scan_voucher_rows", _never)
    body = (await client.get(_url(WP_OTHER), params={"year": 2024})).json()
    assert body == {"attached": 0, "pending": [], "pending_count": 0, "undetermined": 0, "judged": True}
