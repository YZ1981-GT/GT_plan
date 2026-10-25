"""项目配置接口停用 consolidation_type（spec consol-tree-three-code-autobuild 需求 4.3 / 4.5）。

真发请求（TestClient 语义的 ASGITransport）：
- PUT 带非空 ``consolidation_type`` ⇒ 400 中文原因，且**整单拒绝**（同一请求里的其他字段也不落库）；
- PUT 不带该字段 ⇒ 其他字段照常更新；
- GET 不再返回 ``consolidation_type``（合并方式改看企业树接口的 mode）。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project
from app.routers.project_config import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "cfg_tester"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    async def _user():
        return _FakeUser()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def project(db: AsyncSession) -> Project:
    p = Project(
        name="配置测试_2025",
        client_name="配置测试",
        status=ProjectStatus.created,
        report_scope="standalone",
        template_type="soe",
        consolidation_type="subsidiary",  # 历史值：保留但不再读写
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["subsidiary", "branch", "母子合并"])
async def test_put_consolidation_type_is_400_and_nothing_written(client, db, project, value):
    resp = await client.put(
        f"/api/projects/{project.id}/config",
        json={"consolidation_type": value, "report_standard": "listed"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "合并方式由下级企业的与上级关系自动识别，不再手工设置"

    await db.refresh(project)
    assert project.template_type == "soe", "整单拒绝：同请求里的其他字段不得落库"
    assert project.consolidation_type == "subsidiary", "历史列保持原值"


@pytest.mark.asyncio
async def test_put_without_consolidation_type_still_updates(client, db, project):
    resp = await client.put(
        f"/api/projects/{project.id}/config", json={"report_standard": "listed"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["changed_fields"] == ["report_standard"]
    row = (await db.execute(select(Project).where(Project.id == project.id))).scalar_one()
    assert row.template_type == "listed"


@pytest.mark.asyncio
async def test_put_null_consolidation_type_is_allowed(client, project):
    """显式 null 等同未传（前端表单常把空值序列化为 null），不应 400。"""
    resp = await client.put(
        f"/api/projects/{project.id}/config", json={"consolidation_type": None}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["changed_fields"] == []


@pytest.mark.asyncio
async def test_get_no_longer_returns_consolidation_type(client, project):
    resp = await client.get(f"/api/projects/{project.id}/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "consolidation_type" not in body
    assert body["report_scope"] == "standalone"


@pytest.mark.asyncio
async def test_unknown_project_is_404(client):
    resp = await client.put(
        f"/api/projects/{uuid.uuid4()}/config", json={"consolidation_type": "branch"}
    )
    assert resp.status_code == 404
