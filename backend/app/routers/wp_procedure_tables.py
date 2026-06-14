"""程序表数据端点（前端 ProcedureTableRenderer 调用）"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.procedure_table_auto_service import ProcedureTableService

router = APIRouter(
    prefix="/api/projects/{project_id}/procedure-tables",
    tags=["procedure-tables"],
)


@router.get("/{table_code}")
async def get_procedure_table(
    project_id: UUID,
    table_code: str,
    year: int = Query(default=2025),
    business_category: str = Query(default="C"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取指定程序表的完整数据（模板 + 自动值 + 用户覆盖）"""
    svc = ProcedureTableService(db)
    return await svc.get_procedure_table(project_id, year, table_code, business_category)
