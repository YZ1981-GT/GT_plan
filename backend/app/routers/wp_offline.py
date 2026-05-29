"""Sprint 4 Task 15 — 底稿离线导出/导入路由 (US-14).

端点：
- POST /api/workpapers/{wp_id}/offline/export-template
- POST /api/workpapers/{wp_id}/offline/import-preview
- POST /api/workpapers/{wp_id}/offline/import-apply
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.deps import get_current_user, get_db

router = APIRouter(prefix="/api/workpapers", tags=["wp-offline"])


@router.post("/{wp_id}/offline/export-template")
async def export_template(
    wp_id: UUID,
    body: dict[str, Any] | None = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """导出底稿填写模板 (15.9)."""
    from app.services.wp_offline_export_service import WpOfflineExportService

    body = body or {}
    service = WpOfflineExportService(db)

    xlsx_bytes, file_hash = await service.export_template(
        wp_id=wp_id,
        sheet_names=body.get("sheet_names"),
        password=body.get("password"),
        exporter_name=getattr(user, "username", ""),
        deadline=body.get("deadline", ""),
        contact_name=body.get("contact_name", ""),
        contact_email=body.get("contact_email", ""),
        contact_phone=body.get("contact_phone", ""),
    )

    if not xlsx_bytes:
        raise HTTPException(status_code=404, detail="底稿不存在或无数据")

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=wp_template_{wp_id}.xlsx",
            "X-File-Hash": file_hash,
        },
    )


@router.post("/{wp_id}/offline/import-preview")
async def import_preview(
    wp_id: UUID,
    file: UploadFile = File(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """校验并预览导入 diff (15.9)."""
    from app.services.wp_offline_import_service import WpOfflineImportService

    xlsx_bytes = await file.read()
    service = WpOfflineImportService(db)

    result = await service.validate_and_preview(
        xlsx_bytes=xlsx_bytes,
        wp_id=wp_id,
    )

    return result


@router.post("/{wp_id}/offline/import-apply")
async def import_apply(
    wp_id: UUID,
    file: UploadFile = File(...),
    strategy: str = Form("overwrite"),
    merge_cells: str = Form("{}"),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """执行导入 (15.9)."""
    from app.services.wp_offline_import_service import (
        ConflictStrategy,
        WpOfflineImportService,
    )

    xlsx_bytes = await file.read()

    # Parse strategy
    try:
        conflict_strategy = ConflictStrategy(strategy)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的冲突策略: {strategy}")

    # Parse merge_cells
    merge_cells_dict: dict[str, list[str]] | None = None
    try:
        raw = json.loads(merge_cells)
        if raw:
            merge_cells_dict = raw
    except (json.JSONDecodeError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"merge_cells 格式错误: {e}")

    service = WpOfflineImportService(db)
    result = await service.execute_import(
        xlsx_bytes=xlsx_bytes,
        wp_id=wp_id,
        user_id=str(getattr(user, "id", "")),
        strategy=conflict_strategy,
        merge_cells=merge_cells_dict,
    )

    return result.to_dict()
