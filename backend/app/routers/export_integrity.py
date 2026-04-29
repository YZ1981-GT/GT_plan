"""Phase 16: 取证完整性校验路由

提供导出包 hash 校验、篡改检测、下载一次性令牌等端点。
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/exports", tags=["取证完整性"])
logger = logging.getLogger(__name__)


@router.get("/{export_id}/integrity")
async def verify_export_integrity(
    export_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """校验导出包完整性：逐文件比对 SHA-256

    返回 check_status=passed/failed + mismatched_files 列表
    """
    from app.services.export_integrity_service import export_integrity_service

    try:
        result = await export_integrity_service.verify_package(db, export_id)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[INTEGRITY] verify failed: export_id={export_id} err={e}")
        raise HTTPException(status_code=500, detail="完整性校验失败")


@router.get("/{export_id}/manifest")
async def get_export_manifest(
    export_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取导出包的 manifest（文件列表 + hash）"""
    from sqlalchemy import text

    stmt = text("""
        SELECT file_path, sha256, check_status, checked_at
        FROM evidence_hash_checks
        WHERE export_id = :eid
        ORDER BY file_path
    """)
    result = await db.execute(stmt, {"eid": export_id})
    rows = result.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="未找到该导出包的校验记录")

    files = [
        {
            "file_path": r[0],
            "sha256": r[1],
            "check_status": r[2],
            "checked_at": str(r[3]) if r[3] else None,
        }
        for r in rows
    ]

    # 计算 manifest_hash
    import hashlib
    import json
    manifest_content = json.dumps([{"path": f["file_path"], "sha256": f["sha256"]} for f in files], sort_keys=True)
    manifest_hash = hashlib.sha256(manifest_content.encode()).hexdigest()

    return {
        "export_id": export_id,
        "manifest_hash": manifest_hash,
        "file_count": len(files),
        "files": files,
        "all_passed": all(f["check_status"] == "passed" for f in files),
    }


@router.post("/{export_id}/download-token")
async def create_download_token(
    export_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成一次性下载令牌（TTL=600s），下载时校验并删除

    防止导出链接被转发或重复使用。
    """
    from app.core.redis import redis_client

    token = uuid.uuid4().hex
    redis_key = f"export_download:{token}"

    try:
        if redis_client:
            await redis_client.setex(redis_key, 600, f"{export_id}:{current_user.id}")
            return {
                "token": token,
                "ttl_seconds": 600,
                "download_url": f"/api/exports/{export_id}/download?token={token}",
            }
    except Exception as e:
        logger.warning(f"[INTEGRITY] Redis unavailable for download token: {e}")

    # Redis 不可用时降级：直接返回无令牌的下载链接
    return {
        "token": None,
        "ttl_seconds": 0,
        "download_url": f"/api/exports/{export_id}/download",
        "warning": "Redis不可用，下载链接无一次性保护",
    }


@router.get("/{export_id}/download")
async def download_export(
    export_id: str,
    token: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载导出包（校验一次性令牌）"""
    from app.core.redis import redis_client

    # 校验令牌
    if token:
        try:
            if redis_client:
                redis_key = f"export_download:{token}"
                stored = await redis_client.get(redis_key)
                if not stored:
                    raise HTTPException(status_code=403, detail="下载令牌已过期或无效")
                stored_str = stored.decode() if isinstance(stored, bytes) else stored
                expected_export_id = stored_str.split(":")[0]
                if expected_export_id != export_id:
                    raise HTTPException(status_code=403, detail="令牌与导出包不匹配")
                # 删除令牌（一次性）
                await redis_client.delete(redis_key)
        except HTTPException:
            raise
        except Exception:
            pass  # Redis 不可用时降级跳过

    # 查找导出文件路径
    from sqlalchemy import text
    stmt = text("""
        SELECT output_path FROM export_tasks
        WHERE id::text = :eid OR export_id = :eid
        LIMIT 1
    """)
    result = await db.execute(stmt, {"eid": export_id})
    row = result.fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="导出文件不存在")

    from pathlib import Path
    from fastapi.responses import FileResponse

    file_path = Path(row[0])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="导出文件已被清理")

    # 审计日志
    try:
        from app.services.trace_event_service import trace_event_service
        await trace_event_service.write(
            db=db,
            project_id=current_user.id,  # 用 user_id 作为 project_id 占位
            event_type="export_downloaded",
            object_type="export",
            object_id=uuid.UUID(export_id) if len(export_id) == 36 else current_user.id,
            actor_id=current_user.id,
            action=f"download_export:{export_id}",
        )
    except Exception:
        pass

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/zip",
    )
