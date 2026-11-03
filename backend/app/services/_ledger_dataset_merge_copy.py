"""ledger_dataset_merge 的低层跨方言复制实现。"""
from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import DirectionOverride


def dialect_name(db: AsyncSession) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else ""


def month_bucket(table: sa.Table) -> sa.ColumnElement:
    return sa.func.coalesce(sa.cast(sa.extract("month", table.c.voucher_date), sa.Integer), 0)


async def count_rows(db: AsyncSession, table: sa.Table, *where: sa.ColumnElement) -> int:
    result = await db.execute(sa.select(sa.func.count()).select_from(table).where(*where))
    return int(result.scalar_one() or 0)


async def month_buckets(
    db: AsyncSession,
    table: sa.Table,
    dataset_id: UUID,
) -> set[int]:
    bucket = month_bucket(table)
    result = await db.execute(
        sa.select(bucket).where(table.c.dataset_id == dataset_id, table.c.is_deleted == sa.false()).distinct()
    )
    return {int(value) for value in result.scalars().all()}


def public_months(buckets: set[int]) -> tuple[int, ...]:
    return tuple(sorted(value for value in buckets if 1 <= value <= 12))


async def override_id_map(
    db: AsyncSession,
    *,
    table: sa.Table,
    base_dataset_id: UUID,
    source_where: sa.ColumnElement,
) -> dict[UUID, UUID]:
    """仅为会被继承且存在方向覆盖的行预分配新 id。"""
    overrides = DirectionOverride.__table__
    rows = await db.execute(
        sa.select(table.c.id)
        .join(overrides, overrides.c.record_id == table.c.id)
        .where(
            overrides.c.dataset_id == base_dataset_id,
            overrides.c.table_name == table.name,
            source_where,
        )
        .distinct()
    )
    return {old_id: uuid.uuid4() for old_id in rows.scalars().all()}


def _copy_columns_and_exprs(
    table: sa.Table,
    *,
    staged_dataset_id: UUID,
    inherited_batch_id: UUID,
    mapped_ids: dict[UUID, UUID],
) -> tuple[list[str], list[sa.ColumnElement]]:
    names: list[str] = []
    exprs: list[sa.ColumnElement] = []
    id_expr: sa.ColumnElement = sa.func.gen_random_uuid()
    if mapped_ids:
        id_expr = sa.case(
            *((table.c.id == old_id, sa.literal(new_id)) for old_id, new_id in mapped_ids.items()),
            else_=sa.func.gen_random_uuid(),
        )
    for column in table.c:
        name = column.name
        if name in {"created_at", "updated_at"}:
            continue
        names.append(name)
        if name == "id":
            exprs.append(id_expr)
        elif name == "dataset_id":
            exprs.append(sa.literal(staged_dataset_id))
        elif name == "import_batch_id":
            exprs.append(sa.literal(inherited_batch_id))
        elif name == "is_deleted":
            exprs.append(sa.false())
        elif name == "deleted_at":
            exprs.append(sa.null())
        else:
            exprs.append(table.c[name])
    return names, exprs
async def copy_rows(
    db: AsyncSession,
    *,
    table: sa.Table,
    source_where: sa.ColumnElement,
    staged_dataset_id: UUID,
    inherited_batch_id: UUID,
    mapped_ids: dict[UUID, UUID],
) -> int:
    count = await count_rows(db, table, source_where)
    if count == 0:
        return 0
    if dialect_name(db) == "postgresql":
        names, exprs = _copy_columns_and_exprs(
            table,
            staged_dataset_id=staged_dataset_id,
            inherited_batch_id=inherited_batch_id,
            mapped_ids=mapped_ids,
        )
        await db.execute(
            sa.insert(table).from_select(
                names,
                sa.select(*exprs).where(source_where),
                include_defaults=False,
            )
        )
        return count

    rows = (await db.execute(sa.select(table).where(source_where))).mappings().all()
    payloads: list[dict[str, Any]] = []
    for row in rows:
        payload: dict[str, Any] = {}
        for column in table.c:
            name = column.name
            if name in {"created_at", "updated_at"}:
                continue
            if name == "id":
                payload[name] = mapped_ids.get(row[name], uuid.uuid4())
            elif name == "dataset_id":
                payload[name] = staged_dataset_id
            elif name == "import_batch_id":
                payload[name] = inherited_batch_id
            elif name == "is_deleted":
                payload[name] = False
            elif name == "deleted_at":
                payload[name] = None
            else:
                payload[name] = row[name]
        payloads.append(payload)
    await db.execute(sa.insert(table), payloads)
    return len(payloads)
