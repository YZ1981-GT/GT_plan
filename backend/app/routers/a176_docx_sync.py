"""A17-6 总结会会议纪要 — Docx 双向同步端点

POST /api/workpapers/{wp_id}/a176/generate-docx  — 结构化→Word
POST /api/workpapers/{wp_id}/a176/sync-from-docx  — Word→结构化
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a17-6-docx-sync"])


@router.post("/api/workpapers/{wp_id}/a176/generate-docx")
async def a176_generate_docx(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """结构化→Word：从 checklist_responses 生成 docx 文件"""
    from app.services.a176_docx_sync import generate_docx

    row = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wid LIMIT 1"),
        {"wid": wp_id},
    )
    pid = row.scalar_one_or_none()
    if not pid:
        raise HTTPException(404, "底稿不存在")

    try:
        file_path = await generate_docx(UUID(wp_id), pid, db)
        return {"ok": True, "file_path": str(file_path)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("A17-6 generate_docx 失败: %s", e, exc_info=True)
        raise HTTPException(500, f"生成 Word 失败: {str(e)[:200]}")


@router.post("/api/workpapers/{wp_id}/a176/sync-from-docx")
async def a176_sync_from_docx(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Word→结构化：从项目存储的 docx 解析内容回写到 checklist_responses"""
    from app.services.a176_docx_sync import sync_docx_to_responses

    row = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wid LIMIT 1"),
        {"wid": wp_id},
    )
    pid = row.scalar_one_or_none()
    if not pid:
        raise HTTPException(404, "底稿不存在")

    try:
        count = await sync_docx_to_responses(UUID(wp_id), pid, db, current_user.id)
        return {"ok": True, "synced_items": count}
    except Exception as e:
        logger.error("A17-6 sync_from_docx 失败: %s", e, exc_info=True)
        raise HTTPException(500, f"同步失败: {str(e)[:200]}")
