"""自定义底稿模板 API 路由

- POST   /api/custom-templates                    — 创建模板
- GET    /api/custom-templates                    — 我的模板列表
- GET    /api/custom-templates/market             — 模板市场
- GET    /api/custom-templates/{id}               — 模板详情
- PUT    /api/custom-templates/{id}               — 更新模板
- DELETE /api/custom-templates/{id}               — 删除模板
- POST   /api/custom-templates/{id}/publish       — 发布模板
- POST   /api/custom-templates/{id}/unpublish     — 取消发布
- POST   /api/custom-templates/{id}/version       — 创建新版本
- POST   /api/custom-templates/validate           — 验证模板

Validates: Requirements 4.1-4.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.custom_template_service import CustomTemplateService

router = APIRouter(prefix="/api/custom-templates", tags=["custom-templates"])

# 临时用固定 user_id（正式环境从 JWT 获取）
TEMP_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class TemplateCreate(BaseModel):
    template_name: str
    category: str = "personal"
    template_file_path: str
    version: str = "1.0"
    description: str | None = None


class TemplateUpdate(BaseModel):
    template_name: str | None = None
    category: str | None = None
    template_file_path: str | None = None
    description: str | None = None


class VersionCreate(BaseModel):
    new_version: str
    file_path: str


class ValidateRequest(BaseModel):
    file_content: str | None = None


def _svc() -> CustomTemplateService:
    return CustomTemplateService()


@router.post("")
async def create_template(body: TemplateCreate, db: AsyncSession = Depends(get_db)):
    svc = _svc()
    result = await svc.create_template(db, TEMP_USER_ID, body.model_dump())
    await db.commit()
    return result


@router.get("")
async def list_my_templates(
    category: str | None = None, db: AsyncSession = Depends(get_db),
):
    svc = _svc()
    return await svc.list_my_templates(db, TEMP_USER_ID, category)


@router.get("/market")
async def list_market(
    category: str | None = None, db: AsyncSession = Depends(get_db),
):
    svc = _svc()
    return await svc.list_market(db, category)


@router.get("/{template_id}")
async def get_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = _svc()
    result = await svc.get_template(db, template_id)
    if not result:
        raise HTTPException(status_code=404, detail="模板不存在")
    return result


@router.put("/{template_id}")
async def update_template(
    template_id: UUID, body: TemplateUpdate, db: AsyncSession = Depends(get_db),
):
    svc = _svc()
    try:
        result = await svc.update_template(db, template_id, TEMP_USER_ID, body.model_dump(exclude_none=True))
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{template_id}")
async def delete_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = _svc()
    try:
        await svc.delete_template(db, template_id, TEMP_USER_ID)
        await db.commit()
        return {"message": "已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{template_id}/publish")
async def publish_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = _svc()
    try:
        result = await svc.publish_template(db, template_id, TEMP_USER_ID)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{template_id}/unpublish")
async def unpublish_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = _svc()
    try:
        result = await svc.unpublish_template(db, template_id, TEMP_USER_ID)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{template_id}/version")
async def create_version(
    template_id: UUID, body: VersionCreate, db: AsyncSession = Depends(get_db),
):
    svc = _svc()
    try:
        result = await svc.create_version(db, template_id, TEMP_USER_ID, body.new_version, body.file_path)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate")
async def validate_template(body: ValidateRequest):
    svc = _svc()
    return await svc.validate_template(body.file_content)
