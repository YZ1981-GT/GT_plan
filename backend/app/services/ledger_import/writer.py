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
        return _sanitize_raw_extra(extra), None

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

    return _sanitize_raw_extra(truncated) if truncated else None, warning


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

    B3-D 优化：如果所有原始列都已映射到 standard_field（无未映射列），
    直接跳过 build_raw_extra 调用，raw_extra 字段不出现在 std_row 里（视为 NULL）。
    真实账套 mapping 完备时此优化节省 10-15% 写入阶段时间（1-2s / YG36）。
    """
    mapped_headers = set(column_mapping.keys())
    transformed: list[dict[str, Any]] = []
    warnings: list[LedgerImportError] = []

    # 识别多对一映射：哪些 std_field 有多个原始列来源
    std_field_sources: dict[str, list[str]] = {}
    for orig_header, std_field in column_mapping.items():
        std_field_sources.setdefault(std_field, []).append(orig_header)
    multi_source_fields = {
        sf: srcs for sf, srcs in std_field_sources.items() if len(srcs) > 1
    }

    # B3-D: 快路径判定——如果所有原始列都在 mapping 中且无多对一冲突，
    # raw_extra 一定为 None，整个 build_raw_extra 调用可跳过
    unmapped_headers = [h for h in original_headers if h not in mapped_headers]
    skip_raw_extra = not unmapped_headers and not multi_source_fields

    for raw_row in raw_rows:
        std_row: dict[str, Any] = {}
        discarded_mappings: dict[str, list[dict]] = {}

        # Map known columns to standard fields.
        # 多个原始列可能映射到同一个 standard_field（如"核算维度"和"主表项目"都→aux_dimensions），
        # 策略：首个非空值保留到 std_row[std_field]；其余非空值收集到 raw_extra["_discarded_mappings"]
        # 避免被静默丢失（design §9.4 + Sprint 6 Task S6-6）
        for orig_header, std_field in column_mapping.items():
            val = raw_row.get(orig_header)
            val_str = str(val).strip() if val is not None else ""
            existing = std_row.get(std_field)
            existing_str = str(existing).strip() if existing is not None else ""

            if not existing_str:
                # 第一个非空 → 保留
                std_row[std_field] = val
            elif val_str and std_field in multi_source_fields:
                # 已有非空值，此列又有值 → 收集为 discarded
                discarded_mappings.setdefault(std_field, []).append({
                    "header": orig_header,
                    "value": val,
                })

        # Build raw_extra from unmapped columns
        # B3-D: 快路径 skip_raw_extra=True 时直接设 None 不调 build_raw_extra
        if skip_raw_extra:
            extra, warning = None, None
        else:
            extra, warning = build_raw_extra(raw_row, mapped_headers, original_headers)

        # 合并丢弃的多对一映射值到 raw_extra["_discarded_mappings"]
        if discarded_mappings:
            if extra is None:
                extra = {}
            extra["_discarded_mappings"] = discarded_mappings

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
    "clear_project_year",
    "bulk_insert_staged",
    "bulk_copy_staged",
    "bulk_write_staged",
    "DEFAULT_INSERT_CHUNK_SIZE",
    "COPY_THRESHOLD_ROWS",
    "RAW_EXTRA_MAX_BYTES",
]


async def clear_project_year(project_id: UUID, year: int, db) -> None:
    """Soft-delete 四表 + 标记旧 ImportBatch 为 rolled_back（S6-2 从 smart_import_engine 迁出）。

    确保每个 project-year 只保留一份有效数据集，避免新旧导入混存。
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import (
        ImportBatch, ImportStatus,
        TbAuxBalance, TbAuxLedger, TbBalance, TbLedger,
    )

    for model in (TbBalance, TbLedger, TbAuxBalance, TbAuxLedger):
        tbl = model.__table__
        await db.execute(
            sa.update(tbl)
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.is_deleted == sa.false(),
            )
            .values(is_deleted=True)
        )
    await db.execute(
        sa.update(ImportBatch)
        .where(
            ImportBatch.project_id == project_id,
            ImportBatch.year == year,
            ImportBatch.status == ImportStatus.completed,
        )
        .values(status=ImportStatus.rolled_back)
    )
    await db.flush()



