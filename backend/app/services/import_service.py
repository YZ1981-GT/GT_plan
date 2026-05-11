"""数据导入服务 — 同步导入 + 校验 + 批量写入 + 回滚

Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.21, 4.22, 4.23
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import BinaryIO
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, select, update
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
from app.services.import_queue_service import IMPORT_JOB_DATA_TYPE
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

CHUNK_SIZE = 10000
STREAMING_THRESHOLD_MB = 20


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
    on_duplicate: str = "skip",  # skip / overwrite / error
) -> ImportBatch:
    """Create import_batch, parse file, validate, bulk insert, return batch.

    on_duplicate:
      - "skip": 跳过重复记录（默认）
      - "overwrite": 软删除旧数据后重新导入
      - "error": 发现重复时报错中止

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

        # 5. Check for duplicates and handle according to on_duplicate strategy
        table_model = _TABLE_MAP[data_type]
        existing_count = await _count_existing_records(project_id, year, data_type, db)

        if existing_count > 0:
            if on_duplicate == "error":
                batch.status = ImportStatus.failed
                batch.validation_summary = {
                    "error": f"已存在 {existing_count} 条{data_type}数据（{year}年度），请选择覆盖或跳过",
                    "existing_count": existing_count,
                    "duplicate_action_required": True,
                }
                batch.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return batch
            elif on_duplicate == "overwrite":
                # 软删除旧数据（保留到回收站）
                old_count = await _soft_delete_existing(project_id, year, data_type, db)
                logger.info("Overwrite mode: soft-deleted %d existing records", old_count)

        # 6. Bulk insert in chunks (use execute for raw INSERT performance)
        record_count = 0

        for i in range(0, len(parsed_data), CHUNK_SIZE):
            chunk = parsed_data[i : i + CHUNK_SIZE]
            records = []
            for row in chunk:
                record = _build_record_dict(
                    data_type, row, project_id, year, batch.id
                )
                if record:
                    records.append(record)

            if records:
                await db.execute(
                    table_model.__table__.insert(),
                    records,
                )
                record_count += len(records)

            # Periodic flush to avoid holding too much in memory
            if record_count % 50000 == 0 and record_count > 0:
                await db.flush()

        # 7. Update batch status
        batch.record_count = record_count
        batch.status = ImportStatus.completed
        batch.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # 8. Publish data imported event
        await event_bus.publish(EventPayload(
            event_type=EventType.DATA_IMPORTED,
            project_id=project_id,
            year=year,
            batch_id=batch.id,
        ))

        # 9. Backfill account_name from account_chart for records missing it
        await _backfill_account_names(project_id, batch.id, data_type, db)

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
        .where(
            ImportBatch.project_id == project_id,
            ImportBatch.data_type != IMPORT_JOB_DATA_TYPE,
        )
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
    from app.models.dataset_models import DatasetStatus, LedgerDataset
    from app.services.dataset_query import get_active_filter

    # 查找最新 active 年度
    year_result = await db.execute(
        select(LedgerDataset.year).where(
            LedgerDataset.project_id == project_id,
            LedgerDataset.status == DatasetStatus.active,
        ).order_by(LedgerDataset.year.desc()).limit(1)
    )
    active_year = year_result.scalar_one_or_none()

    # Get all account codes from tb_balance
    if active_year is not None:
        balance_result = await db.execute(
            select(TbBalance.account_code)
            .where(
                await get_active_filter(db, TbBalance.__table__, project_id, active_year, current_user_id=None),  # F41: 内部服务调用，显式 opt-out
            )
            .distinct()
        )
    else:
        # 无 active 数据集时降级为 project_id 过滤
        balance_result = await db.execute(
            select(TbBalance.account_code)
            .where(
                TbBalance.project_id == project_id,
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
    from app.services.dataset_query import get_active_filter
    result = await db.execute(
        select(TbBalance).where(
            await get_active_filter(db, TbBalance.__table__, project_id, year, current_user_id=None),  # F41: 内部校验调用，显式 opt-out
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
    """Build an ORM record from a parsed row dict. (Legacy, kept for compatibility)"""
    d = _build_record_dict(table_model.__tablename__, row, project_id, year, batch_id)
    if d is None:
        return None
    return table_model(**d)


def _parse_int(value) -> int | None:
    """Parse a value to int, return None for empty/invalid."""
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _build_record_dict(data_type: str, row: dict, project_id: UUID, year: int, batch_id: UUID) -> dict | None:
    """Build a plain dict for bulk INSERT (much faster than ORM objects for large datasets).

    Returns None if the row is invalid (missing required fields).
    """
    import uuid as _uuid

    base = {
        "id": _uuid.uuid4(),
        "project_id": project_id,
        "year": year,
        "import_batch_id": batch_id,
        "company_code": row.get("company_code", "default"),
        "account_code": row["account_code"],
        "currency_code": row.get("currency_code", "CNY"),
        "is_deleted": False,
    }

    if data_type == "tb_balance":
        base.update({
            "account_name": row.get("account_name"),
            "level": row.get("level"),
            "opening_balance": row.get("opening_balance"),
            "opening_debit": row.get("opening_debit"),
            "opening_credit": row.get("opening_credit"),
            "opening_qty": row.get("opening_qty"),
            "opening_fc": row.get("opening_fc"),
            "debit_amount": row.get("debit_amount"),
            "credit_amount": row.get("credit_amount"),
            "closing_balance": row.get("closing_balance"),
            "closing_debit": row.get("closing_debit"),
            "closing_credit": row.get("closing_credit"),
        })
    elif data_type == "tb_ledger":
        if not row.get("voucher_date") or not row.get("voucher_no"):
            return None
        base.update({
            "voucher_date": row["voucher_date"],
            "voucher_no": row["voucher_no"],
            "account_name": row.get("account_name"),
            "accounting_period": _parse_int(row.get("accounting_period")),
            "voucher_type": row.get("voucher_type"),
            "entry_seq": _parse_int(row.get("entry_seq")),
            "debit_amount": row.get("debit_amount"),
            "credit_amount": row.get("credit_amount"),
            "debit_qty": row.get("debit_qty"),
            "credit_qty": row.get("credit_qty"),
            "debit_fc": row.get("debit_fc"),
            "credit_fc": row.get("credit_fc"),
            "counterpart_account": row.get("counterpart_account"),
            "summary": row.get("summary"),
            "preparer": row.get("preparer"),
        })
    elif data_type == "tb_aux_balance":
        if not row.get("aux_type"):
            return None
        base.update({
            "aux_type": row["aux_type"],
            "aux_type_name": row.get("aux_type_name"),
            "aux_code": row.get("aux_code"),
            "aux_name": row.get("aux_name"),
            "account_name": row.get("account_name"),
            "opening_balance": row.get("opening_balance"),
            "opening_debit": row.get("opening_debit"),
            "opening_credit": row.get("opening_credit"),
            "opening_qty": row.get("opening_qty"),
            "opening_fc": row.get("opening_fc"),
            "debit_amount": row.get("debit_amount"),
            "credit_amount": row.get("credit_amount"),
            "closing_balance": row.get("closing_balance"),
            "closing_debit": row.get("closing_debit"),
            "closing_credit": row.get("closing_credit"),
            "aux_dimensions_raw": row.get("aux_dimensions_raw"),
        })
    elif data_type == "tb_aux_ledger":
        base.update({
            "aux_type": row.get("aux_type"),
            "aux_type_name": row.get("aux_type_name"),
            "aux_code": row.get("aux_code"),
            "aux_name": row.get("aux_name"),
            "account_name": row.get("account_name"),
            "accounting_period": _parse_int(row.get("accounting_period")),
            "voucher_type": row.get("voucher_type"),
            "voucher_date": row.get("voucher_date"),
            "voucher_no": row.get("voucher_no"),
            "debit_amount": row.get("debit_amount"),
            "credit_amount": row.get("credit_amount"),
            "debit_qty": row.get("debit_qty"),
            "credit_qty": row.get("credit_qty"),
            "debit_fc": row.get("debit_fc"),
            "credit_fc": row.get("credit_fc"),
            "summary": row.get("summary"),
            "preparer": row.get("preparer"),
            "aux_dimensions_raw": row.get("aux_dimensions_raw"),
        })
    else:
        return None

    return base


async def _backfill_account_names(
    project_id: UUID, batch_id: UUID, data_type: str, db: AsyncSession
) -> None:
    """从 account_chart 表回填缺失的 account_name（导入文件中可能没有科目名称列）。

    使用单条 UPDATE ... FROM 语句批量更新，支持百万行数据。
    """
    table_model = _TABLE_MAP.get(data_type)
    if table_model is None:
        return

    tbl = table_model.__table__
    ac = AccountChart.__table__

    # UPDATE table SET account_name = ac.account_name
    # FROM account_chart ac
    # WHERE table.account_code = ac.account_code
    #   AND table.project_id = ac.project_id
    #   AND table.import_batch_id = :batch_id
    #   AND table.account_name IS NULL
    #   AND ac.is_deleted = false
    stmt = (
        tbl.update()
        .values(account_name=ac.c.account_name)
        .where(
            tbl.c.account_code == ac.c.account_code,
            tbl.c.project_id == ac.c.project_id,
            tbl.c.import_batch_id == batch_id,
            tbl.c.account_name.is_(None),
            ac.c.is_deleted == False,  # noqa: E712
        )
    )
    await db.execute(stmt)
    await db.flush()


async def _count_existing_records(
    project_id: UUID, year: int, data_type: str, db: AsyncSession
) -> int:
    """统计指定项目+年度+数据类型的已有记录数。"""
    table_model = _TABLE_MAP.get(data_type)
    if not table_model:
        return 0
    result = await db.execute(
        select(func.count()).select_from(table_model).where(
            table_model.project_id == project_id,
            table_model.year == year,
            table_model.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar() or 0


async def _soft_delete_existing(
    project_id: UUID, year: int, data_type: str, db: AsyncSession
) -> int:
    """软删除指定项目+年度+数据类型的所有已有记录（覆盖导入前清理）。"""
    import sqlalchemy as sa
    table_model = _TABLE_MAP.get(data_type)
    if not table_model:
        return 0
    tbl = table_model.__table__
    result = await db.execute(
        sa.update(tbl)
        .where(
            tbl.c.project_id == project_id,
            tbl.c.year == year,
            tbl.c.is_deleted == sa.false(),
        )
        .values(is_deleted=True)
    )
    await db.flush()
    return result.rowcount


async def start_import_streaming(
    project_id: UUID,
    content: bytes | BinaryIO,
    data_type: str,
    year: int,
    db: AsyncSession,
    batch_id: UUID | None = None,
    on_duplicate: str = "skip",
    source_type: str = "generic",
    file_name: str | None = None,
) -> ImportBatch:
    """Streaming import for large Excel/CSV files with chunked parse+insert."""
    data_type = normalize_data_type(data_type)
    table_model = _TABLE_MAP[data_type]

    # 创建 batch 记录
    batch = ImportBatch(
        project_id=project_id,
        year=year,
        source_type=source_type,
        file_name=file_name or "streaming_import",
        data_type=data_type,
        status=ImportStatus.processing,
        started_at=datetime.now(timezone.utc),
    )
    if batch_id:
        batch.id = batch_id
    db.add(batch)
    await db.flush()

    parser = GenericParser()
    total_rows = 0

    try:
        existing_count = await _count_existing_records(project_id, year, data_type, db)
        if existing_count > 0:
            if on_duplicate == "error":
                batch.status = ImportStatus.failed
                batch.validation_summary = {
                    "error": f"已存在 {existing_count} 条{data_type}数据（{year}年度），请选择覆盖或跳过",
                    "existing_count": existing_count,
                    "duplicate_action_required": True,
                }
                batch.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return batch
            if on_duplicate == "overwrite":
                old_count = await _soft_delete_existing(project_id, year, data_type, db)
                logger.info(
                    "Streaming overwrite mode: soft-deleted %d existing records",
                    old_count,
                )

        for chunk in parser.parse_streaming(content, data_type, chunk_size=CHUNK_SIZE):
            if not chunk:
                continue

            records = []
            for row in chunk:
                record = _build_record_dict(data_type, row, project_id, year, batch.id)
                if record:
                    records.append(record)

            if records:
                await db.execute(table_model.__table__.insert(), records)
                total_rows += len(records)

            # 发布进度事件
            try:
                await event_bus.publish_immediate(EventPayload(
                    event_type=EventType.IMPORT_PROGRESS,
                    project_id=project_id,
                    year=year,
                    batch_id=batch.id,
                    extra={"rows_imported": total_rows, "data_type": data_type},
                ))
            except Exception:
                pass  # 进度事件失败不阻断导入

            # 定期 flush
            if total_rows % 50000 == 0 and total_rows > 0:
                await db.flush()

        batch.record_count = total_rows
        batch.status = ImportStatus.completed
        batch.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # 发布导入完成事件
        await event_bus.publish(EventPayload(
            event_type=EventType.DATA_IMPORTED,
            project_id=project_id,
            year=year,
            batch_id=batch.id,
        ))

        # 回填 account_name
        await _backfill_account_names(project_id, batch.id, data_type, db)

        return batch

    except Exception as e:
        logger.exception("Streaming import failed: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        batch.status = ImportStatus.failed
        batch.validation_summary = {"error": str(e)}
        batch.completed_at = datetime.now(timezone.utc)
        db.add(batch)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


async def check_duplicates(
    project_id: UUID, year: int, data_type: str, db: AsyncSession
) -> dict:
    """检查是否存在重复数据（供前端导入前调用）。

    Returns:
        {
            "has_duplicates": bool,
            "existing_count": int,
            "data_type": str,
            "year": int,
            "message": str,
        }
    """
    data_type = normalize_data_type(data_type)
    count = await _count_existing_records(project_id, year, data_type, db)

    type_labels = {
        "tb_balance": "科目余额表",
        "tb_ledger": "序时账",
        "tb_aux_balance": "辅助余额表",
        "tb_aux_ledger": "辅助明细账",
    }
    label = type_labels.get(data_type, data_type)

    return {
        "has_duplicates": count > 0,
        "existing_count": count,
        "data_type": data_type,
        "year": year,
        "message": f"已存在 {count} 条{label}数据（{year}年度）" if count > 0 else "无重复数据",
    }
