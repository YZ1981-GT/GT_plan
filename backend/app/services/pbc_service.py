from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import PBCChecklist, PbcStatus
from datetime import datetime, timezone
import uuid


class PBCService:
    @staticmethod
    def create_item(
        db: Session,
        project_id: str,
        item_name: str,
        category: Optional[str] = None,
        requested_date=None,
        created_by: Optional[str] = None,
    ) -> PBCChecklist:
        item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=uuid.UUID(project_id),
            item_name=item_name,
            category=category,
            requested_date=requested_date,
            status=PbcStatus.PENDING,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by=uuid.UUID(created_by) if created_by else None,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def get_project_items(db: Session, project_id: str) -> List[PBCChecklist]:
        return (
            db.query(PBCChecklist)
            .filter(
                PBCChecklist.project_id == uuid.UUID(project_id),
                PBCChecklist.is_deleted == False,
            )
            .all()
        )

    @staticmethod
    def update_status(
        db: Session,
        item_id: str,
        status: str,
        received_date=None,
        notes: Optional[str] = None,
    ) -> Optional[PBCChecklist]:
        item = db.query(PBCChecklist).filter(PBCChecklist.id == uuid.UUID(item_id)).first()
        if not item:
            return None
        valid_statuses = [e.name for e in PbcStatus]
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Valid values: {valid_statuses}")
        item.status = PbcStatus[status]
        if received_date:
            item.received_date = received_date
        if notes:
            item.notes = notes
        item.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def get_pending_reminders(db: Session, project_id: str) -> List[PBCChecklist]:
        return (
            db.query(PBCChecklist)
            .filter(
                PBCChecklist.project_id == uuid.UUID(project_id),
                PBCChecklist.status.in_([PbcStatus.PENDING, PbcStatus.IN_PROGRESS]),
                PBCChecklist.is_deleted == False,
            )
            .all()
        )



    @staticmethod
    def create_pbc_item(
        db: Session,
        project_id: str,
        item_name: str,
        category: Optional[str] = None,
        requested_date=None,
        notes: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> PBCChecklist:
        """创建 PBC 清单项"""
        item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=uuid.UUID(project_id),
            item_name=item_name,
            category=category,
            requested_date=requested_date,
            status=PbcStatus.pending,
            notes=notes,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by=uuid.UUID(created_by) if created_by else None,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def update_pbc_item(
        db: Session,
        item_id: str,
        item_name: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        received_date=None,
        notes: Optional[str] = None,
    ) -> Optional[PBCChecklist]:
        """更新 PBC 清单项"""
        item = db.query(PBCChecklist).filter(
            PBCChecklist.id == uuid.UUID(item_id),
            PBCChecklist.is_deleted == False,
        ).first()
        if not item:
            return None
        if item_name is not None:
            item.item_name = item_name
        if category is not None:
            item.category = category
        if status is not None:
            valid_statuses = [e.name for e in PbcStatus]
            if status not in valid_statuses:
                raise ValueError(f"Invalid status: {status}. Valid: {valid_statuses}")
            item.status = PbcStatus[status]
        if received_date is not None:
            item.received_date = received_date
        if notes is not None:
            item.notes = notes
        item.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def get_pbc_items(db: Session, project_id: str) -> List[PBCChecklist]:
        """获取项目所有 PBC 清单项"""
        return PBCService.get_project_items(db, project_id)

    @staticmethod
    def get_pbc_status(db: Session, project_id: str) -> dict:
        """PBC 接收状态汇总"""
        items = PBCService.get_project_items(db, project_id)
        total = len(items)
        pending = sum(1 for i in items if i.status == PbcStatus.pending)
        in_progress = sum(1 for i in items if i.status == PbcStatus.in_progress)
        received = sum(1 for i in items if i.status == PbcStatus.received)
        overdue = sum(
            1 for i in items
            if i.status in (PbcStatus.pending, PbcStatus.in_progress)
            and i.requested_date
            and i.requested_date < datetime.now(timezone.utc).date()
        )
        return {
            "project_id": str(project_id),
            "total": total,
            "pending": pending,
            "in_progress": in_progress,
            "received": received,
            "overdue": overdue,
            "completion_rate": float(received / total * 100) if total > 0 else 0.0,
        }
