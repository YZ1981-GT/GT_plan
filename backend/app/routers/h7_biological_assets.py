"""H7 生产性生物资产 — 路由（4端点）.

Spec: .kiro/specs/h7-biological-assets/ Task 5.2
Requirements: 3.4, 13.3

端点：
- GET  /h7/export-template  导出模板
- GET  /h7/export-data      导出数据
- POST /h7/import-data      导入数据
- GET  /h7/industry-check   行业适用性校验
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.h7_biological_assets_service import (
    check_industry_applicability,
    export_h7_template,
    export_h7_data,
    import_h7_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers/{wp_id}/h7", tags=["h7-biological-assets"])


@router.get("/industry-check")
async def industry_check(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
):
    """检查项目行业适用性（农林牧渔）."""
    result = await check_industry_applicability(wp_id, db)
    return {"data": result}


@router.get("/export-template")
async def export_template(
    wp_id: str,
    sheet: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """导出H7底稿模板（空表结构）."""
    content, filename = await export_h7_template(wp_id, sheet, db)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/export-data")
async def export_data(
    wp_id: str,
    sheet: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """导出H7底稿数据（含已填数据）."""
    content, filename = await export_h7_data(wp_id, sheet, db)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("/import-data")
async def import_data(
    wp_id: str,
    file: UploadFile = File(...),
    sheet: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """导入H7底稿数据."""
    result = await import_h7_data(wp_id, file, sheet, db)
    return {"data": result}
