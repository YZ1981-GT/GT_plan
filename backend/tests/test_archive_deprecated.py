"""归档 Deprecated 标记 + 幂等测试

3 场景：
1. 旧端点 Deprecation 头存在且值为 version="R6"
2. 新路径 /api/projects/{pid}/archive/orchestrate 可达
3. 幂等返回同 job_id（24h 内 succeeded/running 不重复打包）

需求 1 AC6, AC7。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401
import app.models.qc_rule_models  # noqa: E402, F401
import app.models.archive_models  # noqa: E402, F401

from app.models.archive_models import ArchiveJob  # noqa: E402
from app.models.base import UserRole  # noqa: E402


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_admin"
        self.email = "admin@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _password_confirmed() -> None:
    """视为已通过二次密码确认（本文件测编排可达与幂等，确认门本身见 test_orchestrate_requires_confirmation_token）。"""
    return None


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """创建包含归档相关路由的测试客户端。

    orchestrate 自 b98cdc51f（2026-05-22）起要求二次密码确认（``require_confirmation_token``，
    令牌存 Redis 一次性消费）；本文件写于其前，未带令牌即 403 / Redis 不可用即 503。
    """
    from app.routers.archive import router as archive_router
    from app.routers.password_confirm import require_confirmation_token
    from app.routers.wp_storage import router as wp_storage_router

    app = FastAPI()
    app.include_router(archive_router)
    app.include_router(wp_storage_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return TEST_USER

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[require_confirmation_token] = _password_confirmed

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.app_under_test = app  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()


# ── 场景 1：旧端点 Deprecation 头存在且值为 version="R6" ──────────────


@pytest.mark.asyncio
async def test_deprecated_endpoint_has_deprecation_header(client: AsyncClient):
    """旧端点 /api/workpapers/projects/{pid}/archive 应返回 Deprecation: version="R6" 头。"""
    project_id = uuid.uuid4()

    # Mock WpStorageService.archive_project 避免实际执行
    with patch(
        "app.routers.wp_storage.WpStorageService"
    ) as MockSvc:
        mock_instance = MockSvc.return_value
        mock_instance.archive_project = AsyncMock(return_value={"status": "ok"})

        resp = await client.post(f"/api/workpapers/projects/{project_id}/archive")

    assert resp.status_code == 200
    assert "deprecation" in resp.headers
    assert resp.headers["deprecation"] == 'version="R6"'


# ── 场景 2：新路径 /api/projects/{pid}/archive/orchestrate 可达 ──────


@pytest.mark.asyncio
async def test_new_orchestrate_endpoint_reachable(client: AsyncClient, db_session: AsyncSession):
    """新路径 POST /api/projects/{pid}/archive/orchestrate 应可达（非 404/405）。

    Mock 掉 gate_engine 和 wp_storage 避免实际执行归档步骤。
    """
    # 先创建一个 Project 记录（archive router 不校验 project 存在性，但 orchestrator 需要）
    from app.models.core import Project

    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name="测试项目",
        client_name="测试客户",
        status="execution",
    )
    db_session.add(project)
    await db_session.flush()

    # Mock 归档步骤避免实际执行
    with patch(
        "app.services.archive_orchestrator.ArchiveOrchestrator._step_gate",
        new_callable=AsyncMock,
    ), patch(
        "app.services.archive_orchestrator.ArchiveOrchestrator._step_wp_storage",
        new_callable=AsyncMock,
    ), patch(
        "app.services.archive_orchestrator.ArchiveOrchestrator._persist_integrity_hashes",
        new_callable=AsyncMock,
    ), patch(
        "app.services.archive_orchestrator.ArchiveOrchestrator._set_project_retention",
        new_callable=AsyncMock,
    ), patch(
        "app.services.archive_orchestrator.ArchiveOrchestrator._notify_project_members",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            f"/api/projects/{project_id}/archive/orchestrate",
            json={"scope": "final"},
        )

    # 端点可达（非 404/405）
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["project_id"] == str(project_id)
    assert body["status"] == "succeeded"


# ── 场景 3：幂等返回同 job_id ──────────────────────────────────────


@pytest.mark.asyncio
async def test_idempotent_returns_same_job_id(client: AsyncClient, db_session: AsyncSession):
    """24h 内已有 succeeded 的 ArchiveJob，再次调用 orchestrate 应返回同一 job_id。"""
    from app.models.core import Project

    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name="幂等测试项目",
        client_name="测试客户",
        status="execution",
    )
    db_session.add(project)
    await db_session.flush()

    # 手动插入一条 24h 内 succeeded 的 ArchiveJob
    existing_job_id = uuid.uuid4()
    existing_job = ArchiveJob(
        id=existing_job_id,
        project_id=project_id,
        scope="final",
        status="succeeded",
        push_to_cloud=False,
        purge_local=False,
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        finished_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(existing_job)
    await db_session.flush()
    await db_session.commit()

    # 再次调用 orchestrate — 应幂等返回已有 job
    resp = await client.post(
        f"/api/projects/{project_id}/archive/orchestrate",
        json={"scope": "final"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(existing_job_id), (
        f"Expected idempotent return of existing job {existing_job_id}, "
        f"got new job {body['id']}"
    )
    assert body["status"] == "succeeded"


# ── 场景 4：编排要求二次密码确认（夹具里视为已确认，这里撤掉该替身验证门本身仍在） ──


@pytest.mark.asyncio
async def test_orchestrate_requires_confirmation_token(client: AsyncClient, db_session: AsyncSession):
    """不带 X-Confirmation-Token ⇒ 403，且不创建归档作业。"""
    from sqlalchemy import func, select

    from app.core.redis import get_redis
    from app.routers.password_confirm import require_confirmation_token

    app = client.app_under_test  # type: ignore[attr-defined]
    app.dependency_overrides.pop(require_confirmation_token)

    async def _redis_available():
        return object()  # 缺令牌时只判「Redis 可用」，不读写

    app.dependency_overrides[get_redis] = _redis_available
    project_id = uuid.uuid4()
    resp = await client.post(f"/api/projects/{project_id}/archive/orchestrate", json={"scope": "final"})

    assert resp.status_code == 403
    assert resp.json()["detail"] == "X-Confirmation-Token header required"
    jobs = (await db_session.execute(
        select(func.count()).select_from(ArchiveJob).where(ArchiveJob.project_id == project_id)
    )).scalar_one()
    assert jobs == 0
