"""Tests for OCRWritebackService — Task 5.4 (Wave 4).

Validates:
  - P13 (写回原子性): transactional-local writes all fields + record atomically.
  - P14 (写回幂等性): same writeback idempotency key → only one business effect.
  - R6.3: Version conflict → zero change on target.
  - R6.4: Only human users can writeback (written_by_user_id NOT NULL).
  - staged-external: Creates staging record, receipt advances state.

Uses in-memory SQLite for unit tests (PG integration deferred to Wave 8).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.evidence_governance_models import (
    OcrConfirmation,
    OcrJob,
    OcrResult,
    OcrWriteback,
    OcrWritebackStaging,
)
from app.services.evidence_governance.contracts import OcrState
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    content_hash_of,
)
from app.services.evidence_governance.ocr_writeback_service import (
    OCRWritebackService,
    WritebackResult,
    WRITE_MODE_TRANSACTIONAL_LOCAL,
    WRITE_MODE_STAGED_EXTERNAL,
    _compute_writeback_idempotency_key,
)

# ---------------------------------------------------------------------------
# SQLite compatibility patches
# ---------------------------------------------------------------------------


def _visit_JSONB(self, type_, **kw):
    return "TEXT"


def _visit_ARRAY(self, type_, **kw):
    return "TEXT"


def _visit_UUID(self, type_, **kw):
    return "CHAR(36)"


try:
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    SQLiteTypeCompiler.visit_JSONB = _visit_JSONB
    SQLiteTypeCompiler.visit_ARRAY = _visit_ARRAY
    SQLiteTypeCompiler.visit_UUID = _visit_UUID
except Exception:
    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _patch_partial_unique_for_sqlite():
    """Remove postgresql_where from partial unique indexes for SQLite.

    Returns the list of swapped indexes so callers can restore the canonical
    (unique/partial) indexes after create_all — leaving the shared ORM metadata
    unmodified for the rest of the aggregated test session.
    """
    removed: list[tuple] = []
    for model in [OcrConfirmation, OcrWriteback, OcrWritebackStaging]:
        table = model.__table__
        for idx in list(table.indexes):
            if hasattr(idx, "dialect_options") and idx.dialect_options.get("postgresql", {}).get("where") is not None:
                table.indexes.discard(idx)
                new_idx = sa.Index(
                    idx.name,
                    *[c for c in idx.columns],
                    unique=False,
                )
                table.indexes.add(new_idx)
                removed.append((table, new_idx, idx))
    return removed


def _restore_partial_unique(removed: list[tuple]) -> None:
    """Restore the canonical (unique/partial) indexes swapped out for SQLite."""
    for table, temp_idx, original_idx in removed:
        table.indexes.discard(temp_idx)
        table.indexes.add(original_idx)


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite async session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    async with engine.begin() as conn:
        _removed = _patch_partial_unique_for_sqlite()
        await conn.run_sync(Base.metadata.create_all)
        _restore_partial_unique(_removed)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def human_actor() -> ActorContext:
    return ActorContext(
        actor_type=ActorType.USER,
        actor_user_id=uuid.uuid4(),
    )


@pytest.fixture
def service_actor() -> ActorContext:
    return ActorContext(
        actor_type=ActorType.SERVICE,
        actor_service_identity_id=uuid.uuid4(),
    )


@pytest.fixture
def project_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_confirmed_job(
    session: AsyncSession,
    project_id: uuid.UUID,
    actor: ActorContext,
    *,
    content_hash: str = "a" * 64,
) -> OcrJob:
    """Insert an OCR Job in 'confirmed' state."""
    job = OcrJob(
        id=uuid.uuid4(),
        project_id=project_id,
        audit_year=2025,
        attachment_id=uuid.uuid4(),
        attachment_version_id=uuid.uuid4(),
        content_hash=content_hash,
        idempotency_key="job-key-" + str(uuid.uuid4()),
        state=OcrState.confirmed.value,
        progress=100,
        attempt_count=1,
        max_attempts=5,
        actor_type=actor.actor_type.value,
        actor_user_id=actor.actor_user_id,
        actor_service_identity_id=actor.actor_service_identity_id,
    )
    session.add(job)
    await session.flush()
    return job


async def _create_result_with_confirmations(
    session: AsyncSession,
    job: OcrJob,
    actor: ActorContext,
    *,
    fields: dict[str, tuple[str, str]] | None = None,
) -> uuid.UUID:
    """Create an OCR result with accepted confirmations for all fields.

    fields: dict[field_key → (original_value, confirmed_value)]
    """
    if fields is None:
        fields = {
            "invoice_number": ("INV-RAW", "INV-001"),
            "amount": ("1234", "1234.56"),
        }

    result = OcrResult(
        id=uuid.uuid4(),
        ocr_job_id=job.id,
        project_id=job.project_id,
        audit_year=job.audit_year,
        attachment_version_id=job.attachment_version_id,
        source_content_hash=job.content_hash,
        raw_text="raw text",
        fields={k: v[0] for k, v in fields.items()},
        confidence=0.95,
        page=1,
        region={"x": 0, "y": 0, "w": 100, "h": 50},
        engine="tesseract",
        model_version="5.0.0",
        config_version="v1",
        result_hash=content_hash_of({"text": "raw text", "fields": {k: v[0] for k, v in fields.items()}}),
        actor_type=actor.actor_type.value,
        actor_user_id=actor.actor_user_id,
        actor_service_identity_id=actor.actor_service_identity_id,
    )
    session.add(result)
    await session.flush()

    # Add accepted confirmations for all fields
    for field_key, (orig, confirmed) in fields.items():
        conf = OcrConfirmation(
            id=uuid.uuid4(),
            ocr_job_id=job.id,
            ocr_result_id=result.id,
            project_id=job.project_id,
            audit_year=job.audit_year,
            field_key=field_key,
            is_required=True,
            original_value=orig,
            confirmed_value=confirmed,
            decision="accepted",
            is_current=True,
            revision_no=1,
            confirmed_by_user_id=actor.actor_user_id,
        )
        session.add(conf)

    await session.flush()
    return result.id


# ---------------------------------------------------------------------------
# Tests: Idempotency key computation
# ---------------------------------------------------------------------------


def test_idempotency_key_deterministic():
    """Same inputs produce same idempotency key."""
    job_id = uuid.uuid4()
    result_id = uuid.uuid4()
    mapping = {"a": "1", "b": "2"}

    key1 = _compute_writeback_idempotency_key(job_id, result_id, "workpaper_cell", "t1", mapping)
    key2 = _compute_writeback_idempotency_key(job_id, result_id, "workpaper_cell", "t1", mapping)
    assert key1 == key2


def test_idempotency_key_different_mapping():
    """Different mapping produces different key."""
    job_id = uuid.uuid4()
    result_id = uuid.uuid4()

    key1 = _compute_writeback_idempotency_key(job_id, result_id, "workpaper_cell", "t1", {"a": "1"})
    key2 = _compute_writeback_idempotency_key(job_id, result_id, "workpaper_cell", "t1", {"a": "2"})
    assert key1 != key2


# ---------------------------------------------------------------------------
# Tests: Service Identity cannot writeback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_identity_cannot_writeback(db_session, service_actor, project_id):
    """Service Identity cannot execute OCR writeback (R6.4 / design §4.5)."""
    service = OCRWritebackService(db_session)

    with pytest.raises(EvidenceGovernanceError) as exc_info:
        await service.execute_writeback(
            job_id=uuid.uuid4(),
            result_id=uuid.uuid4(),
            target_type="workpaper_cell",
            target_id="some-target",
            actor=service_actor,
            project_id=project_id,
            audit_year=2025,
        )
    assert exc_info.value.error_code == EvidenceGovernanceError(
        EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN, ""
    ).error_code


# ---------------------------------------------------------------------------
# Tests: Mapping validation (P12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undecided_field_blocks_writeback(db_session, human_actor, project_id):
    """If required field undecided, writeback is rejected (P12: target changes = 0)."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)

    # Create result with fields but NO confirmations → undecided
    result = OcrResult(
        id=uuid.uuid4(),
        ocr_job_id=job.id,
        project_id=project_id,
        audit_year=2025,
        attachment_version_id=job.attachment_version_id,
        source_content_hash=job.content_hash,
        raw_text="text",
        fields={"invoice_number": "INV-RAW"},
        confidence=0.9,
        page=1,
        region={},
        engine="tesseract",
        model_version="5.0",
        config_version="v1",
        result_hash="b" * 64,
        actor_type=human_actor.actor_type.value,
        actor_user_id=human_actor.actor_user_id,
        actor_service_identity_id=None,
    )
    db_session.add(result)
    await db_session.flush()

    service = OCRWritebackService(db_session)

    with pytest.raises(EvidenceGovernanceError) as exc_info:
        await service.execute_writeback(
            job_id=job.id,
            result_id=result.id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
        )
    assert "REQUIRED_FIELD_UNDECIDED" in str(exc_info.value.error_code.value)


