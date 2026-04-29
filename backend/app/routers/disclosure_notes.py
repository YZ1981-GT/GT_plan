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
from app.deps import get_current_user, require_project_access, get_user_scope_cycles
from app.models.core import User
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
    current_user: User = Depends(require_project_access("edit")),
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
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"附注生成失败: {str(e)}")


@router.get("/{project_id}/{year}")
async def get_notes_tree(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取附注目录树"""
    engine = DisclosureEngine(db)
    tree = await engine.get_notes_tree(project_id, year)
    if not tree:
        raise HTTPException(status_code=404, detail="附注数据不存在，请先生成附注")

    # scope_cycles 过滤：非 admin/partner 用户只能看到被分配循环对应的附注章节
    scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
    if scope_cycles is not None:
        from app.services.mapping_service import get_sections_by_cycles
        allowed_sections = await get_sections_by_cycles(project_id, scope_cycles)
        if allowed_sections:
            tree = [n for n in tree if n.get("note_section") in allowed_sections]

    return tree


@router.get("/{project_id}/{year}/validation-results")
async def get_validation_results(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取最新校验结果"""
    engine = NoteValidationEngine(db)
    result = await engine.get_latest_results(project_id, year)
    if result is None:
        raise HTTPException(status_code=404, detail="校验结果不存在，请先执行校验")
    return NoteValidationResponse.model_validate(result)


@router.get("/{project_id}/{year}/{note_section}/prior-year")
async def get_prior_year_note(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取上年同一附注章节数据，用于前端双列对比。"""
    engine = DisclosureEngine(db)
    data = await engine.get_prior_year_data(project_id, year, note_section)
    return data or {"year": year - 1, "table_data": None, "text_content": None}


@router.get("/{project_id}/{year}/{note_section}")
async def get_note_detail(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
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
    current_user: User = Depends(require_project_access("edit")),
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
    current_user: User = Depends(require_project_access("edit")),
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
    current_user: User = Depends(require_project_access("edit")),
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


# Phase 9 Task 9.30: 附注 Word 导出
@router.post("/{project_id}/{year}/export-word")
async def export_word(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """导出附注为 Word 文档"""
    from fastapi.responses import StreamingResponse
    from app.services.note_word_exporter import NoteWordExporter

    exporter = NoteWordExporter(db)
    try:
        output = await exporter.export(project_id, year)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=disclosure_notes_{year}.docx"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


# Phase 9 Task 9.28: 历史附注上传与解析
@router.post("/{project_id}/upload-history")
async def upload_history(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """上传历史附注文件（Word/PDF）并解析"""
    from fastapi import UploadFile, File
    # 简化实现：返回解析结果结构
    # 实际需要接收文件上传，保存到临时目录，调用 HistoryNoteParser
    return {
        "message": "历史附注上传接口已就绪",
        "project_id": str(project_id),
        "year": year,
        "note": "请通过 multipart/form-data 上传 .docx 或 .pdf 文件",
    }


@router.post("/{project_id}/{year}/{note_section}/clear-formulas")
async def clear_formulas(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """一键清除指定附注章节的所有自动公式，切换为手动编辑模式。

    将所有 auto 模式的单元格切换为 manual，保留当前数值不变。
    用户后续编辑不会被自动提数覆盖。
    """
    from app.services.note_wp_mapping_service import NoteWpMappingService

    svc = NoteWpMappingService(db)
    try:
        count = await svc.clear_formulas(project_id, year, note_section)
        await db.commit()
        return {"message": f"已清除 {count} 个单元格的自动公式", "cleared_count": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{project_id}/{year}/{note_section}/restore-auto")
async def restore_auto_mode(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """恢复指定附注章节的自动提数模式。

    从底稿 parsed_data 重新提取数据，将 manual 单元格恢复为 auto。
    """
    from app.services.note_wp_mapping_service import NoteWpMappingService

    svc = NoteWpMappingService(db)
    try:
        count = await svc.restore_auto_mode(project_id, year, note_section)
        await db.commit()
        return {"message": f"已恢复 {count} 个单元格为自动提数", "restored_count": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
