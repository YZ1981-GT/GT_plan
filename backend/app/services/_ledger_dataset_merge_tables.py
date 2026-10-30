"""ledger_dataset_merge 的逐表月合并与快照继承实现。"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Awaitable, Callable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart, AccountSource, DirectionOverride,
    TbAuxBalance, TbAuxLedger, TbBalance, TbLedger,
)
from app.services._ledger_dataset_merge_copy import (
    copy_rows as _copy_rows,
    count_rows as _count,
    dialect_name as _dialect_name,
    month_bucket as _month_bucket,
    month_buckets as _month_buckets,
    override_id_map as _override_id_map,
    public_months as _public_months,
)
from app.services._ledger_dataset_merge_types import MergeRowCountError, TableMergeReport

PERIODIC_MODELS = (TbLedger, TbAuxLedger)
SNAPSHOT_MODELS = (TbBalance, TbAuxBalance)
ProgressCallback = Callable[[str, int, int], Awaitable[None]]

def _bucket_where(table: sa.Table, year: int, month: int) -> sa.ColumnElement:
    if month == 0:
        return table.c.voucher_date.is_(None)
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return sa.and_(table.c.voucher_date >= start, table.c.voucher_date < end)


async def _merge_periodic_table(
    db: AsyncSession,
    *,
    model: type,
    strategy: str,
    base_dataset_id: UUID,
    staged_dataset_id: UUID,
    inherited_batch_id: UUID,
    id_maps: dict[str, dict[UUID, UUID]],
    year: int,
    progress_callback: ProgressCallback | None,
) -> TableMergeReport:
    table = model.__table__
    bucket = _month_bucket(table)
    base_buckets = await _month_buckets(db, table, base_dataset_id)
    file_buckets = await _month_buckets(db, table, staged_dataset_id)
    initial_file_rows = await _count(
        db, table, table.c.dataset_id == staged_dataset_id, table.c.is_deleted == sa.false()
    )
    initial_undated = await _count(
        db,
        table,
        table.c.dataset_id == staged_dataset_id,
        table.c.is_deleted == sa.false(),
        table.c.voucher_date.is_(None),
    )
    base_undated = await _count(
        db,
        table,
        table.c.dataset_id == base_dataset_id,
        table.c.is_deleted == sa.false(),
        table.c.voucher_date.is_(None),
    )
    overlap = base_buckets & file_buckets
    if strategy == "skip" and overlap:
        await db.execute(
            sa.delete(table).where(
                table.c.dataset_id == staged_dataset_id,
                table.c.is_deleted == sa.false(),
                bucket.in_(sorted(overlap)),
            )
        )
    kept_file_rows = await _count(
        db, table, table.c.dataset_id == staged_dataset_id, table.c.is_deleted == sa.false()
    )
    copy_buckets = base_buckets if strategy == "skip" else base_buckets - file_buckets
    copied_rows = 0
    mapped_ids: dict[UUID, UUID] = {}
    batches = sorted(copy_buckets)
    if _dialect_name(db) == "postgresql":
        # 百万行真实账单条 INSERT 超过 5 分钟；按月分批降低单语句时长并可报告进度。
        for index, month in enumerate(batches, start=1):
            source_where = sa.and_(
                table.c.dataset_id == base_dataset_id,
                table.c.is_deleted == sa.false(),
                _bucket_where(table, year, month),
            )
            month_maps = await _override_id_map(
                db,
                table=table,
                base_dataset_id=base_dataset_id,
                source_where=source_where,
            )
            mapped_ids.update(month_maps)
            copied_rows += await _copy_rows(
                db,
                table=table,
                source_where=source_where,
                staged_dataset_id=staged_dataset_id,
                inherited_batch_id=inherited_batch_id,
                mapped_ids=month_maps,
            )
            if progress_callback:
                await progress_callback(table.name, index, len(batches))
    else:
        source_where = sa.and_(
            table.c.dataset_id == base_dataset_id,
            table.c.is_deleted == sa.false(),
            bucket.in_(batches) if batches else sa.false(),
        )
        mapped_ids = await _override_id_map(
            db,
            table=table,
            base_dataset_id=base_dataset_id,
            source_where=source_where,
        )
        copied_rows = await _copy_rows(
            db,
            table=table,
            source_where=source_where,
            staged_dataset_id=staged_dataset_id,
            inherited_batch_id=inherited_batch_id,
            mapped_ids=mapped_ids,
        )
    id_maps[table.name] = mapped_ids
    expected = kept_file_rows + copied_rows
    actual = await _count(db, table, table.c.dataset_id == staged_dataset_id, table.c.is_deleted == sa.false())
    if actual != expected:
        raise MergeRowCountError(f"{table.name} 行数守恒失败：expected={expected} actual={actual}")
    return TableMergeReport(
        initial_file_rows=initial_file_rows,
        kept_file_rows=kept_file_rows,
        copied_rows=copied_rows,
        expected_rows=expected,
        actual_rows=actual,
        file_months=_public_months(file_buckets),
        base_months=_public_months(base_buckets),
        inherited_months=_public_months(copy_buckets),
        skipped_months=_public_months(overlap if strategy == "skip" else set()),
        overwritten_months=_public_months(overlap if strategy == "overwrite" else set()),
        undated_file_rows=initial_undated,
        undated_base_rows=base_undated,
    )
async def _merge_snapshot_table(
    db: AsyncSession,
    *,
    model: type,
    project_id: UUID,
    base_dataset_id: UUID,
    staged_dataset_id: UUID,
    inherited_batch_id: UUID,
    id_maps: dict[str, dict[UUID, UUID]],
) -> TableMergeReport:
    table = model.__table__
    staged_where = sa.and_(table.c.dataset_id == staged_dataset_id, table.c.is_deleted == sa.false())
    initial = await _count(db, table, staged_where)
    copied = 0
    mapped_ids: dict[UUID, UUID] = {}
    if initial == 0:
        source_where = sa.and_(table.c.dataset_id == base_dataset_id, table.c.is_deleted == sa.false())
        mapped_ids = await _override_id_map(
            db, table=table, base_dataset_id=base_dataset_id, source_where=source_where
        )
        copied = await _copy_rows(
            db,
            table=table,
            source_where=source_where,
            staged_dataset_id=staged_dataset_id,
            inherited_batch_id=inherited_batch_id,
            mapped_ids=mapped_ids,
        )
    id_maps[table.name] = mapped_ids
    expected = initial + copied
    actual = await _count(db, table, staged_where)
    if actual != expected:
        raise MergeRowCountError(f"{table.name} 行数守恒失败：expected={expected} actual={actual}")
    return TableMergeReport(
        initial_file_rows=initial,
        kept_file_rows=initial,
        copied_rows=copied,
        expected_rows=expected,
        actual_rows=actual,
        carried=initial == 0 and copied > 0,
    )


async def _merge_account_chart(
    db: AsyncSession,
    *,
    project_id: UUID,
    base_dataset_id: UUID,
    staged_dataset_id: UUID,
    inherited_batch_id: UUID,
    id_maps: dict[str, dict[UUID, UUID]],
) -> TableMergeReport:
    table = AccountChart.__table__
    staged_where = sa.and_(
        table.c.project_id == project_id,
        table.c.dataset_id == staged_dataset_id,
        table.c.source == AccountSource.client,
        table.c.is_deleted == sa.false(),
    )
    initial = await _count(db, table, staged_where)
    copied = 0
    mapped_ids: dict[UUID, UUID] = {}
    if initial == 0:
        specific = sa.and_(
            table.c.project_id == project_id,
            table.c.dataset_id == base_dataset_id,
            table.c.source == AccountSource.client,
            table.c.is_deleted == sa.false(),
        )
        if await _count(db, table, specific):
            source_where = specific
        else:
            # 兼容 V036~V063 的项目级客户科目；复制后正式纳入 staged 版本。
            source_where = sa.and_(
                table.c.project_id == project_id,
                table.c.dataset_id.is_(None),
                table.c.source == AccountSource.client,
                table.c.is_deleted == sa.false(),
            )
        mapped_ids = await _override_id_map(
            db, table=table, base_dataset_id=base_dataset_id, source_where=source_where
        )
        copied = await _copy_rows(
            db,
            table=table,
            source_where=source_where,
            staged_dataset_id=staged_dataset_id,
            inherited_batch_id=inherited_batch_id,
            mapped_ids=mapped_ids,
        )
    id_maps[table.name] = mapped_ids
    expected = initial + copied
    actual = await _count(db, table, staged_where)
    if actual != expected:
        raise MergeRowCountError(f"account_chart 行数守恒失败：expected={expected} actual={actual}")
    return TableMergeReport(
        initial_file_rows=initial,
        kept_file_rows=initial,
        copied_rows=copied,
        expected_rows=expected,
        actual_rows=actual,
        carried=initial == 0 and copied > 0,
    )
async def _merge_direction_overrides(
    db: AsyncSession,
    *,
    project_id: UUID,
    base_dataset_id: UUID,
    staged_dataset_id: UUID,
    id_maps: dict[str, dict[UUID, UUID]],
) -> TableMergeReport:
    table = DirectionOverride.__table__
    staged_where = sa.and_(table.c.project_id == project_id, table.c.dataset_id == staged_dataset_id)
    initial = await _count(db, table, staged_where)
    copied = 0
    if initial == 0:
        rows = (
            await db.execute(
                sa.select(table).where(
                    table.c.project_id == project_id,
                    table.c.dataset_id == base_dataset_id,
                )
            )
        ).mappings().all()
        payloads: list[dict[str, Any]] = []
        for row in rows:
            target_id = id_maps.get(row["table_name"], {}).get(row["record_id"])
            if target_id is None:
                continue
            payload = {
                column.name: row[column.name]
                for column in table.c
                if column.name not in {"id", "dataset_id", "record_id", "created_at", "updated_at"}
            }
            payload.update(id=uuid.uuid4(), dataset_id=staged_dataset_id, record_id=target_id)
            payloads.append(payload)
        if payloads:
            await db.execute(sa.insert(table), payloads)
            copied = len(payloads)
    expected = initial + copied
    actual = await _count(db, table, staged_where)
    if actual != expected:
        raise MergeRowCountError(f"direction_override 行数守恒失败：expected={expected} actual={actual}")
    return TableMergeReport(
        initial_file_rows=initial,
        kept_file_rows=initial,
        copied_rows=copied,
        expected_rows=expected,
        actual_rows=actual,
        carried=initial == 0 and copied > 0,
    )
