"""Three-Level Review Service — 工作底稿三级复核业务逻辑

Validates: Requirements 3.1, 3.2, 3.3
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import WorkpaperReviewRecord, ReviewStatusEnum
from app.models.core import User
from datetime import datetime, timezone
import uuid

# Review levels: 1=Auditor Self-Review, 2=Manager Review, 3=Partner Review
REVIEW_LEVEL_NAMES = {
    1: "Auditor Self-Review",
    2: "Manager Review",
    3: "Partner Review",
}

REVIEW_LEVEL_PERMISSIONS = {
    1: ["auditor", "manager", "partner", "qc_reviewer", "admin"],
    2: ["manager", "partner", "qc_reviewer", "admin"],
    3: ["partner", "admin"],
}


class ReviewService:
    @staticmethod
    def create_review(
        db: Session,
        workpaper_id: str,
        project_id: str,
        reviewer_id: str,
        review_level: int,
    ) -> WorkpaperReviewRecord:
        if review_level not in REVIEW_LEVEL_NAMES:
            raise ValueError(f"Invalid review level: {review_level}")

        # Check if a review already exists at this level
        existing = db.query(WorkpaperReviewRecord).filter(
            WorkpaperReviewRecord.workpaper_id == workpaper_id,
            WorkpaperReviewRecord.review_level == review_level,
            WorkpaperReviewRecord.is_deleted == False,
        ).first()
        if existing:
            return existing

        r = WorkpaperReviewRecord(
            id=uuid.uuid4(),
            workpaper_id=workpaper_id,
            project_id=project_id,
            reviewer_id=reviewer_id,
            review_level=review_level,
            review_status=ReviewStatusEnum.draft,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        return r

    @staticmethod
    def get_workpaper_reviews(db: Session, workpaper_id: str) -> List[WorkpaperReviewRecord]:
        return db.query(WorkpaperReviewRecord).filter(
            WorkpaperReviewRecord.workpaper_id == workpaper_id,
            WorkpaperReviewRecord.is_deleted == False,
        ).order_by(WorkpaperReviewRecord.review_level.asc()).all()

    @staticmethod
    def start_review(db: Session, review_id: str, user_id: str) -> Optional[WorkpaperReviewRecord]:
        r = db.query(WorkpaperReviewRecord).filter(WorkpaperReviewRecord.id == review_id).first()
        if not r or r.is_deleted:
            return None
        if r.review_status != ReviewStatusEnum.draft:
            raise ValueError("Review is not in pending state")
        r.review_status = ReviewStatusEnum.pending_review
        r.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(r)
        return r

    @staticmethod
    def approve_review(
        db: Session,
        review_id: str,
        user_id: str,
        comments: Optional[str] = None,
        reply_text: Optional[str] = None,
    ) -> Optional[WorkpaperReviewRecord]:
        r = db.query(WorkpaperReviewRecord).filter(WorkpaperReviewRecord.id == review_id).first()
        if not r or r.is_deleted:
            return None
        if r.review_status == ReviewStatusEnum.approved:
            raise ValueError("Review already approved")

        r.review_status = ReviewStatusEnum.approved
        if comments:
            r.comments = comments
        if reply_text:
            r.reply_text = reply_text
        r.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(r)
        return r

    @staticmethod
    def reject_review(
        db: Session,
        review_id: str,
        user_id: str,
        comments: str,
    ) -> Optional[WorkpaperReviewRecord]:
        r = db.query(WorkpaperReviewRecord).filter(WorkpaperReviewRecord.id == review_id).first()
        if not r or r.is_deleted:
            return None
        if r.review_status == ReviewStatusEnum.rejected:
            raise ValueError("Review already rejected")

        r.review_status = ReviewStatusEnum.rejected
        r.comments = comments
        r.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(r)
        return r

    @staticmethod
    def can_user_review_level(user_role: str, level: int) -> bool:
        return user_role in REVIEW_LEVEL_PERMISSIONS.get(level, [])

    @staticmethod
    def is_review_chain_complete(
        db: Session, workpaper_id: str, required_levels: List[int]
    ) -> bool:
        reviews = ReviewService.get_workpaper_reviews(db, workpaper_id)
        approved_levels = {
            r.review_level
            for r in reviews
            if r.review_status == ReviewStatusEnum.approved
        }
        return all(l in approved_levels for l in required_levels)

    @staticmethod
    def get_pending_reviews(
        db: Session, user_id: str, skip: int = 0, limit: int = 50
    ) -> List[WorkpaperReviewRecord]:
        return (
            db.query(WorkpaperReviewRecord)
            .filter(
                WorkpaperReviewRecord.reviewer_id == user_id,
                WorkpaperReviewRecord.review_status.in_(
                    [ReviewStatusEnum.draft, ReviewStatusEnum.pending_review]
                ),
                WorkpaperReviewRecord.is_deleted == False,
            )
            .offset(skip)
            .limit(limit)
            .all()
        )



    @staticmethod
    def submit_for_review(
        db: Session,
        workpaper_id: str,
        submitted_by: str,
    ) -> dict:
        """提交底稿进行复核（更新状态为 prepared）"""
        from app.models.workpaper_models import WorkingPaper, WpStatus
        wp = db.query(WorkingPaper).filter(WorkingPaper.id == workpaper_id).first()
        if not wp:
            raise ValueError("工作底稿不存在")

        # 状态转换校验
        current = getattr(wp, 'status', None)
        current_val = current.value if hasattr(current, 'value') else str(current) if current else None
        if current_val and current_val not in ("draft", "in_progress"):
            raise ValueError(f"当前状态 {current_val} 不允许提交复核")

        wp.status = WpStatus.prepared
        wp.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(wp)

        return {
            "workpaper_id": str(workpaper_id),
            "new_status": "prepared",
            "submitted_by": submitted_by,
        }

    @staticmethod
    def respond_to_review(
        db: Session,
        review_id: str,
        response: str,
        responder_id: str,
    ) -> Optional[WorkpaperReviewRecord]:
        """编制人回复复核意见"""
        r = db.query(WorkpaperReviewRecord).filter(
            WorkpaperReviewRecord.id == review_id
        ).first()
        if not r or r.is_deleted:
            return None
        r.reply_text = response
        r.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(r)
        return r

    @staticmethod
    def resolve_review(
        db: Session,
        review_id: str,
        resolver_id: str,
        comments: Optional[str] = None,
    ) -> Optional[WorkpaperReviewRecord]:
        """确认复核意见已解决"""
        r = db.query(WorkpaperReviewRecord).filter(
            WorkpaperReviewRecord.id == review_id
        ).first()
        if not r or r.is_deleted:
            return None
        r.is_resolved = True
        r.review_status = ReviewStatusEnum.approved
        if comments:
            r.comments = comments
        r.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(r)
        return r

    @staticmethod
    def enforce_status_transition(
        db: Session,
        workpaper_id: str,
        from_status: str,
        to_status: str,
    ) -> bool:
        """校验工作底稿状态转换合法性

        合法的状态转换：
        - draft -> prepared（提交复核）
        - prepared -> level_1_approved（一级复核通过）
        - level_1_approved -> level_2_approved（二级复核通过）
        - level_2_approved -> archived（归档）
        - any -> draft（退回）
        """
        VALID_TRANSITIONS = {
            "draft": ["prepared", "in_progress"],
            "in_progress": ["prepared"],
            "prepared": ["draft", "level_1_approved"],
            "level_1_approved": ["draft", "level_2_approved"],
            "level_2_approved": ["draft", "archived"],
            "archived": [],
        }
        allowed = VALID_TRANSITIONS.get(from_status, [])
        if to_status not in allowed:
            raise ValueError(
                f"非法状态转换：{from_status} -> {to_status}。"
                f"允许的转换: {allowed}"
            )
        return True

    @staticmethod
    def check_review_gate(
        db: Session,
        project_id: str,
        target_status: str,
    ) -> bool:
        """检查项目状态门控条件是否满足"""
        # 关键底稿必须完成二级复核才能进入完成阶段
        # Gate check: 关键底稿(高风险)必须完成二级复核(level>=2)才能进入完成/归档
        if target_status in ("completed", "archived"):
            # 获取该项目所有二级复核
            level2_reviews = db.query(WorkpaperReviewRecord).filter(
                WorkpaperReviewRecord.project_id == project_id,
                WorkpaperReviewRecord.review_level >= 2,
                WorkpaperReviewRecord.is_deleted == False,  # noqa: E712
            ).all()
            for review in level2_reviews:
                if review.review_status != ReviewStatusEnum.approved:
                    return False
        return True

    @staticmethod
    def transition_project_status(
        db: Session,
        project_id: str,
        new_status: str,
    ) -> dict:
        """项目状态转换（带门控校验）"""
        from app.models.core import Project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("项目不存在")

        # 门控检查
        if not ReviewService.check_review_gate(db, project_id, new_status):
            raise ValueError("门控条件不满足，无法转换状态")

        old_status = getattr(project, 'status', None)
        project.status = new_status
        db.commit()
        db.refresh(project)

        return {
            "project_id": str(project_id),
            "old_status": str(old_status) if old_status else None,
            "new_status": new_status,
            "transitioned_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def get_review_timeliness(
        db: Session,
        project_id: str,
    ) -> dict:
        """复核及时性统计"""
        reviews = db.query(WorkpaperReviewRecord).filter(
            WorkpaperReviewRecord.project_id == project_id,
            WorkpaperReviewRecord.is_deleted == False,  # noqa: E712
        ).all()

        total = len(reviews)
        completed = sum(
            1 for r in reviews
            if r.review_status == ReviewStatusEnum.approved
        )
        pending = sum(
            1 for r in reviews
            if r.review_status in (
                ReviewStatusEnum.draft, ReviewStatusEnum.pending_review
            )
        )

        # 计算平均解决天数
        resolution_days = []
        for r in reviews:
            if r.updated_at and r.created_at and r.review_status == ReviewStatusEnum.approved:
                days = (r.updated_at - r.created_at).days
                resolution_days.append(days)

        avg_resolution_days = (
            sum(resolution_days) / len(resolution_days)
            if resolution_days else 0.0
        )

        # 超期复核（超过14天未解决）
        overdue_reviews = []
        now = datetime.now(timezone.utc)
        for r in reviews:
            if r.review_status not in (ReviewStatusEnum.approved,):
                age_days = (now - r.created_at).days
                if age_days > 14:
                    overdue_reviews.append({
                        "review_id": str(r.id),
                        "workpaper_id": str(r.workpaper_id),
                        "review_level": r.review_level,
                        "age_days": age_days,
                    })

        return {
            "project_id": str(project_id),
            "total_reviews": total,
            "completed_reviews": completed,
            "pending_reviews": pending,
            "overdue_reviews": len(overdue_reviews),
            "avg_resolution_days": round(avg_resolution_days, 1),
            "details": overdue_reviews,
        }
