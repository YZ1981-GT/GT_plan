"""底稿批量操作 + 看板 API 路由（从 working_paper.py 拆出，零行为变更）

批量+看板域端点（与 working_paper 主 router 共用 `/api/projects/{project_id}` 前缀）：
- GET    /working-papers-kanban                  — 底稿看板视图（按状态分组）
- POST   /working-papers/batch-assign            — 批量分配编制人/复核人
- POST   /working-papers/batch-submit            — 批量提交复核
- POST   /working-papers/batch-export            — 批量导出 ZIP
- GET    /working-papers/{wp_id}/edit-time        — 编制时间统计

请求模型 `BatchAssignRequest` / `BatchSubmitRequest` 仅由本模块端点使用，随端点同模块迁移。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.workpaper_models import WpIndex, WorkingPaper, WpFileStatus

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


# ═══ 底稿看板视图 + 批量操作 + 编制时间 ═══

class BatchAssignRequest(BaseModel):
    wp_ids: list[str]
    assigned_to: UUID | None = None
    reviewer: UUID | None = None


class BatchSubmitRequest(BaseModel):
    wp_ids: list[str]


@router.get("/working-papers-kanban")
async def get_workpapers_kanban(
    project_id: UUID,
    audit_cycle: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿看板视图 — 按状态分组统计

    返回4列看板数据：待编制 / 编制中 / 待复核 / 已通过
    每列包含底稿列表（编号/名称/负责人/天数）
    """
    query = sa.select(WpIndex, WorkingPaper).outerjoin(
        WorkingPaper, sa.and_(
            WorkingPaper.wp_index_id == WpIndex.id,
            WorkingPaper.is_deleted == sa.false(),
        )
    ).where(
        WpIndex.project_id == project_id,
        WpIndex.is_deleted == sa.false(),
    )
    if audit_cycle:
        query = query.where(WpIndex.audit_cycle == audit_cycle)
    query = query.order_by(WpIndex.wp_code)

    result = await db.execute(query)
    rows = result.all()

    kanban = {
        "not_started": [],   # 待编制
        "in_progress": [],   # 编制中
        "under_review": [],  # 待复核
        "completed": [],     # 已通过
    }

    for idx_row, wp in rows:
        status = wp.status.value if wp and wp.status else "not_started"
        item = {
            "wp_id": str(wp.id) if wp else None,
            "wp_code": idx_row.wp_code,
            "wp_name": idx_row.wp_name,
            "audit_cycle": idx_row.audit_cycle,
            "status": status,
            "assigned_to": str(wp.assigned_to) if wp and wp.assigned_to else None,
            "reviewer": str(wp.reviewer) if wp and hasattr(wp, 'reviewer') and wp.reviewer else None,
        }

        if status in ("not_started",):
            kanban["not_started"].append(item)
        elif status in ("draft", "edit_complete"):
            kanban["in_progress"].append(item)
        elif status in ("under_review", "review_level1", "review_level2"):
            kanban["under_review"].append(item)
        elif status in ("review_passed", "archived"):
            kanban["completed"].append(item)
        else:
            kanban["in_progress"].append(item)

    # 统计
    stats = {k: len(v) for k, v in kanban.items()}
    stats["total"] = sum(stats.values())
    stats["completion_rate"] = round(stats["completed"] / max(stats["total"], 1) * 100, 1)

    return {"kanban": kanban, "stats": stats}


@router.post("/working-papers/batch-assign")
async def batch_assign(
    project_id: UUID,
    data: BatchAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """批量分配底稿（编制人/复核人）"""
    updated = 0
    for wp_id_str in data.wp_ids:
        wp_id = UUID(wp_id_str)
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
        )
        wp = result.scalar_one_or_none()
        if not wp:
            continue
        if data.assigned_to is not None:
            wp.assigned_to = data.assigned_to
        if data.reviewer is not None:
            wp.reviewer = data.reviewer
        updated += 1

    await db.flush()
    await db.commit()
    return {"updated": updated, "message": f"已批量分配 {updated} 个底稿"}


