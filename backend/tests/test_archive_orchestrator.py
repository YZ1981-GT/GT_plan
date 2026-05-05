"""R1 Task 13 集成测试：ArchiveOrchestrator 服务

覆盖需求 5 验收标准：
1. happy path：所有步骤成功 → status=succeeded
2. gate 失败 → status=failed, failed_section='gate'
3. wp_storage 失败 → failed_section='wp_storage'
4. retry 从 last_succeeded_section 下一步开始
5. get_job 返回正确字段

Validates: Requirements 5 (refinement-round1-review-closure)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.archive_models  # noqa: F401
from app.models.base import Base
from app.models.archive_models import ArchiveJob
from app.services.archive_orchestrator import ArchiveOrchestrator

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers: mock patches for the archive steps
# ---------------------------------------------------------------------------


def _mock_gate_allow():
    """Mock gate_engine.evaluate to return allow."""
    from dataclasses import dataclass, field

    @dataclass
    class FakeResult:
        decision: str = "allow"
        hit_rules: list = field(default_factory=list)
        trace_id: str = "test-trace"

    mock = AsyncMock(return_value=FakeResult())
    return mock


def _mock_gate_block():
    """Mock gate_engine.evaluate to return block."""
    from dataclasses import dataclass, field

    @dataclass
    class FakeHit:
        rule_code: str = "TEST_RULE"
        error_code: str = "TEST_ERROR"
        severity: str = "blocking"
        message: str = "Test blocking reason"
        location: dict = field(default_factory=dict)
        suggested_action: str = ""

    @dataclass
    class FakeResult:
        decision: str = "block"
        hit_rules: list = field(default_factory=lambda: [FakeHit()])
        trace_id: str = "test-trace"

    mock = AsyncMock(return_value=FakeResult())
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrate_happy_path(db_session: AsyncSession):
    """所有步骤成功 → status=succeeded, last_succeeded_section 为最后一步。"""
    with (
        patch(
            "app.services.gate_engine.gate_engine.evaluate",
            new=_mock_gate_allow(),
        ),
        patch(
            "app.services.wp_storage_service.WpStorageService.archive_project",
            new_callable=AsyncMock,
            return_value={"archived": True},
        ),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        job = await orchestrator.orchestrate(
            project_id=FAKE_PROJECT_ID,
            scope="final",
            push_to_cloud=False,
            purge_local=False,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert job.status == "succeeded"
    assert job.failed_section is None
    assert job.failed_reason is None
    assert job.last_succeeded_section == "wp_storage"
    assert job.finished_at is not None
    assert job.started_at is not None


@pytest.mark.asyncio
async def test_orchestrate_with_push_to_cloud(db_session: AsyncSession):
    """push_to_cloud=True 时执行 push_to_cloud 步骤。"""
    with (
        patch(
            "app.services.gate_engine.gate_engine.evaluate",
            new=_mock_gate_allow(),
        ),
        patch(
            "app.services.wp_storage_service.WpStorageService.archive_project",
            new_callable=AsyncMock,
            return_value={"archived": True},
        ),
        patch(
            "app.services.private_storage_service.ProjectArchiveService.archive_project",
            new_callable=AsyncMock,
            return_value={"pushed": True},
        ),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        job = await orchestrator.orchestrate(
            project_id=FAKE_PROJECT_ID,
            scope="final",
            push_to_cloud=True,
            purge_local=False,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert job.status == "succeeded"
    assert job.last_succeeded_section == "push_to_cloud"


@pytest.mark.asyncio
async def test_orchestrate_gate_failure(db_session: AsyncSession):
    """gate 阻断 → status=failed, failed_section='gate'。"""
    with patch(
        "app.services.gate_engine.gate_engine.evaluate",
        new=_mock_gate_block(),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        job = await orchestrator.orchestrate(
            project_id=FAKE_PROJECT_ID,
            scope="final",
            push_to_cloud=False,
            purge_local=False,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert job.status == "failed"
    assert job.failed_section == "gate"
    assert "blocked" in job.failed_reason.lower()
    assert job.finished_at is not None


@pytest.mark.asyncio
async def test_orchestrate_wp_storage_failure(db_session: AsyncSession):
    """wp_storage 步骤失败 → failed_section='wp_storage'。"""
    with (
        patch(
            "app.services.gate_engine.gate_engine.evaluate",
            new=_mock_gate_allow(),
        ),
        patch(
            "app.services.wp_storage_service.WpStorageService.archive_project",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Storage write error"),
        ),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        job = await orchestrator.orchestrate(
            project_id=FAKE_PROJECT_ID,
            scope="final",
            push_to_cloud=False,
            purge_local=False,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert job.status == "failed"
    assert job.failed_section == "wp_storage"
    assert "Storage write error" in job.failed_reason
    assert job.last_succeeded_section == "gate"


@pytest.mark.asyncio
async def test_retry_from_last_succeeded_section(db_session: AsyncSession):
    """retry 从 last_succeeded_section 下一步开始。"""
    # 先创建一个失败的 job（gate 成功，wp_storage 失败）
    with (
        patch(
            "app.services.gate_engine.gate_engine.evaluate",
            new=_mock_gate_allow(),
        ),
        patch(
            "app.services.wp_storage_service.WpStorageService.archive_project",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Temporary failure"),
        ),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        job = await orchestrator.orchestrate(
            project_id=FAKE_PROJECT_ID,
            scope="final",
            push_to_cloud=False,
            purge_local=False,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert job.status == "failed"
    assert job.last_succeeded_section == "gate"

    # 重试：wp_storage 这次成功
    with patch(
        "app.services.wp_storage_service.WpStorageService.archive_project",
        new_callable=AsyncMock,
        return_value={"archived": True},
    ):
        orchestrator2 = ArchiveOrchestrator(db_session)
        retried_job = await orchestrator2.retry(
            job_id=job.id,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert retried_job.status == "succeeded"
    assert retried_job.last_succeeded_section == "wp_storage"
    assert retried_job.failed_section is None
    assert retried_job.failed_reason is None


@pytest.mark.asyncio
async def test_retry_invalid_status(db_session: AsyncSession):
    """retry 对非 failed 状态的 job 应抛出 ValueError。"""
    with (
        patch(
            "app.services.gate_engine.gate_engine.evaluate",
            new=_mock_gate_allow(),
        ),
        patch(
            "app.services.wp_storage_service.WpStorageService.archive_project",
            new_callable=AsyncMock,
            return_value={"archived": True},
        ),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        job = await orchestrator.orchestrate(
            project_id=FAKE_PROJECT_ID,
            scope="final",
            push_to_cloud=False,
            purge_local=False,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert job.status == "succeeded"

    orchestrator2 = ArchiveOrchestrator(db_session)
    with pytest.raises(ValueError, match="cannot retry"):
        await orchestrator2.retry(job_id=job.id, initiated_by=FAKE_USER_ID)


@pytest.mark.asyncio
async def test_get_job(db_session: AsyncSession):
    """get_job 返回正确字段。"""
    with (
        patch(
            "app.services.gate_engine.gate_engine.evaluate",
            new=_mock_gate_allow(),
        ),
        patch(
            "app.services.wp_storage_service.WpStorageService.archive_project",
            new_callable=AsyncMock,
            return_value={"archived": True},
        ),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        job = await orchestrator.orchestrate(
            project_id=FAKE_PROJECT_ID,
            scope="final",
            push_to_cloud=False,
            purge_local=False,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    orchestrator2 = ArchiveOrchestrator(db_session)
    result = await orchestrator2.get_job(job.id)

    assert result is not None
    assert result["id"] == str(job.id)
    assert result["project_id"] == str(FAKE_PROJECT_ID)
    assert result["scope"] == "final"
    assert result["status"] == "succeeded"
    assert result["push_to_cloud"] is False
    assert result["purge_local"] is False
    assert result["last_succeeded_section"] == "wp_storage"
    assert result["failed_section"] is None
    assert result["failed_reason"] is None
    assert result["started_at"] is not None
    assert result["finished_at"] is not None
    assert result["initiated_by"] == str(FAKE_USER_ID)


@pytest.mark.asyncio
async def test_get_job_not_found(db_session: AsyncSession):
    """get_job 对不存在的 job 返回 None。"""
    orchestrator = ArchiveOrchestrator(db_session)
    result = await orchestrator.get_job(uuid.uuid4())
    assert result is None
