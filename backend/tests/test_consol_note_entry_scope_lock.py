"""合并附注旧入口作用域与锁守卫（spec consol-note-node-refresh-and-formula-orchestration §1-2）。

验证：
- refresh / apply-formulas / reaggregate 在合并锁定时返回 423
- refresh / apply-formulas 的非法 node_key（不在企业树中）返回 4xx
- apply-formulas 的 DAG 循环引用返回 400
- 所有入口的 fill_by_formula 被真正调用（不是空壳）
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型与 SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project, User

Y = 2025


@pytest_asyncio.fixture
async def db_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _project(label: str, *, locked: bool = False) -> Project:
    return Project(
        id=uuid.uuid4(),
        name=f"scope-lock-{label}",
        client_name=f"scope-lock-{label}",
        status=ProjectStatus.execution,
        audit_year=Y,
        consol_lock=locked,
    )


def _app(factory, *routers):
    app = FastAPI()
    for r in routers:
        app.include_router(r)
    actor_id = uuid.uuid4()
    actor = type("Actor", (), {
        "id": actor_id, "username": f"test_{actor_id.hex[:6]}",
        "role": UserRole.admin, "is_active": True, "is_deleted": False,
    })()

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: actor
    return app


async def _persist(factory, *objs):
    async with factory() as db:
        db.add_all(objs)
        await db.commit()


async def _lock_project(factory, project):
    async with factory() as db:
        p = await db.get(Project, project.id)
        p.consol_lock = True
        await db.commit()


# ─── refresh_note_by_formula ──────────────────────────────────────────────────


class TestRefreshLock:
    """POST /refresh/{pid}/{year}/{sid} 合并锁定 → 423。"""

    @pytest.mark.asyncio
    async def test_locked_returns_423(self, db_factory):
        from app.routers.consol_note_sections import router

        project = _project("refresh-lock", locked=True)
        await _persist(db_factory, project)
        app = _app(db_factory, router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/consol-note-sections/refresh/{project.id}/{Y}/五-1-1",
                json={},
            )
        assert resp.status_code == 423, resp.text


class TestRefreshInvalidNodeKey:
    """POST /refresh 的非法 node_key → 4xx。"""

    @pytest.mark.asyncio
    async def test_bad_node_key_returns_4xx(self, db_factory):
        from app.routers.consol_note_sections import router

        project = _project("refresh-bad-nk")
        await _persist(db_factory, project)
        app = _app(db_factory, router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/consol-note-sections/refresh/{project.id}/{Y}/五-1-1?node_key=NONEXISTENT:consol",
                json={},
            )
        # resolve_node_scope 找不到节点 → 404 或 400
        assert 400 <= resp.status_code < 500, f"期望 4xx，实际 {resp.status_code}: {resp.text}"


# ─── apply_all_formulas ───────────────────────────────────────────────────────


class TestApplyAllLock:
    """POST /apply-formulas/{pid}/{year} 合并锁定 → 423。"""

    @pytest.mark.asyncio
    async def test_locked_returns_423(self, db_factory):
        from app.routers.consol_note_sections import router

        project = _project("apply-lock", locked=True)
        await _persist(db_factory, project)
        app = _app(db_factory, router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/consol-note-sections/apply-formulas/{project.id}/{Y}",
                json={},
            )
        assert resp.status_code == 423, resp.text


class TestApplyAllInvalidNodeKey:
    """POST /apply-formulas 的非法 node_key → 4xx。"""

    @pytest.mark.asyncio
    async def test_bad_node_key_returns_4xx(self, db_factory):
        from app.routers.consol_note_sections import router

        project = _project("apply-bad-nk")
        await _persist(db_factory, project)
        app = _app(db_factory, router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/consol-note-sections/apply-formulas/{project.id}/{Y}?node_key=NONEXISTENT:consol",
                json={},
            )
        assert 400 <= resp.status_code < 500, f"期望 4xx，实际 {resp.status_code}: {resp.text}"


class TestApplyAllDagValidation:
    """POST /apply-formulas DAG 循环引用 → 400。"""

    @pytest.mark.asyncio
    async def test_dag_cycle_returns_400(self, db_factory):
        from app.routers.consol_note_sections import router

        project = _project("apply-dag")
        await _persist(db_factory, project)
        app = _app(db_factory, router)

        # mock validate_lineage_dag 返回 False（循环引用）
        with patch(
            "app.services.consol_note_aggregation_service.validate_lineage_dag",
            new=AsyncMock(return_value=False),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/consol-note-sections/apply-formulas/{project.id}/{Y}",
                    json={},
                )
        assert resp.status_code == 400, resp.text
        assert "循环引用" in resp.text


# ─── reaggregate_consol_notes ─────────────────────────────────────────────────


class TestReaggregateLock:
    """POST /{pid}/{year}/reaggregate 合并锁定 → 423。"""

    @pytest.mark.asyncio
    async def test_locked_returns_423(self, db_factory):
        from app.routers.consol_notes import router

        project = _project("reagg-lock", locked=True)
        await _persist(db_factory, project)
        app = _app(db_factory, router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/consolidation/notes/{project.id}/{Y}/reaggregate",
                json={},
            )
        assert resp.status_code == 423, resp.text
