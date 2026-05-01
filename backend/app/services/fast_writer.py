from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa

logger = logging.getLogger(__name__)


def _copy_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, UUID):
        return value
    return value


def _build_payload(
    columns: list[str],
    rows: list[dict],
    project_id: UUID,
    year: int,
    import_batch_id: UUID,
    *,
    is_deleted: bool,
    dataset_id: UUID | None = None,
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        record = {
            "id": uuid.uuid4(),
            "project_id": project_id,
            "year": year,
            "import_batch_id": import_batch_id,
            "dataset_id": dataset_id,
            "is_deleted": is_deleted,
        }
        for col in columns:
            record[col] = _copy_value(row.get(col))
        payload.append(record)
    return payload


async def copy_insert(
    db,
    table_name: str,
    columns: list[str],
    rows: list[dict],
    project_id: UUID,
    year: int,
    import_batch_id: UUID,
    *,
    is_deleted: bool = False,
    dataset_id: UUID | None = None,
) -> int:
    if not rows:
        return 0

    payload = _build_payload(
        columns,
        rows,
        project_id,
        year,
        import_batch_id,
        is_deleted=is_deleted,
        dataset_id=dataset_id,
    )
    all_columns = ["id", "project_id", "year", "import_batch_id", "dataset_id", "is_deleted", *columns]

    try:
        conn = await db.connection()
        raw_conn = await conn.get_raw_connection()
        driver_conn = getattr(raw_conn, "driver_connection", None)
        if driver_conn is not None and hasattr(driver_conn, "copy_records_to_table"):
            records = [tuple(record.get(col) for col in all_columns) for record in payload]
            await driver_conn.copy_records_to_table(
                table_name,
                records=records,
                columns=all_columns,
            )
            return len(payload)
    except Exception as exc:
        logger.warning("copy_insert fallback to SQL execute for %s: %s", table_name, exc)

    table = sa.table(table_name, *[sa.column(col) for col in all_columns])
    # SQLite doesn't support UUID/Decimal natively — convert to compatible types
    from decimal import Decimal as _Decimal
    for record in payload:
        for k, v in record.items():
            if isinstance(v, UUID):
                record[k] = str(v)
            elif isinstance(v, _Decimal):
                record[k] = float(v)
    await db.execute(table.insert(), payload)
    return len(payload)