# ---------------------------------------------------------------------------
# S7-2: bulk_insert_staged — 通用 4 表流式插入（替代 4 个重复闭包）
# ---------------------------------------------------------------------------

# PG 参数上限 65535，保守按 25 列/行估算，chunk_size=1000 约 25000 参数
DEFAULT_INSERT_CHUNK_SIZE = 1000


def _sanitize_raw_extra(extra: dict) -> dict:
    """将 raw_extra 字典中的非 JSON 原生类型转为可序列化值。

    PG JSONB 列要求值可被 json.dumps 序列化。真实数据的 raw_extra 可能含：
    - datetime / date 对象（如"到期日"列）
    - Decimal（如未映射的金额列）
    - 其他非标准类型

    策略：递归遍历，datetime→isoformat，Decimal→float，其余→str。
    """
    from datetime import date as _date, datetime as _dt
    from decimal import Decimal as _Decimal

    sanitized: dict = {}
    for k, v in extra.items():
        if v is None:
            sanitized[k] = None
        elif isinstance(v, _dt):
            sanitized[k] = v.isoformat()
        elif isinstance(v, _date):
            sanitized[k] = v.isoformat()
        elif isinstance(v, _Decimal):
            sanitized[k] = float(v)
        elif isinstance(v, (str, int, float, bool)):
            sanitized[k] = v
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_raw_extra(v)
        elif isinstance(v, list):
            sanitized[k] = [
                _sanitize_raw_extra(item) if isinstance(item, dict)
                else (item.isoformat() if isinstance(item, (_dt, _date)) else str(item))
                for item in v
            ]
        else:
            sanitized[k] = str(v)
    return sanitized


async def bulk_insert_staged(
    db_session_factory,
    table_model,
    rows: list[dict[str, Any]],
    *,
    project_id: UUID,
    year: int,
    dataset_id: UUID,
    chunk_size: int = DEFAULT_INSERT_CHUNK_SIZE,
    is_deleted: bool = True,
    default_company_code: str = "default",
) -> int:
    """通用 staged 模式批量 insert（S7-2）。

    自动根据 table_model.__table__.columns 从每行字典里取存在的字段，
    不存在的字段跳过；同时注入公共字段（id/project_id/year/dataset_id/is_deleted）。

    Args:
        db_session_factory: `async_session` from core.database（调用方传入避免循环 import）
        table_model: SQLAlchemy ORM 模型类（TbBalance / TbLedger / TbAuxBalance / TbAuxLedger）
        rows: 已转换的数据行列表（converter 产出）
        project_id: 项目 UUID
        year: 会计年度
        dataset_id: staging dataset UUID
        chunk_size: 批大小（默认 1000）
        is_deleted: 是否写 staged（True = 隐藏，等 activate 切换；False = 直接可见）
        default_company_code: company_code 缺省值（NOT NULL 字段）

    Returns:
        实际插入行数
    """
    import uuid as _uuid
    from sqlalchemy import insert

    if not rows:
        return 0

    # 从模型拿合法字段名（SQLAlchemy 列对象）
    valid_cols = {c.name for c in table_model.__table__.columns}
    inserted = 0

    async with db_session_factory() as db:
        logger.info(
            "bulk_insert_staged → table=%s rows=%d dataset=%s chunk=%d",
            table_model.__tablename__, len(rows), dataset_id, chunk_size,
        )
        for i in range(0, len(rows), chunk_size):
            batch = rows[i:i + chunk_size]
            records = []
            for r in batch:
                # 按模型列自省过滤，只取存在的字段
                rec: dict[str, Any] = {}
                for k, v in r.items():
                    if k in valid_cols:
                        rec[k] = v
                # 注入/覆盖公共字段
                rec["id"] = _uuid.uuid4()
                rec["project_id"] = project_id
                rec["year"] = year
                rec["dataset_id"] = dataset_id
                rec["is_deleted"] = is_deleted
                # company_code NOT NULL 兜底
                if "company_code" in valid_cols and not rec.get("company_code"):
                    rec["company_code"] = default_company_code
                # currency_code 默认 CNY
                if "currency_code" in valid_cols and not rec.get("currency_code"):
                    rec["currency_code"] = "CNY"
                # raw_extra JSONB 安全序列化：datetime/date/Decimal 等非 JSON 原生类型转 str
                if "raw_extra" in rec and rec["raw_extra"] is not None:
                    rec["raw_extra"] = _sanitize_raw_extra(rec["raw_extra"])
                records.append(rec)

            if records:
                await db.execute(insert(table_model).values(records))
                inserted += len(records)
        await db.commit()

    return inserted


