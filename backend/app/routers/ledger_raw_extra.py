"""GET /api/projects/{pid}/ledger/raw-extra-fields — 聚合 raw_extra 字段分布。

Per design.md §9.4 聚合查询端点：
返回 { table_name: { field_name: { row_count: N, sample_values: [...] } } }

便于用户或支持人员发现"哦原来还有部门列可以识别"，
写迁移脚本把 raw_extra 里某字段提升为标准列。

注册：Sprint 3 Task 53 统一注册到 router_registry.py。
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User

router = APIRouter(
    prefix="/api/projects/{project_id}/ledger",
    tags=["ledger-import-v2"],
)

_VALID_TABLES = ("tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger")


@router.get("/raw-extra-fields")
async def get_raw_extra_fields(
    project_id: UUID,
    year: Optional[int] = Query(None),
    table: Optional[str] = Query(None),
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate raw_extra field distribution across ledger tables.

    Query params:
        year  — filter by accounting year (optional)
        table — filter by specific table name (optional, must be one of the 4 ledger tables)

    Returns:
        { table_name: { field_name: { row_count: N, sample_values: [...] } } }
    """
    # Validate table param
    if table and table not in _VALID_TABLES:
        return {"error": f"table must be one of {_VALID_TABLES}"}

    tables = [table] if table else list(_VALID_TABLES)
    result: dict = {}

    for tbl in tables:
        # Use PG jsonb_object_keys + lateral to get field distribution
        # This is a raw SQL query for performance on large tables
        year_filter = "AND year = :year" if year else ""
        sql = text(f"""
            SELECT key, COUNT(*) as row_count,
                   (array_agg(value ORDER BY random()) FILTER (WHERE value IS NOT NULL))[1:3] as sample_values
            FROM {tbl},
                 LATERAL jsonb_each_text(raw_extra) AS kv(key, value)
            WHERE project_id = :project_id
              AND raw_extra IS NOT NULL
              {year_filter}
            GROUP BY key
            ORDER BY row_count DESC
            LIMIT 100
        """)  # noqa: S608
        params: dict = {"project_id": str(project_id)}
        if year:
            params["year"] = year

        rows = (await db.execute(sql, params)).fetchall()
        if rows:
            result[tbl] = {
                row.key: {
                    "row_count": row.row_count,
                    "sample_values": list(row.sample_values) if row.sample_values else [],
                }
                for row in rows
            }

    return result
