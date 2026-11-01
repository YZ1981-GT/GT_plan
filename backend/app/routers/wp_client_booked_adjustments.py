"""底稿公共外壳读取所涉“客户已入账”调整提示。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import authorize_wp_read, get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.adjustment_client_booking import effective_booking_impacts_for_accounts
from app.services.project_audit_year import fetch_project_audit_year
from app.services.report_stale_service import account_codes_for_wp_code

router = APIRouter(prefix="/api/workpapers", tags=["workpapers"])


@router.get("/{wp_id}/client-booked-adjustments")
async def get_workpaper_client_booked_adjustments(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project_id = await authorize_wp_read(db, current_user, wp_id)
    row = (await db.execute(select(WpIndex.wp_code).join(
        WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id,
    ).where(
        WorkingPaper.id == wp_id,
        WorkingPaper.project_id == project_id,
        WorkingPaper.is_deleted.is_(False),
        WpIndex.is_deleted.is_(False),
    ))).first()
    if row is None:
        return {"items": [], "count": 0, "wp_code": None, "account_codes": []}
    wp_code = row.wp_code
    year = await fetch_project_audit_year(db, project_id)
    account_codes = account_codes_for_wp_code(wp_code)
    items = await effective_booking_impacts_for_accounts(
        db, project_id=project_id, year=year, account_codes=account_codes,
    ) if year and account_codes else []
    return {"items": items, "count": len(items), "wp_code": wp_code, "account_codes": account_codes}
