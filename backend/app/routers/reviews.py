"""复核管理路由 — 工作底稿复核 API

Validates: Requirements 2.1-2.8
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.review_service import ReviewService
from app.models.collaboration_models import WorkpaperReviewRecord

router = APIRouter(prefix="/reviews", tags=["复核管理"])


class CreateReviewRequest(BaseModel):
    workpaper_id: str
    project_id: str
    review_level: int


class ReviewActionRequest(BaseModel):
    comments: Optional[str] = None
    reply_text: Optional[str] = None


class ReviewRespondRequest(BaseModel):
    response_content: str


class ReviewResolveRequest(BaseModel):
    comments: Optional[str] = None


class ReviewResponse(BaseModel):
    id: str
    workpaper_id: str
    project_id: str
    reviewer_id: Optional[str]
    review_level: int
    review_status: str
    comments: Optional[str]
    reply_text: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TimelinessReport(BaseModel):
    project_id: str
    total_reviews: int
    completed_reviews: int
    pending_reviews: int
    overdue_reviews: int
    avg_resolution_days: float
    details: List[dict]


@router.post("/workpapers/{workpaper_id}/reviews", response_model=ReviewResponse)
def create_review(
    workpaper_id: str,
    req: CreateReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建复核记录"""
    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    if not ReviewService.can_user_review_level(role, req.review_level):
        raise HTTPException(403, f"角色 {role} 无权进行 {req.review_level} 级复核")

    r = ReviewService.create_review(
        db,
        workpaper_id=workpaper_id,
        project_id=req.project_id,
        reviewer_id=str(user.id),
        review_level=req.review_level,
    )
    return _to_response(r)


@router.get("/workpapers/{workpaper_id}/reviews", response_model=List[ReviewResponse])
def list_reviews(
    workpaper_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取复核列表（按 review_level 升序）"""
    reviews = ReviewService.get_workpaper_reviews(db, workpaper_id)
    return [_to_response(r) for r in reviews]


@router.put("/reviews/{review_id}/respond", response_model=ReviewResponse)
def respond_to_review(
    review_id: str,
    req: ReviewRespondRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """编制人回复复核意见"""
    try:
        r = ReviewService.respond_to_review(db, review_id, req.response_content, str(user.id))
        if not r:
            raise HTTPException(404, "复核记录不存在")
        return _to_response(r)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/reviews/{review_id}/resolve", response_model=ReviewResponse)
def resolve_review(
    review_id: str,
    req: ReviewResolveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """确认复核意见已解决"""
    try:
        r = ReviewService.resolve_review(db, review_id, str(user.id), req.comments)
        if not r:
            raise HTTPException(404, "复核记录不存在")
        return _to_response(r)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/users/{user_id}/pending-reviews", response_model=List[ReviewResponse])
def list_pending_reviews(
    user_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取待复核列表"""
    reviews = ReviewService.get_pending_reviews(db, user_id, skip, limit)
    return [_to_response(r) for r in reviews]


@router.get("/projects/{project_id}/reviews/timeliness", response_model=TimelinessReport)
def review_timeliness(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取复核及时性报告"""
    try:
        report = ReviewService.get_review_timeliness(db, project_id)
        return TimelinessReport(**report)
    except Exception as e:
        raise HTTPException(500, f"生成报告失败: {str(e)}")


def _to_response(r: WorkpaperReviewRecord) -> ReviewResponse:
    return ReviewResponse(
        id=str(r.id),
        workpaper_id=str(r.workpaper_id),
        project_id=str(r.project_id),
        reviewer_id=str(r.reviewer_id) if r.reviewer_id else None,
        review_level=r.review_level,
        review_status=r.review_status.value
        if hasattr(r.review_status, 'value')
        else str(r.review_status),
        comments=getattr(r, 'comments', None),
        reply_text=getattr(r, 'reply_text', None),
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