# ---------------------------------------------------------------------------
# Tests: Transactional-local writeback (P13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transactional_local_writeback_success(db_session, human_actor, project_id):
    """Transactional-local writeback creates OcrWriteback and advances Job state."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)
    result_id = await _create_result_with_confirmations(db_session, job, human_actor)

    service = OCRWritebackService(db_session)

    # Mock the adapter's can_edit and lock_for_update
    with patch(
        "app.services.evidence_governance.ocr_writeback_service.get_adapter"
    ) as mock_get_adapter:
        mock_adapter = MagicMock()
        mock_adapter.can_edit = AsyncMock(return_value=True)
        mock_adapter.lock_for_update = AsyncMock(return_value=True)
        mock_adapter.resolve = AsyncMock(return_value=MagicMock(target_version=1))
        mock_get_adapter.return_value = mock_adapter

        result = await service.execute_writeback(
            job_id=job.id,
            result_id=result_id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
            target_version_at_start="1",
        )

    assert result.status == "written_back"
    assert result.write_mode == "transactional_local"
    assert result.fields_written is not None
    assert "invoice_number" in result.fields_written
    assert "amount" in result.fields_written

    # Verify OcrWriteback record created
    stmt = sa.select(OcrWriteback).where(OcrWriteback.id == result.writeback_id)
    row = (await db_session.execute(stmt)).scalar_one_or_none()
    assert row is not None
    assert row.result == "success"
    assert row.write_mode == WRITE_MODE_TRANSACTIONAL_LOCAL
    assert row.written_by_user_id == human_actor.actor_user_id

    # Verify Job advanced to written_back
    await db_session.refresh(job)
    assert job.state == OcrState.written_back.value


# ---------------------------------------------------------------------------
# Tests: Idempotency (P14)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_writeback_idempotency(db_session, human_actor, project_id):
    """Same writeback repeated → return existing result, no new record (P14)."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)
    result_id = await _create_result_with_confirmations(db_session, job, human_actor)

    service = OCRWritebackService(db_session)

    with patch(
        "app.services.evidence_governance.ocr_writeback_service.get_adapter"
    ) as mock_get_adapter:
        mock_adapter = MagicMock()
        mock_adapter.can_edit = AsyncMock(return_value=True)
        mock_adapter.lock_for_update = AsyncMock(return_value=True)
        mock_adapter.resolve = AsyncMock(return_value=MagicMock(target_version=1))
        mock_get_adapter.return_value = mock_adapter

        # First call
        result1 = await service.execute_writeback(
            job_id=job.id,
            result_id=result_id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
            target_version_at_start="1",
        )
        assert result1.status == "written_back"

        # Second call (same params → idempotent)
        result2 = await service.execute_writeback(
            job_id=job.id,
            result_id=result_id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
            target_version_at_start="1",
        )
        assert result2.status == "written_back"
        assert result2.writeback_id == result1.writeback_id

    # Only one OcrWriteback record
    stmt = sa.select(sa.func.count()).select_from(OcrWriteback)
    count = (await db_session.execute(stmt)).scalar()
    assert count == 1