# ---------------------------------------------------------------------------
# B2 / Batch 3 Segment 3: PG COPY 加速大账套入库
# ---------------------------------------------------------------------------

# COPY 阈值：小于此行数走 INSERT（事务边界更清晰），大于等于此走 COPY
# 基于 YG4001-30 (4409 行 / 11 秒) / YG36 (22716 行 / 40 秒) / YG2101 (650K 行 / 20 分钟) 推算：
# - INSERT 批量 1000 行/秒（JSONB 序列化 + 参数绑定开销）
# - COPY 约 5000-10000 行/秒（asyncpg 二进制协议）
# - 阈值 10000 行以上切 COPY 能有 3-5 倍加速
COPY_THRESHOLD_ROWS = 10000


async def bulk_copy_staged(
    db_session_factory,
    table_model,
    rows: list[dict[str, Any]],
    *,
    project_id: UUID,
    year: int,
    dataset_id: UUID,
    is_deleted: bool = True,
    default_company_code: str = "default",
) -> int:
    """用 asyncpg `copy_records_to_table` 替代 INSERT，大账套加速 3-5 倍。

    B3-F 热路径优化（2026-05-10）：
    - 预计算列索引 + JSONB 列位置集合（每行 O(1) 分支判断）
    - 合并 _sanitize_raw_extra + json.dumps 为单次 _jsonb_encode
    - 直接构造 list（比构造 dict 再 values 重排快）

    与 `bulk_insert_staged` 行为兼容：字段自省过滤 / 公共字段注入 / NOT NULL 兜底
    """
    import json as _json
    import uuid as _uuid
    from datetime import datetime as _datetime, timezone as _timezone

    if not rows:
        return 0

    # 1. 预计算：列顺序、索引、JSONB 列位置、NOT NULL 兜底列位置
    columns = list(table_model.__table__.columns)
    valid_col_names = [c.name for c in columns]
    col_index = {name: i for i, name in enumerate(valid_col_names)}

    # JSONB 列索引集合（而非每行查 set）
    jsonb_indices: set[int] = set()
    for i, c in enumerate(columns):
        type_str = str(c.type).upper()
        if "JSONB" in type_str or "JSON" in type_str:
            jsonb_indices.add(i)

    # 2. 公共字段一次性准备
    now = _datetime.now(_timezone.utc).replace(tzinfo=None)
    idx_id = col_index.get("id")
    idx_project = col_index.get("project_id")
    idx_year = col_index.get("year")
    idx_dataset = col_index.get("dataset_id")
    idx_deleted = col_index.get("is_deleted")
    idx_created = col_index.get("created_at")
    idx_updated = col_index.get("updated_at")
    idx_company = col_index.get("company_code")
    idx_currency = col_index.get("currency_code")

    num_cols = len(valid_col_names)

    # 3. 构造 records（直接 list，不走中间 dict）
    records: list[list] = []
    for r in rows:
        # 初始化全 None
        row_list: list[Any] = [None] * num_cols

        # 按列名直接填入（避免遍历所有行字段再按名映射）
        for k, v in r.items():
            idx = col_index.get(k)
            if idx is not None:
                row_list[idx] = v

        # 公共字段覆盖
        if idx_id is not None:
            row_list[idx_id] = _uuid.uuid4()
        if idx_project is not None:
            row_list[idx_project] = project_id
        if idx_year is not None:
            row_list[idx_year] = year
        if idx_dataset is not None:
            row_list[idx_dataset] = dataset_id
        if idx_deleted is not None:
            row_list[idx_deleted] = is_deleted
        if idx_created is not None:
            row_list[idx_created] = now
        if idx_updated is not None:
            row_list[idx_updated] = now

        # NOT NULL 兜底
        if idx_company is not None and not row_list[idx_company]:
            row_list[idx_company] = default_company_code
        if idx_currency is not None and not row_list[idx_currency]:
            row_list[idx_currency] = "CNY"

        # JSONB 列：None 保留，否则 sanitize + json.dumps 合并
        for ji in jsonb_indices:
            val = row_list[ji]
            if val is not None:
                # B3-F: _sanitize_raw_extra 内部已做非标类型转换，但它返回 dict
                # 后续还要 json.dumps；合并为一次 json.dumps(default=_default_json)
                sanitized = _sanitize_raw_extra(val) if isinstance(val, dict) else val
                row_list[ji] = _json.dumps(sanitized, ensure_ascii=False, default=str)

        records.append(row_list)

    # 4. 拿 asyncpg raw connection 跑 copy_records_to_table
    logger.info(
        "bulk_copy_staged → table=%s rows=%d dataset=%s",
        table_model.__tablename__, len(records), dataset_id,
    )
    async with db_session_factory() as db:
        raw_conn = await db.connection()
        asyncpg_conn = await raw_conn.get_raw_connection()
        driver_conn = asyncpg_conn.driver_connection  # type: ignore[attr-defined]
        table_name = table_model.__tablename__

        await driver_conn.copy_records_to_table(
            table_name,
            records=records,
            columns=valid_col_names,
            timeout=300,
        )
        await db.commit()

    return len(records)


