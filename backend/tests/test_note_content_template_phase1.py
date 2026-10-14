"""Phase 1 契约测试：集团根追溯、模板授权与 router 注册。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.services.note_content_template_service import (
    can_view_template,
    resolve_canonical_group_root,
)

_TABLES = [Project.__table__]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _proj(id_: uuid.UUID, *, parent_id: uuid.UUID | None = None, deleted: bool = False) -> Project:
    return Project(id=id_, name=f"p-{str(id_)[:8]}", client_name="测试", parent_project_id=parent_id, is_deleted=deleted)


# ── resolve_canonical_group_root ──────────────────────────────────────────────


class TestResolveCanonicalGroupRoot:
    @pytest.mark.asyncio
    async def test_standalone_returns_self(self, db: AsyncSession):
        pid = uuid.uuid4()
        db.add(_proj(pid))
        await db.flush()
        assert await resolve_canonical_group_root(db, pid) == pid

    @pytest.mark.asyncio
    async def test_child_returns_root(self, db: AsyncSession):
        root, child = uuid.uuid4(), uuid.uuid4()
        db.add_all([_proj(root), _proj(child, parent_id=root)])
        await db.flush()
        assert await resolve_canonical_group_root(db, child) == root

    @pytest.mark.asyncio
    async def test_sibling_shares_root(self, db: AsyncSession):
        root, a, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db.add_all([_proj(root), _proj(a, parent_id=root), _proj(b, parent_id=root)])
        await db.flush()
        assert await resolve_canonical_group_root(db, a) == await resolve_canonical_group_root(db, b)

    @pytest.mark.asyncio
    async def test_multi_level(self, db: AsyncSession):
        root, mid, leaf = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db.add_all([_proj(root), _proj(mid, parent_id=root), _proj(leaf, parent_id=mid)])
        await db.flush()
        assert await resolve_canonical_group_root(db, leaf) == root

    @pytest.mark.asyncio
    async def test_cycle_returns_none(self, db: AsyncSession):
        a, b = uuid.uuid4(), uuid.uuid4()
        db.add_all([_proj(a, parent_id=b), _proj(b, parent_id=a)])
        await db.flush()
        assert await resolve_canonical_group_root(db, a) is None

    @pytest.mark.asyncio
    async def test_deleted_returns_none(self, db: AsyncSession):
        pid = uuid.uuid4()
        db.add(_proj(pid, deleted=True))
        await db.flush()
        assert await resolve_canonical_group_root(db, pid) is None

    @pytest.mark.asyncio
    async def test_nonexistent_returns_none(self, db: AsyncSession):
        assert await resolve_canonical_group_root(db, uuid.uuid4()) is None


# ── can_view_template ─────────────────────────────────────────────────────────


def _user(uid: uuid.UUID, role: str = "auditor") -> MagicMock:
    u = MagicMock(spec=["id", "role"])
    u.id = uid
    u.role = MagicMock()
    u.role.value = role
    return u


def _template(scope: str, *, user_id=None, group_id=None, deleted=False):
    from app.models.note_content_template_models import NoteContentTemplate
    t = MagicMock(spec=NoteContentTemplate)
    t.owner_scope = scope
    t.owner_user_id = user_id
    t.owner_group_project_id = group_id
    t.is_deleted = deleted
    return t


class TestCanViewTemplate:
    @pytest.mark.asyncio
    async def test_personal_visible_to_owner(self, db):
        uid = uuid.uuid4()
        assert await can_view_template(db, _user(uid), _template("personal", user_id=uid), viewer_project_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_personal_hidden_from_other(self, db):
        assert not await can_view_template(db, _user(uuid.uuid4()), _template("personal", user_id=uuid.uuid4()), viewer_project_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_group_visible_to_same_root(self, db):
        root, child = uuid.uuid4(), uuid.uuid4()
        db.add_all([_proj(root), _proj(child, parent_id=root)])
        await db.flush()
        assert await can_view_template(db, _user(uuid.uuid4()), _template("group", group_id=root), viewer_project_id=child)

    @pytest.mark.asyncio
    async def test_group_hidden_from_different_root(self, db):
        a, b, child_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db.add_all([_proj(a), _proj(b), _proj(child_b, parent_id=b)])
        await db.flush()
        assert not await can_view_template(db, _user(uuid.uuid4()), _template("group", group_id=a), viewer_project_id=child_b)

    @pytest.mark.asyncio
    async def test_deleted_always_invisible(self, db):
        uid = uuid.uuid4()
        assert not await can_view_template(db, _user(uid), _template("personal", user_id=uid, deleted=True), viewer_project_id=uuid.uuid4())


# ── router registration ──────────────────────────────────────────────────────


def _resolve(app, method: str, path: str):
    """按 Starlette 分发规则（路由表顺序、首个 FULL 匹配）求实际处理函数。"""
    from starlette.routing import Match

    scope = {"type": "http", "method": method, "path": path, "root_path": "", "query_string": b"", "headers": []}
    for route in app.router.routes:
        match, _child = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "endpoint", route)
    return None


def _concrete(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", lambda _m: str(uuid.uuid4()), path)


class TestRouterRegistration:
    """Task 8 / NFR-9：首版只对 ``register_report_routers`` 源码做文本匹配（铁律 ㉖）；
    改为在完整应用的路由表上按真实分发规则解析，未注册或被前序 catch-all 吞掉都会打红。"""

    @pytest.mark.parametrize("module", ["note_text_batch", "note_content_templates"])
    def test_every_endpoint_dispatches_to_its_handler_in_full_app(self, module):
        import importlib

        from app.main import app

        sub = importlib.import_module(f"app.routers.{module}").router
        assert sub.routes, module
        for route in sub.routes:
            for method in route.methods - {"HEAD", "OPTIONS"}:
                path = _concrete(route.path)
                assert _resolve(app, method, path) is route.endpoint, f"{method} {route.path} 未命中 {module}"

    def test_resolver_detects_catch_all_shadowing(self):
        """守卫自检：同一路径若被先注册的 catch-all 抢走，解析结果不再是本模块 handler。"""
        from fastapi import FastAPI

        from app.routers.note_text_batch import list_text_sections, router

        shadowed = FastAPI()
        shadowed.add_api_route("/api/projects/{project_id}/{rest:path}", lambda project_id, rest: None)
        shadowed.include_router(router)
        path = _concrete("/api/projects/{project_id}/disclosure-note-text-sections")
        assert _resolve(shadowed, "GET", path) is not list_text_sections
