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
    """锁定账户（stub）。"""
    return {"username": username, "locked": True, "message": "账户已锁定"}


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
