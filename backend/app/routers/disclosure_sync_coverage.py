"""披露同步覆盖率只读端点

GET /api/projects/{project_id}/disclosure-sync-coverage?year=YYYY

spec: disclosure-payload-authority-source / Task 2.3

🔴 权限（复盘第三轮修复）：首版**漏挂项目权限依赖**，只有 `Depends(get_db)`
⇒ 任何调用方传任意 `project_id` 即可读到该项目的披露同步状态
（启用了哪些底稿 / 哪些章节已同步），是未授权的跨项目数据泄露（IDOR）。
同业务域全部只读端点（`disclosure_notes.py` 的 tree / readiness / wp-sync-status 等）
一律挂 `require_project_access("readonly")`，本端点须对齐。
守卫：`test_disclosure_sync_coverage_endpoint.py`。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.disclosure_sync_coverage_service import (
    get_project_disclosure_sync_coverage,
)

router = APIRouter()


@router.get("/api/projects/{project_id}/disclosure-sync-coverage")
async def get_disclosure_sync_coverage(
    project_id: UUID,
    year: int = Query(..., description="审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """返回项目级披露同步覆盖率（只读）。

    分母派生自 note_workpaper_sync_registry.json，排除项目未启用底稿。
    口径：`last_sync_at` 非空 = 已同步；`is_stale = true` = 过期。
    汇总数按 `note_section` 去重（共享章节只算一次），`duty_rows` 保留职责行数。

    权限：`require_project_access("readonly")` —— 与附注侧其余只读端点同级。
    """
    return await get_project_disclosure_sync_coverage(db, project_id, year)
