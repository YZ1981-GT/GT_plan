"""底稿下载与导入 API — Phase 10 Task 1.1-1.2

- POST /api/projects/{id}/workpapers/download-pack   批量打包下载
- GET  /api/projects/{id}/workpapers/{wp_id}/download-file  单个下载
- POST /api/projects/{id}/workpapers/{wp_id}/upload-file    上传回传
- GET  /api/projects/{id}/workpapers/{wp_id}/check-version  版本检查
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.phase10_schemas import DownloadPackRequest, UploadWorkpaperRequest
from app.services.wp_download_service import WpDownloadService, WpUploadService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["wp-download"])


@router.post("/workpapers/download-pack")
async def download_pack(
    project_id: UUID,
    body: DownloadPackRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量打包下载底稿为 ZIP"""
    svc = WpDownloadService()
    try:
        buf = await svc.download_pack(
            db=db,
            project_id=project_id,
            wp_ids=body.wp_ids,
            include_prefill=body.include_prefill,
        )
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=workpapers.zip"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/workpapers/{wp_id}/download-file")
async def download_single(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """单个底稿下载"""
    svc = WpDownloadService()
    try:
        info = await svc.download_single(db=db, project_id=project_id, wp_id=wp_id)
        from pathlib import Path
        file_path = Path(info["file_path"])
        return StreamingResponse(
            open(file_path, "rb"),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{info["file_name"]}"',
                "X-WP-Version": str(info["file_version"]),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/workpapers/{wp_id}/check-version")
async def check_version(
    project_id: UUID,
    wp_id: UUID,
    uploaded_version: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """检查版本冲突"""
    svc = WpUploadService()
    try:
        return await svc.check_version_conflict(db=db, wp_id=wp_id, uploaded_version=uploaded_version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/workpapers/{wp_id}/upload-file")
async def upload_file(
    project_id: UUID,
    wp_id: UUID,
    file: UploadFile = File(...),
    uploaded_version: int = Query(...),
    force_overwrite: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """上传离线编辑的底稿文件"""
    svc = WpUploadService()
    content = await file.read()
    try:
        result = await svc.upload_file(
            db=db,
            project_id=project_id,
            wp_id=wp_id,
            file_content=content,
            uploaded_version=uploaded_version,
            force_overwrite=force_overwrite,
        )
        if result.get("status") == "conflict":
            raise HTTPException(status_code=409, detail=result)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/workpapers/{wp_id}/cloud-url")
async def get_cloud_url(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取底稿的云端访问 URL（供其他用户直接打开原始文档）"""
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.models.core import Project
    from app.services.cloud_storage_service import CloudStorageService
    from pathlib import Path

    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.id == wp_id, WorkingPaper.project_id == project_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="底稿不存在")
    wp, idx = row

    proj_r = await db.execute(sa.select(Project).where(Project.id == project_id))
    proj = proj_r.scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    pname = proj.client_name or "unknown"
    ws = proj.wizard_state or {}
    yr = ws.get("steps", {}).get("basic_info", {}).get("data", {}).get("audit_year", 2025)

    file_path = Path(wp.file_path)
    try:
        rel_path = str(file_path.relative_to(Path("storage") / "projects" / str(project_id)))
    except ValueError:
        rel_path = file_path.name

    svc = CloudStorageService()
    url = svc.get_cloud_url(project_id, pname, yr, rel_path)
    return {
        "wp_id": str(wp_id),
        "wp_code": idx.wp_code,
        "cloud_url": url,
        "file_version": wp.file_version,
    }
