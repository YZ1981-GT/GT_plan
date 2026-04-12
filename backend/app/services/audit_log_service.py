"""审计日志服务 — AuditLog 的业务逻辑"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import AuditLog, OpType
from datetime import datetime, timezone
import uuid


class AuditLogService:
    @staticmethod
    def create_log(
        db: Session,
        user_id: str,
        operation: OpType,
        object_type: str,
        object_id: Optional[str] = None,
        project_id: Optional[str] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        """创建审计日志记录"""
        log = AuditLog(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            operation_type=operation,
            object_type=object_type,
            object_id=object_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_logs(
        db: Session,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        object_type: Optional[str] = None,
        operation: Optional[OpType] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AuditLog]:
        """查询审计日志列表（支持多条件过滤）"""
        query = db.query(AuditLog)
        if project_id:
            query = query.filter(AuditLog.project_id == project_id)
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if object_type:
            query = query.filter(AuditLog.object_type == object_type)
        if operation:
            query = query.filter(AuditLog.operation_type == operation)
        return (
            query.order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_log_by_id(db: Session, log_id: str) -> Optional[AuditLog]:
        """根据 ID 获取单条审计日志"""
        return db.query(AuditLog).filter(AuditLog.id == log_id).first()
