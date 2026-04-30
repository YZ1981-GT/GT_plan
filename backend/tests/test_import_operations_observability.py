import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_schemas import EventType
from app.models.audit_platform_models import ImportBatch, ImportStatus
from app.models.core import Log
from app.core.config import settings
from app.models.dataset_models import (
    ActivationRecord,
    ActivationType,
    ImportEventConsumption,
    ImportEventOutbox,
    ImportJob,
    JobStatus,
    OutboxStatus,
)
from app.services.import_event_reliability_service import ImportEventReliabilityService
from app.services.import_event_consumption_service import ImportEventConsumptionService
from app.services.import_event_outbox_service import ImportEventOutboxService
from app.services.import_job_service import ImportJobService
from app.services.import_queue_service import ImportQueueService
from app.services.import_ops_audit_service import ImportOpsAuditService
from app.services.import_slo_service import ImportSLOService


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_import_slo_summary_and_alerts(db_session: AsyncSession):
    project_id = uuid.uuid4()
    other_project_id = uuid.uuid4()
    now = datetime.utcnow()
    db_session.add_all([
        ImportJob(
            project_id=project_id,
            year=2025,
            status=JobStatus.completed,
            started_at=now - timedelta(seconds=20),
            completed_at=now,
        ),
        ImportJob(
            project_id=project_id,
            year=2025,
            status=JobStatus.failed,
            started_at=now - timedelta(seconds=10),
            completed_at=now,
            error_message="boom",
        ),
    ])
    await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=other_project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    await db_session.commit()

    summary = await ImportSLOService.get_summary(db_session, project_id=project_id, year=2025)

    assert summary["total_jobs"] == 2
    assert summary["success_rate"] == 0.5
    assert summary["failure_rate"] == 0.5
    assert summary["duration_seconds"]["p95"] is not None
    assert "enterprise_kpis" in summary
    assert "queue_delay_seconds" in summary["enterprise_kpis"]
    assert "end_to_end_seconds" in summary["enterprise_kpis"]
    assert "throughput_jobs_per_hour" in summary["enterprise_kpis"]
    assert "outbox_backlog_count" in summary["enterprise_kpis"]
    assert summary["enterprise_kpis"]["outbox_backlog_count"] == 1
    assert any(alert["code"] == "IMPORT_FAILURE_RATE_HIGH" for alert in ImportSLOService.build_alerts(summary))


@pytest.mark.asyncio
async def test_import_runner_health_flags_queued_jobs_without_in_process_runner(monkeypatch, db_session: AsyncSession):
    project_id = uuid.uuid4()
    monkeypatch.setattr(settings, "LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED", False)
    db_session.add(
        ImportJob(
            project_id=project_id,
            year=2025,
            status=JobStatus.queued,
            created_at=datetime.utcnow() - timedelta(seconds=30),
        )
    )
    await db_session.commit()

    report = await ImportSLOService.get_runner_health(db_session)

    assert report["status"] == "degraded"
    assert report["runner_mode"] == "external_worker_required"
    assert report["queued_count"] == 1
    assert any(alert["code"] == "IMPORT_RUNNER_EXTERNAL_REQUIRED" for alert in report["alerts"])


@pytest.mark.asyncio
async def test_import_runner_health_flags_stale_running_job(db_session: AsyncSession):
    project_id = uuid.uuid4()
    db_session.add(
        ImportJob(
            project_id=project_id,
            year=2025,
            status=JobStatus.writing,
            started_at=datetime.utcnow() - timedelta(minutes=30),
            heartbeat_at=datetime.utcnow() - timedelta(minutes=30),
        )
    )
    await db_session.commit()

    report = await ImportSLOService.get_runner_health(db_session)

    assert report["status"] == "degraded"
    assert report["stale_running_count"] == 1
    assert any(alert["code"] == "IMPORT_RUNNING_HEARTBEAT_STALE" for alert in report["alerts"])


