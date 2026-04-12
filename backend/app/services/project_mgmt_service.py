from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import (
    ProjectTimeline, WorkHours, BudgetHours, MilestoneType,
)
from datetime import datetime, timezone, date
import uuid
from decimal import Decimal

class ProjectTimelineService:
    @staticmethod
    def create_milestone(
        db: Session,
        project_id: str,
        milestone_type: str,
        due_date: date,
        notes: Optional[str] = None,
    ) -> ProjectTimeline:
        mt = MilestoneType[milestone_type] if milestone_type in [e.name for e in MilestoneType] else MilestoneType.PLANNING
        m = ProjectTimeline(
            id=uuid.uuid4(),
            project_id=project_id,
            milestone_type=mt,
            due_date=due_date,
            is_completed=False,
            notes=notes,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        return m

    @staticmethod
    def get_project_timeline(db: Session, project_id: str) -> List[ProjectTimeline]:
        return db.query(ProjectTimeline).filter(
            ProjectTimeline.project_id == project_id,
            ProjectTimeline.is_deleted == False,
        ).order_by(ProjectTimeline.due_date.asc()).all()

    @staticmethod
    def complete_milestone(db: Session, timeline_id: str) -> Optional[ProjectTimeline]:
        m = db.query(ProjectTimeline).filter(ProjectTimeline.id == timeline_id).first()
        if m:
            m.is_completed = True
            m.completed_date = datetime.now(timezone.utc).date()
            m.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(m)
        return m


class WorkHoursService:
    @staticmethod
    def log_hours(
        db: Session,
        project_id: str,
        user_id: str,
        work_date: date,
        hours: float,
        work_description: Optional[str] = None,
    ) -> WorkHours:
        w = WorkHours(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            work_date=work_date,
            hours=Decimal(str(hours)),
            work_description=work_description,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(w)
        db.commit()
        db.refresh(w)
        return w

    @staticmethod
    def get_user_hours(
        db: Session, project_id: str, user_id: str, skip: int = 0, limit: int = 100
    ) -> List[WorkHours]:
        return db.query(WorkHours).filter(
            WorkHours.project_id == project_id,
            WorkHours.user_id == user_id,
            WorkHours.is_deleted == False,
        ).order_by(WorkHours.work_date.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def get_project_total_hours(db: Session, project_id: str) -> float:
        result = db.query(WorkHours).filter(
            WorkHours.project_id == project_id,
            WorkHours.is_deleted == False,
        ).all()
        return float(sum(w.hours for w in result if w.hours))


class BudgetHoursService:
    @staticmethod
    def set_budget(
        db: Session,
        project_id: str,
        phase: str,
        budget_hours: float,
    ) -> BudgetHours:
        existing = db.query(BudgetHours).filter(
            BudgetHours.project_id == project_id,
            BudgetHours.phase == phase,
            BudgetHours.is_deleted == False,
        ).first()
        if existing:
            existing.budget_hours = Decimal(str(budget_hours))
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            return existing
        b = BudgetHours(
            id=uuid.uuid4(),
            project_id=project_id,
            phase=phase,
            budget_hours=Decimal(str(budget_hours)),
            actual_hours=Decimal("0"),
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(b)
        db.commit()
        db.refresh(b)
        return b

    @staticmethod
    def get_budget_summary(db: Session, project_id: str) -> List[BudgetHours]:
        return db.query(BudgetHours).filter(
            BudgetHours.project_id == project_id,
            BudgetHours.is_deleted == False,
        ).all()

    @staticmethod
    def update_actual_hours(db: Session, project_id: str, phase: str, hours: float):
        budget = db.query(BudgetHours).filter(
            BudgetHours.project_id == project_id,
            BudgetHours.phase == phase,
            BudgetHours.is_deleted == False,
        ).first()
        if budget:
            budget.actual_hours = Decimal(str(hours))
            budget.updated_at = datetime.now(timezone.utc)
            db.commit()
