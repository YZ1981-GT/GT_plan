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


# ---------------------------------------------------------------------------
# Task 16: 归档完整性记录 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrate_success_persists_manifest_hash(db_session: AsyncSession):
    """Task 16: orchestrate 成功后 manifest_hash 非空（各章节 SHA-256 拼接再哈希）。"""
    fake_section_content = [
        ("00-项目封面.pdf", b"fake cover pdf content"),
        ("01-签字流水.pdf", b"fake signature ledger content"),
        ("99-审计日志.jsonl", None),  # None 应被跳过
    ]

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
            "app.services.archive_section_registry.generate_all",
            new_callable=AsyncMock,
            return_value=fake_section_content,
        ),
        patch(
            "app.services.export_integrity_service.export_integrity_service.persist_checks",
            new_callable=AsyncMock,
        ) as mock_persist,
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
    assert job.manifest_hash is not None
    assert len(job.manifest_hash) == 64  # SHA-256 hex digest

    # persist_checks 应被调用一次
    mock_persist.assert_called_once()
    call_args = mock_persist.call_args
    # export_id 应为 job.id 的字符串
    assert call_args.kwargs["export_id"] == str(job.id)
    # file_checks 应包含 2 个条目（None 被跳过）
    assert len(call_args.kwargs["file_checks"]) == 2
    assert call_args.kwargs["file_checks"][0]["file_path"] == "00-项目封面.pdf"
    assert call_args.kwargs["file_checks"][1]["file_path"] == "01-签字流水.pdf"


@pytest.mark.asyncio
async def test_orchestrate_integrity_failure_does_not_block(db_session: AsyncSession):
    """Task 16: persist_hash_checks 失败不阻断归档（status 仍为 succeeded）。"""
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
            "app.services.archive_section_registry.generate_all",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Section generation failed"),
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

    # 归档仍然成功（integrity 失败不阻断）
    assert job.status == "succeeded"
    # manifest_hash 为 None（因为 integrity 步骤失败了）
    assert job.manifest_hash is None


