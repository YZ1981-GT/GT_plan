"""QC 年度质量报告路由 — Round 3 需求 9

POST /api/qc/annual-reports?year=   — 触发异步年报生成
GET  /api/qc/annual-reports         — 列出历史年报
GET  /api/qc/annual-reports/{id}/download — 下载年报

权限：role='qc' | 'admin'
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.services.qc_annual_report_service import qc_annual_report_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qc/annual-reports", tags=["qc-annual-reports"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=202)
async def create_annual_report(
    year: int = Query(..., ge=2000, le=2100, description="报告年份"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """触发年度质量报告异步生成。

    幂等：同一年只允许一个正在运行的任务。
    如果已有 queued/running 状态的同年任务，返回该任务信息。
    """
    result = await qc_annual_report_service.generate_annual_report(
        db,
        year=year,
        user_id=current_user.id,
    )
    await db.commit()
    return result


@router.get("")
async def list_annual_reports(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """列出历史年报。"""
    return await qc_annual_report_service.list_annual_reports(
        db,
        page=page,
        page_size=page_size,
    )


@router.get("/{report_id}/download")
async def download_annual_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """下载年度质量报告文件。"""
    info = await qc_annual_report_service.get_report_download_url(db, report_id)

    if not info:
        raise HTTPException(status_code=404, detail="年报不存在")

    if info["status"] != "succeeded":
        raise HTTPException(
            status_code=409,
            detail=f"年报尚未生成完成，当前状态: {info['status']}",
        )

    file_path = info.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="年报文件不存在")

    return FileResponse(
        path=file_path,
        filename=f"qc_annual_report_{info['year']}.txt",
        media_type="application/octet-stream",
    )
