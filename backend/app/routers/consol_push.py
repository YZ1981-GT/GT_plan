"""合并推送路由（spec consol-elimination-single-source-push 任务 4.4，需求 8 / 7.3）

- ``POST /api/consolidation/{project_id}/{year}/push``      立即推送（后台执行，返回是否新排队）
- ``GET  /api/consolidation/{project_id}/{year}/push-runs`` 最近推送运行（步骤、警告、状态）
- ``GET  /api/consolidation/{project_id}/{year}/push-status`` 最近一次推送 + 是否过期

推送在后台任务里用自己的会话执行（不占请求连接）；结果经 SSE ``consol.pushed`` / ``consol.push_failed``
推给合并页，也可查 ``push-runs`` 兜底。本 router 在 ``router_registry/system.py`` §6 合并报表组登记。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import Project, User
from app.services.consol_push_service import (
    TRIGGER_FORMULA,
    TRIGGER_MANUAL,
    list_runs,
    push_status,
    request_push,
)

router = APIRouter(prefix="/api/consolidation", tags=["合并推送"])


class PushRequest(BaseModel):
    # manual = 用户点「立即推送」；formula_changed = 公式管理保存合并口径公式后由前端调用
    trigger: str = TRIGGER_MANUAL


async def _require_consolidated(db: AsyncSession, project_id: UUID) -> None:
    scope = (await db.execute(
        sa.select(Project.report_scope).where(Project.id == project_id, Project.is_deleted == sa.false())
    )).first()
    if scope is None:
        raise HTTPException(status_code=404, detail="项目不存在或已删除")
    if (scope[0] or "").strip().lower() != "consolidated":
        raise HTTPException(status_code=400, detail="只有合并报表项目可以推送合并数据")


@router.post("/{project_id}/{year}/push")
async def trigger_push(
    project_id: UUID,
    year: int,
    body: PushRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """立即推送：本项目 + 上层合并项目依次重算差额表 → 合并试算 → 合并报表 → 标记附注待更新。"""
    trigger = (body.trigger if body else TRIGGER_MANUAL) or TRIGGER_MANUAL
    if trigger not in (TRIGGER_MANUAL, TRIGGER_FORMULA):
        raise HTTPException(status_code=400, detail="手动推送的触发来源只能是 manual 或 formula_changed")
    await _require_consolidated(db, project_id)
    task = request_push(project_id, year, trigger=trigger, user_id=getattr(user, "id", None))
    return {
        "queued": task is not None,
        "message": "已开始推送，完成后自动刷新" if task is not None else "已有推送在排队，本次请求已并入",
        "project_id": str(project_id),
        "year": year,
    }


@router.get("/{project_id}/{year}/push-runs")
async def get_push_runs(
    project_id: UUID,
    year: int,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """最近的推送运行（新 → 旧）：触发来源、状态、逐项目逐步骤结果、警告。"""
    return {"runs": await list_runs(db, project_id, year, limit=limit)}


@router.get("/{project_id}/{year}/push-status")
async def get_push_status(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """最近一次推送 + 是否过期（子企业试算表在推送后又变了 ⇒ 建议重新推送）。"""
    return await push_status(db, project_id, year)