async def bulk_write_staged(
    db_session_factory,
    table_model,
    rows: list[dict[str, Any]],
    *,
    project_id: UUID,
    year: int,
    dataset_id: UUID,
    chunk_size: int = DEFAULT_INSERT_CHUNK_SIZE,
    is_deleted: bool = True,
    default_company_code: str = "default",
    copy_threshold: int = COPY_THRESHOLD_ROWS,
) -> int:
    """智能派发：小批 INSERT，大批 COPY。

    对现有调用方是无感切换（行为等价，只是更快）。COPY 失败自动降级 INSERT。
    """
    if len(rows) < copy_threshold:
        return await bulk_insert_staged(
            db_session_factory, table_model, rows,
            project_id=project_id, year=year, dataset_id=dataset_id,
            chunk_size=chunk_size, is_deleted=is_deleted,
            default_company_code=default_company_code,
        )
    # 大批走 COPY，失败降级 INSERT
    try:
        return await bulk_copy_staged(
            db_session_factory, table_model, rows,
            project_id=project_id, year=year, dataset_id=dataset_id,
            is_deleted=is_deleted,
            default_company_code=default_company_code,
        )
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "bulk_copy_staged failed (%s), falling back to INSERT for %d rows",
            exc, len(rows),
        )
        return await bulk_insert_staged(
            db_session_factory, table_model, rows,
            project_id=project_id, year=year, dataset_id=dataset_id,
            chunk_size=chunk_size, is_deleted=is_deleted,
            default_company_code=default_company_code,
        )
