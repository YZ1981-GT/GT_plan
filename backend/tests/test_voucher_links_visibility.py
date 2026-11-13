"""已挂查询与项目级挂凭清单按底稿可见性过滤（承接 voucher-runtime-integrity R2 / R3）

SQLite 真 ORM 行 + 端点级请求；可见性 ``_visible_wp_ids`` 在路由模块下一层换成按表放行的替身：

- ``/voucher-links/query``：挂在不可见底稿上的登记不出现；没有底稿的旧登记照常出现；
- ``/sampled-vouchers`` 项目级：同上；
- 按底稿取清单走底稿读门（见 test_voucher_links_ownership.py），不走可见性过滤。

凭证键用规范串（``VoucherKey.to_str()``）：前序版本的用例写成 ``2025:主体:…`` 形式，后端解析不了，
一个键都查不出来，断言却写成「不含 0002」，空结果恒绿（2026-11-03 接手时实测 5 失败 7 报错）。
"""

from __future__ import annotations

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
from app.services.voucher_identity import VoucherKey

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
pytestmark = pytest.mark.asyncio

EDITOR, PROJECT = uuid.uuid4(), uuid.uuid4()
WP_VISIBLE, WP_INVISIBLE = uuid.uuid4(), uuid.uuid4()
YEAR, COMPANY, VDATE = 2025, "主体", date(2025, 6, 15)


def _key(no: str) -> str:
    return VoucherKey.of(year=YEAR, company_code=COMPANY, voucher_date=VDATE, voucher_type="记", voucher_no=no).to_str()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=EDITOR, username="editor", email="e@t.com", hashed_password="x", role="auditor"))
        session.add(Project(id=PROJECT, name="可见性测试", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=EDITOR))
        session.add(ProjectUser(project_id=PROJECT, user_id=EDITOR, role="auditor", permission_level="edit",
                                is_deleted=False))
        for wp_id, code in ((WP_VISIBLE, "D2"), (WP_INVISIBLE, "E1")):
            idx = WpIndex(id=uuid.uuid4(), project_id=PROJECT, wp_code=code, wp_name=code,
                          audit_cycle=code[0], status=WpStatus.not_started)
            session.add(idx)
            session.add(WorkingPaper(id=wp_id, project_id=PROJECT, wp_index_id=idx.id, file_path="x.xlsx",
                                     source_type=WpSourceType.template, file_version=1))
        for wp_id, no in ((WP_VISIBLE, "0001"), (WP_INVISIBLE, "0002"), (None, "0003")):
            session.add(SampledVoucher(id=uuid.uuid4(), project_id=PROJECT, year=YEAR, voucher_no=no,
                                       voucher_date=VDATE, company_code=COMPANY, voucher_type="记",
                                       working_paper_id=wp_id, sampled_by=EDITOR))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.fixture
def visible(monkeypatch):
    """可见底稿集合（替身按它过滤）；用例改它即可。"""
    allowed: set[uuid.UUID] = {WP_VISIBLE}

    async def _impl(_db, _user, wp_ids):
        return {w for w in wp_ids if w in allowed}

    monkeypatch.setattr(voucher_links, "_visible_wp_ids", _impl)
    return allowed


@pytest_asyncio.fixture
async def client(db, visible):
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


async def _links(client, *nos: str) -> dict:
    resp = await client.post(f"/api/projects/{PROJECT}/ledger/voucher-links/query",
                             json={"year": YEAR, "keys": [_key(n) for n in nos]})
    assert resp.status_code == 200, resp.text
    return resp.json()["links"]


async def test_links_keep_visible_and_unassigned_drop_invisible(client):
    links = await _links(client, "0001", "0002", "0003")
    assert set(links) == {_key("0001"), _key("0003")}
    assert [e["wp_code"] for e in links[_key("0001")]] == ["D2"]
    assert [e["working_paper_id"] for e in links[_key("0003")]] == [None]


async def test_links_when_nothing_visible_keep_only_unassigned(client, visible):
    visible.clear()
    assert set(await _links(client, "0001", "0002", "0003")) == {_key("0003")}


async def test_links_when_all_visible_show_all(client, visible):
    visible.add(WP_INVISIBLE)
    assert set(await _links(client, "0001", "0002", "0003")) == {_key("0001"), _key("0002"), _key("0003")}


async def test_project_level_list_filters_by_visibility(client, visible):
    resp = await client.get(f"/api/projects/{PROJECT}/ledger/sampled-vouchers", params={"year": YEAR})
    assert resp.status_code == 200
    assert sorted(i["voucher_no"] for i in resp.json()["items"]) == ["0001", "0003"]
    visible.clear()
    resp = await client.get(f"/api/projects/{PROJECT}/ledger/sampled-vouchers", params={"year": YEAR})
    assert [i["voucher_no"] for i in resp.json()["items"]] == ["0003"]
