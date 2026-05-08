"""写入层 — COPY 流式写入 PG + raw_extra JSONB 保留未映射列。

职责（见 design.md §9.4 / §11 / Sprint 2 Task 32/32a-c/33/34）：

- `write_chunk`          : 复用既有 `fast_writer.copy_insert`，用 asyncpg
  `copy_records_to_table` 走 STDIN（比 INSERT 快 10×），SQLAlchemy 兜底。
- `build_raw_extra`      : 一行中已映射到 `standard_field`（key 或 recommended）
  的列不再重复存；剩余按 `{原始列名: 原始值}` 写入 JSONB。
  - 单行 raw_extra 上限 8KB（PG TOAST 阈值），超限截断并生成
    `EXTRA_TRUNCATED` warning。
  - 空 dict 写 NULL，不存 `{}` 省空间。
- `prepare_rows_with_raw_extra` : 批量转换原始行 → 标准字段行 + raw_extra。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from .detection_types import ImportError as LedgerImportError
from .errors import ErrorCode, make_error

logger = logging.getLogger(__name__)

# raw_extra 单行上限 (bytes)，对齐 design §9.4
RAW_EXTRA_MAX_BYTES = 8192  # 8KB


def build_raw_extra(
    row: dict[str, Any],
    mapped_fields: set[str],
    original_headers: list[str],
) -> tuple[Optional[dict], Optional[LedgerImportError]]:
    """Build raw_extra dict from unmapped columns.

    Args:
        row: Full row dict with original column headers as keys.
        mapped_fields: Set of original column header names that have been
            mapped to standard_field (key or recommended). These are EXCLUDED
            from raw_extra.
        original_headers: All original column headers in order.

    Returns:
        (raw_extra_dict_or_None, optional_warning)
        - None if no unmapped columns or all values empty
        - dict of {original_col_name: original_value} for unmapped columns
        - Warning if truncated due to 8KB limit
    """
    extra: dict[str, Any] = {}
    for header in original_headers:
        if header in mapped_fields:
            continue
        value = row.get(header)
        if value is not None and str(value).strip():
            extra[header] = value

    if not extra:
        return None, None  # Store NULL not {} per design

    # Check size limit
    try:
        serialized = json.dumps(extra, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        serialized = json.dumps(
            {k: str(v) for k, v in extra.items()}, ensure_ascii=False
        )

    if len(serialized.encode("utf-8")) <= RAW_EXTRA_MAX_BYTES:
        return extra, None

    # Truncate: keep columns in order until we hit the limit
    truncated: dict[str, Any] = {}
    current_size = 2  # for "{}"
    warning_generated = False
    for header in original_headers:
        if header in mapped_fields:
            continue
        value = row.get(header)
        if value is None or not str(value).strip():
            continue
        # Estimate size of this entry when added to the JSON object
        entry_json = json.dumps({header: value}, ensure_ascii=False, default=str)
        entry_size = len(entry_json.encode("utf-8")) - 2  # subtract {} wrapper
        if current_size + entry_size + 1 > RAW_EXTRA_MAX_BYTES:  # +1 for comma
            warning_generated = True
            break
        truncated[header] = value
        current_size += entry_size + 1

    warning = None
    if warning_generated:
        warning = make_error(
            ErrorCode.EXTRA_TRUNCATED,
            message=(
                f"raw_extra 超过 8KB 限制，已截断"
                f"（保留前 {len(truncated)} 列，"
                f"丢弃 {len(extra) - len(truncated)} 列）"
            ),
        )

    return truncated if truncated else None, warning


async def write_chunk(
    db,
    *,
    table_name: str,
    rows: list[dict[str, Any]],
    columns: list[str],
    project_id: UUID,
    year: int,
    import_batch_id: UUID,
    dataset_id: UUID | None = None,
) -> int:
    """Write a chunk of rows to the target table using fast_writer.copy_insert.

    This is a thin wrapper around the existing fast_writer.copy_insert,
    adding the raw_extra column if present in the rows.

    Args:
        db: AsyncSession
        table_name: Target table (tb_balance/tb_ledger/tb_aux_balance/tb_aux_ledger)
        rows: List of row dicts with standard field names as keys.
            If a row has 'raw_extra' key, it will be included.
        columns: List of standard column names to write (excluding system columns
            like id/project_id/year/import_batch_id which are added by fast_writer).
            Include 'raw_extra' in this list if rows contain it.
        project_id: Project UUID
        year: Accounting year
        import_batch_id: Import batch UUID
        dataset_id: Optional dataset UUID

    Returns:
        Number of rows written.
    """
    from app.services.fast_writer import copy_insert

    return await copy_insert(
        db,
        table_name,
        columns,
        rows,
        project_id,
        year,
        import_batch_id,
        dataset_id=dataset_id,
    )


def prepare_rows_with_raw_extra(
    raw_rows: list[dict[str, Any]],
    column_mapping: dict[str, str],
    original_headers: list[str],
) -> tuple[list[dict[str, Any]], list[LedgerImportError]]:
    """Transform raw rows into standard-field rows + raw_extra.

    Args:
        raw_rows: Rows with original column headers as keys.
        column_mapping: {original_header: standard_field} for mapped columns.
        original_headers: All original headers in order.

    Returns:
        (transformed_rows, warnings)
        - Each transformed row has standard_field keys + optional 'raw_extra' key
        - Warnings list contains any EXTRA_TRUNCATED warnings
    """
    mapped_headers = set(column_mapping.keys())
    transformed: list[dict[str, Any]] = []
    warnings: list[LedgerImportError] = []

    for raw_row in raw_rows:
        std_row: dict[str, Any] = {}

        # Map known columns to standard fields
        for orig_header, std_field in column_mapping.items():
            std_row[std_field] = raw_row.get(orig_header)

        # Build raw_extra from unmapped columns
        extra, warning = build_raw_extra(raw_row, mapped_headers, original_headers)
        if extra is not None:
            std_row["raw_extra"] = extra
        else:
            std_row["raw_extra"] = None

        if warning is not None:
            warnings.append(warning)

        transformed.append(std_row)

    return transformed, warnings


async def activate_dataset(
    db,
    *,
    dataset_id: UUID,
    activated_by: UUID | None = None,
    record_summary: dict | None = None,
    validation_summary: dict | None = None,
):
    """Activate a staged dataset (atomic switch).

    Delegates to the existing DatasetService.activate() which handles:
    - Setting current active → superseded
    - Setting staged → active
    - Publishing LEDGER_DATASET_ACTIVATED event via outbox

    This is a thin convenience wrapper for the ledger_import module,
    keeping the dependency on DatasetService explicit and centralized.

    Args:
        db: AsyncSession
        dataset_id: UUID of the staged dataset to activate
        activated_by: UUID of the user performing activation (optional)
        record_summary: Optional dict with row counts per table
        validation_summary: Optional dict with validation findings summary
    """
    from app.services.dataset_service import DatasetService

    return await DatasetService.activate(
        db,
        dataset_id=dataset_id,
        activated_by=activated_by,
        record_summary=record_summary,
        validation_summary=validation_summary,
    )


__all__ = [
    "write_chunk",
    "build_raw_extra",
    "prepare_rows_with_raw_extra",
    "activate_dataset",
    "RAW_EXTRA_MAX_BYTES",
]
