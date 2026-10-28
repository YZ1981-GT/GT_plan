"""项目审计阶段 × 真实库（spec voucher-identity-writeback-and-audit-phase 任务 8，pg_only）

在一个最后回滚的外层事务里调真实端点（会话以 create_savepoint 方式加入外层事务，端点自己的 commit
只释放保存点），真库不留痕：

- admin 把一个未删除的真实项目改成预审 + 预审截止日：projects 两列落库、app_audit_log 记一条
  project.audit_phase.change（old / new 原样）；GET 读回；
- V212 的 CHECK 约束拒绝第三个值。
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

pytestmark = pytest.mark.pg_only


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
async def setup(pg):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.models.core import User
    from app.routers import project_audit_phase

    row = (await pg.execute(sa.text(
        "SELECT id, audit_period_start, audit_period_end FROM projects "
        "WHERE NOT is_deleted AND status <> 'archived' AND current_audit_phase = 'final' "
        "AND interim_cutoff_date IS NULL ORDER BY created_at LIMIT 1"))).first()
    admin = (await pg.execute(sa.select(User).where(User.username == "admin"))).scalar_one_or_none()
    if row is None or admin is None:
        pytest.skip("没有可用的真实项目或 admin 用户（数据依赖）")

    async def _db():
        yield pg

    async def _user():
        return admin

    app = FastAPI()
    app.include_router(project_audit_phase.router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, row, admin


async def test_change_persists_and_writes_audit_log(pg, setup):
    client, project, admin = setup
    start = project.audit_period_start
    cutoff = (start + timedelta(days=200)).isoformat() if start else "2025-06-30"
    before = (await pg.execute(sa.text("SELECT count(*) FROM app_audit_log WHERE resource_id = :p "
                                       "AND action = 'project.audit_phase.change'"), {"p": str(project.id)})).scalar()

    resp = await client.put(f"/api/projects/{project.id}/audit-phase",
                            json={"current_audit_phase": "preliminary", "interim_cutoff_date": cutoff})
    assert resp.status_code == 200, resp.text
    assert resp.json()["changed"] is True

    stored = (await pg.execute(sa.text("SELECT current_audit_phase, interim_cutoff_date::text FROM projects "
                                       "WHERE id = :p"), {"p": project.id})).one()
    assert tuple(stored) == ("preliminary", cutoff)
    logs = (await pg.execute(sa.text(
        "SELECT user_id, details FROM app_audit_log WHERE resource_id = :p AND action = 'project.audit_phase.change' "
        "ORDER BY created_at DESC"), {"p": str(project.id)})).all()
    assert len(logs) == before + 1
    details = logs[0].details if isinstance(logs[0].details, dict) else json.loads(logs[0].details)
    assert details == {"old": {"current_audit_phase": "final", "interim_cutoff_date": None},
                       "new": {"current_audit_phase": "preliminary", "interim_cutoff_date": cutoff}}
    assert str(logs[0].user_id) == str(admin.id)

    got = (await client.get(f"/api/projects/{project.id}/audit-phase")).json()
    assert (got["current_audit_phase"], got["interim_cutoff_date"], got["can_edit"]) == ("preliminary", cutoff, True)


async def test_check_constraint_rejects_third_value(pg, setup):
    _, project, _ = setup
    with pytest.raises(sa.exc.IntegrityError, match="ck_projects_current_audit_phase"):
        async with pg.begin_nested():
            await pg.execute(sa.text("UPDATE projects SET current_audit_phase = 'interim' WHERE id = :p"),
                             {"p": project.id})
