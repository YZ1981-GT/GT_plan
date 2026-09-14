"""L7 其他非流动负债 — 导入导出三级端点

3个端点：
- GET  /api/l7-other-noncurrent-liabilities/{wp_id}/export-template   多sheet空白模板xlsx
- GET  /api/l7-other-noncurrent-liabilities/{wp_id}/export-data        当前数据xlsx
- POST /api/l7-other-noncurrent-liabilities/{wp_id}/import-data        解析xlsx写入（multipart）

科目编码: 2801其他非流动负债（贷方/负债类）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 5.5
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.l7_other_noncurrent_liabilities_service import (
    export_data,
    export_template,
    import_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/l7-other-noncurrent-liabilities",
    tags=["L7 其他非流动负债"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def l7_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（多sheet，按动态行表格分sheet）

    Query params:
        sheet: 可选，指定导出单个sheet（L7-1/L7-2/L7-3/L7-4）

    Requirements: 5.5
    """
    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"L7其他非流动负债_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/{wp_id}/export-data")
async def l7_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（多sheet）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 5.5
    """
    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"L7其他非流动负债_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/{wp_id}/import-data")
async def l7_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持多sheet）

    Query params:
        sheet: 可选，指定导入目标sheet

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 5.5
    """
    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result
