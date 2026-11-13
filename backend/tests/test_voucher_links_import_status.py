"""已挂查询的「已导入 / 未导入」（spec voucher-workflow-linkage-lineage-closure R3.4，design §8.3）

SQLite 真 ORM 行 + 端点级请求；检查表 ``checklist_responses`` 按凭证行索引的轻量表建（无 ORM 模型）。

- 手工挂凭：该底稿检查表有这张凭证的身份行（``_gt.vk``）或旧行（凭证号 + 日期）⇒ true，没有 ⇒ false；
- 别的底稿有这张凭证的行不算本底稿已导入；
- 引擎登记 ⇒ null（导入状态只对手工挂凭有意义）；
- 检查表读不了 ⇒ null，已挂结果照常返回；扫描截断且没找到 ⇒ null（不能断言「未导入」）。
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
from app.services import voucher_row_index as row_index
from app.services.voucher_identity import VoucherKey
from tests._voucher_links_gates import allow_wp_gates

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
pytestmark = pytest.mark.asyncio

EDITOR, PROJECT = uuid.uuid4(), uuid.uuid4()
WP_IDENTITY, WP_LEGACY, WP_EMPTY = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
YEAR, COMPANY, D = 2025, "主体", date(2025, 3, 5)


def _key(no: str) -> str:
    return VoucherKey.of(year=YEAR, company_code=COMPANY, voucher_date=D, voucher_type="记", voucher_no=no).to_str()


@pytest.fixture(autouse=True)
def _gates(monkeypatch):
    allow_wp_gates(monkeypatch)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(row_index.CHECKLIST.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=EDITOR, username="editor", email="e@t.com", hashed_password="x", role="auditor"))
        session.add(Project(id=PROJECT, name="导入状态", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=EDITOR))
        session.add(ProjectUser(project_id=PROJECT, user_id=EDITOR, role="auditor", permission_level="edit",
                                is_deleted=False))
        for wp_id, code in ((WP_IDENTITY, "D2"), (WP_LEGACY, "E1"), (WP_EMPTY, "J1")):
            wi = WpIndex(id=uuid.uuid4(), project_id=PROJECT, wp_code=code, wp_name=code, audit_cycle=code[0],
                         status=WpStatus.not_started)
            session.add(wi)
            session.add(WorkingPaper(id=wp_id, project_id=PROJECT, wp_index_id=wi.id, file_path="x.xlsx",
                                     source_type=WpSourceType.template, file_version=1))
        for wp_id in (WP_IDENTITY, WP_LEGACY, WP_EMPTY):
            session.add(SampledVoucher(project_id=PROJECT, year=YEAR, voucher_no="0007", voucher_date=D,
                                       company_code=COMPANY, voucher_type="记", working_paper_id=wp_id, phase="final"))
        session.add(SampledVoucher(project_id=PROJECT, year=YEAR, voucher_no="0007", voucher_date=D, company_code=COMPANY,
                                   voucher_type="记", working_paper_id=WP_EMPTY, phase="final", batch_id=uuid.uuid4()))
        await session.flush()
        rows = [
            (WP_IDENTITY, [{"voucherNo": "0007", "_gt": {"vk": _key("0007"), "src": ["attach"]}}]),
            (WP_LEGACY, {"rows": [{"voucherNo": "0007", "date": "2025-03-05", "isAbnormal": "否"}]}),
            (WP_EMPTY, [{"voucherNo": "0099", "_gt": {"vk": _key("0099")}}]),  # 别的凭证
        ]
        for wp_id, payload in rows:
            await session.execute(sa.insert(row_index.CHECKLIST).values(
                id=uuid.uuid4(), project_id=PROJECT, wp_id=wp_id, item_id=f"item-{wp_id.hex[:6]}",
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
    from app.routers import voucher_links

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


async def _status(client) -> dict[tuple[str, str], object]:
    resp = await client.post(f"/api/projects/{PROJECT}/ledger/voucher-links/query",
                             json={"year": YEAR, "keys": [_key("0007")]})
    assert resp.status_code == 200, resp.text
    return {(e["wp_code"], e["source"]): e["imported"] for e in resp.json()["links"][_key("0007")]}


async def test_import_status_by_identity_legacy_and_absent(client):
    assert await _status(client) == {
        ("D2", "manual"): True,              # 身份行
        ("E1", "manual"): True,              # 旧行：凭证号 + 日期
        ("J1", "manual"): False,             # 检查表里只有别的凭证
        ("J1", "sampling_engine"): None,     # 引擎登记不判
    }


async def test_scan_failure_keeps_links_with_unknown_status(client, monkeypatch):
    async def _boom(*_a, **_k):
        raise RuntimeError("checklist_responses 读不了")

    monkeypatch.setattr(row_index, "scan_voucher_rows", _boom)
    assert set((await _status(client)).values()) == {None}


async def test_truncated_scan_does_not_claim_not_imported(client, monkeypatch):
    real = row_index.scan_voucher_rows

    async def _capped(db, project_id, *, wp_ids=None, max_dicts=row_index.MAX_DICTS):
        return await real(db, project_id, wp_ids=wp_ids, max_dicts=1)

    monkeypatch.setattr(row_index, "scan_voucher_rows", _capped)
    got = await _status(client)
    assert got[("J1", "manual")] is None, "截断后没找到不能说「未导入」"
