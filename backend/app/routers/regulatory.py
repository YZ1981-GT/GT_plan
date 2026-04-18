"""监管对接 API 路由

- POST /api/regulatory/cicpa-report           — 提交中注协审计报告备案
- POST /api/regulatory/archival-standard      — 提交电子底稿归档标准
- GET  /api/regulatory/filings/{id}/status    — 查询备案状态
- POST /api/regulatory/filings/{id}/retry     — 重试失败的备案
- GET  /api/regulatory/filings                — 列出所有备案

Validates: Requirements 8.7
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.regulatory_service import RegulatoryService

router = APIRouter(tags=["regulatory"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CICPAReportRequest(BaseModel):
    project_id: UUID
    submission_data: dict | None = None


class ArchivalStandardRequest(BaseModel):
    project_id: UUID
    submission_data: dict | None = None


class FilingResponseRequest(BaseModel):
    new_status: str
    response_data: dict | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/regulatory/cicpa-report")
async def submit_cicpa_report(
    body: CICPAReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交中注协审计报告备案"""
    svc = RegulatoryService()
    try:
        result = await svc.submit_cicpa_report(
            db,
            project_id=body.project_id,
            submission_data=body.submission_data,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/regulatory/archival-standard")
async def submit_archival_standard(
    body: ArchivalStandardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交电子底稿归档标准"""
    svc = RegulatoryService()
    try:
        result = await svc.submit_archival_standard(
            db,
            project_id=body.project_id,
            submission_data=body.submission_data,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/regulatory/filings/{filing_id}/status")
async def get_filing_status(
    filing_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询备案状态"""
    svc = RegulatoryService()
    try:
        return await svc.check_filing_status(db, filing_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/regulatory/filings/{filing_id}/retry")
async def retry_filing(
    filing_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重试失败的备案"""
    svc = RegulatoryService()
    try:
        result = await svc.retry_filing(db, filing_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/regulatory/filings")
async def list_filings(
    project_id: UUID | None = Query(None),
    filing_type: str | None = Query(None),
    filing_status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出所有备案记录"""
    svc = RegulatoryService()
    return await svc.list_filings(
        db,
        project_id=project_id,
        filing_type=filing_type,
        filing_status=filing_status,
    )


@router.post("/api/regulatory/filings/{filing_id}/response")
async def handle_filing_response(
    filing_id: UUID,
    body: FilingResponseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """处理备案响应（状态更新）"""
    svc = RegulatoryService()
    try:
        result = await svc.handle_filing_response(
            db,
            filing_id=filing_id,
            new_status=body.new_status,
            response_data=body.response_data,
            error_message=body.error_message,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
