"""QC 案例库路由 — Round 3 需求 8

GET    /api/qc/cases                                          — 列出案例
GET    /api/qc/cases/{case_id}                                — 获取案例详情
POST   /api/qc/cases                                          — 手动创建案例
POST   /api/qc/inspections/{id}/items/{item_id}/preview-case  — 预览脱敏内容
POST   /api/qc/inspections/{id}/items/{item_id}/publish-as-case — 确认发布案例

权限：
- 列表/详情：所有登录用户（案例库对所有用户开放只读）
- 创建/发布：role='qc' | 'admin'
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.services.qc_case_library_service import qc_case_library_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qc", tags=["qc-cases"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateCaseRequest(BaseModel):
    """手动创建案例请求体"""

    title: str = Field(..., max_length=200, description="案例标题")
    category: str = Field(..., max_length=50, description="案例分类")
    severity: str = Field(..., description="严重度: blocking / warning / info")
    description: str = Field(..., description="案例描述")
    lessons_learned: Optional[str] = Field(None, description="经验教训")
    related_wp_refs: Optional[list] = Field(None, description="脱敏后的底稿引用")
    related_standards: Optional[list] = Field(None, description="关联准则")


class PublishCaseRequest(BaseModel):
    """发布案例请求体（确认发布时可附加信息）"""

    title: Optional[str] = Field(None, max_length=200, description="案例标题（可选）")
    category: Optional[str] = Field(None, max_length=50, description="案例分类（可选）")
    lessons_learned: Optional[str] = Field(None, description="经验教训（可选）")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/cases")
async def list_cases(
    category: Optional[str] = Query(None, description="按分类筛选"),
    severity: Optional[str] = Query(None, description="按严重度筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出案例库（所有登录用户可访问）。"""
    return await qc_case_library_service.list_cases(
        db,
        category=category,
        severity=severity,
        page=page,
        page_size=page_size,
    )


@router.get("/cases/{case_id}")
async def get_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取案例详情（所有登录用户可访问，同时增加阅读计数）。"""
    result = await qc_case_library_service.get_case(db, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="案例不存在")
    await db.commit()
    return result


@router.post("/cases", status_code=201)
async def create_case(
    body: CreateCaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """手动创建案例（仅 QC/admin）。"""
    result = await qc_case_library_service.create_case(
        db,
        data=body.model_dump(),
        published_by=current_user.id,
    )
    await db.commit()
    return result


@router.post("/inspections/{inspection_id}/items/{item_id}/preview-case")
async def preview_case(
    inspection_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """预览脱敏后的案例内容（质控合伙人确认前）。"""
    result = await qc_case_library_service.preview_desensitized(
        db,
        inspection_id=inspection_id,
        item_id=item_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="抽查子项不存在")
    return result


@router.post("/inspections/{inspection_id}/items/{item_id}/publish-as-case", status_code=201)
async def publish_as_case(
    inspection_id: UUID,
    item_id: UUID,
    body: PublishCaseRequest = PublishCaseRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """确认发布案例（脱敏后入库）。

    质控合伙人预览确认后调用此端点完成发布。
    """
    result = await qc_case_library_service.publish_from_inspection(
        db,
        inspection_id=inspection_id,
        item_id=item_id,
        published_by=current_user.id,
        title=body.title,
        category=body.category,
        lessons_learned=body.lessons_learned,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="抽查子项不存在")
    await db.commit()
    return result
