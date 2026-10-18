"""签发一致性清单 API。

Endpoints:
- GET  /api/projects/{project_id}/signoff/checklist — 获取签发一致性清单
- POST /api/projects/{project_id}/signoff/confirm-warning — 确认 warning 项（写审计日志）

鉴权按项目成员（``require_project_access("readonly")``）：清单含调整分录、报告意见等项目数据，历史实现只校验
登录 ⇒ 任意登录用户可读他人项目（spec deliverable-writeback-and-online-edit-integrity AC-1.4）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import Project, User
from app.services.project_audit_year import resolve_project_audit_year
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
    current_user: User = Depends(require_project_access("readonly")),
) -> SignoffChecklist:
    """获取签发一致性清单（每次实时计算，不走缓存）。

    年度：请求参数优先，其次项目审计年度；都取不到返回 422 —— 历史实现回落「今年 - 1」，
    年度猜错时清单查的是另一年的数据却照样显示「可签发」。
    """
    actual_year = year
    if actual_year is None:
        # ORM + 五级兜底（审计年度列 / 期间止 / 期间起 / 向导 / 项目名后缀），方言无关
        project = await db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        actual_year = resolve_project_audit_year(project)
    if actual_year is None:
        raise HTTPException(status_code=422, detail="无法确定审计年度：项目未设置审计期间，请在请求中指定年度")

    return await SignoffChecklistService(db).generate_checklist(project_id=project_id, year=actual_year)


@router.post("/confirm-warning")
async def confirm_warning(
    project_id: UUID,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict[str, str]:
    """确认 warning 项并写审计日志（``app_audit_log``）。

    🔴 留痕写入失败返回 503，不再静默返回「已确认」：签发前对告警的确认是审计证据，
    没有留痕的「已确认」与没确认没有区别。前端只在本端点成功后才记该项已确认。
    """
    details = {
        "item_index": body.get("item_index", -1),
        "item_message": body.get("item_message", ""),
        "item_category": body.get("item_category", ""),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.execute(
            text(
                "INSERT INTO app_audit_log "
                "(id, user_id, action, resource_type, resource_id, details, created_at) "
                "VALUES (gen_random_uuid(), :user_id, :action, :resource_type, :resource_id, "
                "CAST(:details AS jsonb), :now)"
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
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — 如实返回失败，由前端提示重试
        await db.rollback()
        logger.error("签发清单 warning 确认审计日志写入失败 project=%s: %s", project_id, exc)
        raise HTTPException(status_code=503, detail="确认记录写入失败，请稍后重试") from exc

    return {"status": "confirmed", "message": "已确认该告警项并记录"}
