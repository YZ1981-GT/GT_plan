"""底稿催办端点 — Round 2 需求 4

POST /api/projects/{project_id}/workpapers/{wp_id}/remind
  body: {message?: str}
  resp: {ticket_id, notification_id, remind_count, allowed_next}

7 天内最多 3 次催办（按自然日计），超过返回 429。
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.workpaper_remind_service import workpaper_remind_service

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["workpaper-remind"],
)


# ── 请求/响应 Schema ──────────────────────────────────────────────


class RemindRequest(BaseModel):
    message: Optional[str] = Field(None, description="自定义催办消息（可选）")


class RemindResponse(BaseModel):
    ticket_id: str
    notification_id: Optional[str] = None
    remind_count: int
    allowed_next: Optional[str] = None


# ── 端点 ──────────────────────────────────────────────────────────


@router.post("/{wp_id}/remind", response_model=RemindResponse)
async def remind_workpaper(
    project_id: UUID,
    wp_id: UUID,
    body: RemindRequest = RemindRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """催办底稿编制人。

    创建 IssueTicket(source='reminder') + Notification(type='workpaper_reminder')。
    7 天内同一底稿最多催办 3 次，超限返回 429。
    """
    result = await workpaper_remind_service.remind(
        db=db,
        project_id=project_id,
        wp_id=wp_id,
        operator_id=current_user.id,
        message=body.message,
    )
    return RemindResponse(**result)