@router.post("/working-papers/batch-submit")
async def batch_submit_review(
    project_id: UUID,
    data: BatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """批量提交复核（跳过不满足条件的底稿）"""
    submitted = 0
    skipped = []

    for wp_id_str in data.wp_ids:
        wp_id = UUID(wp_id_str)
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
        )
        wp = result.scalar_one_or_none()
        if not wp:
            skipped.append({"wp_id": wp_id_str, "reason": "不存在"})
            continue
        if wp.status != WpFileStatus.edit_complete:
            skipped.append({"wp_id": wp_id_str, "reason": f"状态为{wp.status.value}，需先完成编制"})
            continue

        # 简化门禁：检查复核人是否已分配
        if not wp.reviewer:
            skipped.append({"wp_id": wp_id_str, "reason": "未分配复核人"})
            continue

        wp.status = WpFileStatus.under_review
        submitted += 1

    await db.flush()
    await db.commit()
    return {"submitted": submitted, "skipped": skipped, "message": f"已提交 {submitted} 个，跳过 {len(skipped)} 个"}


@router.post("/working-papers/batch-export")
async def batch_export_zip(
    project_id: UUID,
    data: BatchSubmitRequest,  # 复用 wp_ids 字段
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """批量导出底稿为 ZIP"""
    import io
    import zipfile
    from pathlib import Path

    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    # Wp_Bound_Gate（Task 4 / R3）：打包底稿正文前用可见集过滤 wp_ids；
    # 不可见/跨项目/未委派/scope 外底稿静默剔除，manifest 只由可见集构建。
    _visible = make_bulk_visible_filter(
        db, current_user, entrypoint="workpaper.detail", action="read_detail",
        method="GET", entry_family="export",
    )
    visible_wp_ids = [wid for wid in data.wp_ids if await _visible(wid, None)]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for wp_id_str in visible_wp_ids:
            wp_id = UUID(wp_id_str)
            result = await db.execute(
                sa.select(WorkingPaper, WpIndex)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
            )
            row = result.first()
            if not row:
                continue
            wp, idx = row
            if wp.file_path:
                fp = Path(wp.file_path)
                if fp.exists():
                    arcname = f"{idx.audit_cycle or 'OTHER'}/{idx.wp_code}.xlsx"
                    zf.write(fp, arcname)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=workpapers_{project_id}.zip"},
    )


@router.get("/working-papers/{wp_id}/edit-time")
async def get_edit_time(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿编制时间统计

    从审计日志中提取编辑时间段（首次编辑→提交复核）。
    """
    from app.models.core import Log

    # 查找该底稿的编辑相关日志
    result = await db.execute(
        sa.select(Log.created_at, Log.action).where(
            sa.or_(
                sa.and_(Log.action == "workpaper_online_open", Log.new_value.contains(str(wp_id))),
                sa.and_(Log.action == "workpaper_online_save", Log.new_value.contains(str(wp_id))),
            )
        ).order_by(Log.created_at)
    )
    logs = result.all()

    if not logs:
        return {"wp_id": str(wp_id), "total_minutes": 0, "sessions": 0, "message": "无编辑记录"}

    # 计算编辑时间（相邻 open-save 配对）
    total_minutes = 0
    sessions = 0
    first_edit = logs[0][0] if logs else None
    last_edit = logs[-1][0] if logs else None

    # 简化计算：总时长 = 最后一次操作 - 第一次操作
    if first_edit and last_edit and first_edit != last_edit:
        diff = (last_edit - first_edit).total_seconds() / 60
        total_minutes = round(diff, 1)
        sessions = len([l for l in logs if l[1] == "workpaper_online_open"])

    return {
        "wp_id": str(wp_id),
        "total_minutes": total_minutes,
        "sessions": sessions,
        "first_edit": first_edit.isoformat() if first_edit else None,
        "last_edit": last_edit.isoformat() if last_edit else None,
    }
