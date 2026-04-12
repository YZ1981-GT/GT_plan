"""Review Router — 三级复核 API 路由

Validates: Requirements 3.1, 3.2, 3.3
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
from app.services.permission_service import Permission, check_project_permission
from app.models.collaboration_models import WorkpaperReviewRecord

router = APIRouter(prefix="/reviews", tags=["reviews"])


class CreateReviewRequest(BaseModel):
    workpaper_id: str
    project_id: str
    review_level: int


class ReviewActionRequest(BaseModel):
    comments: Optional[str] = None
    reply_text: Optional[str] = None


class ReviewResponse(BaseModel):
    id: str
    workpaper_id: str
    project_id: str
    reviewer_id: str
    review_level: int
    review_status: str
    comments: Optional[str]
    reply_text: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=ReviewResponse)
def create_review(
    req: CreateReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    if not ReviewService.can_user_review_level(role, req.review_level):
        raise HTTPException(403, f"Not authorized for level {req.review_level} review")
    if not check_project_permission(db, str(user.id), req.project_id, Permission.REVIEW_SIGN):
        raise HTTPException(403, "No project access")

    r = ReviewService.create_review(
        db, req.workpaper_id, req.project_id, str(user.id), req.review_level
    )
    return _to_response(r)


@router.get("/workpaper/{workpaper_id}", response_model=List[ReviewResponse])
def get_workpaper_reviews(
    workpaper_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    reviews = ReviewService.get_workpaper_reviews(db, workpaper_id)
    return [_to_response(r) for r in reviews]


@router.get("/pending", response_model=List[ReviewResponse])
def get_pending_reviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    reviews = ReviewService.get_pending_reviews(db, str(user.id), skip, limit)
    return [_to_response(r) for r in reviews]


@router.post("/{review_id}/start")
def start_review(
    review_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        r = ReviewService.start_review(db, review_id, str(user.id))
        if not r:
            raise HTTPException(404, "Review not found")
        return _to_response(r)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{review_id}/approve")
def approve_review(
    review_id: str,
    req: ReviewActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        r = ReviewService.approve_review(
            db, review_id, str(user.id), req.comments, req.reply_text
        )
        if not r:
            raise HTTPException(404, "Review not found")
        return _to_response(r)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{review_id}/reject")
def reject_review(
    review_id: str,
    req: ReviewActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not req.comments:
        raise HTTPException(400, "Comments required when rejecting")
    try:
        r = ReviewService.reject_review(db, review_id, str(user.id), req.comments)
        if not r:
            raise HTTPException(404, "Review not found")
        return _to_response(r)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _to_response(r: WorkpaperReviewRecord) -> ReviewResponse:
    return ReviewResponse(
        id=str(r.id),
        workpaper_id=str(r.workpaper_id),
        project_id=str(r.project_id),
        reviewer_id=str(r.reviewer_id),
        review_level=r.review_level,
        review_status=r.review_status.value
        if hasattr(r.review_status, 'value')
        else str(r.review_status),
        comments=r.comments,
        reply_text=r.reply_text,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
