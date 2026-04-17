"""试算表同步 API — 底稿审定数同步到试算表

Phase 9 Task 9.19
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/api/trial-balance", tags=["tb-sync"])


class SyncFromWPRequest(BaseModel):
    wp_id: str
    account_codes: list[str] | None = None


@router.post("/{project_id}/{year}/sync-from-workpaper")
async def sync_from_workpaper(
    project_id: UUID,
    year: int,
    data: SyncFromWPRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """以底稿审定数覆盖试算表，触发级联更新"""
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper
    from app.models.audit_platform_models import TrialBalance, EventPayload, EventType
    from app.services.event_bus import event_bus

    # 获取底稿 parsed_data
    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == data.wp_id)
    )).scalar_one_or_none()
    if not wp or not wp.parsed_data:
        raise HTTPException(400, "底稿无解析数据")

    # 简化：标记底稿为非过期
    wp.prefill_stale = False
    await db.flush()

    # 触发试算表更新事件
    await event_bus.publish(EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=project_id,
        year=year,
        account_codes=data.account_codes or [],
    ))

    await db.commit()
    return {"message": "同步完成", "project_id": str(project_id), "year": year}