@pytest.mark.asyncio
async def test_import_event_health_reports_activation_evidence(db_session: AsyncSession):
    project_id = uuid.uuid4()
    db_session.add(
        ActivationRecord(
            project_id=project_id,
            year=2025,
            dataset_id=uuid.uuid4(),
            action=ActivationType.activate,
        )
    )
    await db_session.commit()

    report = await ImportEventReliabilityService.get_health(db_session, project_id=project_id, year=2025)

    assert report["recent_activation_records"] == 1
    assert report["expected_event_evidence"][0]["expected_event"] == "ledger.dataset_activated"
    assert "replay_report" in report
    assert "outbox_summary" in report


@pytest.mark.asyncio
async def test_import_event_outbox_replay_marks_published(monkeypatch, db_session: AsyncSession):
    project_id = uuid.uuid4()
    published = []

    async def _fake_publish(payload):
        published.append(payload)

    monkeypatch.setattr("app.services.import_event_outbox_service.event_bus.publish_immediate", _fake_publish)
    outbox = await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    await db_session.commit()

    report = await ImportEventOutboxService.replay_pending(db_session)
    await db_session.commit()

    refreshed = await ImportEventOutboxService.get(db_session, outbox.id)
    assert report["published_count"] == 1
    assert refreshed is not None
    assert refreshed.status == OutboxStatus.published
    assert published[0].event_type == EventType.LEDGER_DATASET_ACTIVATED
    assert published[0].extra.get("__event_id") == str(outbox.id)


@pytest.mark.asyncio
async def test_import_event_outbox_replay_respects_project_scope(monkeypatch, db_session: AsyncSession):
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    published: list = []

    async def _fake_publish(payload):
        published.append(payload)

    monkeypatch.setattr("app.services.import_event_outbox_service.event_bus.publish_immediate", _fake_publish)
    outbox_a = await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_a,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    outbox_b = await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_b,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    await db_session.commit()

    report = await ImportEventOutboxService.replay_pending(db_session, project_id=project_a)
    await db_session.commit()

    refreshed_a = await ImportEventOutboxService.get(db_session, outbox_a.id)
    refreshed_b = await ImportEventOutboxService.get(db_session, outbox_b.id)
    assert report["published_count"] == 1
    assert refreshed_a is not None and refreshed_a.status == OutboxStatus.published
    assert refreshed_b is not None and refreshed_b.status == OutboxStatus.pending
    assert len(published) == 1
    assert published[0].project_id == project_a


@pytest.mark.asyncio
async def test_import_event_health_degrades_on_outbox_backlog(db_session: AsyncSession):
    project_id = uuid.uuid4()
    await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    await db_session.commit()

    report = await ImportEventReliabilityService.get_health(db_session, project_id=project_id, year=2025)

    assert report["status"] == "degraded"
    assert report["checks"]["outbox_pending_count"] == 1


@pytest.mark.asyncio
async def test_import_event_outbox_replay_respects_max_attempts(monkeypatch, db_session: AsyncSession):
    project_id = uuid.uuid4()
    called = False

    async def _fake_publish(_payload):
        nonlocal called
        called = True

    monkeypatch.setattr("app.services.import_event_outbox_service.event_bus.publish_immediate", _fake_publish)

    exhausted = ImportEventOutbox(
        event_type=EventType.LEDGER_DATASET_ACTIVATED.value,
        project_id=project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
        status=OutboxStatus.failed,
        attempt_count=5,
        last_error="network timeout",
    )
    db_session.add(exhausted)
    await db_session.commit()

    report = await ImportEventOutboxService.replay_pending(db_session, max_attempts=5)
    await db_session.commit()

    refreshed = await ImportEventOutboxService.get(db_session, exhausted.id)
    assert report["read_count"] == 0
    assert report["published_count"] == 0
    assert report["skipped_exhausted_count"] == 1
    assert refreshed is not None
    assert refreshed.status == OutboxStatus.failed
    assert refreshed.attempt_count == 5
    assert called is False
    assert report["exhausted_skipped_in_this_run"] == 1


