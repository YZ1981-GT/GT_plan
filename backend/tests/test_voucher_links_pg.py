"""挂凭 × 真实账套（spec voucher-identity-writeback-and-audit-phase 任务 6，pg_only）

在一个最后回滚的外层事务里调真实端点（会话以 create_savepoint 方式加入外层事务，端点自己的 commit
只释放保存点），真库 sampled_vouchers 不留痕。

四川物流 2025-01-07「0003」是 FY 与 ZZ 两张凭证：分别挂到同一底稿得到两条记录（V210 手工侧唯一索引
不冲突），各自回拉只拿到自己的分录；只给日期 + 号 409；同一凭证再挂幂等。
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

pytestmark = pytest.mark.pg_only

SICHUAN = uuid.UUID("f4b778ad-23b3-49ab-b3c8-ee62a5f82226")
YEAR = 2025


@pytest.fixture
async def pg():
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
    await engine.dispose()


@pytest.fixture
async def client(pg):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import ledger_penetration, voucher_links

    admin = (await pg.execute(sa.text("SELECT id FROM users WHERE username = 'admin'"))).scalar()
    wp = (await pg.execute(sa.text("SELECT id FROM working_paper WHERE project_id = :p LIMIT 1"), {"p": SICHUAN})).scalar()
    status = (await pg.execute(sa.text("SELECT status FROM projects WHERE id = :p"), {"p": SICHUAN})).scalar()
    if admin is None or wp is None or status is None or str(status) == "archived":
        pytest.skip("四川物流项目 / 底稿 / admin 用户不可用（数据依赖）")

    class _Admin:
        id = admin

        class _Role:
            value = "admin"

        role = _Role()

    async def _db():
        yield pg

    async def _user():
        return _Admin()

    app = FastAPI()
    app.include_router(ledger_penetration.router)
    app.include_router(voucher_links.router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.wp = wp  # type: ignore[attr-defined]
        yield c


async def test_fy_and_zz_0003_attach_as_two_records_on_real_ledger(client, pg):
    url = f"/api/projects/{SICHUAN}/ledger"
    before = (await pg.execute(sa.text("SELECT count(*) FROM sampled_vouchers WHERE project_id = :p"),
                               {"p": SICHUAN})).scalar_one()
    body = {"year": YEAR, "voucher_no": "0003", "voucher_date": "2025-01-07", "working_paper_id": str(client.wp)}

    ambiguous = await client.post(f"{url}/sample-voucher", json=body)
    assert ambiguous.status_code == 409
    assert [c["voucher_type"] for c in ambiguous.json()["detail"]["candidates"]] == ["FY", "ZZ"]

    created = {}
    for vtype in ("FY", "ZZ"):
        resp = await client.post(f"{url}/sample-voucher", json={**body, "voucher_type": vtype})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "created"
        created[vtype] = resp.json()
    again = await client.post(f"{url}/sample-voucher", json={**body, "voucher_type": "FY"})
    assert again.json()["status"] == "updated" and again.json()["id"] == created["FY"]["id"]

    items = (await client.get(f"{url}/sampled-vouchers", params={
        "year": YEAR, "working_paper_id": str(client.wp), "manual_only": True})).json()["items"]
    mine = [i for i in items if i["id"] in {c["id"] for c in created.values()}]
    assert sorted(i["voucher_type"] for i in mine) == ["FY", "ZZ"]
    assert all(i["phase"] == "final" and i["company_code"] for i in mine)

    counts = {}
    for rec in mine:
        lines = (await client.get(f"{url}/voucher/0003", params={
            "year": YEAR, "voucher_date": rec["voucher_date"], "voucher_type": rec["voucher_type"]})).json()
        assert {x["voucher_key"] for x in lines} == {rec["voucher_key"]}
        counts[rec["voucher_type"]] = len(lines)
    assert counts == {"FY": 2, "ZZ": 3}
    after = (await pg.execute(sa.text("SELECT count(*) FROM sampled_vouchers WHERE project_id = :p"),
                              {"p": SICHUAN})).scalar_one()
    assert after == before + 2
