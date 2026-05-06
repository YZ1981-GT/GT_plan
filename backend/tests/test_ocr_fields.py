"""Tests for OCR field extraction endpoint — Round 4 需求 12

Validates:
- OcrFieldsService returns cached fields when ocr_status='completed'
- OcrFieldsService triggers async OCR when status is pending/failed
- Idempotent: repeated calls reuse cached result
- 404 for non-existent or deleted attachment
- Fields extraction from existing ocr_text when no cache

Validates: Requirements 12.2, 12.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment
from app.models.base import Base

# SQLite doesn't have JSONB, map to JSON
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_PROJECT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        tables = [Attachment.__table__]
        await conn.run_sync(lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=tables))
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _create_attachment(
    db: AsyncSession,
    ocr_status: str = "pending",
    ocr_text: str | None = None,
    ocr_fields_cache: dict | None = None,
    is_deleted: bool = False,
) -> uuid.UUID:
    """Insert a test attachment and return its ID"""
    att_id = uuid.uuid4()
    att = Attachment(
        id=att_id,
        project_id=FAKE_PROJECT_ID,
        file_name="test_invoice.pdf",
        file_path="/tmp/test_invoice.pdf",
        file_type="pdf",
        file_size=1024,
        attachment_type="general",
        storage_type="local",
        ocr_status=ocr_status,
        ocr_text=ocr_text,
        ocr_fields_cache=ocr_fields_cache,
        is_deleted=is_deleted,
    )
    db.add(att)
    await db.commit()
    return att_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_cached_when_completed(db_session: AsyncSession):
    """When ocr_status='completed' and cache exists, return 200 + fields"""
    from app.services.ocr_fields_service import OcrFieldsService

    cached_fields = {
        "fields": [
            {"field_name": "amount", "field_value": "15000.00", "confidence_score": 0.95},
            {"field_name": "invoice_no", "field_value": "INV-2026-001", "confidence_score": 0.92},
        ],
        "fields_dict": {"amount": "15000.00", "invoice_no": "INV-2026-001"},
        "document_type": "sales_invoice",
        "extracted_at": "2026-05-06T10:00:00",
    }

    att_id = await _create_attachment(
        db_session,
        ocr_status="completed",
        ocr_text="发票 金额 15000.00",
        ocr_fields_cache=cached_fields,
    )

    svc = OcrFieldsService(db_session)
    body, status_code = await svc.get_or_trigger_ocr_fields(att_id)

    assert status_code == 200
    assert body["status"] == "completed"
    assert body["attachment_id"] == str(att_id)
    assert body["fields"] == cached_fields


@pytest.mark.asyncio
async def test_idempotent_cached(db_session: AsyncSession):
    """Multiple calls to same completed attachment return same cached result"""
    from app.services.ocr_fields_service import OcrFieldsService

    cached_fields = {
        "fields": [{"field_name": "amount", "field_value": "5000", "confidence_score": 0.9}],
        "fields_dict": {"amount": "5000"},
        "document_type": "bank_receipt",
        "extracted_at": "2026-05-06T10:00:00",
    }

    att_id = await _create_attachment(
        db_session,
        ocr_status="completed",
        ocr_text="银行回单",
        ocr_fields_cache=cached_fields,
    )

    svc = OcrFieldsService(db_session)

    body1, status1 = await svc.get_or_trigger_ocr_fields(att_id)
    body2, status2 = await svc.get_or_trigger_ocr_fields(att_id)

    assert status1 == 200
    assert status2 == 200
    assert body1 == body2


@pytest.mark.asyncio
async def test_triggers_async_when_pending(db_session: AsyncSession):
    """When ocr_status='pending', trigger async OCR and return 202"""
    from app.services.ocr_fields_service import OcrFieldsService

    att_id = await _create_attachment(
        db_session,
        ocr_status="pending",
        ocr_text=None,
        ocr_fields_cache=None,
    )

    svc = OcrFieldsService(db_session)

    # Patch the async task to avoid actual OCR execution
    with patch.object(svc, "_run_ocr_async", new_callable=AsyncMock):
        body, status_code = await svc.get_or_trigger_ocr_fields(att_id)

    assert status_code == 202
    assert body["status"] == "processing"
    assert body["attachment_id"] == str(att_id)
    assert "job_id" in body


@pytest.mark.asyncio
async def test_triggers_async_when_failed(db_session: AsyncSession):
    """When ocr_status='failed', trigger async OCR and return 202"""
    from app.services.ocr_fields_service import OcrFieldsService

    att_id = await _create_attachment(
        db_session,
        ocr_status="failed",
        ocr_text=None,
        ocr_fields_cache=None,
    )

    svc = OcrFieldsService(db_session)

    with patch.object(svc, "_run_ocr_async", new_callable=AsyncMock):
        body, status_code = await svc.get_or_trigger_ocr_fields(att_id)

    assert status_code == 202
    assert body["status"] == "processing"
    assert "job_id" in body


@pytest.mark.asyncio
async def test_404_for_nonexistent(db_session: AsyncSession):
    """Return 404 for non-existent attachment"""
    from app.services.ocr_fields_service import OcrFieldsService

    svc = OcrFieldsService(db_session)
    body, status_code = await svc.get_or_trigger_ocr_fields(uuid.uuid4())

    assert status_code == 404
    assert "附件不存在" in body["detail"]


@pytest.mark.asyncio
async def test_404_for_deleted_attachment(db_session: AsyncSession):
    """Deleted attachment should return 404"""
    from app.services.ocr_fields_service import OcrFieldsService

    att_id = await _create_attachment(
        db_session,
        ocr_status="completed",
        ocr_text="some text",
        ocr_fields_cache={"fields": []},
        is_deleted=True,
    )

    svc = OcrFieldsService(db_session)
    body, status_code = await svc.get_or_trigger_ocr_fields(att_id)

    assert status_code == 404


@pytest.mark.asyncio
async def test_extracts_from_text_when_no_cache(db_session: AsyncSession):
    """When completed with ocr_text but no cache, extract fields and cache"""
    from app.services.ocr_fields_service import OcrFieldsService

    att_id = await _create_attachment(
        db_session,
        ocr_status="completed",
        ocr_text="增值税专用发票 购买方：测试公司 金额：15000.00 税额：1950.00",
        ocr_fields_cache=None,
    )

    mock_fields = [
        {"field_name": "buyer_name", "field_value": "测试公司", "confidence_score": 0.9},
        {"field_name": "amount", "field_value": "15000.00", "confidence_score": 0.95},
    ]

    svc = OcrFieldsService(db_session)

    # Mock the OCRService methods used internally
    with patch(
        "app.services.ocr_service_v2.OCRService.classify_document",
        new_callable=AsyncMock,
        return_value="sales_invoice",
    ), patch(
        "app.services.ocr_service_v2.OCRService.extract_fields",
        new_callable=AsyncMock,
        return_value=mock_fields,
    ):
        body, status_code = await svc.get_or_trigger_ocr_fields(att_id)

    assert status_code == 200
    assert body["status"] == "completed"
    assert body["fields"]["document_type"] == "sales_invoice"
    assert len(body["fields"]["fields"]) == 2

    # Verify cache was written to the attachment
    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(Attachment).where(Attachment.id == att_id)
    )
    att = result.scalar_one()
    assert att.ocr_fields_cache is not None
    assert att.ocr_fields_cache["document_type"] == "sales_invoice"


@pytest.mark.asyncio
async def test_stub_extract_when_ai_unavailable(db_session: AsyncSession):
    """When AI service is unavailable, return stub result"""
    from app.services.ocr_fields_service import OcrFieldsService

    att_id = await _create_attachment(
        db_session,
        ocr_status="completed",
        ocr_text="增值税发票内容",
        ocr_fields_cache=None,
    )

    svc = OcrFieldsService(db_session)

    # Mock OCRService to raise an exception (AI unavailable)
    with patch(
        "app.services.ocr_service_v2.OCRService.classify_document",
        new_callable=AsyncMock,
        side_effect=Exception("AI service unavailable"),
    ):
        body, status_code = await svc.get_or_trigger_ocr_fields(att_id)

    # Should still return 200 with stub result
    assert status_code == 200
    assert body["status"] == "completed"
    # Stub should detect invoice from file_name
    assert body["fields"]["document_type"] in ("sales_invoice", "other")


@pytest.mark.asyncio
async def test_get_job_status_returns_none_for_unknown(db_session: AsyncSession):
    """get_job_status returns None for unknown job_id"""
    from app.services.ocr_fields_service import OcrFieldsService

    svc = OcrFieldsService(db_session)
    result = await svc.get_job_status("nonexistent-job-id")
    assert result is None
