"""Tests for linkage_panorama endpoint (Requirements 9.1, 9.4, 9.5, 9.6, 9.7).

覆盖：
- GET graph-data happy path（mock CWR 加载 + DB stale）
- 认证守卫（未登录 → 401）
- JSON 加载失败 → 503
- stale 状态正确叠加到 working_paper
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.base import Base, UserRole
from app.routers.linkage_panorama import router as linkage_panorama_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.admin):
        self.id = uid
        self.username = "test_user"
        self.email = "u@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _make_app_authenticated(db_session: AsyncSession, user: _FakeUser) -> FastAPI:
    app = FastAPI()
    app.include_router(linkage_panorama_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return user

    def _override_project_access(min_permission: str = "readonly"):
        async def _dep(project_id: uuid.UUID):
            return user
        return _dep

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[require_project_access] = _override_project_access
    return app


def _make_app_no_auth(db_session: AsyncSession) -> FastAPI:
    app = FastAPI()
    app.include_router(linkage_panorama_router)

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return app


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_graph_data_happy_path(db_session: AsyncSession):
    """正常流程：加载 CWR + 聚合 + 返回 nodes/edges/statistics 结构。"""
    user = _FakeUser(USER_ID)
    app = _make_app_authenticated(db_session, user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/projects/{PROJECT_ID}/linkage-panorama/graph-data")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert "statistics" in data

    stats = data["statistics"]
    # 节点数 / 边数 用运行时计算（不硬编码）
    assert stats["node_count"] == len(data["nodes"])
    assert stats["edge_count"] == len(data["edges"])
    # severity 5 级分布存在
    assert "severity_distribution" in stats
    # 真实数据下 blocking 应 > 0
    assert stats["severity_distribution"].get("blocking", 0) > 0
    # 节点至少包含主要业务循环节点
    cycles_present = {n["cycle"] for n in data["nodes"]}
    assert "H" in cycles_present
    assert "D" in cycles_present


@pytest.mark.asyncio
async def test_get_graph_data_no_dangling_edges(db_session: AsyncSession):
    user = _FakeUser(USER_ID)
    app = _make_app_authenticated(db_session, user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/projects/{PROJECT_ID}/linkage-panorama/graph-data")
    data = resp.json()
    node_ids = {n["id"] for n in data["nodes"]}
    for edge in data["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids


@pytest.mark.asyncio
async def test_get_graph_data_stale_count_zero_in_empty_db(db_session: AsyncSession):
    """空 DB（无 working_paper 记录） → stale_node_count = 0。"""
    user = _FakeUser(USER_ID)
    app = _make_app_authenticated(db_session, user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/projects/{PROJECT_ID}/linkage-panorama/graph-data")
    stats = resp.json()["statistics"]
    assert stats["stale_node_count"] == 0
    assert stats["stale_edge_count"] == 0


# ---------------------------------------------------------------------------
# 认证 / JSON 失败
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_graph_data_unauthenticated_returns_401(db_session: AsyncSession):
    """无认证 override（默认 get_current_user 会抛 401）。"""
    app = _make_app_no_auth(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/projects/{PROJECT_ID}/linkage-panorama/graph-data")
    # 真实 get_current_user 缺 token → 401，require_project_access 会从 get_current_user 链上抛
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_graph_data_returns_503_when_cwr_file_missing(
    db_session: AsyncSession, monkeypatch
):
    """LINKAGE_PANORAMA_CWR_PATH 指向不存在的文件 → 503。"""
    monkeypatch.setenv("LINKAGE_PANORAMA_CWR_PATH", "/non/existent/path.json")
    user = _FakeUser(USER_ID)
    app = _make_app_authenticated(db_session, user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/projects/{PROJECT_ID}/linkage-panorama/graph-data")
    assert resp.status_code == 503
    assert "CWR" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_graph_data_returns_503_when_cwr_invalid_json(
    db_session: AsyncSession, monkeypatch, tmp_path
):
    """CWR 文件存在但 JSON 损坏 → 503。"""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setenv("LINKAGE_PANORAMA_CWR_PATH", str(bad_file))
    user = _FakeUser(USER_ID)
    app = _make_app_authenticated(db_session, user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/projects/{PROJECT_ID}/linkage-panorama/graph-data")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_get_graph_data_returns_503_when_references_field_missing(
    db_session: AsyncSession, monkeypatch, tmp_path
):
    """JSON 合法但缺 references 字段 → 503。"""
    bad_file = tmp_path / "no_refs.json"
    bad_file.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    monkeypatch.setenv("LINKAGE_PANORAMA_CWR_PATH", str(bad_file))
    user = _FakeUser(USER_ID)
    app = _make_app_authenticated(db_session, user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/projects/{PROJECT_ID}/linkage-panorama/graph-data")
    assert resp.status_code == 503
