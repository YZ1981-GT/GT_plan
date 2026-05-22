"""待回复批注聚合端点 — Phase 6 F5

提供当前用户负责底稿上的未解决批注聚合查询。
JOIN working_paper.assigned_to = current_user.id 实现"我的待回复"。

Validates: Requirements F5.1, F5.2, F5.3, F5.4, F5.8
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.workpaper_models import ReviewRecord, WorkingPaper, WpIndex

router = APIRouter(prefix="/api/projects", tags=["my-reviews"])

# 优先级排序映射（must_fix > suggest > info）
PRIORITY_ORDER = case(
    (ReviewRecord.priority == "must_fix", 1),
    (ReviewRecord.priority == "suggest", 2),
    (ReviewRecord.priority == "info", 3),
    else_=4,
)


@router.get("/{project_id}/my-reviews")
async def get_my_reviews(
    project_id: UUID,
    status: str = Query(default="open", description="批注状态过滤: open/replied/resolved"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回当前用户负责底稿上的批注列表。

    排序：优先级降序（must_fix > suggest > info）+ 创建时间升序
    """
    # 验证项目存在
    project_result = await db.execute(
        select(Project.id).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # 查询：JOIN working_paper.assigned_to = current_user.id
    # ReviewRecord → WorkingPaper → WpIndex（获取 wp_code/wp_name）
    commenter = User.__table__.alias("commenter")

    stmt = (
        select(
            ReviewRecord.id.label("review_id"),
            WpIndex.wp_code,
            WpIndex.wp_name,
            ReviewRecord.cell_reference,
            ReviewRecord.comment_text,
            commenter.c.username.label("commenter_name"),
            ReviewRecord.priority,
            ReviewRecord.created_at,
            WorkingPaper.id.label("wp_id"),
        )
        .join(WorkingPaper, ReviewRecord.working_paper_id == WorkingPaper.id)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .outerjoin(commenter, ReviewRecord.commenter_id == commenter.c.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.assigned_to == current_user.id,
            ReviewRecord.status == status,
            ReviewRecord.is_deleted == False,  # noqa: E712
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
        .order_by(PRIORITY_ORDER.asc(), ReviewRecord.created_at.asc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    items = [
        {
            "review_id": str(row.review_id),
            "wp_code": row.wp_code,
            "wp_name": row.wp_name,
            "wp_id": str(row.wp_id),
            "cell_reference": row.cell_reference,
            "comment_text": row.comment_text,
            "commenter_name": row.commenter_name or "未知用户",
            "priority": row.priority,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]

    # 统计摘要
    must_fix = sum(1 for item in items if item["priority"] == "must_fix")
    suggest = sum(1 for item in items if item["priority"] == "suggest")
    info = sum(1 for item in items if item["priority"] == "info")

    return {
        "items": items,
        "summary": {
            "must_fix": must_fix,
            "suggest": suggest,
            "info": info,
            "total": len(items),
        },
    }
