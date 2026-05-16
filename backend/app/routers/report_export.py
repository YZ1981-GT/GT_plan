"""报表 Excel 导出端点

POST /api/projects/{pid}/reports/export-excel — 导出报表 Excel 文件

Requirements: 3.13, 3.14, 3.15
"""
from __future__ import annotations

import logging
import re
from typing import Any
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
    prefix="/api/projects/{project_id}/reports",
    tags=["report-export"],
)


class ExportExcelRequest(BaseModel):
    """Excel 导出请求参数"""
    year: int = Field(..., description="年度")
    report_types: list[str] | None = Field(
        None,
        description="指定导出哪些报表（balance_sheet/income_statement/cash_flow_statement/equity_statement）",
    )
    include_prior_year: bool = Field(True, description="是否包含上年对比列")
    mode: str = Field("audited", description="unadjusted（未审）或 audited（审定）")


@router.post("/export-excel")
async def export_excel(
    project_id: UUID,
    body: ExportExcelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出报表 Excel 文件

    返回 xlsx 文件流（Content-Disposition attachment）。

    Requirements: 3.13, 3.14, 3.15
    """
    # Validate mode
    if body.mode not in ("unadjusted", "audited"):
        raise HTTPException(status_code=400, detail="mode must be 'unadjusted' or 'audited'")

    # Validate report_types if provided
    valid_types = {"balance_sheet", "income_statement", "cash_flow_statement", "equity_statement"}
    if body.report_types:
        invalid = set(body.report_types) - valid_types
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid report_types: {invalid}. Valid: {valid_types}",
            )

    # Get project for filename
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Generate Excel
    from app.services.report_excel_exporter import ReportExcelExporter

    exporter = ReportExcelExporter(db)
    try:
        output = await exporter.export(
            project_id=project_id,
            year=body.year,
            mode=body.mode,
            report_types=body.report_types,
            include_prior_year=body.include_prior_year,
        )
    except Exception as e:
        logger.exception("Excel export failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Excel export failed: {str(e)}")

    # Build filename
    company_short = _get_company_short_name(project.name or "未知公司")
    mode_label = "未审" if body.mode == "unadjusted" else "审定"
    filename = f"{company_short}_{body.year}年度财务报表({mode_label}).xlsx"
    # Sanitize filename
    filename = _sanitize_filename(filename)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    )


def _get_company_short_name(full_name: str) -> str:
    """Extract short company name (first 4 Chinese chars or full name if short)."""
    # Extract Chinese characters
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', full_name)
    if len(chinese_chars) <= 4:
        return full_name
    return "".join(chinese_chars[:4])


def _sanitize_filename(filename: str) -> str:
    """Replace special characters in filename with underscores."""
    return re.sub(r'[/\\:*?"<>|]', '_', filename)
