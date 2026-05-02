"""WOPI API 路由 — CheckFileInfo / GetFile / PutFile / Lock/Unlock/RefreshLock

保留向后兼容（底稿编辑已迁移至 Univer 纯前端方案）。
支持两种模式：
1. 新版 working_paper 集成模式 (file_id 为 UUID)
2. 旧版 POC 文件模式 (file_id 为文件名字符串)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.deps import get_current_user
from app.models.core import User
from app.services.wopi_service import WOPIHostService

router = APIRouter(tags=["WOPI"])


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


async def _validate_wopi_access(
    db: AsyncSession,
    file_id: str,
    access_token: str | None,
):
    if not access_token:
        return None, JSONResponse(status_code=401, content={"message": "缺少访问令牌"})

    svc = WOPIHostService()
    try:
        token_data = svc.validate_access_token(access_token)
    except ValueError:
        return None, JSONResponse(status_code=401, content={"message": "令牌无效"})

    if token_data.get("file_id") not in (None, file_id):
        return None, JSONResponse(status_code=403, content={"message": "访问令牌与文件不匹配"})

    from app.services.feature_flags import is_enabled

    project_id = token_data.get("project_id")
    if not is_enabled("online_editing", project_id):
        return None, JSONResponse(status_code=403, content={"message": "在线编辑未启用"})

    return token_data, None


def _ensure_ops_access(current_user: User):
    if current_user.role.value not in ("admin", "partner", "manager"):
        return JSONResponse(status_code=403, content={"message": "权限不足"})
    return None


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
        token_data, error_response = await _validate_wopi_access(db, file_id, access_token)
        if error_response:
            return error_response
        try:
            user_id = UUID(token_data["user_id"])
            info = await svc.check_file_info(db, UUID(file_id), user_id)

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
        _, error_response = await _validate_wopi_access(db, file_id, access_token)
        if error_response:
            return error_response
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
        _, error_response = await _validate_wopi_access(db, file_id, access_token)
        if error_response:
            return error_response
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
    access_token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Lock/Unlock/RefreshLock — 通过 X-WOPI-Override 头区分操作。

    Validates: Requirements 3.3
    """
    override = request.headers.get("X-WOPI-Override", "").upper()
    lock_id = request.headers.get("X-WOPI-Lock", "")

    if not _is_uuid(file_id):
        return JSONResponse(status_code=400, content={"message": "锁操作仅支持 UUID file_id"})

    _, error_response = await _validate_wopi_access(db, file_id, access_token)
    if error_response:
        return error_response

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


# ---------------------------------------------------------------------------
# 管理员强制解锁 + 编辑会话监控
# ---------------------------------------------------------------------------

@router.delete("/files/{file_id}/lock")
async def force_unlock(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员强制解锁（不需要 lock_id）"""
    error_response = _ensure_ops_access(current_user)
    if error_response:
        return error_response
    if not _is_uuid(file_id):
        return JSONResponse(status_code=400, content={"message": "仅支持 UUID file_id"})

    file_key = file_id
    from app.services.wopi_service import _locks, _get_redis

    # 清除 Redis 锁
    r = _get_redis()
    if r:
        try:
            await r.delete(f"wopi:lock:{file_key}")
        except Exception:
            pass

    # 清除内存锁
    if file_key in _locks:
        del _locks[file_key]

    return JSONResponse(content={"success": True, "message": "锁已强制释放"})


@router.get("/files/{file_id}/lock-status")
async def get_lock_status(
    file_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询文件锁状态（运维监控用）"""
    error_response = _ensure_ops_access(current_user)
    if error_response:
        return error_response
    if not _is_uuid(file_id):
        return JSONResponse(status_code=400, content={"message": "仅支持 UUID file_id"})

    from app.services.wopi_service import _locks, _get_redis
    import time

    file_key = file_id
    result = {"file_id": file_id, "locked": False}

    # 检查 Redis
    r = _get_redis()
    if r:
        try:
            redis_lock = await r.get(f"wopi:lock:{file_key}")
            if redis_lock:
                ttl = await r.ttl(f"wopi:lock:{file_key}")
                result["locked"] = True
                result["lock_source"] = "redis"
                result["lock_id"] = redis_lock.decode() if isinstance(redis_lock, bytes) else redis_lock
                result["ttl_seconds"] = ttl
                return JSONResponse(content=result)
        except Exception:
            pass

    # 检查内存锁
    if file_key in _locks:
        lock_info = _locks[file_key]
        remaining = lock_info["expires_at"] - time.time()
        if remaining > 0:
            result["locked"] = True
            result["lock_source"] = "memory"
            result["lock_id"] = lock_info["lock_id"]
            result["ttl_seconds"] = int(remaining)
        else:
            del _locks[file_key]

    return JSONResponse(content=result)


@router.get("/health")
async def wopi_health():
    """WOPI 服务健康检查 — 前端用于探测在线编辑可用性"""
    import urllib.request
    import urllib.error

    onlyoffice_url = settings.ONLYOFFICE_URL.rstrip("/")
    try:
        req = urllib.request.Request(f"{onlyoffice_url}/healthcheck")
        resp = urllib.request.urlopen(req, timeout=5)
        if resp.status == 200:
            return JSONResponse(content={"status": "ok", "service": "wopi", "onlyoffice_available": True})
    except (urllib.error.URLError, OSError, Exception):
        pass
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "service": "wopi", "onlyoffice_available": False},
    )


