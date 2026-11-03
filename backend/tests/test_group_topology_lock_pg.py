"""集团拓扑年度 advisory lock 的真实 PostgreSQL 竞态。"""
from __future__ import annotations

import asyncio
import time
import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import engine as app_engine
from app.models.core import Project
from app.services.group_links import reparent_project
from app.services.group_topology_lock import lock_topology_years
from app.services.uscc_validator import USCC_CHARSET, _CHAR_TO_VALUE, _WEIGHTS


def _valid_uscc(number: int) -> str:
    prefix = f"91{number:015d}"
    total = sum(_CHAR_TO_VALUE[prefix[i]] * _WEIGHTS[i] for i in range(17))
    return prefix + USCC_CHARSET[(31 - total % 31) % 31]


def _engine():
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url, poolclass=NullPool)


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_empty_and_numbered_year_locks_serialize_own_domain_but_not_other_years():
    if app_engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as holder:
            await lock_topology_years(holder, [None, 2086])

            async def acquire(year: int | None) -> float:
                async with factory() as session:
                    started = time.perf_counter()
                    await lock_topology_years(session, [year])
                    waited = time.perf_counter() - started
                    await session.rollback()
                    return waited

            blocked_empty = asyncio.create_task(acquire(None))
            blocked_same_year = asyncio.create_task(acquire(2086))
            different_wait = await asyncio.wait_for(acquire(2087), timeout=1)
            assert different_wait < 0.8
            await asyncio.sleep(0.1)
            assert not blocked_empty.done()
            assert not blocked_same_year.done()
            await holder.rollback()
            empty_wait, same_year_wait = await asyncio.wait_for(
                asyncio.gather(blocked_empty, blocked_same_year), timeout=2
            )
            assert empty_wait >= 0.08
            assert same_year_wait >= 0.08
    finally:
        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_concurrent_reverse_reparent_cannot_commit_a_cycle():
    if app_engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    token = int(uuid.uuid4().hex[:8], 16)
    code_a = _valid_uscc(20_000_000 + token % 1_000_000)
    code_b = _valid_uscc(30_000_000 + token % 1_000_000)
    year = 2088
    ids: list[uuid.UUID] = []
    try:
        async with factory() as setup:
            projects = [
                Project(
                    name=f"【测试】拓扑锁A_{token}", client_name="【测试】拓扑锁A",
                    short_name="拓扑锁A", company_code=code_a, audit_year=year,
                    report_scope="standalone", ultimate_company_code=code_a,
                ),
                Project(
                    name=f"【测试】拓扑锁B_{token}", client_name="【测试】拓扑锁B",
                    short_name="拓扑锁B", company_code=code_b, audit_year=year,
                    report_scope="standalone", ultimate_company_code=code_b,
                ),
            ]
            setup.add_all(projects)
            await setup.commit()
            ids = [project.id for project in projects]

        barrier = asyncio.Barrier(2)

        async def reparent(project_id: uuid.UUID, parent_code: str) -> str:
            async with factory() as session:
                project = await session.get(Project, project_id)
                assert project is not None
                await barrier.wait()
                try:
                    await reparent_project(session, project, parent_code)
                    await session.commit()
                    return "committed"
                except HTTPException as exc:
                    await session.rollback()
                    assert exc.status_code == 400
                    assert "循环引用" in str(exc.detail)
                    return "rejected"

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                reparent(ids[0], code_b),
                reparent(ids[1], code_a),
            ),
            timeout=8,
        )
        assert sorted(outcomes) == ["committed", "rejected"]
        async with factory() as verify:
            rows = list((await verify.execute(sa.select(Project).where(
                Project.id.in_(ids)
            ))).scalars().all())
            parents = {row.company_code: row.parent_company_code for row in rows}
            assert not (parents[code_a] == code_b and parents[code_b] == code_a)
    finally:
        try:
            if ids:
                async with factory() as cleanup:
                    await cleanup.execute(sa.delete(Project).where(Project.id.in_(ids)))
                    await cleanup.commit()
        finally:
            await engine.dispose()
