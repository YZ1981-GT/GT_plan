"""安全监控 API — Phase 8 Task 10.4"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models.core import User
from app.services.security_monitor import security_monitor
from app.services.audit_logger_enhanced import audit_logger

router = APIRouter(prefix="/api", tags=["security"])


@router.get("/security/login-attempts")
async def get_login_attempts(
    username: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """获取登录尝试记录。"""
    return {"attempts": security_monitor.get_login_attempts(username, limit)}


@router.post("/security/lock-account")
async def lock_account(
    username: str,
    current_user: User = Depends(get_current_user),
):
    """锁定账户 — 设置 user.is_active=False + Redis 黑名单"""
    from sqlalchemy import select, update as sa_update
    from app.models.core import User as UserModel

    # 查找用户
    result = await db.execute(
        select(UserModel).where(UserModel.username == username)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"用户 {username} 不存在")

    # 锁定：设置 is_active=False
    user.is_active = False
    await db.flush()

    # 写入 Redis 黑名单使现有 token 立即失效
    try:
        from app.core.redis import redis_client
        if redis_client:
            await redis_client.setex(f"account_locked:{user.id}", 86400, "1")  # 24h
    except Exception:
        pass

    await db.commit()

    # 写审计日志
    try:
        from app.services.trace_event_service import trace_event_service, generate_trace_id
        await trace_event_service.write(
            db=db,
            project_id=user.id,
            event_type="account_locked",
            object_type="user",
            object_id=user.id,
            actor_id=current_user.id,
            action=f"lock_account:{username}",
            trace_id=generate_trace_id(),
        )
    except Exception:
        pass

    return {"username": username, "locked": True, "message": "账户已锁定，现有会话将在刷新时失效"}


@router.get("/security/sessions")
async def get_sessions(
    user_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """获取活跃会话列表。"""
    return {"sessions": security_monitor.get_active_sessions(user_id)}


@router.get("/audit-logs/export")
async def export_audit_logs(
    format: str = "csv",
    user_id: str | None = None,
    action: str | None = None,
    limit: int = 1000,
    current_user: User = Depends(get_current_user),
):
    """导出审计日志。"""
    from fastapi.responses import Response

    logs = audit_logger.query_logs(user_id=user_id, action=action, limit=limit)
    content = audit_logger.export_csv(logs)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )
