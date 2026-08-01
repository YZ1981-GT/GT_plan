"""程序行两层裁剪与方案 preview/apply API（Task 6）

Feature: procedure-delegation-notification
需求：3.3-3.8、4.2-4.6 / Design C4、D4、API section

端点（全部挂 **项目级 Delegator 守卫** `require_project_delegator_pid`，fail-closed 403）：
- ``POST /api/projects/{pid}/procedure-trim/preview``：方案预览 + 一次性 preview 凭证。
- ``POST /api/projects/{pid}/procedure-trim/apply``：消费 preview，经 TransitionService 真实应用；
  返回真实 applied/unchanged/conflict；legacy UUID 无法唯一转换 → 409 migration_conflict。
- ``POST /api/projects/{pid}/procedure-trim/schemes``：保存 canonical key + revision + 文本快照方案。
- ``POST /api/projects/{pid}/procedure-trim/rows/{task_id}/not-applicable``：细裁 → cancel。
- ``POST /api/projects/{pid}/procedure-trim/rows/{task_id}/restore``：细裁恢复 → reopen（须重新 assign→ack）。

约定：service 只 flush；router 显式 commit。均为显式 POST 写命令，非 GET/render 读路径。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.procedure_authorization import (
    DelegatorContext,
    require_project_delegator_pid,
)
from app.services.procedure_trim_service import ProcedureTrimService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["procedure-row-tasks"])


class TrimSchemeEntry(BaseModel):
    kind: str  # "scope" | "row"
    # scope
    cycle: str | None = None
    wp_index_code: str | None = None
    target_status: str | None = None
    # 粗裁理由（审计轨迹；execute 时忽略）。旧 PUT /procedures/{cycle}/trim 下线后由此承载。
    skip_reason: str | None = Field(default=None, max_length=500)
    # row
    template_code: str | None = None
    sheet_key: str | None = None
    definition_key: str | None = None
    target_applicability: str | None = None


class TrimPreviewRequest(BaseModel):
    entries: list[TrimSchemeEntry] = Field(default_factory=list)
    scheme_id: UUID | None = None


class TrimApplyRequest(TrimPreviewRequest):
    preview_id: UUID
    request_id: str


class TrimSchemeSaveRequest(BaseModel):
    scheme_name: str
    audit_cycle: str
    entries: list[TrimSchemeEntry] = Field(default_factory=list)


class RowTrimRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    request_id: str | None = None


class RowRestoreRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    request_id: str | None = None


def _entries_payload(entries: list[TrimSchemeEntry]) -> list[dict]:
    return [e.model_dump(exclude_none=True) for e in entries]


@router.post("/{pid}/procedure-trim/preview")
async def trim_preview(
    pid: UUID,
    body: TrimPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """方案预览：解析计划 + 一次性 preview 凭证。"""
    svc = ProcedureTrimService(db)
    result = await svc.preview_scheme(
        pid,
        actor_user_id=user.id,
        entries=_entries_payload(body.entries) if body.entries else None,
        scheme_id=body.scheme_id,
    )
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/apply")
async def trim_apply(
    pid: UUID,
    body: TrimApplyRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """方案应用：消费 preview，真实 applied/unchanged/conflict；legacy UUID 无法唯一转换 → 409。"""
    svc = ProcedureTrimService(db)
    try:
        result = await svc.apply_scheme(
            pid,
            actor_user_id=user.id,
            preview_id=body.preview_id,
            request_id=body.request_id,
            entries=_entries_payload(body.entries) if body.entries else None,
            scheme_id=body.scheme_id,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/schemes")
async def trim_save_scheme(
    pid: UUID,
    body: TrimSchemeSaveRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """保存裁剪方案（canonical key + revision + 文本快照）。"""
    svc = ProcedureTrimService(db)
    result = await svc.save_scheme(
        pid,
        scheme_name=body.scheme_name,
        audit_cycle=body.audit_cycle,
        entries=_entries_payload(body.entries),
        created_by=user.id,
    )
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/rows/{task_id}/not-applicable")
async def trim_row_not_applicable(
    pid: UUID,
    task_id: UUID,
    body: RowTrimRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """细裁 → not_applicable：经 TransitionService cancel（applicability→not_applicable + workflow→cancelled）。"""
    svc = ProcedureTrimService(db)
    try:
        result = await svc.set_row_not_applicable(
            pid,
            task_id,
            actor_user_id=user.id,
            reason=body.reason,
            request_id=body.request_id,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/rows/{task_id}/restore")
async def trim_row_restore(
    pid: UUID,
    task_id: UUID,
    body: RowRestoreRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """细裁恢复 → execute：经 TransitionService reopen（cancelled→unassigned，须重新 assign→ack）。"""
    svc = ProcedureTrimService(db)
    try:
        result = await svc.restore_row_execute(
            pid,
            task_id,
            actor_user_id=user.id,
            request_id=body.request_id,
            reason=body.reason,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result
