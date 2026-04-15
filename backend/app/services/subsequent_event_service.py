from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import SubsequentEvent, SEChecklist, SubsequentEventType
from datetime import datetime, timezone
import uuid


class SubsequentEventService:
    @staticmethod
    def create_event(
        db: Session,
        project_id: str,
        event_date: str,
        event_type: str,
        description: str,
        financial_impact: Optional[float] = None,
        created_by: Optional[str] = None,
    ) -> SubsequentEvent:
        # Normalize event_type to lowercase to match enum values
        et_value = event_type.upper() if event_type.upper() in ["ADJUSTING", "NON_ADJUSTING"] else event_type.lower()
        try:
            et = SubsequentEventType(et_value)
        except ValueError:
            et = SubsequentEventType.ADJUSTING
        e = SubsequentEvent(
            id=uuid.uuid4(),
            project_id=uuid.UUID(project_id),
            event_date=event_date,
            event_type=et,
            description=description,
            financial_impact=financial_impact,
            is_disclosed=False,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by=uuid.UUID(created_by) if created_by else None,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        return e

    @staticmethod
    def get_project_events(db: Session, project_id: str) -> List[SubsequentEvent]:
        return (
            db.query(SubsequentEvent)
            .filter(
                SubsequentEvent.project_id == uuid.UUID(project_id),
                SubsequentEvent.is_deleted == False,
            )
            .order_by(SubsequentEvent.event_date.desc())
            .all()
        )

    @staticmethod
    def mark_disclosed(
        db: Session, event_id: str, note_id: Optional[str] = None
    ) -> Optional[SubsequentEvent]:
        e = db.query(SubsequentEvent).filter(SubsequentEvent.id == uuid.UUID(event_id)).first()
        if e:
            e.is_disclosed = True
            e.disclosed_in_note_id = uuid.UUID(note_id) if note_id else None
            e.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(e)
        return e

    @staticmethod
    def get_checklist(db: Session, project_id: str) -> List[SEChecklist]:
        return (
            db.query(SEChecklist)
            .filter(
                SEChecklist.project_id == uuid.UUID(project_id),
                SEChecklist.is_deleted == False,
            )
            .order_by(SEChecklist.item_code.asc())
            .all()
        )

    @staticmethod
    def init_checklist(db: Session, project_id: str) -> List[SEChecklist]:
        # Standard checklist items
        items = [
            ("SE-001", "获取资产负债表日后所有重大期后事项相关资料"),
            ("SE-002", "审阅资产负债表日至审计报告日之间的调整事项"),
            ("SE-003", "审阅非调整事项（重要事项披露）"),
            ("SE-004", "识别期后事项中的财务报表重大错报风险"),
            ("SE-005", "检查期后事项对持续经营假设的影响"),
            ("SE-006", "获取管理层声明书确认期后事项完整性"),
        ]
        created = []
        for code, desc in items:
            existing = (
                db.query(SEChecklist)
                .filter(
                    SEChecklist.project_id == uuid.UUID(project_id),
                    SEChecklist.item_code == code,
                    SEChecklist.is_deleted == False,
                )
                .first()
            )
            if not existing:
                item = SEChecklist(
                    id=uuid.uuid4(),
                    project_id=uuid.UUID(project_id),
                    item_code=code,
                    description=desc,
                    is_completed=False,
                    is_deleted=False,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(item)
                created.append(item)
        if created:
            db.commit()
        return created or SubsequentEventService.get_checklist(db, project_id)

    @staticmethod
    def complete_checklist_item(
        db: Session,
        item_id: str,
        user_id: str,
        notes: Optional[str] = None,
    ) -> Optional[SEChecklist]:
        item = db.query(SEChecklist).filter(SEChecklist.id == uuid.UUID(item_id)).first()
        if item:
            item.is_completed = True
            item.completed_at = datetime.now(timezone.utc)
            item.completed_by = uuid.UUID(user_id)
            item.notes = notes
            item.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(item)
        return item



    @staticmethod
    def update_event(
        db: Session,
        event_id: str,
        event_date: Optional[str] = None,
        event_type: Optional[str] = None,
        description: Optional[str] = None,
        financial_impact: Optional[float] = None,
        is_disclosed: Optional[bool] = None,
        adjustment_id: Optional[str] = None,
        disclosed_in_note_id: Optional[str] = None,
    ) -> Optional[SubsequentEvent]:
        """更新期后事项"""
        e = db.query(SubsequentEvent).filter(
            SubsequentEvent.id == uuid.UUID(event_id),
            SubsequentEvent.is_deleted == False,
        ).first()
        if not e:
            return None
        if event_date is not None:
            e.event_date = event_date
        if event_type is not None:
            et = SubsequentEventType[event_type.upper()] if event_type.upper() in [
                "ADJUSTING", "NON_ADJUSTING"
            ] else SubsequentEventType.ADJUSTING
            e.event_type = et
        if description is not None:
            e.description = description
        if financial_impact is not None:
            e.financial_impact = financial_impact
        if is_disclosed is not None:
            e.is_disclosed = is_disclosed
        if adjustment_id is not None:
            e.adjustment_id = uuid.UUID(adjustment_id) if adjustment_id else None
        if disclosed_in_note_id is not None:
            e.disclosed_in_note_id = uuid.UUID(disclosed_in_note_id) if disclosed_in_note_id else None
        e.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(e)
        return e

    @staticmethod
    def delete_event(db: Session, event_id: str) -> bool:
        """软删除期后事项"""
        e = db.query(SubsequentEvent).filter(
            SubsequentEvent.id == uuid.UUID(event_id),
            SubsequentEvent.is_deleted == False,
        ).first()
        if not e:
            return False
        e.soft_delete()
        e.updated_at = datetime.now(timezone.utc)
        db.commit()
        return True

    @staticmethod
    def get_events(db: Session, project_id: str) -> List[SubsequentEvent]:
        """获取项目所有期后事项"""
        return SubsequentEventService.get_project_events(db, project_id)

    @staticmethod
    def update_checklist_item(
        db: Session,
        item_id: str,
        is_completed: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> Optional[SEChecklist]:
        """更新检查清单项"""
        item = db.query(SEChecklist).filter(
            SEChecklist.id == uuid.UUID(item_id),
            SEChecklist.is_deleted == False,
        ).first()
        if not item:
            return None
        if is_completed is not None:
            item.is_completed = is_completed
            if is_completed:
                item.completed_at = datetime.now(timezone.utc)
        if notes is not None:
            item.notes = notes
        item.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def get_by_project(db: Session, project_id: str) -> List[SubsequentEvent]:
        """按项目获取所有期后事项（别名）"""
        return SubsequentEventService.get_project_events(db, project_id)



    @staticmethod
    def create_checklist_item(db: Session, project_id: str, data: dict) -> SEChecklist:
        """创建检查清单项"""
        item = SEChecklist(
            project_id=uuid.UUID(project_id),
            item_code=data.get("item_code"),
            description=data.get("description", ""),
            is_completed=data.get("is_completed", False),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def update_checklist_item(db: Session, item_id: str, data: dict) -> Optional[SEChecklist]:
        """更新检查清单项"""
        item = db.query(SEChecklist).filter(
            SEChecklist.id == uuid.UUID(item_id),
            SEChecklist.is_deleted == False,
        ).first()
        if not item:
            return None
        if "item_code" in data and data["item_code"] is not None:
            item.item_code = data["item_code"]
        if "description" in data and data["description"] is not None:
            item.description = data["description"]
        if "is_completed" in data and data["is_completed"] is not None:
            item.is_completed = data["is_completed"]
            if data["is_completed"]:
                item.completed_at = datetime.now(timezone.utc)
            else:
                item.completed_at = None
        if "notes" in data and data["notes"] is not None:
            item.notes = data["notes"]
        item.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete_checklist_item(db: Session, item_id: str) -> bool:
        """删除检查清单项（软删除）"""
        item = db.query(SEChecklist).filter(
            SEChecklist.id == uuid.UUID(item_id),
            SEChecklist.is_deleted == False,
        ).first()
        if not item:
            return False
        item.soft_delete()
        item.updated_at = datetime.now(timezone.utc)
        db.commit()
        return True
