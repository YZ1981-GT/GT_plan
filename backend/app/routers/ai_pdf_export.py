"""AI PDF 导出路由

提供底稿和 AI 内容的 PDF 导出接口。
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.pdf_export_service import PDFExportService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai/pdf-export", tags=["AI-PDF导出"])


class WorkpaperPDFRequest(BaseModel):
    """底稿 PDF 导出请求"""
    workpaper_id: str


class AIContentPDFRequest(BaseModel):
    """AI 内容 PDF 导出请求"""
    project_id: str


class PDFExportResponse(BaseModel):
    """PDF 导出响应"""
    file_path: str
    ai_content_count: int
    page_count: int
    download_url: str


@router.post("/workpaper", response_model=PDFExportResponse)
async def export_workpaper_pdf(
    req: WorkpaperPDFRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PDFExportResponse:
    """导出底稿 PDF（含 AI 内容高亮标注）"""
    service = PDFExportService(db)
    workpaper_uuid = uuid.UUID(req.workpaper_id)

    output_dir = Path("exports/pdf")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"workpaper_{workpaper_uuid}_{uuid.uuid4().hex[:8]}.pdf")

    result = await service.export_workpaper_with_ai_markers(workpaper_uuid, output_path)

    return PDFExportResponse(
        file_path=result["file_path"],
        ai_content_count=result["ai_content_count"],
        page_count=result["page_count"],
        download_url=f"/api/ai/pdf-export/download?path={result['file_path']}",
    )


@router.post("/ai-content", response_model=PDFExportResponse)
async def export_ai_content_pdf(
    req: AIContentPDFRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PDFExportResponse:
    """导出项目中所有 AI 内容的独立 PDF 报告"""
    service = PDFExportService(db)
    project_uuid = uuid.UUID(req.project_id)

    output_dir = Path("exports/pdf")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"ai_content_{project_uuid}_{uuid.uuid4().hex[:8]}.pdf")

    result = await service.generate_ai_content_pdf(project_uuid, output_path)

    return PDFExportResponse(
        file_path=result["file_path"],
        ai_content_count=result["ai_content_count"],
        page_count=result["page_count"],
        download_url=f"/api/ai/pdf-export/download?path={result['file_path']}",
    )


@router.get("/download")
async def download_pdf(
    path: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """下载已导出的 PDF 文件"""
    file_path = Path(path).resolve()
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/pdf",
    )
