"""Sprint C.0 — 附注离线导出/导入路由 (D15).

端点：
- POST /api/disclosure-notes/{project_id}/{year}/offline-export
- POST /api/disclosure-notes/{project_id}/{year}/offline-import/preview
- POST /api/disclosure-notes/{project_id}/{year}/offline-import/execute
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.deps import get_current_user, get_db

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-offline"])


@router.post("/{project_id}/{year}/offline-export")
async def export_offline_package(
    project_id: UUID,
    year: int,
    body: dict[str, Any] | None = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
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
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """执行导入 (C.0.18)."""
    import json

    from app.services.note_offline_import_service import (
        ConflictResolution,
        NoteOfflineImportService,
    )

    xlsx_bytes = await file.read()
    decisions_dict = {}
    try:
        raw = json.loads(decisions)
        for sid, choice in raw.items():
            decisions_dict[sid] = ConflictResolution(choice)
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"decisions 格式错误: {e}")

    service = NoteOfflineImportService(db)
    result = await service.execute_import(
        xlsx_bytes=xlsx_bytes,
        project_id=project_id,
        year=year,
        user_id=str(getattr(user, "id", "")),
        decisions=decisions_dict,
    )

    return result.to_dict()