@pytest.mark.asyncio
async def test_retry_success_persists_manifest_hash(db_session: AsyncSession):
    """Task 16: retry 成功后也调 persist_hash_checks，manifest_hash 非空。"""
    # 先创建一个失败的 job
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
    assert job.manifest_hash is None

    # 重试成功
    fake_section_content = [
        ("00-项目封面.pdf", b"cover content"),
        ("01-签字流水.pdf", b"ledger content"),
    ]

    with (
        patch(
            "app.services.wp_storage_service.WpStorageService.archive_project",
            new_callable=AsyncMock,
            return_value={"archived": True},
        ),
        patch(
            "app.services.archive_section_registry.generate_all",
            new_callable=AsyncMock,
            return_value=fake_section_content,
        ),
        patch(
            "app.services.export_integrity_service.export_integrity_service.persist_checks",
            new_callable=AsyncMock,
        ) as mock_persist,
    ):
        orchestrator2 = ArchiveOrchestrator(db_session)
        retried_job = await orchestrator2.retry(
            job_id=job.id,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert retried_job.status == "succeeded"
    assert retried_job.manifest_hash is not None
    assert len(retried_job.manifest_hash) == 64
    mock_persist.assert_called_once()


@pytest.mark.asyncio
async def test_manifest_hash_deterministic(db_session: AsyncSession):
    """Task 16: 相同内容产生相同 manifest_hash（确定性）。"""
    import hashlib

    content_a = b"cover pdf bytes"
    content_b = b"ledger pdf bytes"

    fake_sections = [
        ("00-项目封面.pdf", content_a),
        ("01-签字流水.pdf", content_b),
    ]

    # 手动计算期望的 manifest_hash
    hash_a = hashlib.sha256(content_a).hexdigest()
    hash_b = hashlib.sha256(content_b).hexdigest()
    expected_manifest = hashlib.sha256((hash_a + hash_b).encode("utf-8")).hexdigest()

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
            "app.services.archive_section_registry.generate_all",
            new_callable=AsyncMock,
            return_value=fake_sections,
        ),
        patch(
            "app.services.export_integrity_service.export_integrity_service.persist_checks",
            new_callable=AsyncMock,
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

    assert job.manifest_hash == expected_manifest


# ---------------------------------------------------------------------------
# Batch 2-1: section_progress tests (R1 Bug Fix 5 retrospective)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrate_writes_section_progress_on_each_step(db_session: AsyncSession):
    """Fix 5: orchestrate 成功后 section_progress 每个 section 都有 succeeded/finished_at。"""
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
        patch(
            "app.services.data_lifecycle_service.DataLifecycleService.archive_project_data",
            new_callable=AsyncMock,
            return_value={"archived": True},
        ),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        job = await orchestrator.orchestrate(
            project_id=FAKE_PROJECT_ID,
            scope="final",
            push_to_cloud=True,
            purge_local=True,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    assert job.status == "succeeded"
    assert job.section_progress is not None
    # 应包含 4 个 section
    for section in ["gate", "wp_storage", "push_to_cloud", "purge_local"]:
        assert section in job.section_progress, f"section_progress missing {section}"
        sp = job.section_progress[section]
        assert sp.get("status") == "succeeded"
        assert sp.get("finished_at") is not None


@pytest.mark.asyncio
async def test_retry_skips_succeeded_sections_via_section_progress(db_session: AsyncSession):
    """Fix 5: retry 对已 succeeded 的 section 不再重跑（以 section_progress 为权威）。"""
    # 构造一个 failed job：section_progress 显示 gate 已成功，wp_storage 未 succeeded
    now_iso = datetime.now(timezone.utc).isoformat()
    job = ArchiveJob(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        scope="final",
        status="failed",
        push_to_cloud=False,
        purge_local=False,
        last_succeeded_section="gate",
        failed_section="wp_storage",
        failed_reason="old failure",
        section_progress={
            "gate": {"status": "succeeded", "finished_at": now_iso},
        },
        started_at=datetime.now(timezone.utc),
        initiated_by=FAKE_USER_ID,
    )
    db_session.add(job)
    await db_session.flush()
    await db_session.commit()

    # retry：gate 若被错误重跑则 mock_gate 会被调用
    mock_gate = _mock_gate_allow()
    with (
        patch(
            "app.services.gate_engine.gate_engine.evaluate",
            new=mock_gate,
        ),
        patch(
            "app.services.wp_storage_service.WpStorageService.archive_project",
            new_callable=AsyncMock,
            return_value={"archived": True},
        ),
        patch(
            "app.services.archive_orchestrator.ArchiveOrchestrator._persist_integrity_hashes",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.archive_orchestrator.ArchiveOrchestrator._set_project_retention",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.archive_orchestrator.ArchiveOrchestrator._notify_project_members",
            new_callable=AsyncMock,
        ),
    ):
        orchestrator = ArchiveOrchestrator(db_session)
        retried_job = await orchestrator.retry(
            job_id=job.id,
            initiated_by=FAKE_USER_ID,
        )
        await db_session.commit()

    # 断言 gate step 的 mock 未被调用（已跳过）
    assert mock_gate.call_count == 0, (
        f"gate step should have been skipped but was called {mock_gate.call_count} times"
    )
    assert retried_job.status == "succeeded"
    assert retried_job.section_progress.get("wp_storage", {}).get("status") == "succeeded"


@pytest.mark.asyncio
async def test_section_progress_and_last_succeeded_consistent(db_session: AsyncSession):
    """Fix 5: orchestrate 成功后 section_progress 和 last_succeeded_section 都更新，一致。"""
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
    # section_progress 包含所有执行的 step
    assert set(job.section_progress.keys()) == {"gate", "wp_storage"}
    # last_succeeded_section 等于最后一个 section
    assert job.last_succeeded_section == "wp_storage"
    # 最后一个 section 在 section_progress 中也为 succeeded
    assert job.section_progress[job.last_succeeded_section]["status"] == "succeeded"