# ---------------------------------------------------------------------------
# Tests: Version conflict (zero change)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_target_version_conflict_zero_change(db_session, human_actor, project_id):
    """Target version changed → VERSION_CONFLICT, target zero change."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)
    result_id = await _create_result_with_confirmations(db_session, job, human_actor)

    service = OCRWritebackService(db_session)

    with patch(
        "app.services.evidence_governance.ocr_writeback_service.get_adapter"
    ) as mock_get_adapter:
        mock_adapter = MagicMock()
        mock_adapter.can_edit = AsyncMock(return_value=True)
        # Target version is now 2, but we started with version 1
        mock_adapter.resolve = AsyncMock(return_value=MagicMock(target_version=2))
        mock_get_adapter.return_value = mock_adapter

        result = await service.execute_writeback(
            job_id=job.id,
            result_id=result_id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
            target_version_at_start="1",
        )

    assert result.status == "conflict"
    assert "VERSION_CONFLICT" in result.conflict_reason

    # No OcrWriteback record created
    stmt = sa.select(sa.func.count()).select_from(OcrWriteback)
    count = (await db_session.execute(stmt)).scalar()
    assert count == 0


# ---------------------------------------------------------------------------
# Tests: Permission denied (zero change)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_edit_permission_zero_change(db_session, human_actor, project_id):
    """Actor without target edit permission → SCOPE_NOT_FOUND_OR_FORBIDDEN."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)
    result_id = await _create_result_with_confirmations(db_session, job, human_actor)

    service = OCRWritebackService(db_session)

    with patch(
        "app.services.evidence_governance.ocr_writeback_service.get_adapter"
    ) as mock_get_adapter:
        mock_adapter = MagicMock()
        mock_adapter.can_edit = AsyncMock(return_value=False)
        mock_get_adapter.return_value = mock_adapter

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await service.execute_writeback(
                job_id=job.id,
                result_id=result_id,
                target_type="workpaper_cell",
                target_id="t1",
                actor=human_actor,
                project_id=project_id,
                audit_year=2025,
            )
        assert exc_info.value.error_code.value == "SCOPE_NOT_FOUND_OR_FORBIDDEN"


