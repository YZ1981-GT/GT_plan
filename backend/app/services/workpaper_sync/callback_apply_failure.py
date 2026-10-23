"""回调后的 apply 在协调器接手之前就失败：失败落到 application / operation 上（spec writeback-followup-issue-closure R3.4）。

incoming 已 durable、向文档服务器只能回 `error 0`（非零它会丢件或反复重投），所以 apply 的任何失败
都只能留在 operation 上等重试。协调器内部的失败由它自己记（`_record_post_durable_failure`）；
但在它接手之前 —— 注册 / 绑定找不到 adapter、协调器入口校验抛出 —— 原先只打一条日志：
application 停在 `queued`、operation 停在 `application_bound`，前端一直等到窗口超时，
既看不到原因也没有可重试的状态。这里按同一套状态边把两者推到 `error`（可重试态，出边见
`APPLICATION_EDGES` / `OPERATION_EDGES`），事件与 operation 行都带上错误码。
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import WorkpaperContentApplication, WorkpaperSyncOperation
from app.services.workpaper_sync.models import (
    APPLICATION_EDGES,
    OPERATION_EDGES,
    ActorType,
    ApplicationEventType,
    ApplicationState,
    OperationState,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository

__all__ = ["record_pre_apply_failure"]


async def record_pre_apply_failure(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    operation_id: uuid.UUID,
    error_code: str,
    stage: str,
    detail: str = "",
) -> bool:
    """把 application 与 operation 推到 `error` 并提交；任一方已不能进 `error`（终态 / 已是 error）则不动它。

    返回是否改了 application。调用方先 rollback 掉失败的事务再调用。
    """
    repo = WorkpaperSyncRepository(session)
    app = (
        await session.execute(
            sa.select(WorkpaperContentApplication)
            .where(WorkpaperContentApplication.id == application_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if app is None:
        return False
    current = ApplicationState(app.state)
    if ApplicationState.error not in APPLICATION_EDGES.get(current, frozenset()):
        return False
    await repo.append_application_event(
        application_id=app.id,
        event_type=ApplicationEventType.state_changed,
        origin_request_sequence=int(app.origin_request_sequence),
        effective_request_sequence=int(app.effective_request_sequence),
        from_state=current,
        to_state=ApplicationState.error,
        actor_type=ActorType.callback,
        error_code=error_code,
    )
    app.state = ApplicationState.error.value
    op = (
        await session.execute(
            sa.select(WorkpaperSyncOperation)
            .where(WorkpaperSyncOperation.id == operation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if op is not None:
        op_state = OperationState(op.state)
        if OperationState.error in OPERATION_EDGES.get(op_state, frozenset()):
            await repo.append_operation_event(
                operation_id=op.id,
                from_state=op_state,
                to_state=OperationState.error,
                stage=f"{stage}#1",
                actor_type=ActorType.callback,
                error_code=error_code,
                client_edit_epoch=int(app.client_edit_epoch),
                origin_request_sequence=int(app.origin_request_sequence),
                effective_request_sequence=int(app.effective_request_sequence),
            )
            op.state = OperationState.error.value
            op.error_code = error_code[:60]
            op.error_stage = stage[:40]
            op.error_detail = detail[:4000] or None
    await session.commit()
    return True
