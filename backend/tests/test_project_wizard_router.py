"""项目初始化向导 API 路由单元测试

Validates: Requirements 1.1-1.8
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole
from app.routers.project_wizard import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    """轻量级用户替身，避免 SQLAlchemy 映射属性问题。"""

    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_manager"
        self.email = "manager@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """构造带依赖覆盖的测试 HTTP 客户端。"""
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return TEST_USER

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


BASIC_INFO = {
    "client_name": "测试客户",
    "audit_year": 2024,
    "project_type": "annual",
    "accounting_standard": "enterprise",
}


# ===================================================================
# POST /api/projects — 创建项目
# ===================================================================


class TestCreateProject:
    """Validates: Requirements 1.2, 1.3"""

    @pytest.mark.asyncio
    async def test_create_project_success(self, client: AsyncClient):
        resp = await client.post("/api/projects", json=BASIC_INFO)
        assert resp.status_code == 200
        body = resp.json()
        assert body["client_name"] == "测试客户"
        assert body["audit_year"] == 2024
        assert body["status"] == "created"
        assert "id" in body

    @pytest.mark.asyncio
    async def test_create_project_missing_field(self, client: AsyncClient):
        resp = await client.post(
            "/api/projects",
            json={"client_name": "测试", "audit_year": 2024},
        )
        assert resp.status_code == 422


# ===================================================================
# GET /api/projects/{id}/wizard — 获取向导状态
# ===================================================================


class TestGetWizardState:
    """Validates: Requirements 1.4, 1.5"""

    @pytest.mark.asyncio
    async def test_get_wizard_state(self, client: AsyncClient):
        # 先创建项目
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.get(f"/api/projects/{project_id}/wizard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project_id
        assert body["current_step"] == "basic_info"
        assert body["completed"] is False
        assert "basic_info" in body["steps"]

    @pytest.mark.asyncio
    async def test_get_wizard_state_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/projects/{fake_id}/wizard")
        assert resp.status_code == 404


# ===================================================================
# PUT /api/projects/{id}/wizard/{step} — 更新步骤
# ===================================================================


class TestUpdateStep:
    """Validates: Requirements 1.3, 1.4, 1.5"""

    @pytest.mark.asyncio
    async def test_update_step_success(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/projects/{project_id}/wizard/account_import",
            json={"file_name": "chart.xlsx", "count": 50},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "account_import" in body["steps"]
        assert body["steps"]["account_import"]["completed"] is True

    @pytest.mark.asyncio
    async def test_update_step_dependency_fail(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        # account_mapping 依赖 account_import
        resp = await client.put(
            f"/api/projects/{project_id}/wizard/account_mapping",
            json={"mappings": []},
        )
        assert resp.status_code == 400


# ===================================================================
# POST /api/projects/{id}/wizard/validate/{step} — 校验步骤
# ===================================================================


class TestValidateStep:
    """Validates: Requirements 1.8"""

    @pytest.mark.asyncio
    async def test_validate_basic_info_valid(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/projects/{project_id}/wizard/validate/basic_info"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_confirmation_incomplete(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/projects/{project_id}/wizard/validate/confirmation"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert len(body["messages"]) > 0


# ===================================================================
# POST /api/projects/{id}/wizard/confirm — 确认项目
# ===================================================================


class TestConfirmProject:
    """Validates: Requirements 1.7"""

    @pytest.mark.asyncio
    async def test_confirm_project_success(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        # 完成所有前置步骤
        for step in [
            "account_import",
            "account_mapping",
            "materiality",
            "template_set",
            "confirmation",
        ]:
            await client.put(
                f"/api/projects/{project_id}/wizard/{step}",
                json={"done": True},
            )

        resp = await client.post(f"/api/projects/{project_id}/wizard/confirm")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "planning"
        assert body["audit_year"] == 2024

    @pytest.mark.asyncio
    async def test_confirm_project_missing_steps(self, client: AsyncClient):
        create_resp = await client.post("/api/projects", json=BASIC_INFO)
        project_id = create_resp.json()["id"]

        resp = await client.post(f"/api/projects/{project_id}/wizard/confirm")
        assert resp.status_code == 400
