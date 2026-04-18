"""WOPI API 路由 — CheckFileInfo / GetFile / PutFile / Lock/Unlock/RefreshLock

支持两种模式：
1. 新版 working_paper 集成模式 (file_id 为 UUID)
2. 旧版 POC 文件模式 (file_id 为文件名字符串)

通过 X-WOPI-Override 头区分 Lock/Unlock/RefreshLock 操作。

Validates: Requirements 3.1, 3.2, 3.3, 3.7
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.wopi_service import WOPIHostService

router = APIRouter(tags=["WOPI"])


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# CheckFileInfo
# ---------------------------------------------------------------------------

@router.get("/files/{file_id}")
async def wopi_check_file_info(
    file_id: str,
    access_token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """CheckFileInfo — 返回文件元信息 JSON。"""
    if _is_uuid(file_id):
        svc = WOPIHostService()
        try:
            # Validate token if provided
            user_id = None
            if access_token:
                try:
                    token_data = svc.validate_access_token(access_token)
                    user_id = UUID(token_data["user_id"])
                except ValueError:
                    return JSONResponse(status_code=401, content={"message": "令牌无效"})
            info = await svc.check_file_info(db, UUID(file_id), user_id)

            # 功能开关：online_editing 关闭时强制只读
            from app.services.feature_flags import is_enabled
            # 从底稿获取 project_id
            from app.models.workpaper_models import WorkingPaper
            import sqlalchemy as sa
            wp_result = await db.execute(
                sa.select(WorkingPaper.project_id).where(WorkingPaper.id == UUID(file_id))
            )
            wp_row = wp_result.first()
            project_id = str(wp_row[0]) if wp_row else None
            if not is_enabled("online_editing", project_id):
                info["ReadOnly"] = True
                info["UserCanWrite"] = False
                info["UserCanNotWriteRelative"] = True

            return JSONResponse(content=info)
        except FileNotFoundError:
            return JSONResponse(status_code=404, content={"message": f"底稿不存在: {file_id}"})
    else:
        # Legacy POC mode
        from pathlib import Path
        from app.core.config import settings
        poc_dir = Path(settings.STORAGE_ROOT) / "poc"
        file_path = poc_dir / file_id
        if not file_path.is_file():
            return JSONResponse(status_code=404, content={"message": f"文件不存在: {file_id}"})
        stat = file_path.stat()
        return JSONResponse(content={
            "BaseFileName": file_path.name,
            "Size": stat.st_size,
            "UserCanWrite": True,
            "UserCanNotWriteRelative": False,
            "Version": str(int(stat.st_mtime)),
            "LastModifiedTime": stat.st_mtime,
        })


# ---------------------------------------------------------------------------
# GetFile
# ---------------------------------------------------------------------------

@router.get("/files/{file_id}/contents")
async def wopi_get_file(
    file_id: str,
    access_token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """GetFile — 返回文件二进制内容。"""
    if _is_uuid(file_id):
        svc = WOPIHostService()
        try:
            content = await svc.get_file(db, UUID(file_id))
            return Response(content=content, media_type="application/octet-stream")
        except FileNotFoundError:
            return JSONResponse(status_code=404, content={"message": f"底稿不存在: {file_id}"})
    else:
        from pathlib import Path
        from app.core.config import settings
        poc_dir = Path(settings.STORAGE_ROOT) / "poc"
        file_path = poc_dir / file_id
        if not file_path.is_file():
            return JSONResponse(status_code=404, content={"message": f"文件不存在: {file_id}"})
        return Response(content=file_path.read_bytes(), media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# PutFile
# ---------------------------------------------------------------------------

@router.post("/files/{file_id}/contents")
async def wopi_put_file(
    file_id: str,
    request: Request,
    access_token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """PutFile — 接收原始字节并保存文件内容。"""
    body = await request.body()

    if _is_uuid(file_id):
        svc = WOPIHostService()
        lock_id = request.headers.get("X-WOPI-Lock")
        try:
            result = await svc.put_file(db, UUID(file_id), body, lock_id)
            await db.commit()
            return JSONResponse(content=result)
        except FileNotFoundError:
            return JSONResponse(status_code=404, content={"message": f"底稿不存在: {file_id}"})
        except PermissionError as e:
            return JSONResponse(status_code=409, content={"message": str(e)})
    else:
        from pathlib import Path
        from app.core.config import settings
        poc_dir = Path(settings.STORAGE_ROOT) / "poc"
        poc_dir.mkdir(parents=True, exist_ok=True)
        (poc_dir / file_id).write_bytes(body)
        return JSONResponse(content={"message": "文件保存成功"})


# ---------------------------------------------------------------------------
# Lock / Unlock / RefreshLock (via X-WOPI-Override header)
# ---------------------------------------------------------------------------

@router.post("/files/{file_id}")
async def wopi_lock_operations(
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Lock/Unlock/RefreshLock — 通过 X-WOPI-Override 头区分操作。

    Validates: Requirements 3.3
    """
    override = request.headers.get("X-WOPI-Override", "").upper()
    lock_id = request.headers.get("X-WOPI-Lock", "")

    if not _is_uuid(file_id):
        return JSONResponse(status_code=400, content={"message": "锁操作仅支持 UUID file_id"})

    svc = WOPIHostService()
    uid = UUID(file_id)

    if override == "LOCK":
        result = svc.lock(uid, lock_id)
    elif override == "UNLOCK":
        result = svc.unlock(uid, lock_id)
    elif override == "REFRESH_LOCK":
        result = svc.refresh_lock(uid, lock_id)
    else:
        return JSONResponse(status_code=400, content={
            "message": f"未知操作: {override}，支持 LOCK/UNLOCK/REFRESH_LOCK"
        })

    if result.get("success"):
        return JSONResponse(content=result)
    else:
        status = result.get("status", 409)
        return JSONResponse(status_code=status, content=result)