@pytest.mark.asyncio
async def test_import_event_outbox_replay_reports_exhausted_in_current_window(monkeypatch, db_session: AsyncSession):
    project_id = uuid.uuid4()

    async def _fake_publish(_payload):
        return None

    monkeypatch.setattr("app.services.import_event_outbox_service.event_bus.publish_immediate", _fake_publish)
    now = datetime.utcnow()
    db_session.add_all(
        [
            ImportEventOutbox(
                event_type=EventType.LEDGER_DATASET_ACTIVATED.value,
                project_id=project_id,
                year=2025,
                payload={"dataset_id": str(uuid.uuid4())},
                status=OutboxStatus.failed,
                attempt_count=5,
                created_at=now - timedelta(seconds=2),
            ),
            ImportEventOutbox(
                event_type=EventType.LEDGER_DATASET_ACTIVATED.value,
                project_id=project_id,
                year=2025,
                payload={"dataset_id": str(uuid.uuid4())},
                status=OutboxStatus.pending,
                attempt_count=0,
                created_at=now - timedelta(seconds=1),
            ),
        ]
    )
    await db_session.commit()

    report = await ImportEventOutboxService.replay_pending(db_session, max_attempts=5, limit=1)
    await db_session.commit()

    assert report["read_count"] == 1
    assert report["published_count"] == 1
    assert report["exhausted_total_count"] == 1
    assert report["exhausted_skipped_in_this_run"] == 1


@pytest.mark.asyncio
async def test_import_event_health_marks_exhausted_failed_outbox(db_session: AsyncSession):
    project_id = uuid.uuid4()
    max_attempts = int(settings.LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS or 20)

    exhausted = ImportEventOutbox(
        event_type=EventType.LEDGER_DATASET_ACTIVATED.value,
        project_id=project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
        status=OutboxStatus.failed,
        attempt_count=max_attempts,
        last_error="permanent downstream error",
    )
    db_session.add(exhausted)
    await db_session.commit()

    report = await ImportEventReliabilityService.get_health(db_session, project_id=project_id, year=2025)

    assert report["status"] == "degraded"
    assert report["checks"]["outbox_failed_count"] == 1
    assert report["checks"]["outbox_exhausted_failed_count"] == 1
    assert report["checks"]["outbox_max_retry_attempts"] == max_attempts
    assert "OUTBOX_FAILED_EXHAUSTED" in report["checks"]["degradation_reasons"]


@pytest.mark.asyncio
async def test_force_release_with_job_id_cancels_only_target_job(db_session: AsyncSession):
    project_id = uuid.uuid4()
    ok, _msg, batch_id = await ImportQueueService.acquire_lock(
        project_id,
        user_id=str(uuid.uuid4()),
        db=db_session,
        source_type="smart_import",
        file_name="sample.xlsx",
        year=2025,
    )
    assert ok is True
    assert batch_id is not None

    job = await ImportJobService.create_job(
        db_session,
        project_id=project_id,
        year=2025,
        options={"queue_batch_id": str(batch_id)},
    )
    await ImportJobService.transition(
        db_session,
        job.id,
        JobStatus.queued,
        progress_pct=0,
        progress_message="导入作业已排队",
    )
    await db_session.commit()

    msg = await ImportQueueService.force_release(project_id, db_session, job_id=job.id)
    assert "已重置作业" in msg or "已清理作业" in msg

    refreshed_job = await ImportJobService.get_job(db_session, job.id)
    assert refreshed_job is not None
    assert refreshed_job.status == JobStatus.canceled

    refreshed_batch = await db_session.get(ImportBatch, batch_id)
    assert refreshed_batch is not None
    assert refreshed_batch.status == ImportStatus.failed


