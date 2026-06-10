"""出品物溯源与章节状态查询端点 — deliverable-lineage-and-writeback Task 5.1/17.1/17.2/17.3

GET /api/projects/{project_id}/deliverables/{word_export_task_id}/trace
    溯源查询（project:read），2s 超时返回明确错误（需求 10.1）

GET /api/projects/{project_id}/deliverables/{word_export_task_id}/section-states
    章节状态查询（project:read）

POST /api/projects/{project_id}/deliverables/{word_export_task_id}/writeback
    回填触发（project:edit），终态拒绝，>100 章节走异步（需求 7.1, 10.2, 10.3, 10.4, 11.1）

POST /api/projects/{project_id}/deliverables/{word_export_task_id}/refresh-section
    单章节增量刷新（project:edit）（需求 5.1, 10.3, 10.4, 11.1）

POST /api/projects/{project_id}/deliverables/{word_export_task_id}/refresh-stale
    批量刷新所有过期章节（project:edit）（需求 5.7, 10.2, 10.3, 10.4, 11.1）

Requirements: 1.1, 3.1, 5.1, 5.7, 7.1, 10.1, 10.2, 10.3, 10.4, 11.1, 11.3
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_project_access
from app.models.core import User
from app.services.audit_logger_enhanced import audit_logger
from app.services.deliverable_section_state_service import DeliverableSectionStateService
from app.services.linkage_facade_service import LinkageFacadeService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/deliverables/{word_export_task_id}",
    tags=["deliverable-lineage"],
)

# ---------------------------------------------------------------------------
# Terminal state constants — deliverables in these states forbid writeback/refresh
# (needs 11.1/11.3, reuse TERMINAL_REEXPORT_STATUSES concept)
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = frozenset({"signed", "confirmed", "archived"})

# ---------------------------------------------------------------------------
# Async job threshold — >100 sections delegates to export_jobs_v2 (need 10.2)
# ---------------------------------------------------------------------------

ASYNC_SECTION_THRESHOLD = 100


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class WritebackRequest(BaseModel):
    year: int
    resolutions: dict[str, str] | None = None


class RefreshSectionRequest(BaseModel):
    year: int
    section_code: str
    confirm_overwrite: bool = False


class RefreshStaleRequest(BaseModel):
    year: int
    confirm_overwrite: bool = False


@router.get("/trace")
async def trace_deliverable(
    project_id: UUID,
    word_export_task_id: UUID,
    section_code: str = Query(..., description="章节编码（如 八、1）"),
    year: int | None = Query(default=None, description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """出品物章节溯源查询。

    调用 LinkageFacadeService.trace(source_type='deliverable')，
    source_id = '{word_export_task_id}:{section_code}'。
    2 秒超时返回明确错误（需求 10.1）。
    """
    source_id = f"{word_export_task_id}:{section_code}"
    facade = LinkageFacadeService(db)

    try:
        contracts = await asyncio.wait_for(
            facade.trace(
                project_id=project_id,
                source_type="deliverable",
                source_id=source_id,
                year=year,
            ),
            timeout=2.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="溯源查询超时（超过 2 秒），请稍后重试",
        )

    # 补充章节级 stale 状态
    dss = DeliverableSectionStateService(db)
    states = await dss.get_section_states(word_export_task_id)
    section_state = next(
        (s for s in states if s["section_code"] == section_code),
        None,
    )

    return {
        "contracts": contracts,
        "section_state": section_state,
    }


@router.get("/section-states")
async def get_section_states(
    project_id: UUID,
    word_export_task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """出品物章节状态列表查询。

    返回所有章节的 stale 状态 + 锚点 + 快照哈希。
    """
    dss = DeliverableSectionStateService(db)
    sections = await dss.get_section_states(word_export_task_id)
    return {"sections": sections}



# ---------------------------------------------------------------------------
# Helper: terminal state check (needs 11.1/11.3)
# ---------------------------------------------------------------------------


async def _check_terminal_state(
    db: AsyncSession,
    word_export_task_id: UUID,
) -> str | None:
    """Check if deliverable is in terminal state. Returns status if terminal, None otherwise."""
    from sqlalchemy import select, text

    # Query WordExportTask.status
    result = await db.execute(
        text(
            "SELECT status FROM word_export_tasks WHERE id = :tid"
        ),
        {"tid": str(word_export_task_id)},
    )
    row = result.first()
    if row is None:
        return None  # task not found, will be caught downstream
    status = row[0]
    if status in TERMINAL_STATUSES:
        return status
    return None


# ---------------------------------------------------------------------------
# Helper: async job delegation for large documents (needs 10.2)
# ---------------------------------------------------------------------------


async def _delegate_to_async_job(
    db: AsyncSession,
    project_id: UUID,
    word_export_task_id: UUID,
    user_id: UUID,
    action: str,
    payload: dict[str, Any],
) -> dict:
    """Delegate operation to export_jobs_v2 for large documents (>100 sections)."""
    from app.services.export_job_service import ExportJobService

    job_svc = ExportJobService(db)
    job_id = await job_svc.create_job(
        project_id=project_id,
        user_id=user_id,
        job_type=action,
        params={
            "word_export_task_id": str(word_export_task_id),
            **payload,
        },
    )
    await db.flush()
    return {"job_id": str(job_id)}


# ---------------------------------------------------------------------------
# POST /writeback — 回填触发（needs 7.1, 10.2, 10.3, 10.4, 11.1/11.3）
# ---------------------------------------------------------------------------


@router.post("/writeback")
async def writeback_deliverable(
    project_id: UUID,
    word_export_task_id: UUID,
    body: WritebackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """出品物文字回填到附注模块（显式按钮触发）。

    权限: project:edit（无权限 403，需求 10.3）
    终态: signed/confirmed/archived 拒绝（需求 11.1/11.3）
    大文档: >100 章节走异步（需求 10.2）
    审计日志: 写 app_audit_log（需求 10.4）
    """
    # 终态检查（needs 11.1/11.3）
    terminal_status = await _check_terminal_state(db, word_export_task_id)
    if terminal_status:
        raise HTTPException(
            status_code=409,
            detail=f"该出品物已{terminal_status}，不可回填或刷新；如需修改请走撤回/解锁流程",
        )

    # 获取章节状态以判断是否需要异步（needs 10.2）
    dss = DeliverableSectionStateService(db)
    sections = await dss.get_section_states(word_export_task_id)

    if len(sections) > ASYNC_SECTION_THRESHOLD:
        # 大文档 → 异步 job
        result = await _delegate_to_async_job(
            db, project_id, word_export_task_id, current_user.id,
            action="deliverable_writeback",
            payload={"year": body.year, "resolutions": body.resolutions},
        )
        # 写审计日志（needs 10.4）
        await audit_logger.log_action(
            user_id=current_user.id,
            action="deliverable_writeback_async",
            object_type="deliverable",
            object_id=word_export_task_id,
            project_id=project_id,
            details={"year": body.year, "async_job_id": result["job_id"], "section_count": len(sections)},
        )
        return result

    # 同步执行回填
    from app.services.deliverable_writeback_service import DeliverableWritebackService

    writeback_svc = DeliverableWritebackService(db)
    try:
        result = await writeback_svc.writeback(
            word_export_task_id=word_export_task_id,
            project_id=project_id,
            year=body.year,
            actor_id=current_user.id,
            resolutions=body.resolutions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # 写审计日志（needs 10.4）
    await audit_logger.log_action(
        user_id=current_user.id,
        action="deliverable_writeback",
        object_type="deliverable",
        object_id=word_export_task_id,
        project_id=project_id,
        details={"year": body.year, "section_count": len(sections), "has_resolutions": body.resolutions is not None},
    )

    return result


# ---------------------------------------------------------------------------
# POST /refresh-section — 单章节增量刷新（needs 5.1, 10.3, 10.4, 11.1/11.3）
# ---------------------------------------------------------------------------


@router.post("/refresh-section")
async def refresh_section(
    project_id: UUID,
    word_export_task_id: UUID,
    body: RefreshSectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """单章节增量刷新。

    权限: project:edit（无权限 403，需求 10.3）
    终态: signed/confirmed/archived 拒绝（需求 11.1/11.3）
    审计日志: 写 app_audit_log（需求 10.4）
    """
    # 终态检查（needs 11.1/11.3）
    terminal_status = await _check_terminal_state(db, word_export_task_id)
    if terminal_status:
        raise HTTPException(
            status_code=409,
            detail=f"该出品物已{terminal_status}，不可回填或刷新；如需修改请走撤回/解锁流程",
        )

    # 写审计日志（needs 10.4）
    await audit_logger.log_action(
        user_id=current_user.id,
        action="deliverable_refresh_section",
        object_type="deliverable",
        object_id=word_export_task_id,
        project_id=project_id,
        details={
            "year": body.year,
            "section_code": body.section_code,
            "confirm_overwrite": body.confirm_overwrite,
        },
    )

    # Call DeliverableRefreshService
    from app.services.deliverable_refresh_service import DeliverableRefreshService

    refresh_svc = DeliverableRefreshService(db)
    try:
        result = await refresh_svc.refresh_section(
            word_export_task_id=word_export_task_id,
            project_id=project_id,
            year=body.year,
            section_code=body.section_code,
            actor_id=current_user.id,
            confirm_overwrite=body.confirm_overwrite,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return result


# ---------------------------------------------------------------------------
# POST /refresh-stale — 批量刷新所有过期章节（needs 5.7, 10.2, 10.3, 10.4, 11.1/11.3）
# ---------------------------------------------------------------------------


@router.post("/refresh-stale")
async def refresh_stale(
    project_id: UUID,
    word_export_task_id: UUID,
    body: RefreshStaleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """批量刷新所有过期章节。

    权限: project:edit（无权限 403，需求 10.3）
    终态: signed/confirmed/archived 拒绝（需求 11.1/11.3）
    大文档: >100 stale 章节走异步（需求 10.2）
    审计日志: 写 app_audit_log（需求 10.4）
    """
    # 终态检查（needs 11.1/11.3）
    terminal_status = await _check_terminal_state(db, word_export_task_id)
    if terminal_status:
        raise HTTPException(
            status_code=409,
            detail=f"该出品物已{terminal_status}，不可回填或刷新；如需修改请走撤回/解锁流程",
        )

    # 获取 stale 章节
    dss = DeliverableSectionStateService(db)
    sections = await dss.get_section_states(word_export_task_id)
    stale_sections = [s for s in sections if s.get("is_stale")]

    if len(stale_sections) > ASYNC_SECTION_THRESHOLD:
        # 大文档 → 异步 job（needs 10.2）
        result = await _delegate_to_async_job(
            db, project_id, word_export_task_id, current_user.id,
            action="deliverable_refresh_stale",
            payload={"year": body.year, "confirm_overwrite": body.confirm_overwrite},
        )
        # 写审计日志（needs 10.4）
        await audit_logger.log_action(
            user_id=current_user.id,
            action="deliverable_refresh_stale_async",
            object_type="deliverable",
            object_id=word_export_task_id,
            project_id=project_id,
            details={"year": body.year, "async_job_id": result["job_id"], "stale_count": len(stale_sections)},
        )
        return result

    # 写审计日志（needs 10.4）
    await audit_logger.log_action(
        user_id=current_user.id,
        action="deliverable_refresh_stale",
        object_type="deliverable",
        object_id=word_export_task_id,
        project_id=project_id,
        details={
            "year": body.year,
            "stale_count": len(stale_sections),
            "confirm_overwrite": body.confirm_overwrite,
        },
    )

    # Call DeliverableRefreshService
    from app.services.deliverable_refresh_service import DeliverableRefreshService

    refresh_svc = DeliverableRefreshService(db)
    try:
        result = await refresh_svc.refresh_all_stale_sections(
            word_export_task_id=word_export_task_id,
            project_id=project_id,
            year=body.year,
            actor_id=current_user.id,
            confirm_overwrite=body.confirm_overwrite,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return result
