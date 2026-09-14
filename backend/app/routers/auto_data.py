"""通用 auto_data_source resolver API 端点.

GET /api/projects/{project_id}/auto-data/{source}
供前端直接调用注册的 resolver（如 a15_financial_ratios）。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.auto_data_resolvers import resolve_auto_data_source

router = APIRouter(prefix="/api/projects/{project_id}/auto-data", tags=["auto-data"])


@router.get("/{source}")
async def get_auto_data(
    project_id: UUID,
    source: str,
    year: int = Query(..., description="审计年度"),
    db: AsyncSession = Depends(get_db),
):
    """调用注册的 auto_data_source resolver 返回结果。"""
    result = await resolve_auto_data_source(db, project_id, year, source)
    if result is None:
        return {"summary": f"未注册的数据源: {source}", "_error": True}
    return result