@pytest.mark.asyncio
async def test_force_release_without_job_id_requires_force_flag(db_session: AsyncSession):
    project_id = uuid.uuid4()
    ok, _msg, batch_id = await ImportQueueService.acquire_lock(
        project_id,
        user_id=str(uuid.uuid4()),
        db=db_session,
        source_type="smart_import",
        file_name="sample.xlsx",
        year=2025,
    )
    assert ok is True
    assert batch_id is not None

    msg = await ImportQueueService.force_release(project_id, db_session)
    assert "已拒绝项目级重置" in msg

    batch = await db_session.get(ImportBatch, batch_id)
    assert batch is not None
    assert batch.status == ImportStatus.processing


@pytest.mark.asyncio
async def test_import_ops_audit_log_writes_structured_entry(db_session: AsyncSession, monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session_factory():
        yield db_session

    monkeypatch.setattr("app.services.import_ops_audit_service.async_session_factory", _session_factory)

    project_id = uuid.uuid4()
    await ImportOpsAuditService.log_operation(
        user_id=None,
        action_type="import_event_replay",
        project_id=project_id,
        params={"limit": 50, "max_attempts": 20},
        scope={"project_id": str(project_id), "year": 2025},
        outcome="success",
        duration_ms=123,
        result={"published_count": 3, "failed_count": 0},
    )

    rows = (await db_session.execute(
        sa.select(Log)
        .where(
            Log.action_type == "import_event_replay",
            Log.object_type == "import_operations",
            Log.object_id == project_id,
        )
        .order_by(Log.created_at.desc())
        .limit(1)
    )).scalars().all()
    assert len(rows) == 1
    entry = rows[0]
    assert entry.user_id is None
    assert entry.new_value["outcome"] == "success"
    assert entry.new_value["duration_ms"] == 123
    assert entry.new_value["scope"]["year"] == 2025
    assert entry.new_value["result"]["published_count"] == 3


@pytest.mark.asyncio
async def test_import_ops_audit_log_fallback_to_null_user_on_fk_violation(db_session: AsyncSession, monkeypatch):
    from contextlib import asynccontextmanager

    bind = db_session.bind
    assert bind is not None
    session_factory = async_sessionmaker(bind=bind, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _session_factory():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr("app.services.import_ops_audit_service.async_session_factory", _session_factory)

    missing_user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    await ImportOpsAuditService.log_operation(
        user_id=missing_user_id,
        action_type="import_reset",
        project_id=project_id,
        params={"force": True},
        scope={"project_id": str(project_id)},
        outcome="success",
        duration_ms=35,
        result={"message": "ok"},
    )

    row = (
        await db_session.execute(
            sa.select(Log)
            .where(
                Log.action_type == "import_reset",
                Log.object_type == "import_operations",
                Log.object_id == project_id,
            )
            .order_by(Log.created_at.desc())
            .limit(1)
        )
    ).scalar_one()
    assert row.user_id is None
    assert row.new_value["actor_user_id"] == str(missing_user_id)
    assert row.new_value["audit_write_degraded"] is True


@pytest.mark.asyncio
async def test_import_event_consumption_cleanup_removes_old_rows(db_session: AsyncSession):
    project_id = uuid.uuid4()
    old = ImportEventConsumption(
        event_id="evt-old",
        handler_name="TrialBalanceService.on_data_imported",
        project_id=project_id,
        year=2025,
        consumed_at=datetime.utcnow() - timedelta(days=200),
    )
    fresh = ImportEventConsumption(
        event_id="evt-new",
        handler_name="TrialBalanceService.on_data_imported",
        project_id=project_id,
        year=2025,
        consumed_at=datetime.utcnow() - timedelta(days=5),
    )
    db_session.add_all([old, fresh])
    await db_session.commit()

    report = await ImportEventConsumptionService.cleanup_older_than_days(
        db_session, retention_days=180, batch_size=100
    )
    await db_session.commit()

    assert report["deleted_count"] == 1
    remaining = (
        await db_session.execute(sa.select(sa.func.count()).select_from(ImportEventConsumption))
    ).scalar_one()
    assert remaining == 1
