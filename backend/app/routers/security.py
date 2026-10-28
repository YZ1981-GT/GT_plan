"""安全监控 API — Phase 8 Task 10.4

全部仅 admin（原先只要求登录：任何登录用户都能看登录尝试 / 会话 / 导出审计日志，锁定账户一调即 500）。
spec procedure-chain-followup-closure R1.3。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_role
from app.models.core import User
from app.schemas.auth import UserUpdate
from app.services import auth_service
from app.services.audit_logger_enhanced import audit_logger
from app.services.security_monitor import security_monitor

router = APIRouter(prefix="/api", tags=["security"])


@router.get("/security/login-attempts")
async def get_login_attempts(
    username: str | None = None,
    limit: int = 50,
    current_user: User = Depends(require_role(["admin"])),
):
    """获取登录尝试记录。"""
    return {"attempts": security_monitor.get_login_attempts(username, limit)}


@router.post("/security/lock-account")
async def lock_account(
    username: str,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """锁定账户 = 停用（与用户管理页「停用」同一逻辑：不能锁自己、至少保留一个启用的管理员）。

    被锁用户下一次请求即 401（``get_current_user`` 每次请求校验 ``is_active``），登录也会被拒；
    原先另写的 Redis ``account_locked:`` 键没有任何读取方，已删除。
    """
    user = (await db.execute(
        select(User).where(User.username == username, User.is_deleted == False)  # noqa: E712
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail=f"用户 {username} 不存在")
    await auth_service.update_user(
        db, actor_id=current_user.id, user_id=user.id, data=UserUpdate(is_active=False),
    )
    await db.commit()
    return {"username": username, "locked": True, "message": "账户已停用，该用户的现有会话下一次请求即失效"}


@router.get("/security/sessions")
async def get_sessions(
    user_id: str | None = None,
    current_user: User = Depends(require_role(["admin"])),
):
    """获取活跃会话列表。"""
    return {"sessions": security_monitor.get_active_sessions(user_id)}


@router.get("/audit-logs/export")
async def export_audit_logs(
    format: str = "csv",
    user_id: str | None = None,
    action: str | None = None,
    limit: int = 1000,
    current_user: User = Depends(require_role(["admin"])),
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
