"""底稿 xlsx 导出端点

POST /api/workpapers/{wp_id}/export-xlsx
按 design §5.1.3 实现：导出 xlsx（致同模板填值还原）。

Requirements: 2.1（一键导出 Excel）
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_render_schema_service import WpRenderSchemaService
from app.services.wp_xlsx_export_service import (
    ExportValidationError,
    TemplateNotFoundError,
    export_workpaper_xlsx,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-xlsx-export"],
)

# Singleton schema service (stateless + cache)
_schema_service = WpRenderSchemaService()


@router.post("/{wp_id}/export-xlsx")
async def export_xlsx(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出底稿 xlsx（致同模板填值还原）。

    EARS:
    - WHEN 模板 xlsx 不存在 THEN 返回 500 + 提示"模板缺失"
    - WHEN 用户数据不完整（必填字段为空） THEN 返回 422 + 字段清单
    - IF wp_id 不存在 THEN 返回 404
    """
    # ─── Step 1: 查 working_paper ─────────────────────────────────────────
    wp_query = sa.select(WorkingPaper).where(
        WorkingPaper.id == wp_id,
        WorkingPaper.is_deleted == False,  # noqa: E712
    )
    wp_result = await db.execute(wp_query)
    working_paper = wp_result.scalars().first()

    if working_paper is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # ─── Step 2: 查 wp_index 获取 wp_code ────────────────────────────────
    wp_index_query = sa.select(WpIndex).where(
        WpIndex.id == working_paper.wp_index_id,
        WpIndex.is_deleted == False,  # noqa: E712
    )
    wp_index_result = await db.execute(wp_index_query)
    wp_index = wp_index_result.scalars().first()

    if wp_index is None:
        raise HTTPException(status_code=404, detail="底稿索引不存在")

    wp_code = wp_index.wp_code

    # ─── Step 3: 加载 render schema ──────────────────────────────────────
    try:
        schema = _schema_service.load_schema(wp_code=wp_code)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail=f"渲染 schema 未找到：wp_code={wp_code}",
        )

    # ─── Step 4: 获取项目元数据 ──────────────────────────────────────────
    project_query = sa.select(Project).where(
        Project.id == working_paper.project_id,
    )
    project_result = await db.execute(project_query)
    project = project_result.scalars().first()

    project_meta: dict = {}
    if project:
        project_meta = {
            "entity_name": project.client_name or "",
            "period_end": (
                project.audit_period_end.isoformat()
                if project.audit_period_end
                else ""
            ),
            "index_no": wp_code,
        }

    # ─── Step 5: 获取 html_data ──────────────────────────────────────────
    parsed_data = working_paper.parsed_data or {}
    html_data = parsed_data.get("html_data", {})

    # ─── Step 6: 调用导出服务 ────────────────────────────────────────────
    try:
        xlsx_buf = await export_workpaper_xlsx(
            wp_code=wp_code,
            html_data=html_data,
            schema=schema,
            project_meta=project_meta,
        )
    except TemplateNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail=f"模板文件缺失：{e}",
        )
    except ExportValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "export_validation_error",
                "message": f"导出必填字段缺失：{e.missing_fields}",
                "missing_fields": e.missing_fields,
            },
        )

    # ─── Step 7: 构造下载文件名 ──────────────────────────────────────────
    # 取第一个 sheet 名作为文件名后缀
    sheets_schema = schema.get("sheets", {})
    first_sheet_name = next(iter(sheets_schema), wp_code)
    filename = f"{wp_code}_{first_sheet_name}.xlsx"

    # ─── Step 8: 返回 StreamingResponse ──────────────────────────────────
    content_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # RFC 5987: 非 ASCII 文件名用 filename* 编码，ASCII fallback 用 filename
    from urllib.parse import quote
    ascii_filename = f"{wp_code}.xlsx"
    encoded_filename = quote(filename)
    content_disposition = (
        f"attachment; filename=\"{ascii_filename}\"; "
        f"filename*=UTF-8''{encoded_filename}"
    )
    headers = {
        "Content-Disposition": content_disposition,
    }

    return StreamingResponse(
        content=xlsx_buf,
        media_type=content_type,
        headers=headers,
    )
