"""数据生命周期路由测试

Validates: persisted import queue status endpoints.
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
from app.models.audit_platform_schemas import BasicInfoSchema
from app.routers.data_lifecycle import router
from app.services import project_wizard_service
from app.services.import_queue_service import ImportQueueService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
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


async def _create_test_project(db: AsyncSession):
    return await project_wizard_service.create_project(
        BasicInfoSchema(
            client_name="测试客户",
            audit_year=2024,
            project_type="annual",
            accounting_standard="enterprise",
        ),
        db,
    )


class TestImportQueueRouter:
    @pytest.mark.asyncio
    async def test_get_import_status_reads_completed_job_from_db(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        project = await _create_test_project(db_session)
        ok, msg, batch_id = await ImportQueueService.acquire_lock(
            project.id,
            str(TEST_USER.id),
            db_session,
            source_type="smart_import",
            file_name="chart.xlsx",
            year=0,
        )
        assert ok is True
        assert batch_id is not None

        await ImportQueueService.complete_job(
            project.id,
            batch_id,
            db_session,
            message="导入完成",
            result={"total_imported": 3},
            year=2024,
            record_count=3,
        )

        resp = await client.get(f"/api/data-lifecycle/import-queue/{project.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["batch_id"] == str(batch_id)
        assert body["status"] == "completed"
        assert body["progress"] == 100
        assert body["result"] == {"total_imported": 3}

    @pytest.mark.asyncio
    async def test_get_import_queue_lists_processing_job_from_db(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        project = await _create_test_project(db_session)
        ok, msg, batch_id = await ImportQueueService.acquire_lock(
            project.id,
            str(TEST_USER.id),
            db_session,
            source_type="smart_import",
            file_name="chart.xlsx",
            year=0,
        )
        assert ok is True
        assert batch_id is not None

        resp = await client.get("/api/data-lifecycle/import-queue")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["active"]) == 1
        assert body["active"][0]["project_id"] == str(project.id)
        assert body["active"][0]["batch_id"] == str(batch_id)
        assert body["active"][0]["status"] == "processing"
