"""T10（pg_only、只读回滚）：停用条目导航仍可达（design §3.3 / §3.4）。

- 4 个未删项目里 K14~K18 底稿（和平药房缺 K17）经 `resolve_instance` 可达，`full_resolve` 带项目上下文时
  仍标停用、带 replaced_by，并附上项目实例 wp_id；
- 孤儿 cell 的父 sheet（I6-7 等 5 张补登 sheet）在有 wp_index 实例的项目里经 `resolve_instance` 可达。
项目与实例由真库现查（不写死 id），查不到任何实例即红（防空转）。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.acnr.resolver import full_resolve, resolve_instance

pytestmark = [pytest.mark.pg_only]

_K = ("K14", "K15", "K16", "K17", "K18")
_PLATFORM = ("I6-7", "J2-5", "J3-4", "J3-5", "M6-5")
_PARENT = {"I6-7": "I6", "J2-5": "J2", "J3-4": "J3", "J3-5": "J3", "M6-5": "M6"}


async def _with_session(fn):
    eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with async_sessionmaker(eng, expire_on_commit=False)() as s:
            await s.execute(text("SET TRANSACTION READ ONLY"))
            try:
                return await fn(s)
            finally:
                await s.rollback()
    finally:
        await eng.dispose()


async def _instances(s, codes) -> list[tuple[str, str, str]]:
    rows = (await s.execute(text(
        "SELECT w.project_id::text, w.wp_code, w.id::text FROM wp_index w JOIN projects p ON p.id = w.project_id "
        "WHERE w.wp_code = ANY(:codes) AND COALESCE(p.is_deleted, false) = false "
        "AND COALESCE(w.is_deleted, false) = false ORDER BY 1, 2"), {"codes": list(codes)})).all()
    return [tuple(r) for r in rows]


@pytest.mark.asyncio
async def test_k14_k18_reachable_and_marked_deprecated():
    async def run(s):
        inst = await _instances(s, _K)
        projects = {p for p, _, _ in inst}
        assert len(projects) == 4 and len(inst) == 19, (len(projects), len(inst))  # 和平药房缺 K17
        for pid, code, _ in inst:
            ri = await resolve_instance(db=s, project_id=uuid.UUID(pid), parent_wp_code=code, sheet_code=code)
            assert ri.found and ri.wp_id, (pid, code, ri.error)
            r = await full_resolve(addr_id=f"{code}/{code}", project_id=pid, db=s)
            assert r.found and r.deprecated is True and r.replaced_by, (pid, code)
            assert r.wp_id == str(ri.wp_id), (pid, code, r.wp_id, ri.wp_id)
        return len(inst)

    assert await _with_session(run) == 19


@pytest.mark.asyncio
async def test_orphan_parent_sheets_reachable_in_projects_with_instances():
    async def run(s):
        inst = await _instances(s, _PLATFORM)
        assert {c for _, c, _ in inst} == set(_PLATFORM), inst
        for pid, code, _ in inst:
            ri = await resolve_instance(db=s, project_id=uuid.UUID(pid), parent_wp_code=_PARENT[code], sheet_code=code)
            assert ri.found and ri.wp_id, (pid, code, ri.error)
        return len(inst)

    assert await _with_session(run) >= 5
