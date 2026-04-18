"""质量自检 API 路由

- POST /api/projects/{id}/working-papers/{wp_id}/qc-check  — 执行自检
- GET  /api/projects/{id}/working-papers/{wp_id}/qc-results — 获取结果
- GET  /api/projects/{id}/qc-summary                        — 项目级汇总

Validates: Requirements 8.1-9.3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WpQcResult
from app.services.qc_engine import QCEngine

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["qc"],
)


@router.post("/working-papers/{wp_id}/qc-check")
async def qc_check(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行质量自检"""
    engine = QCEngine()
    try:
        result = await engine.check(db=db, wp_id=wp_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/working-papers/{wp_id}/qc-results")
async def get_qc_results(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取自检结果（最新一次）"""
    result = await db.execute(
        sa.select(WpQcResult)
        .where(WpQcResult.working_paper_id == wp_id)
        .order_by(WpQcResult.check_timestamp.desc())
        .limit(1)
    )
    qc = result.scalar_one_or_none()
    if qc is None:
        return {"message": "尚未执行自检", "findings": [], "passed": None}

    return {
        "id": str(qc.id),
        "working_paper_id": str(qc.working_paper_id),
        "check_timestamp": qc.check_timestamp.isoformat() if qc.check_timestamp else None,
        "findings": qc.findings,
        "passed": qc.passed,
        "blocking_count": qc.blocking_count,
        "warning_count": qc.warning_count,
        "info_count": qc.info_count,
    }


@router.get("/qc-summary")
async def get_qc_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """项目级QC汇总"""
    engine = QCEngine()
    return await engine.get_project_summary(db=db, project_id=project_id)
