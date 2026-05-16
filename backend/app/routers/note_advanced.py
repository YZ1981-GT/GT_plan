"""附注高级功能路由 — 上年导入/交叉引用/变动分析

Requirements: 42.1-42.5, 43.1-43.5, 51.1-51.8
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db

router = APIRouter(prefix="/api/projects/{project_id}/notes")


# ---------------------------------------------------------------------------
# 上年附注导入 (Requirements: 51.1-51.8)
# ---------------------------------------------------------------------------


@router.post("/import-prior-year")
async def import_prior_year_notes(
    project_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Import prior year notes from a .docx file.

    Parses Word document sections and matches to current year notes by title.
    """
    if not file.filename or not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="仅支持 .docx 格式文件")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="文件大小超过 50MB 限制")

    from app.services.note_prior_year_import_service import NotePriorYearImportService

    service = NotePriorYearImportService(db)
    # Default year from project context (use current year)
    from app.models.core import Project
    import sqlalchemy as sa
    result = await db.execute(sa.select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    year = project.current_year if hasattr(project, 'current_year') else 2025

    import_result = await service.import_from_docx(project_id, year, file_bytes)
    await db.commit()
    return import_result


@router.post("/inherit-prior-year")
async def inherit_prior_year_notes(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Inherit notes from prior year database (continuous audit projects)."""
    from app.services.note_prior_year_import_service import NotePriorYearImportService

    service = NotePriorYearImportService(db)
    result = await service.inherit_from_prior_year(project_id, year)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# 交叉引用 (Requirements: 42.1-42.5)
# ---------------------------------------------------------------------------


@router.get("/cross-references")
async def get_cross_references(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get cross-reference mappings between report rows and note sections."""
    from app.services.note_cross_reference_service import NoteCrossReferenceService

    service = NoteCrossReferenceService(db)
    return await service.generate_cross_references(project_id, year)


@router.post("/cross-references/update")
async def update_cross_references(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update all cross-references after section reordering."""
    from app.services.note_cross_reference_service import NoteCrossReferenceService

    service = NoteCrossReferenceService(db)
    result = await service.update_all_references(project_id, year)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# 变动分析 (Requirements: 43.1-43.5)
# ---------------------------------------------------------------------------


@router.post("/generate-variation-analysis")
async def generate_variation_analysis(
    project_id: UUID,
    year: int = 2025,
    threshold: float | None = None,
    force_row_codes: list[str] | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate variation analysis paragraphs for accounts exceeding threshold.

    Default threshold: 20%. Accounts with change rate > threshold get
    auto-generated analysis paragraphs with {原因占位} for user to fill.
    """
    from app.services.note_variation_analysis_service import NoteVariationAnalysisService

    service = NoteVariationAnalysisService(db)
    effective_threshold = Decimal(str(threshold)) if threshold else None
    return await service.generate_variation_analysis(
        project_id, year, effective_threshold, force_row_codes
    )
