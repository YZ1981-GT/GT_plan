"""签发一致性清单 API（P2-2）。

Endpoints:
- GET  /api/projects/{project_id}/signoff/checklist — 获取签发一致性清单
- POST /api/projects/{project_id}/signoff/confirm-warning — 确认 warning 项（审计日志）

Requirements: 5.1, 5.2, 5.3
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.core import User
from app.services.signoff_checklist_service import (
    SignoffChecklist,
    SignoffChecklistService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/signoff",
    tags=["signoff-checklist"],
)


@router.get("/checklist", response_model=SignoffChecklist)
async def get_signoff_checklist(
    project_id: UUID,
    year: int | None = Query(None, description="审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignoffChecklist:
    """获取签发一致性清单。

    每次请求实时计算，不走缓存。
    """
    # 若未指定年度，从项目获取
    actual_year = year
    if actual_year is None:
        try:
            result = await db.execute(
                text("SELECT EXTRACT(YEAR FROM audit_period_end)::int FROM projects WHERE id = :pid"),
                {"pid": str(project_id)},
            )
            row = result.fetchone()
            actual_year = row[0] if row and row[0] else 2025
        except Exception:
            actual_year = 2025

    svc = SignoffChecklistService(db)
    checklist = await svc.generate_checklist(
        project_id=project_id,
        year=actual_year,
    )
    return checklist


@router.post("/confirm-warning")
async def confirm_warning(
    project_id: UUID,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """确认 warning 项，记录审计日志。

    P2-2.4: 确认动作写入 app_audit_log。
    """
    item_index = body.get("item_index", -1)
    item_message = body.get("item_message", "")
    item_category = body.get("item_category", "")

    details = {
        "item_index": item_index,
        "item_message": item_message,
        "item_category": item_category,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await db.execute(
            text(
                "INSERT INTO app_audit_log "
                "(id, user_id, action, resource_type, resource_id, details, created_at) "
                "VALUES (gen_random_uuid(), :user_id, :action, :resource_type, :resource_id, :details::jsonb, :now)"
            ),
            {
                "user_id": str(current_user.id),
                "action": "signoff_warning_confirmed",
                "resource_type": "signoff_checklist",
                "resource_id": str(project_id),
                "details": json.dumps(details, ensure_ascii=False),
                "now": datetime.now(timezone.utc),
            },
        )
        await db.flush()
        await db.commit()
    except Exception as exc:
        logger.error("签发清单 warning 确认审计日志写入失败: %s", exc)
        # 审计日志写入失败不阻断业务
        pass

    return {"status": "confirmed", "message": f"已确认 {item_category} 警告项"}
