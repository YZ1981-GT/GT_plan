"""EQCR 快照 API 路由。

提供 EQCR 独立复核快照的创建、获取和刷新功能。
快照数据为只读，供 EQCR 合伙人在复核期间查看冻结版本。

路由内部已声明 prefix="/api/projects/{project_id}/eqcr/snapshot"，注册时不加额外前缀。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services import eqcr_snapshot_service

router = APIRouter(
    prefix="/api/projects/{project_id}/eqcr/snapshot",
)


@router.post("", summary="创建 EQCR 快照")
async def create_snapshot(
    project_id: UUID,
    year: int = Query(default=None, description="快照年度，默认当前年度-1"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("edit")),
):
    """创建 EQCR 快照（manager+ 权限）。

    聚合底稿+报表+AJE+VR 数据，生成只读快照供 EQCR 复核使用。
    """
    if year is None:
        from datetime import datetime

        year = datetime.utcnow().year - 1

    result = await eqcr_snapshot_service.create_snapshot(
        db=db,
        project_id=project_id,
        year=year,
        user_id=_user.id,
    )
    return result


@router.get("", summary="获取当前 EQCR 快照")
async def get_current_snapshot(
    project_id: UUID,
    year: int = Query(default=None, description="快照年度，默认当前年度-1"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
):
    """获取当前有效的 EQCR 快照。

    返回最新的 is_current=TRUE 快照数据。
    """
    if year is None:
        from datetime import datetime

        year = datetime.utcnow().year - 1

    result = await eqcr_snapshot_service.get_current_snapshot(
        db=db,
        project_id=project_id,
        year=year,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="当前项目暂无 EQCR 快照，请先创建快照",
        )
    return result


@router.post("/refresh", summary="刷新 EQCR 快照")
async def refresh_snapshot(
    project_id: UUID,
    year: int = Query(default=None, description="快照年度，默认当前年度-1"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("edit")),
):
    """刷新 EQCR 快照（EQCR 权限）。

    将旧快照标记为非当前，创建新快照反映最新项目数据。
    """
    if year is None:
        from datetime import datetime

        year = datetime.utcnow().year - 1

    result = await eqcr_snapshot_service.refresh_snapshot(
        db=db,
        project_id=project_id,
        year=year,
        user_id=_user.id,
    )
    return result
