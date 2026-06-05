"""附注-底稿映射 API

Phase 9 Task 9.21
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.schemas._common import OptionalAmountDecimal
from app.services.note_wp_mapping_service import NoteWpMappingService

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-wp-mapping"])


@router.get("/{project_id}/wp-mapping")
async def get_mapping(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteWpMappingService(db)
    return await svc.get_mapping(project_id)


@router.put("/{project_id}/wp-mapping")
async def update_mapping(
    project_id: UUID,
    mapping: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteWpMappingService(db)
    result = await svc.update_mapping(project_id, mapping)
    await db.commit()
    return result


@router.post("/{project_id}/{year}/refresh-from-workpapers")
async def refresh_from_workpapers(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteWpMappingService(db)
    result = await svc.refresh_from_workpapers(project_id, year)
    await db.commit()
    # 透传更丰富返回体：显式添加 cells_updated 便于前端消费
    # service 返回 refreshed=cells_updated（向后兼容旧键名），
    # 同时增加 cells_updated 明确语义供前端区分提示文案（Req 2.7, 2.8）
    result["cells_updated"] = result.get("refreshed", 0)
    return result


class ToggleModeRequest(BaseModel):
    row_label: str
    col_index: int
    mode: str  # auto / manual
    manual_value: OptionalAmountDecimal = None


@router.post("/{project_id}/{year}/{note_id}/toggle-mode")
async def toggle_mode(
    project_id: UUID,
    year: int,
    note_id: UUID,
    data: ToggleModeRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = NoteWpMappingService(db)
    result = await svc.toggle_cell_mode(note_id, data.row_label, data.col_index, data.mode, data.manual_value)
    await db.commit()
    return result
