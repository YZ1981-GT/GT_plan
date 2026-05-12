"""F14 / Sprint 4.3 — `ImportJobRunner.resume_from_checkpoint` 单元测试。

覆盖路由表核心路径：
1. failed + parse_write_streaming_done + staged dataset 存在 → resume 成功
2. failed + activate_dataset_done + staged dataset 存在 → resume 成功
3. failed + staged dataset 已清理 → full_restart_required
4. status=completed → invalid_status（不允许恢复）
5. 未知 phase + staged dataset 存在 → full_rerun

Fixture 采用 test_cancel_cleanup_guarantee.py 同款 SQLite in-memory + async_session patch。
同时 patch ``ImportJobRunner.enqueue`` 为 no-op 避免触发真实后台任务。
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容：PG JSONB/UUID 降级
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.dataset_models import (
    DatasetStatus,
    ImportJob,
    JobStatus,
    LedgerDataset,
)
from app.services.import_job_runner import ImportJobRunner
from app.services.ledger_import.phases import (
    PHASE_ACTIVATE_DATASET_DONE,
    PHASE_ACTIVATION_GATE_DONE,
    PHASE_PARSE_WRITE_STREAMING_DONE,
)


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine_and_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    yield engine, session_factory
    await engine.dispose()


def _patch_env(session_factory):
    """同时 patch runner 模块内的 async_session + ImportJobRunner.enqueue no-op。

    `import_job_runner.py` 在模块顶部 `from app.core.database import async_session`，
    所以必须 patch runner 模块下的本地 symbol（`app.services.import_job_runner.async_session`）。
    直接 patch `app.core.database.async_session` 对已 import 的 reference 无效。
    """
    async_session_patch = patch(
        "app.services.import_job_runner.async_session", session_factory
    )
    enqueue_patch = patch.object(ImportJobRunner, "enqueue", lambda job_id: None)
    return async_session_patch, enqueue_patch


async def _create_job(
    session_factory,
    *,
    status: JobStatus,
    current_phase: str | None,
    with_staged_dataset: bool = True,
    project_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """建一个 ImportJob（指定 status + current_phase），可选挂一个 staged LedgerDataset。"""
    project_id = project_id or uuid.uuid4()
    job_id = uuid.uuid4()
    year = 2024
    dataset_id: uuid.UUID | None = None

    async with session_factory() as db:
        job = ImportJob(
            id=job_id,
            project_id=project_id,
            year=year,
            status=status,
            current_phase=current_phase,
            error_message="simulated failure" if status == JobStatus.failed else None,
        )
        db.add(job)

        if with_staged_dataset:
            dataset_id = uuid.uuid4()
            ds = LedgerDataset(
                id=dataset_id,
                project_id=project_id,
                year=year,
                status=DatasetStatus.staged,
                source_type="ledger_import_v2",
                job_id=job_id,
            )
            db.add(ds)

        await db.commit()

    return job_id, dataset_id


# ---------------------------------------------------------------------------
# Case 1: failed + parse_write_streaming_done + staged → resume_from_activation_gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_from_parse_write_streaming_done(engine_and_session):
    _, session_factory = engine_and_session
    job_id, dataset_id = await _create_job(
        session_factory,
        status=JobStatus.failed,
        current_phase=PHASE_PARSE_WRITE_STREAMING_DONE,
        with_staged_dataset=True,
    )

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is True
    assert result["from_phase"] == PHASE_PARSE_WRITE_STREAMING_DONE
    assert result["action"] == "resume_from_activation_gate"
    assert str(dataset_id) in result["message"]

    # job 应已重置为 queued，error_message 清空
    async with session_factory() as db:
        job = (
            await db.execute(sa.select(ImportJob).where(ImportJob.id == job_id))
        ).scalar_one()
        assert job.status == JobStatus.queued
        assert job.progress_pct == 0
        assert job.error_message is None
        assert job.current_phase == JobStatus.queued.value


# ---------------------------------------------------------------------------
# Case 2: failed + activation_gate_done + staged → resume_from_activate_dataset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_from_activation_gate_done(engine_and_session):
    _, session_factory = engine_and_session
    job_id, _dataset_id = await _create_job(
        session_factory,
        status=JobStatus.failed,
        current_phase=PHASE_ACTIVATION_GATE_DONE,
        with_staged_dataset=True,
    )

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is True
    assert result["action"] == "resume_from_activate_dataset"
    assert result["from_phase"] == PHASE_ACTIVATION_GATE_DONE


# ---------------------------------------------------------------------------
# Case 3: failed + activate_dataset_done + staged → resume_from_rebuild_aux_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_from_activate_dataset_done(engine_and_session):
    _, session_factory = engine_and_session
    job_id, _ = await _create_job(
        session_factory,
        status=JobStatus.failed,
        current_phase=PHASE_ACTIVATE_DATASET_DONE,
        with_staged_dataset=True,
    )

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is True
    assert result["action"] == "resume_from_rebuild_aux_summary"


# ---------------------------------------------------------------------------
# Case 4: staged dataset 已清理 → full_restart_required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_requires_full_restart_when_staged_missing(engine_and_session):
    _, session_factory = engine_and_session
    job_id, _ = await _create_job(
        session_factory,
        status=JobStatus.failed,
        current_phase=PHASE_PARSE_WRITE_STREAMING_DONE,
        with_staged_dataset=False,  # 无 staged
    )

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is False
    assert result["action"] == "full_restart_required"
    assert result["from_phase"] == PHASE_PARSE_WRITE_STREAMING_DONE

    # job 状态不应被动
    async with session_factory() as db:
        job = (
            await db.execute(sa.select(ImportJob).where(ImportJob.id == job_id))
        ).scalar_one()
        assert job.status == JobStatus.failed  # 没被改动


# ---------------------------------------------------------------------------
# Case 5: 非 failed/timed_out 状态 → invalid_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_invalid_status_completed(engine_and_session):
    _, session_factory = engine_and_session
    job_id, _ = await _create_job(
        session_factory,
        status=JobStatus.completed,
        current_phase=PHASE_ACTIVATE_DATASET_DONE,
        with_staged_dataset=True,
    )

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is False
    assert result["action"] == "invalid_status"
    assert "completed" in result["message"]


@pytest.mark.asyncio
async def test_resume_invalid_status_running(engine_and_session):
    _, session_factory = engine_and_session
    job_id, _ = await _create_job(
        session_factory,
        status=JobStatus.running,
        current_phase="writing",
        with_staged_dataset=True,
    )

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is False
    assert result["action"] == "invalid_status"


# ---------------------------------------------------------------------------
# Case 6: 未知 phase + staged 存在 → full_rerun（staged 保留）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_unknown_phase_full_rerun(engine_and_session):
    _, session_factory = engine_and_session
    job_id, _ = await _create_job(
        session_factory,
        status=JobStatus.failed,
        current_phase="writing",  # 不在 RESUME_FROM_PHASE 表中
        with_staged_dataset=True,
    )

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is True
    assert result["action"] == "full_rerun"
    assert result["from_phase"] == "writing"

    # job 应已重置为 queued
    async with session_factory() as db:
        job = (
            await db.execute(sa.select(ImportJob).where(ImportJob.id == job_id))
        ).scalar_one()
        assert job.status == JobStatus.queued
        assert job.error_message is None


# ---------------------------------------------------------------------------
# Case 7: 不存在的 job_id → not_found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_job_not_found(engine_and_session):
    _, session_factory = engine_and_session
    fake_job_id = uuid.uuid4()

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(fake_job_id)

    assert result["resumed"] is False
    assert result["action"] == "not_found"
    assert result["job_id"] == str(fake_job_id)


# ---------------------------------------------------------------------------
# Case 8: timed_out 也允许恢复（与 failed 同等处理）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_from_timed_out_job(engine_and_session):
    _, session_factory = engine_and_session
    job_id, _ = await _create_job(
        session_factory,
        status=JobStatus.timed_out,
        current_phase=PHASE_PARSE_WRITE_STREAMING_DONE,
        with_staged_dataset=True,
    )

    as_patch, enq_patch = _patch_env(session_factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is True
    assert result["action"] == "resume_from_activation_gate"
