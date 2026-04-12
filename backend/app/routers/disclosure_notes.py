"""附注 API 路由

覆盖：
- POST /api/disclosure-notes/generate — 生成附注初稿
- GET  /api/disclosure-notes/{project_id}/{year} — 获取附注目录树
- GET  /api/disclosure-notes/{project_id}/{year}/{note_section} — 获取章节详情
- PUT  /api/disclosure-notes/{id} — 更新附注章节
- POST /api/disclosure-notes/{project_id}/{year}/validate — 执行附注校验
- GET  /api/disclosure-notes/{project_id}/{year}/validation-results — 获取校验结果
- PUT  /api/disclosure-notes/findings/{validation_id}/confirm — 确认校验发现

Validates: Requirements 4.1-4.11, 5.1-5.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.report_schemas import (
    DisclosureNoteDetail,
    DisclosureNoteGenerateRequest,
    DisclosureNoteUpdate,
    NoteValidationFindingConfirm,
    NoteValidationResponse,
)
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_validation_engine import NoteValidationEngine

router = APIRouter(
    prefix="/api/disclosure-notes",
    tags=["disclosure-notes"],
)


@router.post("/generate")
async def generate_notes(
    data: DisclosureNoteGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """生成附注初稿"""
    engine = DisclosureEngine(db)
    try:
        results = await engine.generate_notes(
            data.project_id, data.year, data.template_type,
        )
        await db.commit()
        return {
            "message": "附注生成成功",
            "note_count": len(results),
            "notes": results,
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"附注生成失败: {str(e)}")


@router.get("/{project_id}/{year}")
async def get_notes_tree(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """获取附注目录树"""
    engine = DisclosureEngine(db)
    tree = await engine.get_notes_tree(project_id, year)
    if not tree:
        raise HTTPException(status_code=404, detail="附注数据不存在，请先生成附注")
    return tree


@router.get("/{project_id}/{year}/validation-results")
async def get_validation_results(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """获取最新校验结果"""
    engine = NoteValidationEngine(db)
    result = await engine.get_latest_results(project_id, year)
    if result is None:
        raise HTTPException(status_code=404, detail="校验结果不存在，请先执行校验")
    return NoteValidationResponse.model_validate(result)


@router.get("/{project_id}/{year}/{note_section}")
async def get_note_detail(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
):
    """获取指定附注章节详情"""
    engine = DisclosureEngine(db)
    note = await engine.get_note_detail(project_id, year, note_section)
    if note is None:
        raise HTTPException(status_code=404, detail="附注章节不存在")
    return DisclosureNoteDetail.model_validate(note)


@router.put("/{note_id}")
async def update_note(
    note_id: UUID,
    data: DisclosureNoteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新附注章节内容"""
    engine = DisclosureEngine(db)
    note = await engine.update_note(
        note_id,
        table_data=data.table_data,
        text_content=data.text_content,
        status=data.status,
    )
    if note is None:
        raise HTTPException(status_code=404, detail="附注章节不存在")
    await db.commit()
    return DisclosureNoteDetail.model_validate(note)


@router.post("/{project_id}/{year}/validate")
async def validate_notes(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """执行附注校验"""
    engine = NoteValidationEngine(db)
    try:
        result = await engine.validate_all(project_id, year)
        await db.commit()
        return result
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"校验执行失败: {str(e)}")


@router.put("/findings/{validation_id}/confirm")
async def confirm_finding(
    validation_id: UUID,
    finding_index: int,
    data: NoteValidationFindingConfirm,
    db: AsyncSession = Depends(get_db),
):
    """确认校验发现为"已确认-无需修改" """
    engine = NoteValidationEngine(db)
    success = await engine.confirm_finding(
        validation_id, finding_index, data.reason,
    )
    if not success:
        raise HTTPException(status_code=404, detail="校验结果或发现不存在")
    await db.commit()
    return {"message": "校验发现已确认", "confirmed": True}
