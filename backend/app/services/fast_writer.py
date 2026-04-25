# -*- coding: utf-8 -*-
"""高性能数据库写入 — 使用 PostgreSQL COPY 命令

COPY FROM STDIN 比 INSERT 快 5-10 倍，适合百万行级别的批量写入。
通过 asyncpg 的 raw connection 直接执行 COPY。
"""

import csv
import io
import logging
import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def _format_value(v: Any) -> str:
    """将 Python 值转为 COPY 格式的字符串。"""
    if v is None:
        return r"\N"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, _uuid.UUID):
        return str(v)
    # 字符串：转义制表符和换行符
    s = str(v)
    s = s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    return s


async def copy_insert(
    db_session,
    table_name: str,
    columns: list[str],
    rows: list[dict],
    project_id: _uuid.UUID,
    year: int,
    batch_id: _uuid.UUID,
    progress_callback=None,
) -> int:
    """使用 COPY FROM STDIN 批量写入数据。

    Args:
        db_session: SQLAlchemy AsyncSession
        table_name: 目标表名
        columns: 列名列表
        rows: 数据行（dict 列表）
        project_id, year, batch_id: 公共字段
        progress_callback: (written, total) -> None

    Returns:
        写入的行数
    """
    if not rows:
        return 0

    # 构建完整列列表（含公共字段）
    all_columns = ["id", "project_id", "year", "import_batch_id", "is_deleted"] + columns
    col_str = ", ".join(all_columns)

    total = len(rows)
    written = 0

    # 分批处理（每批 10 万行，避免内存过大）
    BATCH = 100000

    # 获取 raw asyncpg connection
    raw_conn = await db_session.connection()
    raw_dbapi = await raw_conn.get_raw_connection()
    # SQLAlchemy AsyncAdapt wrapper → 原生 asyncpg connection
    asyncpg_conn = raw_dbapi.driver_connection if hasattr(raw_dbapi, 'driver_connection') else raw_dbapi

    for start in range(0, total, BATCH):
        chunk = rows[start:start + BATCH]

        # 构建 TSV 数据
        buf = io.StringIO()
        for row in chunk:
            vals = [
                str(_uuid.uuid4()),  # id
                str(project_id),     # project_id
                str(year),           # year
                str(batch_id),       # import_batch_id
                "false",             # is_deleted
            ]
            for col in columns:
                vals.append(_format_value(row.get(col)))
            buf.write("\t".join(vals) + "\n")

        tsv_data = buf.getvalue().encode("utf-8")
        buf.close()

        # 执行 COPY
        try:
            result = await asyncpg_conn.copy_to_table(
                table_name,
                source=io.BytesIO(tsv_data),
                columns=all_columns,
                format="text",
            )
            # result 格式: "COPY 50000"
            count = int(result.split()[-1]) if result else len(chunk)
            written += count
        except Exception as e:
            logger.warning("COPY 失败，降级为 INSERT: %s", e)
            # COPY 失败后事务已 abort，必须先 rollback 再降级
            try:
                await asyncpg_conn.execute("ROLLBACK")
                await asyncpg_conn.execute("BEGIN")
            except Exception:
                pass
            # 降级为普通 INSERT（通过 SQLAlchemy 执行）
            import sqlalchemy as sa
            tbl = sa.table(table_name, *[sa.column(c) for c in all_columns])
            insert_records = []
            for row in chunk:
                rec = {
                    "id": _uuid.uuid4(), "project_id": project_id,
                    "year": year, "import_batch_id": batch_id, "is_deleted": False,
                }
                for col in columns:
                    rec[col] = row.get(col)
                insert_records.append(rec)
            # 分批 INSERT（避免单条逐行太慢）
            IBATCH = 5000
            for i in range(0, len(insert_records), IBATCH):
                await db_session.execute(tbl.insert(), insert_records[i:i + IBATCH])
            await db_session.flush()
            written += len(chunk)

        if progress_callback:
            progress_callback(written, total)

    return written
