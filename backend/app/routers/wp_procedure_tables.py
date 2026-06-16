"""程序表数据端点（前端 ProcedureTableRenderer 调用）

提供：
- GET /{table_code}  单表获取
- GET /batch         批量获取多个程序表（减少前端请求数）
- POST /custom-items 持久化用户自定义程序行
- DELETE /custom-items/{item_id} 删除自定义程序行
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.procedure_table_auto_service import ProcedureTableService, list_table_codes
from app.services.field_override_service import FieldOverrideService

_logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/procedure-tables",
    tags=["procedure-tables"],
)


# ─── P1: 批量获取端点（减少前端 N 次请求） ───────────────────────────
@router.get("/batch")
async def get_procedure_tables_batch(
    project_id: UUID,
    codes: str = Query(description="逗号分隔的表编码，如 A1,A2,A3"),
    year: int = Query(default=2025),
    business_category: str = Query(default="C"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """批量获取多个程序表数据（一次请求返回多表）"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    valid_codes = set(list_table_codes())
    invalid = [c for c in code_list if c not in valid_codes]
    if invalid:
        raise HTTPException(400, f"未知程序表编码: {', '.join(invalid)}")

    svc = ProcedureTableService(db)
    results = {}
    for code in code_list:
        results[code] = await svc.get_procedure_table(project_id, year, code, business_category)
    return {"tables": results}


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


# ─── P0: 自定义程序行持久化（用户新增的程序不丢失） ─────────────────────
class CustomItemCreate(BaseModel):
    table_code: str
    year: int = 2025
    description: str
    phase: str = "completion"
    ref_index: str = ""


@router.post("/custom-items")
async def create_custom_item(
    project_id: UUID,
    body: CustomItemCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """持久化用户自定义程序行（存入 field_overrides 表）"""
    override_svc = FieldOverrideService(db)
    scope = f"procedure_table:{body.table_code}:custom_items"

    # 读取现有自定义行
    existing = await override_svc.get_batch(project_id, body.year, scope)
    # 生成新 ID
    import time
    item_id = f"custom-{int(time.time() * 1000)}"
    item_data = {
        "id": item_id,
        "description": body.description,
        "phase": body.phase,
        "ref_index": body.ref_index,
        "status": "pending",
    }
    # 存储（item_key = item_id）
    await override_svc.set(
        project_id, body.year, scope, item_id, "data", json.dumps(item_data, ensure_ascii=False)
    )
    await db.commit()
    return {"item_id": item_id, **item_data}


@router.delete("/custom-items/{item_id}")
async def delete_custom_item(
    project_id: UUID,
    item_id: str,
    table_code: str = Query(...),
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """删除用户自定义程序行"""
    import sqlalchemy as sa
    from app.models.workpaper_field_override_models import WorkpaperFieldOverride
    scope = f"procedure_table:{table_code}:custom_items"
    stmt = sa.delete(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.year == year,
        WorkpaperFieldOverride.scope == scope,
        WorkpaperFieldOverride.item_key == item_id,
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted", "item_id": item_id}
