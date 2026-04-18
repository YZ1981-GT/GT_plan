"""吐槽与求助专栏服务 — Phase 10 Task 11.1"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase10_models import ForumPost, ForumComment

logger = logging.getLogger(__name__)


class ForumService:
    """论坛 CRUD"""

    async def create_post(
        self, db: AsyncSession, author_id: UUID,
        title: str, content: str, category: str = "share",
        is_anonymous: bool = False,
    ) -> dict[str, Any]:
        post = ForumPost(
            author_id=author_id, title=title, content=content,
            category=category, is_anonymous=is_anonymous,
        )
        db.add(post)
        await db.flush()
        return self._post_to_dict(post)

    async def list_posts(
        self, db: AsyncSession, category: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        conditions = [ForumPost.is_deleted == sa.false()]
        if category:
            conditions.append(ForumPost.category == category)
        stmt = (
            sa.select(ForumPost).where(*conditions)
            .order_by(ForumPost.created_at.desc()).limit(limit)
        )
        result = await db.execute(stmt)
        posts = result.scalars().all()
        items = []
        for p in posts:
            d = self._post_to_dict(p)
            count_stmt = sa.select(sa.func.count()).select_from(ForumComment).where(
                ForumComment.post_id == p.id, ForumComment.is_deleted == sa.false()
            )
            d["comment_count"] = (await db.execute(count_stmt)).scalar() or 0
            items.append(d)
        return items

    async def create_comment(
        self, db: AsyncSession, post_id: UUID, author_id: UUID, content: str,
    ) -> dict[str, Any]:
        comment = ForumComment(post_id=post_id, author_id=author_id, content=content)
        db.add(comment)
        await db.flush()
        return {
            "id": str(comment.id), "post_id": str(comment.post_id),
            "author_id": str(comment.author_id), "content": comment.content,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        }

    async def get_comments(
        self, db: AsyncSession, post_id: UUID, limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = (
            sa.select(ForumComment)
            .where(ForumComment.post_id == post_id, ForumComment.is_deleted == sa.false())
            .order_by(ForumComment.created_at.asc()).limit(limit)
        )
        result = await db.execute(stmt)
        return [
            {
                "id": str(c.id), "post_id": str(c.post_id),
                "author_id": str(c.author_id), "content": c.content,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in result.scalars().all()
        ]

    async def like_post(self, db: AsyncSession, post_id: UUID) -> dict[str, Any]:
        post = await db.get(ForumPost, post_id)
        if not post:
            raise ValueError("帖子不存在")
        post.like_count = (post.like_count or 0) + 1
        await db.flush()
        return {"id": str(post.id), "like_count": post.like_count}

    async def delete_post(self, db: AsyncSession, post_id: UUID) -> bool:
        post = await db.get(ForumPost, post_id)
        if not post:
            return False
        post.is_deleted = True
        await db.flush()
        return True

    def _post_to_dict(self, p: ForumPost) -> dict[str, Any]:
        return {
            "id": str(p.id),
            "author_id": None if p.is_anonymous else str(p.author_id),
            "is_anonymous": p.is_anonymous,
            "category": p.category,
            "title": p.title,
            "content": p.content,
            "like_count": p.like_count or 0,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
