"""复核批注 API 路由

- GET  /api/working-papers/{wp_id}/reviews              — 列表
- POST /api/working-papers/{wp_id}/reviews              — 添加
- PUT  /api/working-papers/{wp_id}/reviews/{id}/reply   — 回复
- PUT  /api/working-papers/{wp_id}/reviews/{id}/resolve — 解决

Validates: Requirements 5.1-5.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.wp_review_service import WpReviewService

router = APIRouter(
    prefix="/api/working-papers/{wp_id}/reviews",
    tags=["wp-review"],
)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class AddCommentRequest(BaseModel):
    commenter_id: UUID
    comment_text: str
    cell_reference: str | None = None


class ReplyRequest(BaseModel):
    replier_id: UUID
    reply_text: str


class ResolveRequest(BaseModel):
    resolved_by: UUID


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_reviews(
    wp_id: UUID,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取复核意见列表"""
    svc = WpReviewService()
    return await svc.list_reviews(db=db, working_paper_id=wp_id, status=status)


@router.post("")
async def add_comment(
    wp_id: UUID,
    data: AddCommentRequest,
    db: AsyncSession = Depends(get_db),
):
    """添加复核意见"""
    svc = WpReviewService()
    result = await svc.add_comment(
        db=db,
        working_paper_id=wp_id,
        commenter_id=data.commenter_id,
        comment_text=data.comment_text,
        cell_reference=data.cell_reference,
    )
    await db.commit()
    return result


@router.put("/{review_id}/reply")
async def reply_review(
    wp_id: UUID,
    review_id: UUID,
    data: ReplyRequest,
    db: AsyncSession = Depends(get_db),
):
    """回复复核意见"""
    svc = WpReviewService()
    try:
        result = await svc.reply(
            db=db,
            review_id=review_id,
            replier_id=data.replier_id,
            reply_text=data.reply_text,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{review_id}/resolve")
async def resolve_review(
    wp_id: UUID,
    review_id: UUID,
    data: ResolveRequest,
    db: AsyncSession = Depends(get_db),
):
    """标记为已解决"""
    svc = WpReviewService()
    try:
        result = await svc.resolve(
            db=db,
            review_id=review_id,
            resolved_by=data.resolved_by,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
