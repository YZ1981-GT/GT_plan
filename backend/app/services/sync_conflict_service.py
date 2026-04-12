from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import SyncLog, SyncType, SyncStatus
from datetime import datetime, timezone
import uuid
import hashlib
import json


class SyncConflictService:
    """检测并解决同步冲突"""

    @staticmethod
    def compute_hash(data: dict) -> str:
        """计算数据的哈希值用于冲突检测"""
        normalized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    def detect_conflict(
        db: Session,
        project_id: str,
        local_data: dict,
        server_data: dict,
    ) -> bool:
        """检测本地数据与服务器数据是否存在冲突"""
        local_hash = SyncConflictService.compute_hash(local_data)
        server_hash = SyncConflictService.compute_hash(server_data)
        return local_hash != server_hash

    @staticmethod
    def resolve_conflict(
        db: Session,
        project_id: str,
        winning_data: dict,
        losing_data: dict,
        resolution: str,  # "server_wins", "client_wins", "manual_merge"
        user_id: str,
    ) -> dict:
        """解决冲突并记录"""
        resolution_map = {
            "server_wins": winning_data,
            "client_wins": losing_data,
            "manual_merge": winning_data,  # manual merge data provided as winning_data
        }
        resolved = resolution_map.get(resolution, winning_data)

        SyncConflictService.record_resolution(
            db, project_id, winning_data, losing_data, resolution, user_id
        )
        return resolved

    @staticmethod
    def record_resolution(
        db: Session,
        project_id: str,
        winning_data: dict,
        losing_data: dict,
        resolution: str,
        user_id: str,
    ):
        sync_log = SyncLog(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            sync_type=SyncType.CONFLICT_RESOLUTION,
            details={
                "resolution": resolution,
                "winning_hash": SyncConflictService.compute_hash(winning_data),
                "losing_hash": SyncConflictService.compute_hash(losing_data),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(sync_log)
        db.commit()

    @staticmethod
    def get_conflict_history(
        db: Session, project_id: str, skip: int = 0, limit: int = 20
    ) -> List[SyncLog]:
        return (
            db.query(SyncLog)
            .filter(
                SyncLog.project_id == project_id,
                SyncLog.sync_type == SyncType.CONFLICT_RESOLUTION,
                SyncLog.is_deleted == False,
            )
            .order_by(SyncLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