# ---------------------------------------------------------------------------
# Tests: Staged-external writeback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staged_external_writeback(db_session, human_actor, project_id):
    """staged-external creates staging record and returns 'staged' status."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)
    result_id = await _create_result_with_confirmations(db_session, job, human_actor)

    service = OCRWritebackService(db_session)

    with patch(
        "app.services.evidence_governance.ocr_writeback_service.get_adapter"
    ) as mock_get_adapter, patch(
        "app.services.evidence_governance.ocr_writeback_service._get_write_mode",
        return_value=WRITE_MODE_STAGED_EXTERNAL,
    ):
        mock_adapter = MagicMock()
        mock_adapter.can_edit = AsyncMock(return_value=True)
        mock_adapter.resolve = AsyncMock(return_value=MagicMock(target_version=1))
        mock_get_adapter.return_value = mock_adapter

        result = await service.execute_writeback(
            job_id=job.id,
            result_id=result_id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
        )

    assert result.status == "staged"
    assert result.write_mode == "staged_external"

    # Verify OcrWriteback record created with pending status
    stmt = sa.select(OcrWriteback).where(OcrWriteback.id == result.writeback_id)
    wb = (await db_session.execute(stmt)).scalar_one_or_none()
    assert wb is not None
    assert wb.result == "pending"
    assert wb.write_mode == WRITE_MODE_STAGED_EXTERNAL

    # Verify staging record created
    stmt = sa.select(OcrWritebackStaging).where(
        OcrWritebackStaging.ocr_writeback_id == result.writeback_id
    )
    staging = (await db_session.execute(stmt)).scalar_one_or_none()
    assert staging is not None
    assert staging.consume_state == "pending"
    assert staging.payload is not None


# ---------------------------------------------------------------------------
# Tests: External receipt processing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_external_receipt_success(db_session, human_actor, project_id):
    """Successful receipt advances Job to written_back and marks staging consumed."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)
    result_id = await _create_result_with_confirmations(db_session, job, human_actor)

    service = OCRWritebackService(db_session)

    # First create a staged writeback
    with patch(
        "app.services.evidence_governance.ocr_writeback_service.get_adapter"
    ) as mock_get_adapter, patch(
        "app.services.evidence_governance.ocr_writeback_service._get_write_mode",
        return_value=WRITE_MODE_STAGED_EXTERNAL,
    ):
        mock_adapter = MagicMock()
        mock_adapter.can_edit = AsyncMock(return_value=True)
        mock_adapter.resolve = AsyncMock(return_value=MagicMock(target_version=1))
        mock_get_adapter.return_value = mock_adapter

        staged_result = await service.execute_writeback(
            job_id=job.id,
            result_id=result_id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
        )

    # Find the staging record
    stmt = sa.select(OcrWritebackStaging).where(
        OcrWritebackStaging.ocr_writeback_id == staged_result.writeback_id
    )
    staging = (await db_session.execute(stmt)).scalar_one()

    # Process successful receipt
    await service.receive_external_receipt(
        staging_id=staging.id,
        success=True,
        actor=human_actor,
        receipt_data={"external_ref": "EXT-123"},
    )
    await db_session.flush()

    # Verify staging consumed
    await db_session.refresh(staging)
    assert staging.consume_state == "consumed"
    assert staging.consumed_at is not None

    # Verify writeback success
    wb = await db_session.get(OcrWriteback, staged_result.writeback_id)
    assert wb.result == "success"

    # Verify Job advanced
    await db_session.refresh(job)
    assert job.state == OcrState.written_back.value


