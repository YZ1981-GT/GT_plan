"""账龄配置 API 端点单元测试（aging-config-enhancement Task 2.2）

覆盖：
- GET  /api/projects/{project_id}/aging/config  正常返回结构 + 无配置默认值
- PUT  /api/projects/{project_id}/aging/config  校验失败返回 422 (空 label/重复 label/段数超限)
- PUT  成功保存并返回配置 (含 CUSTOM/subject_overrides 往返)
- GET  /api/aging/presets                        返回预设定义

约定：参照 test_project_wizard_router.py，构造仅挂载目标 router 的裸 FastAPI app，
覆盖 get_db / get_current_user 依赖，使用内存 SQLite。

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project
from app.routers.aging_config import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    """轻量级用户替身（admin 角色）。"""

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


@pytest_asyncio.fixture
async def project_id(db_session: AsyncSession) -> str:
    """在库中插入一个项目并返回其 id。"""
    pid = uuid.uuid4()
    project = Project(
        id=pid,
        name="测试项目",
        client_name="测试客户",
        status=ProjectStatus.created,
        wizard_state={},
    )
    db_session.add(project)
    await db_session.commit()
    return str(pid)


# ===================================================================
# GET /api/projects/{id}/aging/config — 读取配置
# ===================================================================


class TestGetAgingConfig:
    """Validates: Requirements 2.1, 2.5"""

    @pytest.mark.asyncio
    async def test_get_config_default_when_no_config(
        self, client: AsyncClient, project_id: str
    ):
        """无 aging_config 时返回默认值（FIVE_YEAR 6 段）。"""
        resp = await client.get(f"/api/projects/{project_id}/aging/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["preset"] == "FIVE_YEAR"
        assert body["subject_overrides"] == {}
        # FIVE_YEAR = 6 段
        assert len(body["effective_segments"]) == 6
        first = body["effective_segments"][0]
        assert {"key", "label", "dayFrom", "dayTo"} <= set(first.keys())
        assert first["label"] == "1年以内"

    @pytest.mark.asyncio
    async def test_get_config_returns_saved_config(
        self, client: AsyncClient, project_id: str
    ):
        """PUT 保存后 GET 应返回一致配置。"""
        await client.put(
            f"/api/projects/{project_id}/aging/config",
            json={"preset": "THREE_YEAR"},
        )
        resp = await client.get(f"/api/projects/{project_id}/aging/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["preset"] == "THREE_YEAR"
        assert len(body["effective_segments"]) == 4

    @pytest.mark.asyncio
    async def test_get_config_project_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/projects/{fake_id}/aging/config")
        assert resp.status_code == 404


# ===================================================================
# PUT /api/projects/{id}/aging/config — 保存配置（成功 + 校验）
# ===================================================================


class TestPutAgingConfigSuccess:
    """Validates: Requirements 2.2"""

    @pytest.mark.asyncio
    async def test_put_preset_success(self, client: AsyncClient, project_id: str):
        resp = await client.put(
            f"/api/projects/{project_id}/aging/config",
            json={"preset": "FIVE_YEAR"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["preset"] == "FIVE_YEAR"
        assert len(body["effective_segments"]) == 6

    @pytest.mark.asyncio
    async def test_put_custom_success(self, client: AsyncClient, project_id: str):
        payload = {
            "preset": "CUSTOM",
            "custom_segments": [
                {"key": "seg_1", "label": "6个月以内", "dayFrom": 0, "dayTo": 180},
                {"key": "seg_2", "label": "6个月-1年", "dayFrom": 181, "dayTo": 365},
                {"key": "seg_3", "label": "1年以上", "dayFrom": 366, "dayTo": None},
            ],
        }
        resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["preset"] == "CUSTOM"
        assert len(body["effective_segments"]) == 3
        assert [s["label"] for s in body["effective_segments"]] == [
            "6个月以内",
            "6个月-1年",
            "1年以上",
        ]

    @pytest.mark.asyncio
    async def test_put_subject_overrides_roundtrip(
        self, client: AsyncClient, project_id: str
    ):
        payload = {
            "preset": "FIVE_YEAR",
            "subject_overrides": {"D3": "THREE_YEAR", "F1": "THREE_YEAR"},
        }
        resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert resp.status_code == 200
        assert resp.json()["subject_overrides"] == {
            "D3": "THREE_YEAR",
            "F1": "THREE_YEAR",
        }

        # 持久化验证：再次 GET 应保留 overrides
        get_resp = await client.get(f"/api/projects/{project_id}/aging/config")
        assert get_resp.json()["subject_overrides"] == {
            "D3": "THREE_YEAR",
            "F1": "THREE_YEAR",
        }


class TestPutAgingConfigValidation:
    """Validates: Requirements 2.3"""

    @pytest.mark.asyncio
    async def test_put_custom_too_few_segments_422(
        self, client: AsyncClient, project_id: str
    ):
        payload = {
            "preset": "CUSTOM",
            "custom_segments": [
                {"key": "seg_1", "label": "唯一段", "dayFrom": 0, "dayTo": None},
            ],
        }
        resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error_code"] == "INVALID_SEGMENT_COUNT"

    @pytest.mark.asyncio
    async def test_put_custom_too_many_segments_422(
        self, client: AsyncClient, project_id: str
    ):
        payload = {
            "preset": "CUSTOM",
            "custom_segments": [
                {"key": f"seg_{i}", "label": f"段{i}", "dayFrom": i, "dayTo": None}
                for i in range(11)  # 11 段 > 10
            ],
        }
        resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error_code"] == "INVALID_SEGMENT_COUNT"

    @pytest.mark.asyncio
    async def test_put_empty_label_422(self, client: AsyncClient, project_id: str):
        payload = {
            "preset": "CUSTOM",
            "custom_segments": [
                {"key": "seg_1", "label": "正常段", "dayFrom": 0, "dayTo": 180},
                {"key": "seg_2", "label": "   ", "dayFrom": 181, "dayTo": None},
            ],
        }
        resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error_code"] == "EMPTY_SEGMENT_LABEL"

    @pytest.mark.asyncio
    async def test_put_duplicate_label_422(
        self, client: AsyncClient, project_id: str
    ):
        payload = {
            "preset": "CUSTOM",
            "custom_segments": [
                {"key": "seg_1", "label": "重复段", "dayFrom": 0, "dayTo": 180},
                {"key": "seg_2", "label": "重复段", "dayFrom": 181, "dayTo": None},
            ],
        }
        resp = await client.put(
            f"/api/projects/{project_id}/aging/config", json=payload
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error_code"] == "DUPLICATE_SEGMENT_LABEL"


# ===================================================================
# GET /api/aging/presets — 预设定义
# ===================================================================


class TestGetAgingPresets:
    """Validates: Requirements 2.4"""

    @pytest.mark.asyncio
    async def test_get_presets(self, client: AsyncClient):
        resp = await client.get("/api/aging/presets")
        assert resp.status_code == 200
        presets = resp.json()["presets"]
        assert set(presets.keys()) == {"THREE_YEAR", "FIVE_YEAR"}
        assert len(presets["THREE_YEAR"]) == 4
        assert len(presets["FIVE_YEAR"]) == 6
        # 段结构字段完整
        seg = presets["FIVE_YEAR"][0]
        assert {"key", "label", "dayFrom", "dayTo"} <= set(seg.keys())
        assert [s["label"] for s in presets["THREE_YEAR"]] == [
            "1年以内",
            "1-2年",
            "2-3年",
            "3年以上",
        ]
