"""挂凭 × 真实账套（spec voucher-identity-writeback-and-audit-phase 任务 6，pg_only）

在一个最后回滚的外层事务里调真实端点（会话以 create_savepoint 方式加入外层事务，端点自己的 commit
只释放保存点），真库 sampled_vouchers 不留痕。

辽宁卫生 2025-01-03「0004」是 ZJGJ 与 ZZ 两张凭证：分别挂到同一底稿得到两条记录（V210 手工侧唯一索引
不冲突），各自回拉只拿到自己的分录；只给日期 + 号 409；同一凭证再挂幂等。
（原用四川物流 2025-01-07「0003」，该项目 2026-10 已软删：任务 8 起挂凭按项目取阶段，软删项目 404。）
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

pytestmark = pytest.mark.pg_only

LIAONING = uuid.UUID("d9295a0c-f347-4aa5-a1d1-faf7847d379b")
VOUCHER_NO, VOUCHER_DATE, TYPES = "0004", "2025-01-03", ("ZJGJ", "ZZ")
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
    wp = (await pg.execute(sa.text("SELECT id FROM working_paper WHERE project_id = :p AND is_deleted = false LIMIT 1"),
                           {"p": LIAONING})).scalar()
    proj = (await pg.execute(sa.text("SELECT status, is_deleted FROM projects WHERE id = :p"), {"p": LIAONING})).first()
    if admin is None or wp is None or proj is None or proj.is_deleted or str(proj.status) == "archived":
        pytest.skip("辽宁卫生项目 / 底稿 / admin 用户不可用（数据依赖；软删、归档都跳过）")

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


async def test_same_day_same_no_two_types_attach_as_two_records_on_real_ledger(client, pg):
    url = f"/api/projects/{LIAONING}/ledger"
    before = (await pg.execute(sa.text("SELECT count(*) FROM sampled_vouchers WHERE project_id = :p"),
                               {"p": LIAONING})).scalar_one()
    body = {"year": YEAR, "voucher_no": VOUCHER_NO, "voucher_date": VOUCHER_DATE, "working_paper_id": str(client.wp)}

    ambiguous = await client.post(f"{url}/sample-voucher", json=body)
    assert ambiguous.status_code == 409
    assert [c["voucher_type"] for c in ambiguous.json()["detail"]["candidates"]] == list(TYPES)

    created = {}
    for vtype in TYPES:
        resp = await client.post(f"{url}/sample-voucher", json={**body, "voucher_type": vtype})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "created"
        created[vtype] = resp.json()
    again = await client.post(f"{url}/sample-voucher", json={**body, "voucher_type": TYPES[0]})
    assert again.json()["status"] == "updated" and again.json()["id"] == created[TYPES[0]]["id"]

    items = (await client.get(f"{url}/sampled-vouchers", params={
        "year": YEAR, "working_paper_id": str(client.wp), "manual_only": True})).json()["items"]
    mine = [i for i in items if i["id"] in {c["id"] for c in created.values()}]
    assert sorted(i["voucher_type"] for i in mine) == sorted(TYPES)
    assert all(i["phase"] == "final" and i["company_code"] for i in mine)

    counts = {}
    for rec in mine:
        lines = (await client.get(f"{url}/voucher/{VOUCHER_NO}", params={
            "year": YEAR, "voucher_date": rec["voucher_date"], "voucher_type": rec["voucher_type"]})).json()
        assert {x["voucher_key"] for x in lines} == {rec["voucher_key"]}
        counts[rec["voucher_type"]] = len(lines)
    assert counts == {"ZJGJ": 2, "ZZ": 2}
    after = (await pg.execute(sa.text("SELECT count(*) FROM sampled_vouchers WHERE project_id = :p"),
                              {"p": LIAONING})).scalar_one()
    assert after == before + 2


async def test_batch_attach_isolates_a_rejected_pair_and_links_show_both_workpapers(client, pg):
    """任务 14：真库里一条被数据库拒绝（科目编码超过 varchar(50)）只回滚它自己，同批其余照写；已挂查询合并两张底稿。"""
    url = f"/api/projects/{LIAONING}/ledger"
    wps = [str(w) for w in (await pg.execute(sa.text(
        "SELECT wp.id FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id "
        "WHERE wp.project_id = :p AND wp.is_deleted = false ORDER BY wi.wp_code LIMIT 2"), {"p": LIAONING})).scalars()]
    if len(wps) < 2:
        pytest.skip("辽宁卫生项目底稿不足两张")
    before = (await pg.execute(sa.text("SELECT count(*) FROM sampled_vouchers WHERE project_id = :p"),
                               {"p": LIAONING})).scalar_one()
    resp = await client.post(f"{url}/sample-vouchers/batch", json={"year": YEAR, "working_paper_ids": wps, "vouchers": [
        {"voucher_no": VOUCHER_NO, "voucher_date": VOUCHER_DATE, "voucher_type": TYPES[0], "account_code": "X" * 60},
        {"voucher_no": VOUCHER_NO, "voucher_date": VOUCHER_DATE, "voucher_type": TYPES[1], "account_code": "1002"},
    ]})
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert {(r["voucher_type"], r["working_paper_id"]): (r["status"], r.get("error_code")) for r in results} == {
        **{(TYPES[0], w): ("failed", "ATTACH_WRITE_FAILED") for w in wps},
        **{(TYPES[1], w): ("created", None) for w in wps},
    }
    assert all(r["wp_code"] for r in results)
    after = (await pg.execute(sa.text("SELECT count(*) FROM sampled_vouchers WHERE project_id = :p"),
                              {"p": LIAONING})).scalar_one()
    assert after == before + 2

    keys = {r["voucher_type"]: r["voucher_key"] for r in results}
    links = (await client.post(f"{url}/voucher-links/query", json={"year": YEAR, "keys": list(keys.values())})).json()["links"]
    manual = {e["working_paper_id"] for e in links.get(keys[TYPES[1]], []) if e["source"] == "manual"}
    assert set(wps) <= manual
    assert not {e["working_paper_id"] for e in links.get(keys[TYPES[0]], []) if e["source"] == "manual"} & set(wps)
