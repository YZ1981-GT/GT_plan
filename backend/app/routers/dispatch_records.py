"""分发记录 REST Router — D0-1 跨底稿分发持久化

DEPRECATED: cross-workpaper-dispatch-persistence 机制从未被前端组件采用，
由 coordination/importFromSummary.ts 通用读取器取代（2026-07-28 confirmation-linkage-completion R3）。
前端 useConfirmationDispatch/useDownstreamDispatch/dispatchApi.ts 已删除。
本路由、service、模型及 V093 表保留休眠不删（避免破坏性 DDL），待运维决定是否清理。

Feature: cross-workpaper-dispatch-persistence

端点：
  POST   /api/projects/{project_id}/dispatch-records    批量创建（去重）
  GET    /api/projects/{project_id}/dispatch-records    查询（可选 ?target=&confirm_index=）
  DELETE /api/projects/{project_id}/dispatch-records/{record_id}  撤回单条
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import ProjectUser, User
from app.services.dispatch_service import (
    BatchResult,
    DispatchEntry,
    DispatchNotFoundError,
    DispatchPermissionError,
    DispatchService,
    VALID_TARGETS,
)
from app.services.event_bus import event_bus

import sqlalchemy as sa

router = APIRouter(
    prefix="/api/projects/{project_id}/dispatch-records",
    tags=["分发记录"],
)


# ─── Pydantic Schemas ────────────────────────────────────────────────────────


class DispatchEntrySchema(BaseModel):
    confirm_index: str = Field(..., min_length=1, max_length=50)
    target: str = Field(..., max_length=10)
    entity_name: str | None = None
    account_type: str | None = None
    amount: Decimal | None = None
    reason: str | None = None

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        if v not in VALID_TARGETS:
            raise ValueError(f"target must be one of {sorted(VALID_TARGETS)}")
        return v


class BatchCreateRequest(BaseModel):
    entries: list[DispatchEntrySchema] = Field(..., min_length=1)


class DispatchRecordResponse(BaseModel):
    id: str
    project_id: str
    confirm_index: str
    target: str
    entity_name: str | None = None
    account_type: str | None = None
    amount: Decimal | None = None
    reason: str | None = None
    dispatched_by: str
    dispatched_at: str

    model_config = {"from_attributes": True}


class BatchCreateResponse(BaseModel):
    dispatched: list[DispatchRecordResponse]
    skipped: list[dict[str, Any]]


class ListResponse(BaseModel):
    items: list[DispatchRecordResponse]
    total: int


# ─── 辅助函数 ────────────────────────────────────────────────────────────────


def _record_to_response(record) -> DispatchRecordResponse:
    """将 ORM 对象转换为响应 schema"""
    return DispatchRecordResponse(
        id=str(record.id),
        project_id=str(record.project_id),
        confirm_index=record.confirm_index,
        target=record.target,
        entity_name=record.entity_name,
        account_type=record.account_type,
        amount=record.amount,
        reason=record.reason,
        dispatched_by=str(record.dispatched_by),
        dispatched_at=record.dispatched_at.isoformat(),
    )


async def _is_manager_or_partner(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> bool:
    """检查用户是否为项目的 manager/partner 角色"""
    result = await db.execute(
        sa.select(ProjectUser.role).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == user_id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    )
    role = result.scalar_one_or_none()
    return role in ("manager", "partner", "signing_partner")


# ─── 端点 ────────────────────────────────────────────────────────────────────


@router.post("", response_model=BatchCreateResponse)
async def create_dispatch_records(
    project_id: uuid.UUID,
    body: BatchCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量创建分发记录（去重：ON CONFLICT DO NOTHING）"""
    entries = [
        DispatchEntry(
            confirm_index=e.confirm_index,
            target=e.target,
            entity_name=e.entity_name,
            account_type=e.account_type,
            amount=e.amount,
            reason=e.reason,
        )
        for e in body.entries
    ]

    result: BatchResult = await DispatchService.batch_create(
        db, project_id, entries, current_user.id
    )

    # publish EventBus 事件
    if result.dispatched:
        event_bus.publish(
            EventPayload(
                event_type=EventType.DISPATCH_CREATED,
                project_id=project_id,
                extra={
                    "confirm_indices": [r.confirm_index for r in result.dispatched],
                    "target": result.dispatched[0].target if result.dispatched else "",
                    "dispatched_by": str(current_user.id),
                },
            )
        )

    await db.commit()

    return BatchCreateResponse(
        dispatched=[_record_to_response(r) for r in result.dispatched],
        skipped=result.skipped,
    )


@router.get("", response_model=ListResponse)
async def list_dispatch_records(
    project_id: uuid.UUID,
    target: str | None = None,
    confirm_index: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询分发记录（可选过滤）"""
    records = await DispatchService.list_records(
        db, project_id, target=target, confirm_index=confirm_index
    )
    return ListResponse(
        items=[_record_to_response(r) for r in records],
        total=len(records),
    )


@router.delete("/{record_id}")
async def revoke_dispatch_record(
    project_id: uuid.UUID,
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤回分发记录"""
    is_manager = await _is_manager_or_partner(db, current_user.id, project_id)

    # admin 系统角色也视为 manager
    if current_user.role.value in ("admin", "partner"):
        is_manager = True

    try:
        record = await DispatchService.revoke(
            db, record_id, current_user.id, is_manager=is_manager
        )
    except DispatchNotFoundError:
        raise HTTPException(status_code=404, detail="分发记录不存在")
    except DispatchPermissionError:
        raise HTTPException(status_code=403, detail="权限不足：仅分发人或项目经理可撤回")

    # publish EventBus 事件
    event_bus.publish(
        EventPayload(
            event_type=EventType.DISPATCH_REVOKED,
            project_id=project_id,
            extra={
                "confirm_indices": [record.confirm_index],
                "target": record.target,
                "dispatched_by": str(record.dispatched_by),
            },
        )
    )

    await db.commit()

    return {"detail": "撤回成功", "id": str(record_id)}
