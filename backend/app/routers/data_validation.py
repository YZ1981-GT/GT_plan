"""数据校验 API — Phase 8 Task 7.4"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.data_validation_engine import DataValidationEngine

router = APIRouter(prefix="/api/projects/{project_id}/data-validation", tags=["data-validation"])


@router.post("")
async def validate_project(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """运行全部数据校验。"""
    engine = DataValidationEngine(db)
    return await engine.validate_project(project_id, year)


@router.get("/findings")
async def get_findings(
    project_id: UUID,
    severity: str | None = None,
    check_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取校验结果（支持筛选）。"""
    engine = DataValidationEngine(db)
    result = await engine.validate_project(project_id)
    findings = result["findings"]
    if severity:
        findings = [f for f in findings if f["severity"] == severity]
    if check_type:
        findings = [f for f in findings if f["check_type"] == check_type]
    return {"findings": findings, "total": len(findings)}


@router.post("/fix")
async def fix_findings(
    project_id: UUID,
    finding_ids: list[str] = [],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一键修复常见错误。"""
    engine = DataValidationEngine(db)
    return await engine.auto_fix(project_id, finding_ids)


@router.post("/export")
async def export_findings(
    project_id: UUID,
    format: str = "csv",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出校验结果。"""
    from fastapi.responses import Response

    engine = DataValidationEngine(db)
    result = await engine.validate_project(project_id)
    content = engine.export_findings(result["findings"], format)
    return Response(
        content=content,
        media_type="text/csv" if format == "csv" else "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=validation_{project_id}.{format}"},
    )
