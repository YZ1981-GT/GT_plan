"""私人库 + 归档 + 存储统计 API — Phase 10 Task 3.1-3.3

- GET    /api/users/{id}/private-storage         文件列表
- POST   /api/users/{id}/private-storage/upload  上传
- DELETE /api/users/{id}/private-storage/{name}   删除
- GET    /api/users/{id}/private-storage/quota   容量
- POST   /api/projects/{id}/archive              归档
- GET    /api/admin/storage-stats                统计
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.private_storage_service import (
    PrivateStorageService, ProjectArchiveService, StorageStatsService,
)

router = APIRouter(tags=["private-storage"])


# ── 私人库 ────────────────────────────────────────────────

@router.get("/api/users/{user_id}/private-storage")
async def list_private_files(user_id: UUID):
    svc = PrivateStorageService()
    return await svc.list_files(user_id)


@router.post("/api/users/{user_id}/private-storage/upload")
async def upload_private_file(user_id: UUID, file: UploadFile = File(...)):
    svc = PrivateStorageService()
    content = await file.read()
    try:
        return await svc.upload_file(user_id, file.filename or "unnamed", content)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))


@router.delete("/api/users/{user_id}/private-storage/{filename}")
async def delete_private_file(user_id: UUID, filename: str):
    svc = PrivateStorageService()
    ok = await svc.delete_file(user_id, filename)
    if not ok:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"deleted": True}


@router.get("/api/users/{user_id}/private-storage/quota")
async def get_quota(user_id: UUID):
    svc = PrivateStorageService()
    return await svc.check_quota(user_id)


# ── 归档 ──────────────────────────────────────────────────

@router.post("/api/projects/{project_id}/archive")
async def archive_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ProjectArchiveService()
    result = await svc.archive_project(db, project_id)
    await db.commit()
    return result


# ── 存储统计 ──────────────────────────────────────────────

@router.get("/api/admin/storage-stats")
async def get_storage_stats():
    svc = StorageStatsService()
    return await svc.get_stats()
