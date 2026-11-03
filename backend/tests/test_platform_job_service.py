"""平台通用耐久任务的幂等、租约与 attempt 围栏。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, User  # noqa: F401 - 注册 FK 目标
from app.models.platform_job_models import PlatformJob, PlatformJobAttempt
from app.services import platform_job_service as jobs

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[PlatformJob.__table__, PlatformJobAttempt.__table__],
            )
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


async def _create(factory, *, key="job-1", payload=None, max_attempts=3):
    async with factory() as db:
        job, created = await jobs.create_or_get_job(
            db,
            operation="test_operation",
            project_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            idempotency_key=key,
            payload_ref=payload or {"value": 1},
            progress_total=10,
            max_attempts=max_attempts,
        )
        await db.commit()
        return job, created


@pytest.mark.asyncio
async def test_idempotent_create_replays_same_job_and_rejects_payload_drift(factory):
    project_id, actor_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as db:
        first, created = await jobs.create_or_get_job(
            db,
            operation="bulk_import",
            project_id=project_id,
            actor_id=actor_id,
            idempotency_key="same-key",
            payload_ref={"path": "one.zip"},
        )
        await db.commit()
        replay, replay_created = await jobs.create_or_get_job(
            db,
            operation="bulk_import",
            project_id=project_id,
            actor_id=actor_id,
            idempotency_key="same-key",
            payload_ref={"path": "one.zip"},
        )
        assert created is True and replay_created is False
        assert replay.id == first.id
        with pytest.raises(jobs.PlatformJobConflict):
            await jobs.create_or_get_job(
                db,
                operation="bulk_import",
                project_id=project_id,
                actor_id=actor_id,
                idempotency_key="same-key",
                payload_ref={"path": "different.zip"},
            )


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed_and_old_attempt_cannot_finish(factory):
    await _create(factory)
    async with factory() as db:
        first = await jobs.claim_next(db, worker_id="worker-a", lease_seconds=30)
        assert first is not None
        await db.commit()

    async with factory() as db:
        await db.execute(
            sa.update(PlatformJob)
            .where(PlatformJob.id == first.job_id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await db.commit()

    async with factory() as db:
        second = await jobs.claim_next(db, worker_id="worker-b", lease_seconds=30)
        assert second is not None
        assert second.attempt == 2
        assert second.lease_token != first.lease_token
        await db.commit()

    async with factory() as db:
        assert await jobs.finish_success(db, first, result_ref={"winner": "old"}) is False
        await db.rollback()
        assert await jobs.finish_success(db, second, result_ref={"winner": "new"}) is True
        await db.commit()

    async with factory() as db:
        job = await db.get(PlatformJob, first.job_id)
        attempts = list((await db.execute(
            sa.select(PlatformJobAttempt).order_by(PlatformJobAttempt.attempt_no)
        )).scalars())
        assert job.status == "succeeded"
        assert job.result_ref == {"winner": "new"}
        assert [attempt.status for attempt in attempts] == ["lost_lease", "succeeded"]


@pytest.mark.asyncio
async def test_progress_is_monotonic_and_fenced(factory):
    await _create(factory)
    async with factory() as db:
        claim = await jobs.claim_next(db, worker_id="worker")
        await db.commit()
    assert claim is not None

    async with factory() as db:
        assert await jobs.update_progress(db, claim, current=7, message="七")
        assert await jobs.update_progress(db, claim, current=3, message="迟到")
        await db.commit()
    async with factory() as db:
        job = await db.get(PlatformJob, claim.job_id)
        assert job.progress_current == 7
        assert job.progress_message == "七"


@pytest.mark.asyncio
async def test_retryable_failure_requeues_then_final_attempt_fails(factory):
    await _create(factory, max_attempts=2)
    async with factory() as db:
        first = await jobs.claim_next(db, worker_id="worker-a")
        await db.commit()
    assert first is not None

    async with factory() as db:
        assert await jobs.finish_failure(
            db,
            first,
            error_code="temporary",
            error_message="稍后重试",
            retryable=True,
        )
        # 测试直接把退避时间推进到已到期。
        await db.execute(
            sa.update(PlatformJob)
            .where(PlatformJob.id == first.job_id)
            .values(next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await db.commit()

    async with factory() as db:
        second = await jobs.claim_next(db, worker_id="worker-b")
        assert second is not None and second.attempt == 2
        assert await jobs.finish_failure(
            db,
            second,
            error_code="permanent",
            error_message="最终失败",
            retryable=True,
        )
        await db.commit()
    async with factory() as db:
        job = await db.get(PlatformJob, first.job_id)
        assert job.status == "failed"
        assert job.error_code == "permanent"


@pytest.mark.asyncio
async def test_cancel_queued_is_terminal_and_running_invalidates_renewal(factory):
    queued, _ = await _create(factory, key="queued")
    async with factory() as db:
        snapshot = await jobs.request_cancel(
            db,
            project_id=queued.project_id,
            actor_id=queued.actor_id,
            job_id=queued.id,
        )
        await db.commit()
        assert snapshot["status"] == "cancelled"

    running, _ = await _create(factory, key="running")
    async with factory() as db:
        claim = await jobs.claim_next(db, worker_id="worker")
        # queued 创建在前但已终态，故本次认领 running。
        assert claim is not None and claim.job_id == running.id
        await db.commit()
    async with factory() as db:
        await jobs.request_cancel(
            db,
            project_id=running.project_id,
            actor_id=running.actor_id,
            job_id=running.id,
        )
        await db.commit()
    async with factory() as db:
        assert await jobs.renew_lease(db, claim) is False
        assert await jobs.finish_success(db, claim, result_ref={}) is False
        assert await jobs.finish_cancelled(db, claim) is True
        await db.commit()


@pytest.mark.asyncio
async def test_active_capacity_counts_jobs_across_workers(factory):
    project_id, actor_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as db:
        first, _ = await jobs.create_or_get_job(
            db,
            operation="bulk_tab_import",
            project_id=project_id,
            actor_id=actor_id,
            idempotency_key="capacity-1",
            payload_ref={"path": "one"},
            reserved_bytes=100,
        )
        await jobs.enforce_active_capacity(
            db,
            first,
            global_limit=1,
            user_limit=1,
            project_limit=1,
            reserved_bytes_limit=100,
        )
        await db.commit()

    async with factory() as db:
        second, _ = await jobs.create_or_get_job(
            db,
            operation="bulk_tab_import",
            project_id=project_id,
            actor_id=actor_id,
            idempotency_key="capacity-2",
            payload_ref={"path": "two"},
            reserved_bytes=100,
        )
        with pytest.raises(jobs.PlatformJobCapacityExceeded):
            await jobs.enforce_active_capacity(
                db,
                second,
                global_limit=1,
                user_limit=1,
                project_limit=1,
                reserved_bytes_limit=100,
            )
        await db.rollback()
