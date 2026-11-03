"""合并试算表 / 合并工作底稿取数器（从 ``routers/custom_query`` 原样迁入；合并项目才在指标树上可见，任务 20）。"""

from __future__ import annotations

from sqlalchemy import text


async def _query_tb_summary(db, pid, year, filters, limit):
    sheet_type = filters.get("report_type", "balance_sheet")
    result = await db.execute(
        text("SELECT data FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": pid, "y": year, "sk": f"tb_summary_{sheet_type}"},
    )
    row = result.fetchone()
    if row and isinstance(row[0], dict):
        rows = row[0].get("rows", [])[:limit]
        return {"rows": rows, "columns": ["row_code", "row_name", "unadjusted", "aje_dr", "aje_cr", "rcl_dr", "rcl_cr", "audited"], "total": len(rows)}
    return {"rows": [], "columns": [], "total": 0}


async def _query_worksheet(db, pid, year, filters, limit):
    sheet_key = filters.get("sheet_key", "info")
    result = await db.execute(
        text("SELECT data, updated_at FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": pid, "y": year, "sk": sheet_key},
    )
    row = result.fetchone()
    if row and isinstance(row[0], dict):
        data = row[0]
        rows = data.get("rows", [])[:limit]
        columns = list(rows[0].keys()) if rows else []
        return {"rows": rows, "columns": columns, "total": len(rows), "updated_at": str(row[1]) if row[1] else None}
    return {"rows": [], "columns": [], "total": 0}
