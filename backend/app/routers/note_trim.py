"""附注章节裁剪 API

Phase 9 Task 9.27
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.note_edit_gate import require_note_edit_access
from app.services.note_trim_service import NoteTrimService

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-trim"])


class NoteTrimItem(BaseModel):
    id: str
    status: str
    skip_reason: str | None = None


class NoteTrimRequest(BaseModel):
    items: list[NoteTrimItem]


# 两个 GET 原先被 disclosure_notes 的 /{project_id}/{year}… 截走、从未可达（只挂了登录）；2026-10-31 改由
# router_registry 先注册后可达，按附注其余只读端点同级补项目只读鉴权（spec platform-performance-residual-findings-closure）。
@router.get("/{project_id}/sections")
async def get_sections(
    project_id: UUID,
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    svc = NoteTrimService(db)
    resolved_template_type = await svc.resolve_template_type(project_id, template_type)
    sections = await svc.get_sections(project_id, resolved_template_type)
    await db.commit()
    return sections


@router.put("/{project_id}/sections/trim")
async def save_trim(
    project_id: UUID,
    data: NoteTrimRequest,
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=False)),
):
    svc = NoteTrimService(db)
    resolved_template_type = await svc.resolve_template_type(project_id, template_type)
    count = await svc.save_trim(project_id, resolved_template_type, [i.model_dump() for i in data.items])
    await db.commit()
    return {"updated": count}


@router.get("/{project_id}/sections/trim-scheme")
async def get_trim_scheme(
    project_id: UUID,
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    svc = NoteTrimService(db)
    resolved_template_type = await svc.resolve_template_type(project_id, template_type)
    scheme = await svc.get_trim_scheme(project_id, resolved_template_type) or {}
    await db.commit()
    return scheme


@router.post("/{project_id}/{year}/auto-trim")
async def auto_trim(
    project_id: UUID,
    year: int,
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=False)),
):
    """自动裁剪：扫描 binding 列出科目，TrialBalance 全 0 → 标 not_applicable.

    Sprint 3 Task 3.7（v2 §5.3 简化版）。
    """
    svc = NoteTrimService(db)
    result = await svc.auto_trim(project_id, year, template_type)
    await db.commit()
    return result
