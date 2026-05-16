"""附注 Word 导出端点

POST /api/projects/{pid}/notes/export-word — 导出附注 Word 文件

Requirements: 4.1, 4.11
"""
from __future__ import annotations

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/notes",
    tags=["note-export"],
)


class ExportWordRequest(BaseModel):
    """Word 导出请求参数"""
    year: int = Field(..., description="年度")
    template_type: str = Field("soe", description="模板类型 (soe/listed)")
    sections: list[str] | None = Field(None, description="指定导出章节列表")
    skip_empty: bool = Field(False, description="是否跳过空章节")


@router.post("/export-word")
async def export_word(
    project_id: UUID,
    body: ExportWordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出附注为 Word 文档（致同标准格式）

    Requirements: 4.1, 4.11
    """
    # Validate template_type
    if body.template_type not in ("soe", "listed"):
        raise HTTPException(status_code=400, detail="template_type must be 'soe' or 'listed'")

    # Get project for filename
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Generate Word document
    from app.services.note_word_exporter import NoteWordExporter

    exporter = NoteWordExporter(db)
    try:
        output = await exporter.export(
            project_id=project_id,
            year=body.year,
            template_type=body.template_type,
            sections=body.sections,
            skip_empty=body.skip_empty,
        )
    except Exception as e:
        logger.exception("Word export failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Word export failed: {str(e)}")

    # Build filename per 致同 naming convention
    company_short = _get_company_short_name(project)
    filename = sanitize_export_filename(f"{company_short}_{body.year}年度财务报表附注.docx")

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    )


def _get_company_short_name(project: Project) -> str:
    """Get company short name from project config."""
    # Try wizard_state first for explicit short name
    if project.wizard_state and isinstance(project.wizard_state, dict):
        short_name = project.wizard_state.get("company_short_name")
        if short_name:
            return short_name

    # Fall back to client_name or project name
    name = project.client_name or project.name or "未知公司"
    # Extract meaningful short name (first 4 Chinese chars)
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', name)
    if len(chinese_chars) <= 6:
        return name
    return "".join(chinese_chars[:4])


def sanitize_export_filename(filename: str) -> str:
    """Replace special characters in filename with underscores.

    Requirements: 32.4
    """
    return re.sub(r'[/\\:*?"<>|]', '_', filename)