@pytest.mark.asyncio
async def test_receive_external_receipt_failure(db_session, human_actor, project_id):
    """Failed receipt marks staging/writeback as failed, Job stays unchanged."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)
    result_id = await _create_result_with_confirmations(db_session, job, human_actor)

    service = OCRWritebackService(db_session)

    with patch(
        "app.services.evidence_governance.ocr_writeback_service.get_adapter"
    ) as mock_get_adapter, patch(
        "app.services.evidence_governance.ocr_writeback_service._get_write_mode",
        return_value=WRITE_MODE_STAGED_EXTERNAL,
    ):
        mock_adapter = MagicMock()
        mock_adapter.can_edit = AsyncMock(return_value=True)
        mock_adapter.resolve = AsyncMock(return_value=MagicMock(target_version=1))
        mock_get_adapter.return_value = mock_adapter

        staged_result = await service.execute_writeback(
            job_id=job.id,
            result_id=result_id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
        )

    stmt = sa.select(OcrWritebackStaging).where(
        OcrWritebackStaging.ocr_writeback_id == staged_result.writeback_id
    )
    staging = (await db_session.execute(stmt)).scalar_one()

    # Process failed receipt
    await service.receive_external_receipt(
        staging_id=staging.id,
        success=False,
        actor=human_actor,
        receipt_data={"error": "target locked by another process"},
    )
    await db_session.flush()

    # Verify staging failed
    await db_session.refresh(staging)
    assert staging.consume_state == "failed"

    # Verify writeback failed
    wb = await db_session.get(OcrWriteback, staged_result.writeback_id)
    assert wb.result == "failed"

    # Job stays in confirmed (not advanced)
    await db_session.refresh(job)
    assert job.state == OcrState.confirmed.value


@pytest.mark.asyncio
async def test_receive_external_receipt_idempotent(db_session, human_actor, project_id):
    """Re-consuming an already-consumed staging is a no-op."""
    job = await _create_confirmed_job(db_session, project_id, human_actor)
    result_id = await _create_result_with_confirmations(db_session, job, human_actor)

    service = OCRWritebackService(db_session)

    with patch(
        "app.services.evidence_governance.ocr_writeback_service.get_adapter"
    ) as mock_get_adapter, patch(
        "app.services.evidence_governance.ocr_writeback_service._get_write_mode",
        return_value=WRITE_MODE_STAGED_EXTERNAL,
    ):
        mock_adapter = MagicMock()
        mock_adapter.can_edit = AsyncMock(return_value=True)
        mock_adapter.resolve = AsyncMock(return_value=MagicMock(target_version=1))
        mock_get_adapter.return_value = mock_adapter

        staged_result = await service.execute_writeback(
            job_id=job.id,
            result_id=result_id,
            target_type="workpaper_cell",
            target_id="t1",
            actor=human_actor,
            project_id=project_id,
            audit_year=2025,
        )

    stmt = sa.select(OcrWritebackStaging).where(
        OcrWritebackStaging.ocr_writeback_id == staged_result.writeback_id
    )
    staging = (await db_session.execute(stmt)).scalar_one()

    # Consume once
    await service.receive_external_receipt(
        staging_id=staging.id,
        success=True,
        actor=human_actor,
    )
    await db_session.flush()

    # Consume again (idempotent — no-op)
    await service.receive_external_receipt(
        staging_id=staging.id,
        success=True,
        actor=human_actor,
    )
    await db_session.flush()

    # Still consumed (not errored)
    await db_session.refresh(staging)
    assert staging.consume_state == "consumed"
