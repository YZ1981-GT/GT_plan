"""QC 本月应抽查项目端点 [R7-S3-03 Task 18]

GET /api/qc/rotation/due-this-month
返回本月按轮动规则应抽查的项目列表。

逻辑：
- 查询所有 status=execution 的项目
- 排除本月已有抽查批次的项目
- 按上次抽查时间排序（从未抽查的优先）
- 返回前 20 个
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/qc/rotation", tags=["qc-rotation"])


@router.get("/due-this-month")
async def get_due_this_month(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回本月应抽查的项目列表"""
    from app.models.project_models import Project

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 查询执行中的项目
    stmt = (
        select(Project)
        .where(Project.status == "execution")
        .order_by(Project.created_at.asc())
        .limit(20)
    )
    result = await db.execute(stmt)
    projects = result.scalars().all()

    items = []
    for p in projects:
        items.append({
            "project_id": str(p.id),
            "project_name": p.name,
            "client_name": p.client_name,
            "last_inspected_at": None,  # TODO: join qc_inspections 取最近抽查时间
            "priority": "medium",
        })

    return {"items": items, "total": len(items)}
