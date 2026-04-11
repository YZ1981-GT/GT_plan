"""底稿模板 API 路由

- POST   /api/templates              — 上传模板
- GET    /api/templates              — 模板列表
- GET    /api/templates/{code}       — 获取模板详情
- POST   /api/templates/{code}/versions — 创建新版本
- DELETE /api/templates/{id}         — 删除模板
- GET    /api/template-sets          — 模板集列表
- GET    /api/template-sets/{id}     — 模板集详情
- POST   /api/template-sets          — 创建模板集
- PUT    /api/template-sets/{id}     — 更新模板集
- POST   /api/template-sets/seed     — 初始化内置模板集

Validates: Requirements 1.1-1.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.workpaper_schemas import TemplateResponse, TemplateSetResponse
from app.services.template_engine import TemplateEngine

router = APIRouter(tags=["templates"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class TemplateUploadRequest(BaseModel):
    template_code: str
    template_name: str
    audit_cycle: str | None = None
    applicable_standard: str | None = None
    description: str | None = None
    named_ranges: list[dict] | None = None


class VersionCreateRequest(BaseModel):
    change_type: str = "minor"  # "major" or "minor"


class TemplateSetCreateRequest(BaseModel):
    set_name: str
    template_codes: list[str] | None = None
    applicable_audit_type: str | None = None
    applicable_standard: str | None = None
    description: str | None = None


class TemplateSetUpdateRequest(BaseModel):
    set_name: str | None = None
    template_codes: list[str] | None = None
    applicable_audit_type: str | None = None
    applicable_standard: str | None = None
    description: str | None = None


class GenerateWorkpapersRequest(BaseModel):
    template_set_id: UUID
    year: int = 2025


# ---------------------------------------------------------------------------
# Template endpoints
# ---------------------------------------------------------------------------


@router.post("/api/templates", response_model=TemplateResponse)
async def upload_template(
    data: TemplateUploadRequest,
    db: AsyncSession = Depends(get_db),
):
    """上传模板文件（MVP: 仅保存元数据）"""
    engine = TemplateEngine()
    template = await engine.upload_template(
        db=db,
        template_code=data.template_code,
        template_name=data.template_name,
        audit_cycle=data.audit_cycle,
        applicable_standard=data.applicable_standard,
        description=data.description,
        named_ranges=data.named_ranges,
    )
    await db.commit()
    return template


@router.get("/api/templates", response_model=list[TemplateResponse])
async def list_templates(
    audit_cycle: str | None = None,
    applicable_standard: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """模板列表（支持按循环、准则筛选）"""
    engine = TemplateEngine()
    return await engine.list_templates(
        db=db,
        audit_cycle=audit_cycle,
        applicable_standard=applicable_standard,
    )


@router.get("/api/templates/{code}", response_model=TemplateResponse)
async def get_template(
    code: str,
    version: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取模板详情（默认最新版本）"""
    engine = TemplateEngine()
    tpl = await engine.get_template(db=db, template_code=code, version=version)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"模板 {code} 不存在")
    return tpl


@router.post("/api/templates/{code}/versions", response_model=TemplateResponse)
async def create_version(
    code: str,
    data: VersionCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建新版本"""
    engine = TemplateEngine()
    try:
        tpl = await engine.create_version(
            db=db,
            template_code=code,
            change_type=data.change_type,
        )
        await db.commit()
        return tpl
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除模板（校验无引用）"""
    engine = TemplateEngine()
    try:
        await engine.delete_template(db=db, template_id=template_id)
        await db.commit()
        return {"message": "模板已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Template set endpoints
# ---------------------------------------------------------------------------


@router.get("/api/template-sets", response_model=list[TemplateSetResponse])
async def list_template_sets(
    db: AsyncSession = Depends(get_db),
):
    """模板集列表"""
    engine = TemplateEngine()
    return await engine.get_template_sets(db=db)


@router.get("/api/template-sets/{set_id}", response_model=TemplateSetResponse)
async def get_template_set(
    set_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """模板集详情"""
    engine = TemplateEngine()
    ts = await engine.get_template_set(db=db, set_id=set_id)
    if ts is None:
        raise HTTPException(status_code=404, detail="模板集不存在")
    return ts


@router.post("/api/template-sets", response_model=TemplateSetResponse)
async def create_template_set(
    data: TemplateSetCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建模板集"""
    engine = TemplateEngine()
    ts = await engine.create_template_set(
        db=db,
        set_name=data.set_name,
        template_codes=data.template_codes,
        applicable_audit_type=data.applicable_audit_type,
        applicable_standard=data.applicable_standard,
        description=data.description,
    )
    await db.commit()
    return ts


@router.put("/api/template-sets/{set_id}", response_model=TemplateSetResponse)
async def update_template_set(
    set_id: UUID,
    data: TemplateSetUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新模板集"""
    engine = TemplateEngine()
    try:
        ts = await engine.update_template_set(
            db=db,
            set_id=set_id,
            set_name=data.set_name,
            template_codes=data.template_codes,
            applicable_audit_type=data.applicable_audit_type,
            applicable_standard=data.applicable_standard,
            description=data.description,
        )
        await db.commit()
        return ts
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/template-sets/seed")
async def seed_template_sets(
    db: AsyncSession = Depends(get_db),
):
    """初始化6个内置模板集（幂等）"""
    engine = TemplateEngine()
    created = await engine.seed_builtin_template_sets(db=db)
    await db.commit()
    return {"message": f"已创建 {len(created)} 个内置模板集", "count": len(created)}


# ---------------------------------------------------------------------------
# Generate project workpapers
# ---------------------------------------------------------------------------


@router.post("/api/projects/{project_id}/working-papers/generate")
async def generate_project_workpapers(
    project_id: UUID,
    data: GenerateWorkpapersRequest,
    db: AsyncSession = Depends(get_db),
):
    """从模板集生成项目底稿"""
    engine = TemplateEngine()
    try:
        workpapers = await engine.generate_project_workpapers(
            db=db,
            project_id=project_id,
            template_set_id=data.template_set_id,
            year=data.year,
        )
        await db.commit()
        return {
            "message": f"已生成 {len(workpapers)} 个底稿",
            "count": len(workpapers),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
