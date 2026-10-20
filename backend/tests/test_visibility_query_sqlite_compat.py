"""VisibilityQueryService 的 SQLite 兼容层（preexisting-test-failures-closure G1）。

SQLAlchemy 的 ``Uuid`` 在 SQLite 上存 32 位十六进制文本（无连字符），原生 SQL 绑定的却是
``str(uuid)``（带连字符）——比较恒不相等，admin 在 SQLite 夹具下看不到任何底稿，依赖
可见性闸门的端点全部 404。查回来的 ``wi.id`` 也是文本，调用方拿 ORM 的 UUID 比对可见集
同样恒不命中。PostgreSQL 不受影响（真库用例见 tests/procedure_delegation_visibility/）。
"""
from __future__ import annotations

import importlib
import pkgutil
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.workpaper_models import WpIndex, WpStatus
from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole
from app.services.wp_visibility.visibility_query import ACCESS_KIND_ADMIN, VisibilityQueryService

for _module in pkgutil.walk_packages(app.models.__path__, "app.models."):
    importlib.import_module(_module.name)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)()
    project_id, other_project = uuid.uuid4(), uuid.uuid4()
    for pid in (project_id, other_project):
        session.add(Project(id=pid, name=f"【测试】可见性_{pid.hex[:6]}", client_name="测试客户",
                            project_type=ProjectType.annual, status=ProjectStatus.planning,
                            created_by=uuid.uuid4()))
    await session.flush()
    mine = [WpIndex(project_id=project_id, wp_code=code, wp_name=code, audit_cycle=code[0],
                    status=WpStatus.not_started) for code in ("B1-1", "E1-1")]
    foreign = WpIndex(project_id=other_project, wp_code="D2-1", wp_name="D2-1", audit_cycle="D",
                      status=WpStatus.not_started)
    session.add_all([*mine, foreign])
    await session.commit()
    ctx = VisibilityContext(user_id=uuid.uuid4(), project_id=project_id, role=VisibilityRole.admin,
                            is_admin=True, scope_cycles=frozenset())
    try:
        yield session, ctx, mine, foreign
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_sees_exactly_the_project_workpapers_as_uuids(seeded):
    session, ctx, mine, _foreign = seeded
    grants = await VisibilityQueryService(session).grants_for_project(ctx)
    assert grants.wp_index_ids() == frozenset(idx.id for idx in mine)
    assert all(isinstance(wp_index_id, uuid.UUID) for wp_index_id in grants.wp_index_ids())
    assert all(grants.is_visible(idx.id) for idx in mine)


@pytest.mark.asyncio
async def test_single_workpaper_grant_is_admin_and_respects_project(seeded):
    session, ctx, mine, foreign = seeded
    svc = VisibilityQueryService(session)
    grants = await svc.grants_for_wp_index(ctx, mine[0].id)
    assert [g.access_kind for g in grants] == [ACCESS_KIND_ADMIN]
    # 别的项目的底稿：按 project_id 过滤，不可见
    assert await svc.grants_for_wp_index(ctx, foreign.id) == []
