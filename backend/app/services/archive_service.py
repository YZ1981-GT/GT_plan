from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import ArchiveChecklist, ArchiveModification, ApprovalStatus
from datetime import datetime, timezone
import uuid


class ArchiveService:
    @staticmethod
    def init_checklist(db: Session, project_id: str) -> List[ArchiveChecklist]:
        """项目归档时初始化检查清单"""
        items = [
            ("ARC-001", "审计报告定稿并签署", "report"),
            ("ARC-002", "所有工作底稿已完成并签署", "workpaper"),
            ("ARC-003", "三级复核全部完成", "review"),
            ("ARC-004", "管理层书面声明书已获取", "document"),
            ("ARC-005", "期后事项复核完成", "subsequent"),
            ("ARC-006", "持续经营评价完成", "going_concern"),
            ("ARC-007", "重大错报汇总表完成", "misstatement"),
            ("ARC-008", "审计调整分录汇总完成", "adjustment"),
            ("ARC-009", "PBC清单全部接收", "pbc"),
            ("ARC-010", "往来询证函汇总完成", "confirmation"),
            ("ARC-011", "所有电子文件整理归档", "document"),
            ("ARC-012", "纸质文件装订成册", "document"),
        ]
        created = []
        for code, name, cat in items:
            existing = db.query(ArchiveChecklist).filter(
                ArchiveChecklist.project_id == project_id,
                ArchiveChecklist.item_code == code,
                ArchiveChecklist.is_deleted == False,
            ).first()
            if not existing:
                item = ArchiveChecklist(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    item_code=code,
                    item_name=name,
                    category=cat,
                    is_completed=False,
                    is_deleted=False,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(item)
                created.append(item)
        if created:
            db.commit()
        return created or ArchiveService.get_checklist(db, project_id)

    @staticmethod
    def get_checklist(db: Session, project_id: str) -> List[ArchiveChecklist]:
        return db.query(ArchiveChecklist).filter(
            ArchiveChecklist.project_id == project_id,
            ArchiveChecklist.is_deleted == False,
        ).order_by(ArchiveChecklist.item_code.asc()).all()

    @staticmethod
    def complete_item(
        db: Session,
        item_id: str,
        user_id: str,
        notes: Optional[str] = None,
    ) -> Optional[ArchiveChecklist]:
        item = db.query(ArchiveChecklist).filter(ArchiveChecklist.id == item_id).first()
        if item:
            item.is_completed = True
            item.completed_at = datetime.now(timezone.utc)
            item.completed_by = user_id
            item.notes = notes
            item.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(item)
        return item

    @staticmethod
    def request_modification(
        db: Session,
        project_id: str,
        requested_by: str,
        modification_type: str,
        description: str,
    ) -> ArchiveModification:
        mod = ArchiveModification(
            id=uuid.uuid4(),
            project_id=project_id,
            requested_by=requested_by,
            requested_at=datetime.now(timezone.utc),
            modification_type=modification_type,
            description=description,
            approval_status=ApprovalStatus.PENDING,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(mod)
        db.commit()
        db.refresh(mod)
        return mod

    @staticmethod
    def approve_modification(
        db: Session,
        mod_id: str,
        approved_by: str,
        comments: Optional[str] = None,
    ) -> Optional[ArchiveModification]:
        mod = db.query(ArchiveModification).filter(ArchiveModification.id == mod_id).first()
        if not mod:
            return None
        mod.approval_status = ApprovalStatus.APPROVED
        mod.approved_by = approved_by
        mod.approved_at = datetime.now(timezone.utc)
        if comments:
            mod.approval_comments = comments
        mod.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(mod)
        return mod

    @staticmethod
    def reject_modification(
        db: Session,
        mod_id: str,
        approved_by: str,
        comments: Optional[str] = None,
    ) -> Optional[ArchiveModification]:
        mod = db.query(ArchiveModification).filter(ArchiveModification.id == mod_id).first()
        if not mod:
            return None
        mod.approval_status = ApprovalStatus.REJECTED
        mod.approved_by = approved_by
        mod.approved_at = datetime.now(timezone.utc)
        if comments:
            mod.approval_comments = comments
        mod.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(mod)
        return mod

    @staticmethod
    def get_pending_modifications(db: Session, project_id: str) -> List[ArchiveModification]:
        return db.query(ArchiveModification).filter(
            ArchiveModification.project_id == project_id,
            ArchiveModification.approval_status == ApprovalStatus.PENDING,
            ArchiveModification.is_deleted == False,
        ).all()



    @staticmethod
    def generate_checklist(db: Session, project_id: str) -> List[ArchiveChecklist]:
        """生成归档检查清单（别名）"""
        return ArchiveService.init_checklist(db, project_id)

    @staticmethod
    def update_checklist_item(
        db: Session,
        item_id: str,
        is_completed: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> Optional[ArchiveChecklist]:
        """更新检查清单项"""
        item = db.query(ArchiveChecklist).filter(
            ArchiveChecklist.id == item_id,
            ArchiveChecklist.is_deleted == False,
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
    def check_archive_ready(db: Session, project_id: str) -> dict:
        """校验清单是否全部完成"""
        checklist = ArchiveService.get_checklist(db, project_id)
        total = len(checklist)
        completed = sum(1 for c in checklist if c.is_completed)
        pending = total - completed

        # 关键项必须完成
        key_items = [c for c in checklist if c.category in ("report", "review", "workpaper")]
        key_completed = sum(1 for c in key_items if c.is_completed)

        return {
            "project_id": str(project_id),
            "total_items": total,
            "completed_items": completed,
            "pending_items": pending,
            "key_items_total": len(key_items),
            "key_items_completed": key_completed,
            "is_ready": completed == total,
            "key_ready": key_completed == len(key_items),
            "incomplete_items": [
                {"code": c.item_code, "name": c.item_name}
                for c in checklist if not c.is_completed
            ],
        }

    @staticmethod
    def archive_project(
        db: Session,
        project_id: str,
        archived_by: str,
    ) -> dict:
        """执行归档：校验清单 + 锁定数据"""
        ready = ArchiveService.check_archive_ready(db, project_id)
        if not ready["is_ready"]:
            raise ValueError(
                f"归档条件未满足，{ready['pending_items']} 项检查清单未完成"
            )

        # 更新项目状态为已归档
        from app.models.core import Project
        project = db.query(Project).filter(Project.id == project_id).first()
        if project and hasattr(project, 'is_archived'):
            project.is_archived = True
        if project and hasattr(project, 'archived_at'):
            project.archived_at = datetime.now(timezone.utc)
        if project and hasattr(project, 'archived_by'):
            project.archived_by = archived_by

        # 计算归档到期日（归档日期 + 10年 = 保密期）
        archive_date = datetime.now(timezone.utc).date()
        retention_expiry = archive_date.replace(
            year=archive_date.year + 10
        )

        db.commit()

        return {
            "project_id": str(project_id),
            "archived_at": datetime.now(timezone.utc),
            "retention_expiry_date": retention_expiry,
            "message": "归档成功",
        }

    @staticmethod
    def export_archive_pdf(
        db: Session,
        project_id: str,
        password: Optional[str] = None,
    ) -> bytes:
        """导出电子档案 PDF"""
        # 简化：返回提示信息，实际由 PDF 引擎生成
        return b"PDF placeholder - implement with pdf_export_engine"

    @staticmethod
    def request_post_archive_modification(
        db: Session,
        project_id: str,
        modification_type: str,
        description: str,
        requested_by: str,
    ) -> ArchiveModification:
        """申请归档后修改"""
        return ArchiveService.request_modification(
            db, project_id, requested_by, modification_type, description
        )
