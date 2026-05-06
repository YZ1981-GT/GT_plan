"""质控复核人员视角 API — QC总览 / 按人员进度 / 问题追踪 / 归档前检查"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.qc_dashboard_service import (
    QCDashboardService,
    StaffProgressService,
    ReviewIssueTracker,
    ArchiveReadinessService,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/qc-dashboard",
    tags=["qc-dashboard"],
)


@router.get("/overview")
async def get_qc_overview(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """QC 质量总览看板"""
    svc = QCDashboardService(db)
    return await svc.get_overview(project_id)


@router.get("/staff-progress")
async def get_staff_progress(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """按人员统计底稿进度"""
    svc = StaffProgressService(db)
    return await svc.get_staff_progress(project_id)


@router.get("/open-issues")
async def get_open_issues(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """未解决的复核意见汇总"""
    svc = ReviewIssueTracker(db)
    return await svc.get_open_issues(project_id)


@router.get("/archive-readiness")
async def check_archive_readiness(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """归档前 readiness 门面（R1 Task 7）：
    内部调 ``gate_engine.evaluate('export_package')``，按 12 项类目分组返回。
    """
    svc = ArchiveReadinessService(db)
    return await svc.check_readiness(project_id, actor_id=current_user.id)


@router.post("/archive-readiness")
async def run_archive_readiness_check(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """重新执行归档前检查（同 GET 但语义为"立即重跑并生成新 gate_eval_id"）"""
    svc = ArchiveReadinessService(db)
    return await svc.check_readiness(project_id, actor_id=current_user.id)
