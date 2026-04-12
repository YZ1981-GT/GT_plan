"""项目看板服务 — 概览统计 + 工时管理 + 时间节点 + PBC

Validates: Requirements 5.1-5.6
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import (
    ProjectTimeline, WorkHours, BudgetHours, PBCChecklist, PbcStatus,
    MilestoneType,
)
from app.models.core import Project, ProjectUser
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
import uuid


class DashboardService:
    # -------------------------------------------------------------------------
    # 项目概览
    # -------------------------------------------------------------------------

    @staticmethod
    def get_project_overview(db: Session, project_id: str) -> dict:
        """项目概览统计"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # 团队人数
        team_size = db.query(ProjectUser).filter(
            ProjectUser.project_id == project_id,
            ProjectUser.is_deleted == False,  # noqa: E712
        ).count()

        # PBC 待处理数量
        pbc_pending = db.query(PBCChecklist).filter(
            PBCChecklist.project_id == project_id,
            PBCChecklist.status.in_([PbcStatus.pending, PbcStatus.in_progress]),
            PBCChecklist.is_deleted == False,  # noqa: E712
        ).count()

        # 距截止日天数（从 project_timeline 取 report 里程碑）
        days_until_deadline = 30
        timeline = db.query(ProjectTimeline).filter(
            ProjectTimeline.project_id == project_id,
            ProjectTimeline.milestone_type == MilestoneType.report,
            ProjectTimeline.is_deleted == False,  # noqa: E712
        ).first()
        if timeline and timeline.due_date:
            days_until_deadline = (timeline.due_date - date.today()).days

        return {
            "project_id": str(project_id),
            "project_name": getattr(project, 'name', str(project_id)),
            "status": getattr(project.status, 'value', str(getattr(project, 'status', 'draft')))
                      if hasattr(project, 'status') else "draft",
            "workpaper_completion_rate": 0.0,
            "review_completion_rate": 0.0,
            "days_until_deadline": days_until_deadline,
            "team_size": team_size,
            "pbc_pending_count": pbc_pending,
            "overdue_count": 0,
        }

    @staticmethod
    def get_risk_alerts(db: Session, project_id: str) -> List[dict]:
        """风险预警列表"""
        alerts = []

        # PBC 超期预警
        pbc_items = db.query(PBCChecklist).filter(
            PBCChecklist.project_id == project_id,
            PBCChecklist.status == PbcStatus.pending,
            PBCChecklist.requested_date < date.today(),
            PBCChecklist.is_deleted == False,  # noqa: E712
        ).all()
        for item in pbc_items:
            alerts.append({
                "alert_id": str(item.id),
                "alert_type": "pbc_overdue",
                "severity": "high",
                "message": f"PBC 项目「{item.item_name}」已超期",
                "related_object_type": "pbc_checklist",
                "related_object_id": str(item.id),
                "created_at": datetime.now(timezone.utc),
            })

        # 距截止日≤15天预警
        timeline = db.query(ProjectTimeline).filter(
            ProjectTimeline.project_id == project_id,
            ProjectTimeline.is_completed == False,  # noqa: E712
            ProjectTimeline.is_deleted == False,  # noqa: E712
        ).all()
        for t in timeline:
            if t.due_date:
                days = (t.due_date - date.today()).days
                if 0 <= days <= 15:
                    alerts.append({
                        "alert_id": str(t.id),
                        "alert_type": "deadline_approaching",
                        "severity": "medium" if days > 7 else "high",
                        "message": f"里程碑「{t.milestone_type.value if hasattr(t.milestone_type, 'value') else t.milestone_type}」距截止仅剩 {days} 天",
                        "related_object_type": "project_timeline",
                        "related_object_id": str(t.id),
                        "created_at": datetime.now(timezone.utc),
                    })
                elif days < 0:
                    alerts.append({
                        "alert_id": str(t.id),
                        "alert_type": "deadline_overdue",
                        "severity": "high",
                        "message": f"里程碑「{t.milestone_type.value if hasattr(t.milestone_type, 'value') else t.milestone_type}」已超期 {abs(days)} 天",
                        "related_object_type": "project_timeline",
                        "related_object_id": str(t.id),
                        "created_at": datetime.now(timezone.utc),
                    })

        return alerts

    # -------------------------------------------------------------------------
    # 工时管理
    # -------------------------------------------------------------------------

    @staticmethod
    def get_workload_summary(db: Session, project_id: str) -> List[dict]:
        """预算 vs 实际工时汇总"""
        budget_items = db.query(BudgetHours).filter(
            BudgetHours.project_id == project_id,
            BudgetHours.is_deleted == False,  # noqa: E712
        ).all()

        summaries = []
        for b in budget_items:
            summaries.append({
                "project_id": str(project_id),
                "phase": b.phase,
                "budget_hours": float(b.budget_hours),
                "actual_hours": float(b.actual_hours),
                "utilization_rate": float(b.actual_hours / b.budget_hours * 100)
                                    if b.budget_hours > 0 else 0.0,
            })
        return summaries

    @staticmethod
    def record_workhours(
        db: Session,
        project_id: str,
        user_id: str,
        work_date: date,
        hours: Decimal,
        work_description: Optional[str] = None,
    ) -> WorkHours:
        """记录工时"""
        wh = WorkHours(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            work_date=work_date,
            hours=hours,
            work_description=work_description,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(wh)
        db.commit()
        # 自动更新 BudgetHours.actual_hours
        DashboardService.auto_update_actual_hours(db, project_id, user_id)
        db.refresh(wh)
        return wh

    @staticmethod
    def auto_update_actual_hours(db: Session, project_id: str, user_id: str) -> None:
        """工时变更时自动更新 budget_hours.actual_hours"""
        # 按 user 角色匹配 phase，或者按 project 汇总
        total = db.query(WorkHours).filter(
            WorkHours.project_id == project_id,
            WorkHours.user_id == user_id,
            WorkHours.is_deleted == False,  # noqa: E712
        ).count()
        # 简化：只更新默认 phase
        budget = db.query(BudgetHours).filter(
            BudgetHours.project_id == project_id,
            BudgetHours.phase == "default",
            BudgetHours.is_deleted == False,  # noqa: E712
        ).first()
        if budget:
            total_hours = sum(
                float(w.hours or 0) for w in db.query(WorkHours).filter(
                    WorkHours.project_id == project_id,
                    WorkHours.is_deleted == False,  # noqa: E712
                ).all()
            )
            budget.actual_hours = Decimal(str(total_hours))
            budget.updated_at = datetime.now(timezone.utc)
            db.commit()

    # -------------------------------------------------------------------------
    # 时间节点
    # -------------------------------------------------------------------------

    @staticmethod
    def create_timeline(
        db: Session,
        project_id: str,
        milestone_type: str,
        due_date: date,
        notes: Optional[str] = None,
    ) -> ProjectTimeline:
        """创建时间节点"""
        from app.models.collaboration_models import MilestoneType
        mt = MilestoneType[milestone_type.upper()] if milestone_type.upper() in [
            e.name for e in MilestoneType
        ] else MilestoneType.report

        tl = ProjectTimeline(
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
        db.add(tl)
        db.commit()
        db.refresh(tl)
        return tl

    @staticmethod
    def update_timeline(
        db: Session,
        timeline_id: str,
        due_date: Optional[date] = None,
        completed_date: Optional[date] = None,
        is_completed: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> Optional[ProjectTimeline]:
        """更新时间节点"""
        tl = db.query(ProjectTimeline).filter(
            ProjectTimeline.id == timeline_id
        ).first()
        if not tl:
            return None
        if due_date is not None:
            tl.due_date = due_date
        if completed_date is not None:
            tl.completed_date = completed_date
        if is_completed is not None:
            tl.is_completed = is_completed
        if notes is not None:
            tl.notes = notes
        tl.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(tl)
        return tl

    @staticmethod
    def get_timelines(db: Session, project_id: str) -> List[ProjectTimeline]:
        """获取项目时间节点"""
        return db.query(ProjectTimeline).filter(
            ProjectTimeline.project_id == project_id,
            ProjectTimeline.is_deleted == False,  # noqa: E712
        ).order_by(ProjectTimeline.due_date.asc()).all()

    @staticmethod
    def auto_calc_archive_deadline(report_date: date) -> date:
        """report_date + 60天 = 归档截止日"""
        return report_date + timedelta(days=60)

    @staticmethod
    def check_overdue(db: Session, project_id: str) -> List[dict]:
        """检查距截止日≤15天的节点，触发通知"""
        overdue_timelines = db.query(ProjectTimeline).filter(
            ProjectTimeline.project_id == project_id,
            ProjectTimeline.is_completed == False,  # noqa: E712
            ProjectTimeline.is_deleted == False,  # noqa: E712
        ).all()

        notifications = []
        for tl in overdue_timelines:
            if tl.due_date:
                days = (tl.due_date - date.today()).days
                if 0 <= days <= 15:
                    notifications.append({
                        "timeline_id": str(tl.id),
                        "milestone": tl.milestone_type.value
                                    if hasattr(tl.milestone_type, 'value')
                                    else str(tl.milestone_type),
                        "days_remaining": days,
                        "is_overdue": days < 0,
                    })
        return notifications

    # -------------------------------------------------------------------------
    # PBC 清单
    # -------------------------------------------------------------------------

    @staticmethod
    def create_pbc_item(
        db: Session,
        project_id: str,
        item_name: str,
        category: Optional[str] = None,
        requested_date: Optional[date] = None,
        notes: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> PBCChecklist:
        """创建 PBC 清单项"""
        item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=project_id,
            item_name=item_name,
            category=category,
            requested_date=requested_date,
            status=PbcStatus.pending,
            notes=notes,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by=created_by,
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
        received_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> Optional[PBCChecklist]:
        """更新 PBC 清单项"""
        item = db.query(PBCChecklist).filter(
            PBCChecklist.id == item_id,
            PBCChecklist.is_deleted == False,  # noqa: E712
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
                raise ValueError(f"Invalid status: {status}")
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
        """获取 PBC 清单"""
        return db.query(PBCChecklist).filter(
            PBCChecklist.project_id == project_id,
            PBCChecklist.is_deleted == False,  # noqa: E712
        ).order_by(PBCChecklist.requested_date.asc()).all()

    @staticmethod
    def get_pbc_status(db: Session, project_id: str) -> dict:
        """PBC 接收状态汇总"""
        items = DashboardService.get_pbc_items(db, project_id)
        total = len(items)
        pending = sum(1 for i in items if i.status == PbcStatus.pending)
        in_progress = sum(1 for i in items if i.status == PbcStatus.in_progress)
        received = sum(1 for i in items if i.status == PbcStatus.received)
        overdue = sum(
            1 for i in items
            if i.status in (PbcStatus.pending, PbcStatus.in_progress)
            and i.requested_date
            and i.requested_date < date.today()
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
