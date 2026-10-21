"""附注章节模板可扩展性路由

Requirements: 49.1-49.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.disclosure import DisclosureNote
from app.services.note_custom_section_service import NoteCustomSectionService
from app.services.note_edit_gate import (
    assert_note_edit_access,
    require_note_edit_access,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/notes/custom-sections",
    tags=["note-custom-section"],
)


class CreateSectionRequest(BaseModel):
    year: int
    section_type: str = Field("mixed", description="text / table / mixed")
    title: str
    content: str | None = None
    table_structure: dict | None = None


class SaveAsTemplateRequest(BaseModel):
    section_id: str
    template_name: str | None = None


class ApplyTemplateRequest(BaseModel):
    year: int
    template_id: str


@router.post("/create")
async def create_custom_section(
    project_id: UUID,
    body: CreateSectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=False)),
):
    """创建自定义附注章节"""
    svc = NoteCustomSectionService(db)
    result = await svc.create_custom_section(
        project_id=project_id,
        year=body.year,
        section_type=body.section_type,
        title=body.title,
        content=body.content,
        table_structure=body.table_structure,
    )
    await db.commit()
    return result


@router.post("/save-as-template")
async def save_as_template(
    project_id: UUID,
    body: SaveAsTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=False)),
):
    """保存章节为模板。门禁之后校验章节属于路径中的项目，不属于返回 404。"""
    # 门禁已通过（路径依赖）。校验 section 属于本项目（design §4.8 B2 save-as-template）
    section_project_id = (
        await db.execute(
            select(DisclosureNote.project_id).where(
                DisclosureNote.id == UUID(body.section_id)
            )
        )
    ).scalar_one_or_none()
    if section_project_id is None or section_project_id != project_id:
        raise HTTPException(status_code=404, detail="附注章节不存在")

    svc = NoteCustomSectionService(db)
    result = await svc.save_as_template(
        section_id=UUID(body.section_id),
        template_name=body.template_name,
    )
    await db.commit()
    return result


@router.post("/apply-template")
async def apply_template(
    project_id: UUID,
    body: ApplyTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=False)),
):
    """从模板库应用模板到项目"""
    svc = NoteCustomSectionService(db)
    result = await svc.apply_template(
        project_id=project_id,
        year=body.year,
        template_id=UUID(body.template_id),
    )
    await db.commit()
    return result


@router.get("/templates")
async def list_templates(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出所有章节模板"""
    svc = NoteCustomSectionService(db)
    return await svc.list_templates()
