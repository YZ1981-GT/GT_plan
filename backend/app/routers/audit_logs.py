"""审计日志路由 — AuditLog 查询接口"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.audit_log_service import AuditLogService
from app.services.permission_service import Permission, check_project_permission
from app.models.collaboration_models import OpType

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


class AuditLogResponse(BaseModel):
    """审计日志响应"""
    id: str
    project_id: Optional[str]
    user_id: str
    operation_type: str
    object_type: str
    object_id: Optional[str]
    old_value: Optional[dict]
    new_value: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[AuditLogResponse])
def list_logs(
    project_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    object_type: Optional[str] = Query(None),
    operation: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询审计日志列表"""
    if project_id:
        if not check_project_permission(
            db, str(user.id), project_id, Permission.PROJECT_READ
        ):
            raise HTTPException(status_code=403, detail="No access")
    valid_ops = [e.name for e in OpType]
    op = OpType[operation] if operation and operation in valid_ops else None
    logs = AuditLogService.get_logs(
        db, project_id, user_id, object_type, op, skip, limit
    )
    return [
        AuditLogResponse(
            id=str(l.id),
            project_id=str(l.project_id) if l.project_id else None,
            user_id=str(l.user_id),
            operation_type=l.operation_type.value
            if hasattr(l.operation_type, "value")
            else str(l.operation_type),
            object_type=l.object_type,
            object_id=l.object_id,
            old_value=l.old_value,
            new_value=l.new_value,
            ip_address=l.ip_address,
            created_at=l.created_at,
        )
        for l in logs
    ]
