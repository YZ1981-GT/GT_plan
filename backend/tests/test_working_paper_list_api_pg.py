"""底稿列表端点 /api/projects/{pid}/working-papers 的真库测试（preexisting-test-failures-closure G1）。

列表查询是 PostgreSQL 专有 SQL（DISTINCT ON / ``ANY(CAST(:ids AS uuid[]))``），SQLite 夹具
跑不起来；原 test_wopi_working_paper_qc_review 的 SQLite 版还按「直接返回数组」断言长度，
而响应自 procedure-delegation-visibility-isolation Task 8 起是
``{items,total,stats,page,page_size}``（``len(dict) == 5 ≠ 2``）。

每个用例在一个最终回滚的事务里建数据，不污染开发库。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from tests.procedure_delegation_visibility._factories import (
    mk_project,
    mk_working_paper,
    mk_wp_index,
)

IS_PG = settings.DATABASE_URL.startswith("postgresql")
pytestmark = [pytest.mark.pg_only, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]


@pytest_asyncio.fixture
async def pg_session():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_workpapers_api(pg_session):
    from app.main import app
    from tests._test_auth_helper import override_auth

    project = await mk_project(pg_session)
    for code, cycle in (("B1-1", "B"), ("E1-1", "E")):
        idx = await mk_wp_index(pg_session, project.id, wp_code=code, audit_cycle=cycle)
        await mk_working_paper(pg_session, project.id, idx.id)

    async with override_auth(app, db_session=pg_session) as client:
        resp = await client.get(f"/api/projects/{project.id}/working-papers")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    assert set(data) == {"items", "total", "stats", "page", "page_size"}
    assert data["total"] == 2
    assert sorted(item["wp_code"] for item in data["items"]) == ["B1-1", "E1-1"]
