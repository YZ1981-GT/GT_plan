"""私人库 + 存储统计 API — Phase 10 Task 3.1-3.3

- GET    /api/users/{id}/private-storage         文件列表
- POST   /api/users/{id}/private-storage/upload  上传
- DELETE /api/users/{id}/private-storage/{name}   删除
- GET    /api/users/{id}/private-storage/quota   容量
- GET    /api/admin/storage-stats                统计
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.deps import assert_self_or_admin, get_current_user, require_role
from app.models.core import User
from app.services.private_storage_service import (
    InvalidPrivateFileName, PrivateStorageService, StorageStatsService,
)

router = APIRouter(tags=["private-storage"])


# ── 私人库：只有本人或 admin（原先不鉴权：任何人可列 / 传 / 删任意用户的私人文件）──────────

@router.get("/api/users/{user_id}/private-storage")
async def list_private_files(user_id: UUID, current_user: User = Depends(get_current_user)):
    assert_self_or_admin(current_user, user_id)
    svc = PrivateStorageService()
    return await svc.list_files(user_id)


@router.post("/api/users/{user_id}/private-storage/upload")
async def upload_private_file(
    user_id: UUID, file: UploadFile = File(...), current_user: User = Depends(get_current_user),
):
    assert_self_or_admin(current_user, user_id)
    svc = PrivateStorageService()
    content = await file.read()
    try:
        return await svc.upload_file(user_id, file.filename or "unnamed", content)
    except InvalidPrivateFileName as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))


@router.delete("/api/users/{user_id}/private-storage/{filename}")
async def delete_private_file(user_id: UUID, filename: str, current_user: User = Depends(get_current_user)):
    assert_self_or_admin(current_user, user_id)
    svc = PrivateStorageService()
    try:
        ok = await svc.delete_file(user_id, filename)
    except InvalidPrivateFileName as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"deleted": True}


@router.get("/api/users/{user_id}/private-storage/quota")
async def get_quota(user_id: UUID, current_user: User = Depends(get_current_user)):
    assert_self_or_admin(current_user, user_id)
    svc = PrivateStorageService()
    return await svc.check_quota(user_id)


# ── 存储统计 ──────────────────────────────────────────────

@router.get("/api/admin/storage-stats")
async def get_storage_stats(_admin: User = Depends(require_role(["admin"]))):
    """存储统计（仅 admin；原先不鉴权）"""
    svc = StorageStatsService()
    return await svc.get_stats()
