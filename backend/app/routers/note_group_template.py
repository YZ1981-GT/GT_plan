"""集团模板继承与下发路由

Requirements: 52.1-52.7
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.note_group_template_service import NoteGroupTemplateService

router = APIRouter(
    prefix="/api/projects/{project_id}/notes/group-template",
    tags=["note-group-template"],
)


class SaveTemplateRequest(BaseModel):
    year: int
    template_name: str


class DistributeRequest(BaseModel):
    template_id: str
    target_project_ids: list[str]
    strategy: str = Field("bc_keep_data", description="下发策略")


@router.post("/save")
async def save_as_group_template(
    project_id: UUID,
    body: SaveTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存当前附注结构为集团模板"""
    svc = NoteGroupTemplateService(db)
    result = await svc.save_as_group_template(
        project_id=project_id,
        year=body.year,
        template_name=body.template_name,
        created_by=current_user.id,
    )
    await db.commit()
    return result


@router.post("/distribute")
async def distribute_template(
    project_id: UUID,
    body: DistributeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下发集团模板到子企业项目"""
    svc = NoteGroupTemplateService(db)
    result = await svc.distribute_template(
        template_id=UUID(body.template_id),
        target_project_ids=[UUID(pid) for pid in body.target_project_ids],
        strategy=body.strategy,
    )
    await db.commit()
    return result


@router.post("/detach")
async def detach_from_group_template(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """脱离集团模板"""
    svc = NoteGroupTemplateService(db)
    result = await svc.detach_from_group_template(project_id)
    await db.commit()
    return result


@router.get("/list")
async def list_templates(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出所有集团模板"""
    svc = NoteGroupTemplateService(db)
    return await svc.list_templates()
