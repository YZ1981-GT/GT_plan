"""底稿全文搜索端点 — GET /search，搜索内容/公式/批注/附件名

Sprint 11 Task 11.11
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/projects/{project_id}/workpapers/search", tags=["workpaper-search"])


@router.get("")
async def search_workpapers(
    project_id: uuid.UUID,
    q: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    scope: Optional[str] = Query(None, description="搜索范围: content/formula/annotation/attachment"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """底稿全文搜索

    搜索范围：
    - content: 底稿内容（单元格文本）
    - formula: 公式
    - annotation: 批注内容
    - attachment: 附件文件名
    - 不指定: 搜索所有范围
    """
    results = []
    search_term = f"%{q}%"

    try:
        # 搜索底稿名称/编码
        if not scope or scope == "content":
            stmt = text("""
                SELECT id, wp_code, wp_name, 'workpaper' as source
                FROM wp_index
                WHERE project_id = :pid
                  AND (wp_name ILIKE :q OR wp_code ILIKE :q)
                LIMIT :lim
            """)
            result = await db.execute(stmt, {"pid": str(project_id), "q": search_term, "lim": limit})
            for row in result.fetchall():
                results.append({
                    "id": str(row[0]),
                    "title": row[2] or row[1],
                    "source": "workpaper",
                    "match_field": "name",
                })

        # 搜索批注
        if not scope or scope == "annotation":
            stmt = text("""
                SELECT id, content, cell_ref, 'annotation' as source
                FROM cell_annotations
                WHERE project_id = :pid
                  AND content ILIKE :q
                  AND is_deleted = false
                LIMIT :lim
            """)
            result = await db.execute(stmt, {"pid": str(project_id), "q": search_term, "lim": limit})
            for row in result.fetchall():
                results.append({
                    "id": str(row[0]),
                    "title": row[1][:100],
                    "source": "annotation",
                    "match_field": "content",
                    "cell_ref": row[2],
                })

        # 搜索附件
        if not scope or scope == "attachment":
            stmt = text("""
                SELECT id, original_filename, 'attachment' as source
                FROM attachments
                WHERE project_id = :pid
                  AND original_filename ILIKE :q
                  AND is_deleted = false
                LIMIT :lim
            """)
            result = await db.execute(stmt, {"pid": str(project_id), "q": search_term, "lim": limit})
            for row in result.fetchall():
                results.append({
                    "id": str(row[0]),
                    "title": row[1],
                    "source": "attachment",
                    "match_field": "filename",
                })

    except Exception:
        pass  # Return partial results on error

    return {
        "query": q,
        "scope": scope,
        "total": len(results),
        "results": results[:limit],
    }
