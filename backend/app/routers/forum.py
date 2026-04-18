"""论坛 API — Phase 10 Task 11.1"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.phase10_schemas import CreatePostRequest, CreateCommentRequest
from app.services.forum_service import ForumService

router = APIRouter(prefix="/api/forum", tags=["forum"])

_svc = ForumService()


@router.post("/posts")
async def create_post(req: CreatePostRequest, db: AsyncSession = Depends(get_db)):
    author_id = UUID("00000000-0000-0000-0000-000000000000")
    result = await _svc.create_post(
        db, author_id, req.title, req.content, req.category, req.is_anonymous,
    )
    await db.commit()
    return result


@router.get("/posts")
async def list_posts(
    category: str | None = None, limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    return await _svc.list_posts(db, category, limit)


@router.get("/posts/{post_id}/comments")
async def get_comments(post_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _svc.get_comments(db, post_id)


@router.post("/posts/{post_id}/comments")
async def create_comment(
    post_id: UUID, req: CreateCommentRequest, db: AsyncSession = Depends(get_db),
):
    author_id = UUID("00000000-0000-0000-0000-000000000000")
    result = await _svc.create_comment(db, post_id, author_id, req.content)
    await db.commit()
    return result


@router.post("/posts/{post_id}/like")
async def like_post(post_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        result = await _svc.like_post(db, post_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/posts/{post_id}")
async def delete_post(post_id: UUID, db: AsyncSession = Depends(get_db)):
    ok = await _svc.delete_post(db, post_id)
    if not ok:
        raise HTTPException(status_code=404, detail="帖子不存在")
    await db.commit()
    return {"deleted": True}
