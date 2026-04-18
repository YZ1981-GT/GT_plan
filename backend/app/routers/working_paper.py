"""底稿管理 API 路由

- GET    /api/projects/{id}/working-papers          — 底稿列表
- GET    /api/projects/{id}/working-papers/{wp_id}   — 底稿详情
- GET    /api/projects/{id}/working-papers/{wp_id}/download — 下载
- POST   /api/projects/{id}/working-papers/{wp_id}/upload   — 上传
- PUT    /api/projects/{id}/working-papers/{wp_id}/status   — 更新状态
- PUT    /api/projects/{id}/working-papers/{wp_id}/assign   — 分配
- POST   /api/projects/{id}/working-papers/{wp_id}/prefill  — 预填充
- POST   /api/projects/{id}/working-papers/{wp_id}/parse    — 解析回写
- GET    /api/projects/{id}/wp-index                 — 底稿索引列表
- GET    /api/projects/{id}/wp-cross-refs            — 交叉索引

Validates: Requirements 6.1-7.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.working_paper_service import WorkingPaperService
from app.services.prefill_service import PrefillService, ParseService
from app.models.workpaper_models import WpIndex, WpCrossRef, WorkingPaper

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class UploadRequest(BaseModel):
    recorded_version: int


class StatusUpdateRequest(BaseModel):
    status: str


class AssignRequest(BaseModel):
    assigned_to: UUID | None = None
    reviewer: UUID | None = None


# ---------------------------------------------------------------------------
# Working paper endpoints
# ---------------------------------------------------------------------------

@router.get("/working-papers")
async def list_workpapers(
    project_id: UUID,
    audit_cycle: str | None = None,
    status: str | None = None,
    assigned_to: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """底稿列表（支持筛选）"""
    svc = WorkingPaperService()
    return await svc.list_workpapers(
        db=db,
        project_id=project_id,
        audit_cycle=audit_cycle,
        status=status,
        assigned_to=assigned_to,
    )


@router.get("/working-papers/{wp_id}")
async def get_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """底稿详情"""
    svc = WorkingPaperService()
    detail = await svc.get_workpaper(db=db, wp_id=wp_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return detail


@router.get("/working-papers/{wp_id}/download")
async def download_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载底稿（含预填充）"""
    svc = WorkingPaperService()
    try:
        return await svc.download_for_offline(db=db, wp_id=wp_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/working-papers/{wp_id}/upload")
async def upload_workpaper(
    project_id: UUID,
    wp_id: UUID,
    data: UploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传离线编辑的底稿"""
    svc = WorkingPaperService()
    try:
        result = await svc.upload_offline_edit(
            db=db, wp_id=wp_id, recorded_version=data.recorded_version,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/working-papers/{wp_id}/status")
async def update_status(
    project_id: UUID,
    wp_id: UUID,
    data: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新底稿状态（含复核提交硬门槛）"""
    new_status = data.status

    # 提交复核时强制检查 4 项门禁
    if new_status in ("review_level1_passed", "review_level2_passed", "review_passed"):
        wp_result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = wp_result.scalar_one_or_none()
        if not wp:
            raise HTTPException(status_code=404, detail="底稿不存在")

        blocking_reasons = []

        # 门禁 1：复核人已分配
        if not wp.reviewer:
            blocking_reasons.append("复核人未分配")

        # 门禁 2：阻断级 QC 通过
        from app.models.workpaper_models import WpQcResult
        qc_result = await db.execute(
            sa.select(WpQcResult)
            .where(WpQcResult.working_paper_id == wp_id)
            .order_by(WpQcResult.check_timestamp.desc())
            .limit(1)
        )
        qc = qc_result.scalar_one_or_none()
        if qc is None:
            blocking_reasons.append("未执行质量自检")
        elif qc.blocking_count > 0:
            blocking_reasons.append(f"存在 {qc.blocking_count} 个阻断级 QC 问题")

        # 门禁 3：无未解决复核意见
        try:
            from app.models.phase10_models import CellAnnotation
            ann_result = await db.execute(
                sa.select(sa.func.count()).select_from(CellAnnotation).where(
                    CellAnnotation.project_id == project_id,
                    CellAnnotation.object_type == "workpaper",
                    CellAnnotation.object_id == wp_id,
                    CellAnnotation.status != "resolved",
                    CellAnnotation.is_deleted == sa.false(),
                )
            )
            unresolved = ann_result.scalar() or 0
            if unresolved > 0:
                blocking_reasons.append(f"{unresolved} 条未解决复核意见")
        except Exception:
            pass  # cell_annotations 表可能不存在

        if blocking_reasons:
            raise HTTPException(
                status_code=400,
                detail=f"无法提交复核：{'；'.join(blocking_reasons)}",
            )

    svc = WorkingPaperService()
    try:
        result = await svc.update_status(db=db, wp_id=wp_id, new_status=new_status)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/working-papers/{wp_id}/assign")
async def assign_workpaper(
    project_id: UUID,
    wp_id: UUID,
    data: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分配编制人/复核人"""
    svc = WorkingPaperService()
    try:
        result = await svc.assign_workpaper(
            db=db, wp_id=wp_id,
            assigned_to=data.assigned_to,
            reviewer=data.reviewer,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/working-papers/{wp_id}/prefill")
async def prefill_workpaper(
    project_id: UUID,
    wp_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发预填充"""
    svc = PrefillService()
    result = await svc.prefill_workpaper(db=db, project_id=project_id, year=year, wp_id=wp_id)
    return result


@router.post("/working-papers/{wp_id}/parse")
async def parse_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发解析回写"""
    svc = ParseService()
    result = await svc.parse_workpaper(db=db, project_id=project_id, wp_id=wp_id)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# WP Index & Cross-ref endpoints
# ---------------------------------------------------------------------------

@router.get("/wp-index")
async def list_wp_index(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """底稿索引列表"""
    result = await db.execute(
        sa.select(WpIndex)
        .where(WpIndex.project_id == project_id, WpIndex.is_deleted == sa.false())
        .order_by(WpIndex.wp_code)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "wp_code": i.wp_code,
            "wp_name": i.wp_name,
            "audit_cycle": i.audit_cycle,
            "status": i.status.value if i.status else None,
            "assigned_to": str(i.assigned_to) if i.assigned_to else None,
            "reviewer": str(i.reviewer) if i.reviewer else None,
        }
        for i in items
    ]


@router.get("/wp-cross-refs")
async def list_wp_cross_refs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """交叉索引关系"""
    result = await db.execute(
        sa.select(WpCrossRef)
        .where(WpCrossRef.project_id == project_id)
        .order_by(WpCrossRef.created_at)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "source_wp_id": str(i.source_wp_id),
            "target_wp_code": i.target_wp_code,
            "cell_reference": i.cell_reference,
        }
        for i in items
    ]
