"""模板库三层体系 API

提供：
- 事务所默认模板列表
- 集团定制模板管理
- 项目模板选择与拉取
- 可用模板列表（供选择器）
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.template_library_models import TemplateType
from app.services.template_library_service import TemplateLibraryService

router = APIRouter(prefix="/api/template-library", tags=["模板库"])


class GroupTemplateRequest(BaseModel):
    source_template_id: str
    group_id: str
    group_name: str


class SelectTemplateRequest(BaseModel):
    template_id: str


@router.get("/available")
async def get_available_templates(
    template_type: str | None = Query(None),
    group_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取可用模板列表（事务所默认 + 集团定制）"""
    svc = TemplateLibraryService(db)
    tt = TemplateType(template_type) if template_type else None
    gid = UUID(group_id) if group_id else None
    return await svc.get_available_templates(template_type=tt, group_id=gid)


@router.get("/firm")
async def list_firm_templates(
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出事务所默认模板"""
    svc = TemplateLibraryService(db)
    tt = TemplateType(template_type) if template_type else None
    items = await svc.list_firm_templates(tt)
    return [{"id": str(t.id), "name": t.name, "type": t.template_type.value,
             "wp_code": t.wp_code, "audit_cycle": t.audit_cycle,
             "report_scope": t.report_scope, "version": t.version} for t in items]


@router.post("/group")
async def create_group_template(
    data: GroupTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从事务所模板派生集团定制模板"""
    svc = TemplateLibraryService(db)
    try:
        item = await svc.create_group_template(
            source_template_id=UUID(data.source_template_id),
            group_id=UUID(data.group_id),
            group_name=data.group_name,
            created_by=current_user.id,
        )
        await db.commit()
        return {"id": str(item.id), "name": item.name, "message": "集团定制模板创建成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/group/{group_id}")
async def list_group_templates(
    group_id: UUID,
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出集团定制模板"""
    svc = TemplateLibraryService(db)
    tt = TemplateType(template_type) if template_type else None
    items = await svc.list_group_templates(group_id, tt)
    return [{"id": str(t.id), "name": t.name, "type": t.template_type.value,
             "group_name": t.group_name, "wp_code": t.wp_code,
             "version": t.version, "source_template_id": str(t.source_template_id) if t.source_template_id else None} for t in items]


@router.post("/projects/{project_id}/select")
async def select_template(
    project_id: UUID,
    data: SelectTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为项目选择模板"""
    svc = TemplateLibraryService(db)
    try:
        sel = await svc.select_template_for_project(
            project_id=project_id,
            template_id=UUID(data.template_id),
            selected_by=current_user.id,
        )
        await db.commit()
        return {"selection_id": str(sel.id), "message": "模板选择成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/templates")
async def get_project_templates(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取项目已选择的模板"""
    svc = TemplateLibraryService(db)
    return await svc.get_project_templates(project_id)


@router.post("/projects/{project_id}/pull/{template_id}")
async def pull_template(
    project_id: UUID,
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """拉取模板文件到项目目录"""
    svc = TemplateLibraryService(db)
    result = await svc.pull_template_to_project(project_id, template_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
