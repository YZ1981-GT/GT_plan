"""公式审计日志 API — 记录公式变更历史，满足审计留痕要求

表结构：formula_audit_log
  - project_id + year + module + row_code 定位公式
  - action: 'create' | 'update' | 'delete' | 'execute'
  - old_formula / new_formula: 变更前后的公式
  - result_value: 执行结果（execute 类型）
  - created_by: 操作人

API:
  GET  /api/formula-audit-log/{project_id}/{year}  — 查询公式变更历史
  POST /api/formula-audit-log/{project_id}/{year}  — 记录一条日志
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/api/formula-audit-log", tags=["formula-audit-log"])

_table_created = False

async def ensure_table(db: AsyncSession):
    global _table_created
    if _table_created:
        return
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS formula_audit_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL,
                year INT NOT NULL,
                module VARCHAR(50) NOT NULL DEFAULT 'report',
                row_code VARCHAR(100) NOT NULL,
                action VARCHAR(20) NOT NULL,
                old_formula TEXT,
                new_formula TEXT,
                result_value NUMERIC,
                trace JSONB,
                created_by UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fal_proj_year ON formula_audit_log(project_id, year)"
        ))
        await db.commit()
        _table_created = True
    except Exception:
        await db.rollback()
        _table_created = True


class LogEntry(BaseModel):
    module: str = 'report'
    row_code: str
    action: str  # create | update | delete | execute
    old_formula: str = ''
    new_formula: str = ''
    result_value: float | None = None
    trace: list | None = None


@router.get("/{project_id}/{year}")
async def get_audit_log(
    project_id: str, year: int,
    module: str = '',
    row_code: str = '',
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    await ensure_table(db)
    query = "SELECT id, module, row_code, action, old_formula, new_formula, result_value, trace, created_at FROM formula_audit_log WHERE project_id = :pid AND year = :y"
    params: dict = {"pid": project_id, "y": year}
    if module:
        query += " AND module = :mod"
        params["mod"] = module
    if row_code:
        query += " AND row_code = :rc"
        params["rc"] = row_code
    query += " ORDER BY created_at DESC LIMIT :lim"
    params["lim"] = limit
    result = await db.execute(text(query), params)
    return [
        {
            "id": str(r[0]), "module": r[1], "row_code": r[2], "action": r[3],
            "old_formula": r[4], "new_formula": r[5],
            "result_value": float(r[6]) if r[6] is not None else None,
            "trace": r[7], "created_at": str(r[8]) if r[8] else None,
        }
        for r in result.fetchall()
    ]


@router.post("/{project_id}/{year}")
async def add_audit_log(
    project_id: str, year: int,
    body: LogEntry,
    db: AsyncSession = Depends(get_db),
):
    await ensure_table(db)
    import json
    now = datetime.utcnow()
    trace_json = json.dumps(body.trace, ensure_ascii=False) if body.trace else None
    await db.execute(text("""
        INSERT INTO formula_audit_log (id, project_id, year, module, row_code, action, old_formula, new_formula, result_value, trace, created_at)
        VALUES (:id, :pid, :y, :mod, :rc, :act, :of, :nf, :rv, CAST(:tr AS jsonb), :now)
    """), {
        "id": str(uuid.uuid4()), "pid": project_id, "y": year,
        "mod": body.module, "rc": body.row_code, "act": body.action,
        "of": body.old_formula, "nf": body.new_formula,
        "rv": body.result_value, "tr": trace_json, "now": now,
    })
    await db.commit()
    return {"ok": True, "created_at": str(now)}
