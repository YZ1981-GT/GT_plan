"""Sprint C.0 — 附注离线导出/导入路由 (D15).

端点：
- POST /api/disclosure-notes/{project_id}/{year}/offline-export
- POST /api/disclosure-notes/{project_id}/{year}/offline-import/preview
- POST /api/disclosure-notes/{project_id}/{year}/offline-import/execute
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.deps import get_current_user, get_db, require_project_access
from app.services.note_edit_gate import require_note_edit_access

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-offline"])
logger = logging.getLogger(__name__)


@router.post("/{project_id}/{year}/offline-export")
async def export_offline_package(
    project_id: UUID,
    year: int,
    body: dict[str, Any] | None = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
    _=Depends(require_project_access("readonly")),
):
    """导出附注离线编辑包 (C.0.17)."""
    from app.services.note_offline_export_service import NoteOfflineExportService

    body = body or {}
    service = NoteOfflineExportService(db)

    xlsx_bytes, file_hash = await service.export_sections(
        project_id=project_id,
        year=year,
        section_ids=body.get("section_ids"),
        include_formulas=body.get("include_formulas", True),
        include_provenance=body.get("include_provenance", True),
        password=body.get("password"),
        exporter_name=getattr(user, "username", ""),
        partner_info=body.get("partner_info"),
    )

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=note_export_{project_id}_{year}.xlsx",
            "X-File-Hash": file_hash,
        },
    )


@router.post("/{project_id}/{year}/offline-import/preview")
async def preview_import(
    project_id: UUID,
    year: int,
    file: UploadFile = File(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
    _=Depends(require_project_access("readonly")),
):
    """校验并预览导入 (C.0.18)."""
    from app.services.note_offline_import_service import NoteOfflineImportService

    xlsx_bytes = await file.read()
    service = NoteOfflineImportService(db)

    result = await service.validate_and_preview(
        xlsx_bytes=xlsx_bytes,
        project_id=project_id,
        year=year,
    )

    return result


@router.post("/{project_id}/{year}/offline-import/execute")
async def execute_import(
    project_id: UUID,
    year: int,
    file: UploadFile = File(...),
    decisions: str = Form("{}"),
    merge_cells: str = Form("{}"),
    db=Depends(get_db),
    user=Depends(get_current_user),
    _=Depends(require_note_edit_access(consol_lock=False)),
):
    """执行导入 (C.0.18)."""
    import json

    from app.services.note_offline_import_service import (
        ConflictResolution,
        NoteOfflineImportService,
    )

    xlsx_bytes = await file.read()
    decisions_dict = {}
    merge_cells_dict: dict[str, list[str]] = {}
    try:
        raw = json.loads(decisions)
        if not isinstance(raw, dict):
            raise ValueError("decisions 必须是对象")
        for sid, choice in raw.items():
            decisions_dict[str(sid)] = ConflictResolution(choice)
        raw_merge = json.loads(merge_cells)
        if not isinstance(raw_merge, dict) or any(
            not isinstance(cells, list) or any(not isinstance(cell, str) for cell in cells)
            for cells in raw_merge.values()
        ):
            raise ValueError("merge_cells 必须是 {章节: [单元格坐标]} 对象")
        merge_cells_dict = {str(sid): list(cells) for sid, cells in raw_merge.items()}
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"离线导入决策格式错误: {e}")

    service = NoteOfflineImportService(db)
    result = await service.execute_import(
        xlsx_bytes=xlsx_bytes,
        project_id=project_id,
        year=year,
        user_id=str(getattr(user, "id", "")),
        decisions=decisions_dict,
        merge_cells=merge_cells_dict,
    )
    if not result.success:
        await db.rollback()
        raise HTTPException(status_code=400, detail={"errors": result.errors})

    # service 只 flush，router 统一 commit；提交成功后逐章发事件，使交付件 / 合并附注 / 地址目录同步失效。
    await db.commit()
    if result.changed_sections:
        try:
            from app.models.audit_platform_schemas import EventPayload, EventType
            from app.services.event_bus import event_bus

            for section in result.changed_sections:
                await event_bus.publish(EventPayload(
                    event_type=EventType.NOTE_SECTION_SAVED,
                    project_id=project_id,
                    year=year,
                    extra={"section_code": section, "action": "offline_import"},
                ))
        except Exception:  # noqa: BLE001 — 数据已提交，通知失败只能告警
            logger.warning(
                "离线导入已提交但 NOTE_SECTION_SAVED 发布失败 project=%s sections=%s",
                project_id, result.changed_sections, exc_info=True,
            )

    return result.to_dict()
