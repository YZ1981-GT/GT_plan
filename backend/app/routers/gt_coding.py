"""致同底稿编码体系 API 路由

- GET    /api/gt-coding                          — 编码体系列表
- GET    /api/gt-coding/tree                     — 编码树形结构
- GET    /api/gt-coding/linkage                  — 三测联动关系
- GET    /api/gt-coding/{coding_id}              — 编码详情
- POST   /api/gt-coding/seed                     — 加载种子数据
- POST   /api/projects/{project_id}/generate-index — 生成底稿索引

Validates: Requirements 7.1, 7.2, 7.5, 7.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.services.gt_coding_service import GTCodingService

router = APIRouter(tags=["gt-coding"])


class GenerateIndexRequest(BaseModel):
    template_set: str = "standard"


class CreateCodingRequest(BaseModel):
    code_prefix: str
    code_range: str
    cycle_name: str
    wp_type: str
    description: str | None = None
    parent_cycle: str | None = None
    sort_order: int | None = None


class UpdateCodingRequest(BaseModel):
    code_range: str | None = None
    cycle_name: str | None = None
    description: str | None = None
    parent_cycle: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class CloneCodingRequest(BaseModel):
    source_prefix: str | None = None


# ── 编码体系 ──

@router.get("/api/gt-coding")
async def list_codings(
    wp_type: str | None = None,
    code_prefix: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编码体系列表"""
    svc = GTCodingService()
    return await svc.list_codings(db, wp_type=wp_type, code_prefix=code_prefix)


@router.get("/api/gt-coding/tree")
async def get_coding_tree(db: AsyncSession = Depends(get_db)):
    """编码树形结构"""
    svc = GTCodingService()
    return await svc.get_tree(db)


@router.get("/api/gt-coding/linkage")
async def get_three_test_linkage():
    """三测联动关系"""
    svc = GTCodingService()
    return svc.get_three_test_linkage()


@router.get("/api/gt-coding/template-library")
async def get_template_library(
    wp_type: str | None = None,
    cycle_prefix: str | None = None,
):
    """获取致同标准底稿模板库目录"""
    svc = GTCodingService()
    return svc.get_template_library(wp_type=wp_type, cycle_prefix=cycle_prefix)


@router.get("/api/gt-coding/{coding_id}")
async def get_coding(coding_id: UUID, db: AsyncSession = Depends(get_db)):
    """编码详情"""
    svc = GTCodingService()
    result = await svc.get_coding(db, coding_id)
    if result is None:
        raise HTTPException(status_code=404, detail="编码不存在")
    return result


@router.post("/api/gt-coding/seed")
async def load_seed_data(db: AsyncSession = Depends(get_db)):
    """加载种子数据（幂等）"""
    svc = GTCodingService()
    result = await svc.load_seed_data(db)
    await db.commit()
    return result


# ── 自定义编码（Task 9.4） ──

@router.post("/api/gt-coding")
async def create_custom_coding(
    body: CreateCodingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "partner"])),
):
    """创建自定义编码条目"""
    svc = GTCodingService()
    try:
        result = await svc.create_custom_coding(
            db,
            code_prefix=body.code_prefix,
            code_range=body.code_range,
            cycle_name=body.cycle_name,
            wp_type=body.wp_type,
            description=body.description,
            parent_cycle=body.parent_cycle,
            sort_order=body.sort_order,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/gt-coding/{coding_id}")
async def update_custom_coding(
    coding_id: UUID,
    body: UpdateCodingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "partner"])),
):
    """更新自定义编码条目"""
    svc = GTCodingService()
    try:
        result = await svc.update_custom_coding(
            db, coding_id, body.model_dump(exclude_none=True)
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/gt-coding/{coding_id}")
async def delete_custom_coding(
    coding_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "partner"])),
):
    """删除自定义编码条目"""
    svc = GTCodingService()
    try:
        result = await svc.delete_custom_coding(db, coding_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/projects/{project_id}/clone-coding")
async def clone_coding_for_project(
    project_id: UUID,
    body: CloneCodingRequest = CloneCodingRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """克隆标准编码体系到项目级自定义"""
    svc = GTCodingService()
    try:
        result = await svc.clone_coding_for_project(
            db, project_id, source_prefix=body.source_prefix
        )
        await db.commit()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 底稿索引生成 ──

@router.post("/api/projects/{project_id}/generate-index")
async def generate_project_index(
    project_id: UUID,
    body: GenerateIndexRequest = GenerateIndexRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据致同编码体系为项目自动生成底稿索引"""
    svc = GTCodingService()
    try:
        result = await svc.generate_project_index(
            db, project_id, template_set=body.template_set
        )
        await db.commit()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
