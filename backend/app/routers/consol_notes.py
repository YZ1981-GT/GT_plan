"""合并附注 API 路由

覆盖:
- POST /api/consolidation/notes/{project_id}/{year}  生成合并附注
- GET  /api/consolidation/notes/{project_id}/{year}  获取合并附注
- POST /api/consolidation/notes/integrate            合并附注与单体附注整合

Validates: Phase 2 Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_schemas import ConsolDisclosureSection
from app.services.consol_disclosure_service import (
    generate_consol_notes_sync,
    integrate_consol_notes_sync,
    save_consol_notes_sync,
)

router = APIRouter(
    prefix="/api/consolidation/notes",
    tags=["合并附注"],
)


class ConsolNotesIntegrateRequest(BaseModel):
    """合并附注整合请求"""
    project_id: UUID
    year: int
    existing_notes: list[dict] | None = None


# ---------------------------------------------------------------------------
# 合并附注接口
# ---------------------------------------------------------------------------


@router.post("/{project_id}/{year}", response_model=list[ConsolDisclosureSection])
async def create_consol_notes(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """生成合并附注"""
    sections = generate_consol_notes_sync(db, project_id, year)
    return sections


@router.get("/{project_id}/{year}", response_model=list[ConsolDisclosureSection])
async def get_consol_notes(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取合并附注"""
    sections = generate_consol_notes_sync(db, project_id, year)
    return sections


@router.post("/integrate", response_model=list[ConsolDisclosureSection])
async def integrate_notes(
    data: ConsolNotesIntegrateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """将合并附注与 Phase 1 单体附注整合"""
    sections = integrate_consol_notes_sync(
        db, data.project_id, data.year, data.existing_notes,
    )
    return sections


@router.post("/{project_id}/{year}/save")
async def save_consol_notes(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """保存合并附注到数据库"""
    sections = generate_consol_notes_sync(db, project_id, year)
    saved = save_consol_notes_sync(db, project_id, year, sections)
    return {
        "message": "合并附注保存成功",
        "saved_count": len(saved),
        "sections": [s.section_code for s in sections],
    }