@router.get("/stats")
async def wopi_stats(
    current_user: User = Depends(get_current_user),
):
    """WOPI 运维统计（锁数量、活跃编辑会话）"""
    error_response = _ensure_ops_access(current_user)
    if error_response:
        return error_response
    import time
    from app.services.wopi_service import _locks, _get_redis

    # 内存锁统计
    now = time.time()
    active_memory = {k: v for k, v in _locks.items() if v["expires_at"] > now}
    expired_memory = len(_locks) - len(active_memory)

    # 清理过期内存锁
    for k in list(_locks.keys()):
        if _locks[k]["expires_at"] <= now:
            del _locks[k]

    stats = {
        "active_locks_memory": len(active_memory),
        "expired_cleaned": expired_memory,
    }

    # Redis 锁统计
    r = _get_redis()
    if r:
        try:
            keys = []
            async for key in r.scan_iter(match="wopi:lock:*"):
                keys.append(key)
            stats["active_locks_redis"] = len(keys)
            stats["redis_available"] = True
        except Exception:
            stats["redis_available"] = False
    else:
        stats["redis_available"] = False

    return JSONResponse(content=stats)


# ---------------------------------------------------------------------------
# Document Server API Callback（非 WOPI 协议，DS API 保存回调）
# ---------------------------------------------------------------------------

@router.post("/ds-callback/{file_id}")
async def ds_callback(
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Document Server 保存回调端点（向后兼容）。

    保留用于 WOPI 协议兼容，底稿编辑已迁移至 Univer。
    POST JSON: { "status": 2, "url": "http://...", "key": "..." }
    status=2 表示文档已修改并准备好下载。
    """
    import httpx
    import logging
    _log = logging.getLogger(__name__)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": 0})  # DS 要求返回 {"error": 0}

    status = body.get("status", 0)
    download_url = body.get("url", "")
    doc_key = body.get("key", "")

    _log.info(f"[DS Callback] file_id={file_id} status={status} key={doc_key} url={download_url[:80]}")

    # status=2: 文档已修改，需要下载保存
    # status=6: 文档已修改但强制保存（自动保存）
    if status in (2, 6) and download_url:
        try:
            # 从 DS 下载修改后的文件
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(download_url)
            if resp.status_code != 200:
                _log.error(f"[DS Callback] download failed: {resp.status_code}")
                return JSONResponse(content={"error": 1})

            file_content = resp.content

            # 保存到本地（复用 WOPI put_file 逻辑）
            if _is_uuid(file_id):
                svc = WOPIHostService()
                await svc.put_file(db=db, file_id=UUID(file_id), content=file_content)
                await db.commit()
                _log.info(f"[DS Callback] saved {len(file_content)} bytes for {file_id}")
            else:
                _log.warning(f"[DS Callback] non-UUID file_id: {file_id}")

        except Exception as e:
            _log.error(f"[DS Callback] save error: {e}")
            return JSONResponse(content={"error": 1})

    # DS 要求返回 {"error": 0} 表示成功
    return JSONResponse(content={"error": 0})
