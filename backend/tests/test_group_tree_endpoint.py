"""GET /api/projects/tree 端点验证（group-tree-architecture Task 1.2）。

覆盖：
- 端点已挂载（in-process ASGI httpx），返回 {"trees", "independents"} 结构
- scope=consolidated 过滤
- year 过滤
- 静态路径 /tree 在通配 /{project_id} 之前解析（同时注册两 router，
  顺序与 router_registry/system.py §2 一致：batch_project 先于 project_wizard）
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole
from app.models.consolidation_models import Company, ConsolMethod
from app.models.core import Project
from app.routers.batch_project import router as batch_project_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

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


async def _seed(session: AsyncSession) -> None:
    """种子：一个合并根 + 两个子公司（2025），一个独立项目（2024）。"""
    ultimate = "91110000000000000U"
    # 合并根项目
    session.add(Project(
        id=uuid.uuid4(),
        name="集团母公司_2025",
        client_name="集团母公司",
        company_code=ultimate,
        parent_company_code=None,
        ultimate_company_code=ultimate,
        report_scope="consolidated",
        audit_period_end=date(2025, 12, 31),
    ))
    # 子公司 A（合并）
    session.add(Project(
        id=uuid.uuid4(),
        name="子公司A_2025",
        client_name="子公司A",
        company_code="91110000000000001A",
        parent_company_code=ultimate,
        ultimate_company_code=ultimate,
        report_scope="consolidated",
        audit_period_end=date(2025, 12, 31),
    ))
    # 子公司 B（标准报表，非合并）
    session.add(Project(
        id=uuid.uuid4(),
        name="子公司B_2025",
        client_name="子公司B",
        company_code="91110000000000002B",
        parent_company_code="91110000000000001A",
        ultimate_company_code=ultimate,
        report_scope="standalone",
        audit_period_end=date(2025, 12, 31),
    ))
    # 独立项目（不同年度、无 ultimate）
    session.add(Project(
        id=uuid.uuid4(),
        name="独立项目_2024",
        client_name="独立项目",
        company_code="91110000000000003C",
        parent_company_code=None,
        ultimate_company_code=None,
        report_scope="standalone",
        audit_period_end=date(2024, 12, 31),
    ))
    await session.commit()


def _make_app(db_session: AsyncSession) -> FastAPI:
    app = FastAPI()
    # 注册顺序与 router_registry/system.py §2 一致：batch_project 在前。
    # 此处也注册 project_wizard（含 GET /{project_id} 通配）以验证 /tree 不被截获。
    from app.routers.project_wizard import router as project_wizard_router

    app.include_router(batch_project_router)
    app.include_router(project_wizard_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(USER_ID)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


@pytest.mark.asyncio
async def test_tree_endpoint_mounted_and_returns_forest(db_session: AsyncSession):
    """端点挂载，返回 trees + independents 结构。"""
    await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/projects/tree")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "trees" in data
    assert "independents" in data
    # 一棵集团树（同一 ultimate）
    assert len(data["trees"]) == 1
    tree = data["trees"][0]
    assert tree["ultimateCode"] == "91110000000000000U"
    assert tree["ultimateName"] == "集团母公司"
    # 独立项目（ultimate 为空）进 independents
    independent_names = {n["companyName"] for n in data["independents"]}
    assert "独立项目" in independent_names


@pytest.mark.asyncio
async def test_tree_endpoint_scope_filter(db_session: AsyncSession):
    """scope=consolidated 仅含合并项目（子公司B standalone 不在树中）。"""
    await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/projects/tree", params={"scope": "consolidated"})

    assert resp.status_code == 200, resp.text
    data = resp.json()

    def _collect_codes(node: dict, acc: set) -> None:
        acc.add(node["companyCode"])
        for c in node.get("children", []):
            _collect_codes(c, acc)

    codes: set = set()
    for tree in data["trees"]:
        for child in tree["children"]:
            _collect_codes(child, codes)
    # standalone 子公司B 被 scope 过滤掉
    assert "91110000000000002B" not in codes
    # 合并子公司A 在树中
    assert "91110000000000001A" in codes


@pytest.mark.asyncio
async def test_tree_endpoint_year_filter(db_session: AsyncSession):
    """year=2024 仅含 2024 项目（独立项目），无 2025 集团树。"""
    await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/projects/tree", params={"year": 2024})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["trees"]) == 0
    independent_names = {n["companyName"] for n in data["independents"]}
    assert "独立项目" in independent_names


@pytest.mark.asyncio
async def test_tree_not_captured_by_wildcard(db_session: AsyncSession):
    """静态路径 /tree 不被 GET /{project_id} 通配截获（不返回 422 UUID parse error）。"""
    await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/projects/tree")
    # 若被通配截获会因 "tree" 非 UUID 返回 422
    assert resp.status_code == 200, resp.text


# ─── Phase 2（Task 14.1）：companies 表富集 shareholding / consol_method ──────────


async def _seed_with_companies(session: AsyncSession) -> None:
    """种子：合并根 + 一个子公司，并在 companies 表填持股/合并方式。"""
    ultimate = "91110000000000000U"
    sub_code = "91110000000000001A"
    root_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    session.add(Project(
        id=root_id,
        name="集团母公司_2025",
        client_name="集团母公司",
        company_code=ultimate,
        parent_company_code=None,
        ultimate_company_code=ultimate,
        report_scope="consolidated",
        audit_period_end=date(2025, 12, 31),
    ))
    session.add(Project(
        id=sub_id,
        name="子公司A_2025",
        client_name="子公司A",
        company_code=sub_code,
        parent_company_code=ultimate,
        ultimate_company_code=ultimate,
        report_scope="consolidated",
        audit_period_end=date(2025, 12, 31),
    ))
    # companies 表：子公司 A 全资合并，母公司无持股数据（验证优雅降级）
    session.add(Company(
        id=uuid.uuid4(),
        project_id=sub_id,
        company_code=sub_code,
        company_name="子公司A",
        parent_code=ultimate,
        ultimate_code=ultimate,
        shareholding=100,
        consol_method=ConsolMethod.full,
        is_active=True,
    ))
    await session.commit()


def _find_node_by_code(node: dict, code: str):
    if node.get("companyCode") == code:
        return node
    for c in node.get("children", []):
        found = _find_node_by_code(c, code)
        if found:
            return found
    return None


@pytest.mark.asyncio
async def test_tree_endpoint_enriches_shareholding_and_method(db_session: AsyncSession):
    """companies 表有匹配 → 节点带 shareholding / consolMethod；无匹配 → 保持 null。"""
    await _seed_with_companies(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/projects/tree", params={"scope": "consolidated"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    tree = data["trees"][0]

    sub = None
    root = None
    for child in tree["children"]:
        root = root or _find_node_by_code(child, "91110000000000000U")
        sub = sub or _find_node_by_code(child, "91110000000000001A")

    # 子公司 A 富集成功
    assert sub is not None
    assert sub["shareholding"] == 100.0
    assert sub["consolMethod"] == "full"
    # 母公司无 companies 行 → 优雅降级保持 null
    assert root is not None
    assert root["shareholding"] is None
    assert root["consolMethod"] is None


@pytest.mark.asyncio
async def test_tree_endpoint_no_companies_rows_degrades_gracefully(db_session: AsyncSession):
    """无任何 companies 行（仅 Projects 种子）→ 所有节点 shareholding/consolMethod 为 null，不报错。"""
    await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/projects/tree")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    tree = data["trees"][0]
    for child in tree["children"]:
        assert child.get("shareholding") is None
        assert child.get("consolMethod") is None
