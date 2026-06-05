"""批量建项 API 路由

Feature: project-creation-enhancement, Task 8.2
Endpoints:
  - GET  /api/projects/batch-template  → 下载建项模板
  - POST /api/projects/batch-import    → 批量导入建项
  - POST /api/projects/batch-export    → 导出选中项目数据
"""

from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.batch_project_service import (
    BatchImportResult,
    export_projects,
    generate_template,
    parse_and_import,
)

router = APIRouter(prefix="/api/projects", tags=["批量建项"])


def _make_content_disposition(filename: str) -> str:
    """RFC5987 编码 Content-Disposition（支持中文文件名）。"""
    encoded = quote(filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


@router.get("/batch-template")
async def download_batch_template(
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """下载建项模板 Excel。"""
    output = await generate_template()
    filename = "建项模板.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _make_content_disposition(filename)},
    )


@router.post("/batch-import", response_model=BatchImportResult)
async def batch_import_projects(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchImportResult:
    """批量导入建项（上传 Excel 文件）。"""
    file_bytes = await file.read()
    return await parse_and_import(file_bytes, db)


class BatchExportRequest(BaseModel):
    project_ids: list[UUID]


@router.post("/batch-export")
async def batch_export_projects(
    body: BatchExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出选中项目数据为 Excel。"""
    from datetime import date as date_type

    output = await export_projects(body.project_ids, db)
    today = date_type.today().strftime("%Y%m%d")
    filename = f"项目数据导出_{today}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _make_content_disposition(filename)},
    )
