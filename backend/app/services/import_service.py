"""数据导入服务 — 同步导入 + 校验 + 批量写入 + 回滚

Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.21, 4.22, 4.23
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    ImportBatch,
    ImportStatus,
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)
from app.models.audit_platform_schemas import (
    ImportBatchResponse,
    ImportProgress,
    ImportValidationResult,
)
from app.services.import_engine.parsers import (
    GenericParser,
    ParserFactory,
    normalize_data_type,
)
from app.services.import_engine.validation import ValidationContext, ValidationEngine
from app.services.event_bus import event_bus
from app.models.audit_platform_schemas import EventPayload, EventType

logger = logging.getLogger(__name__)

# Table model mapping
_TABLE_MAP = {
    "tb_balance": TbBalance,
    "tb_ledger": TbLedger,
    "tb_aux_balance": TbAuxBalance,
    "tb_aux_ledger": TbAuxLedger,
}

CHUNK_SIZE = 5000


# ---------------------------------------------------------------------------
# start_import (synchronous for MVP)
# ---------------------------------------------------------------------------


async def start_import(
    project_id: UUID,
    file: UploadFile,
    source_type: str,
    data_type: str,
    year: int,
    db: AsyncSession,
) -> ImportBatch:
    """Create import_batch, parse file, validate, bulk insert, return batch.

    Validates: Requirements 4.3, 4.4, 4.5, 4.6
    """
    data_type = normalize_data_type(data_type)

    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    # 1. Create import_batch record
    batch = ImportBatch(
        project_id=project_id,
        year=year,
        source_type=source_type,
        file_name=file.filename,
        data_type=data_type,
        status=ImportStatus.processing,
        started_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    await db.flush()

    try:
        # 2. Parse file
        content = await file.read()
        parser = ParserFactory.get_parser(source_type)
        parsed_data = parser.parse(content, data_type)

        if not parsed_data:
            batch.status = ImportStatus.failed
            batch.validation_summary = {"error": "文件中未解析到有效数据"}
            batch.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise HTTPException(status_code=400, detail="文件中未解析到有效数据")

        # 3. Build validation context
        account_codes = await _get_account_codes(project_id, db)
        context = ValidationContext(
            project_year=year,
            account_codes=account_codes,
        )

        # Load existing balance data for cross-table validation
        if data_type in ("tb_ledger", "tb_aux_balance"):
            context.balance_data = await _load_balance_data(project_id, year, db)

        # 4. Validate
        engine = ValidationEngine()
        validation_result = engine.validate(parsed_data, data_type, context)

        # Store validation summary
        batch.validation_summary = {
            "passed": validation_result.passed,
            "has_reject": validation_result.has_reject,
            "has_warning": validation_result.has_warning,
            "rules": [r.model_dump() for r in validation_result.rules],
        }

        if not validation_result.passed:
            batch.status = ImportStatus.failed
            batch.completed_at = datetime.now(timezone.utc)
            await db.commit()
            # Return the batch with failure info rather than raising
            return batch

        # 5. Bulk insert in chunks
        table_model = _TABLE_MAP[data_type]
        record_count = 0

        for i in range(0, len(parsed_data), CHUNK_SIZE):
            chunk = parsed_data[i : i + CHUNK_SIZE]
            records = []
            for row in chunk:
                record = _build_record(
                    table_model, row, project_id, year, batch.id
                )
                if record:
                    records.append(record)

            if records:
                db.add_all(records)
                await db.flush()
                record_count += len(records)

        # 6. Update batch status
        batch.record_count = record_count
        batch.status = ImportStatus.completed
        batch.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # 7. Publish data imported event
        await event_bus.publish(EventPayload(
            event_type=EventType.DATA_IMPORTED,
            project_id=project_id,
            year=year,
            batch_id=batch.id,
        ))

        return batch

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Import failed: %s", e)
        batch.status = ImportStatus.failed
        batch.validation_summary = {"error": str(e)}
        batch.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


# ---------------------------------------------------------------------------
# get_import_progress
# ---------------------------------------------------------------------------


async def get_import_progress(
    batch_id: UUID,
    db: AsyncSession,
) -> ImportProgress:
    """Return batch status as ImportProgress.

    Validates: Requirements 4.4
    """
    result = await db.execute(
        select(ImportBatch).where(ImportBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")

    elapsed = 0.0
    if batch.started_at:
        end = batch.completed_at or datetime.now(timezone.utc)
        elapsed = (end - batch.started_at).total_seconds()

    # Extract warnings from validation summary
    warnings = []
    if batch.validation_summary:
        rules = batch.validation_summary.get("rules", [])
        for rule in rules:
            if not rule.get("passed") and rule.get("severity") == "warning":
                warnings.append(rule.get("message", ""))

    stage = "pending"
    if batch.status == ImportStatus.processing:
        stage = "importing"
    elif batch.status == ImportStatus.completed:
        stage = "completed"
    elif batch.status == ImportStatus.failed:
        stage = "failed"
    elif batch.status == ImportStatus.rolled_back:
        stage = "rolled_back"

    progress = 100.0 if batch.status in (
        ImportStatus.completed, ImportStatus.failed, ImportStatus.rolled_back
    ) else 0.0

    error_msg = None
    if batch.status == ImportStatus.failed and batch.validation_summary:
        error_msg = batch.validation_summary.get("error")
        if not error_msg:
            # Check for reject rules
            rules = batch.validation_summary.get("rules", [])
            for rule in rules:
                if not rule.get("passed") and rule.get("severity") == "reject":
                    error_msg = rule.get("message")
                    break

    return ImportProgress(
        batch_id=batch.id,
        status=batch.status,
        stage=stage,
        records_processed=batch.record_count,
        total_records=batch.record_count,
        progress_percent=progress,
        elapsed_seconds=elapsed,
        validation_warnings=warnings,
        error_message=error_msg,
    )


# ---------------------------------------------------------------------------
# get_import_batches
# ---------------------------------------------------------------------------


async def get_import_batches(
    project_id: UUID,
    db: AsyncSession,
) -> list[ImportBatchResponse]:
    """List all import batches for a project."""
    result = await db.execute(
        select(ImportBatch)
        .where(ImportBatch.project_id == project_id)
        .order_by(ImportBatch.created_at.desc())
    )
    batches = result.scalars().all()
    return [ImportBatchResponse.model_validate(b) for b in batches]


# ---------------------------------------------------------------------------
# Post-import processing (Task 9.6)
# ---------------------------------------------------------------------------


async def apply_mappings(project_id: UUID, db: AsyncSession) -> None:
    """Apply existing account mappings after import.

    No-op for MVP — will be used when trial balance recalc is implemented.

    Validates: Requirements 4.21
    """
    # Placeholder: In the future, this will trigger trial balance recalculation
    logger.info("apply_mappings called for project %s (no-op for MVP)", project_id)


async def queue_unmapped(project_id: UUID, db: AsyncSession) -> list[str]:
    """Identify accounts with no mapping and return their codes.

    Validates: Requirements 4.22
    """
    from app.models.audit_platform_models import AccountMapping

    # Get all account codes from tb_balance
    balance_result = await db.execute(
        select(TbBalance.account_code)
        .where(
            TbBalance.project_id == project_id,
            TbBalance.is_deleted == False,  # noqa: E712
        )
        .distinct()
    )
    balance_codes = {row[0] for row in balance_result.all()}

    # Get all mapped codes
    mapping_result = await db.execute(
        select(AccountMapping.original_account_code)
        .where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        )
    )
    mapped_codes = {row[0] for row in mapping_result.all()}

    unmapped = sorted(balance_codes - mapped_codes)
    if unmapped:
        logger.info(
            "Project %s has %d unmapped accounts: %s",
            project_id,
            len(unmapped),
            unmapped[:10],
        )
    return unmapped


async def rollback_import(batch_id: UUID, db: AsyncSession) -> ImportBatch:
    """Delete all records with matching import_batch_id, set status to rolled_back.

    Validates: Requirements 4.23
    """
    result = await db.execute(
        select(ImportBatch).where(ImportBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")

    if batch.status == ImportStatus.rolled_back:
        raise HTTPException(status_code=400, detail="该批次已回滚")

    # Delete records from all 4 tables
    for table_model in (TbBalance, TbLedger, TbAuxBalance, TbAuxLedger):
        await db.execute(
            delete(table_model).where(table_model.import_batch_id == batch_id)
        )

    batch.status = ImportStatus.rolled_back
    batch.record_count = 0
    batch.completed_at = datetime.now(timezone.utc)
    await db.commit()

    # Publish import rolled back event
    await event_bus.publish(EventPayload(
        event_type=EventType.IMPORT_ROLLED_BACK,
        project_id=batch.project_id,
        year=batch.year,
        batch_id=batch.id,
    ))

    return batch


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_account_codes(project_id: UUID, db: AsyncSession) -> set[str]:
    """Get all account codes for a project (both standard and client)."""
    result = await db.execute(
        select(AccountChart.account_code)
        .where(
            AccountChart.project_id == project_id,
            AccountChart.is_deleted == False,  # noqa: E712
        )
    )
    return {row[0] for row in result.all()}


async def _load_balance_data(
    project_id: UUID, year: int, db: AsyncSession
) -> list[dict]:
    """Load existing balance data for cross-table validation."""
    result = await db.execute(
        select(TbBalance).where(
            TbBalance.project_id == project_id,
            TbBalance.year == year,
            TbBalance.is_deleted == False,  # noqa: E712
        )
    )
    rows = result.scalars().all()
    return [
        {
            "account_code": r.account_code,
            "opening_balance": r.opening_balance or Decimal("0"),
            "debit_amount": r.debit_amount or Decimal("0"),
            "credit_amount": r.credit_amount or Decimal("0"),
            "closing_balance": r.closing_balance or Decimal("0"),
        }
        for r in rows
    ]


def _build_record(table_model, row: dict, project_id: UUID, year: int, batch_id: UUID):
    """Build an ORM record from a parsed row dict."""
    base_kwargs = {
        "project_id": project_id,
        "year": year,
        "import_batch_id": batch_id,
        "company_code": row.get("company_code", "default"),
        "account_code": row["account_code"],
    }

    if table_model is TbBalance:
        return TbBalance(
            **base_kwargs,
            account_name=row.get("account_name"),
            opening_balance=row.get("opening_balance"),
            debit_amount=row.get("debit_amount"),
            credit_amount=row.get("credit_amount"),
            closing_balance=row.get("closing_balance"),
            currency_code=row.get("currency_code", "CNY"),
        )
    elif table_model is TbLedger:
        return TbLedger(
            **base_kwargs,
            voucher_date=row["voucher_date"],
            voucher_no=row["voucher_no"],
            account_name=row.get("account_name"),
            debit_amount=row.get("debit_amount"),
            credit_amount=row.get("credit_amount"),
            counterpart_account=row.get("counterpart_account"),
            summary=row.get("summary"),
            preparer=row.get("preparer"),
            currency_code=row.get("currency_code", "CNY"),
        )
    elif table_model is TbAuxBalance:
        return TbAuxBalance(
            **base_kwargs,
            aux_type=row["aux_type"],
            aux_code=row.get("aux_code"),
            aux_name=row.get("aux_name"),
            opening_balance=row.get("opening_balance"),
            debit_amount=row.get("debit_amount"),
            credit_amount=row.get("credit_amount"),
            closing_balance=row.get("closing_balance"),
            currency_code=row.get("currency_code", "CNY"),
        )
    elif table_model is TbAuxLedger:
        return TbAuxLedger(
            **base_kwargs,
            voucher_date=row.get("voucher_date"),
            voucher_no=row.get("voucher_no"),
            aux_type=row.get("aux_type"),
            aux_code=row.get("aux_code"),
            aux_name=row.get("aux_name"),
            debit_amount=row.get("debit_amount"),
            credit_amount=row.get("credit_amount"),
            summary=row.get("summary"),
            preparer=row.get("preparer"),
            currency_code=row.get("currency_code", "CNY"),
        )
    return None
