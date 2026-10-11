"""application 落终态 ⇒ 绑在它上面的 forcesave request 同事务终结（D1）。

═══ 修的是什么 ═══

`REQUEST_EDGES[correlated]` 登记了 `terminal / superseded / authorization_stale` 三条出边，
但此前全仓**零生产写入方**。`correlated` 的语义是「incoming 已 durable、内容尚未应用」，
三个消费方都以「request 已终结」为前提：

* participant 主动离开的 in-flight 门（`RoomService._outstanding_request_ids_of`）；
* close barrier 的 predecessor 计数（`reconcile_close_intents` 的 `predecessors_open`）；
* editor destroy 闸（`command_service.classify_editor_destroy` 的 `is_terminal`）。

于是保存成功后 request 永远停在 `correlated`，initiator 离开恒 409
`participant_leave_refused_in_flight`（真库：每一次 OO→HTML 保存都如此，2026-10-11 现算 68 条）。
守卫里 4 处用裸 `UPDATE … SET state='terminal'` 模拟这一步，恰好盖住了生产侧的缺口。

═══ 为什么是伴生模块 ═══

`repository.py` 在行数门禁 whitelist 上（基线 +5% 已用尽），门禁语义是「打磨应让文件变小
不变大」。本函数只用到仓储的 `lock_room` 与 `session`，不需要住在仓储类里。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperForcesaveRequest,
    WorkpaperSyncOperation,
)
from app.services.workpaper_sync.models import (
    REQUEST_STATE_FOR_TERMINAL_APPLICATION,
    ApplicationState,
    StateTransitionError,
    assert_transition,
    is_terminal,
)

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from app.models.workpaper_sync_models import WorkpaperContentApplication
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

__all__ = ["settle_requests_of_terminal_application"]


async def settle_requests_of_terminal_application(
    repo: "WorkpaperSyncRepository", application: "WorkpaperContentApplication"
) -> tuple[uuid.UUID, ...]:
    """application 已落终态 ⇒ 绑在它上面的每条 request 同事务终结。

    目标状态取 :data:`REQUEST_STATE_FOR_TERMINAL_APPLICATION`（单源）；非终态 application
    调用即 :class:`StateTransitionError` —— `conflict` / `error` 之后裁决或重试仍可能应用
    内容，提前终结会让 in-flight 门在内容落地前就放人离开。

    「绑在它上面」= `origin_request_id` + 每个 shell 的 request：primary（`application_id`
    指向它）与直指该 primary 的 duplicate（同 application key、较高 sequence 折叠进来的
    那些 —— correlation 同样把它们落成了 `correlated`）。只取 origin 会让折叠场景下后发
    保存的那位 initiator 照样离不开。

    🔴 锁序 room → request：撤销路径（`RoomService._cancel_outstanding_requests_locked`）
    先锁 room 再锁 request。apply 调到这里时 room 尚未上锁（`advance_server_last_applied`
    在后面），若直接锁 request，两条事务就能互等。同一事务内对 room 重复 `FOR UPDATE`
    是幂等的，所以由本函数先锁 room，调用方无需关心顺序。

    已终结的 request 原样跳过（重放、或已被撤销路径取消的，不得二次改写）。只 flush 不 commit。
    """
    app_state = ApplicationState(application.state)
    target = REQUEST_STATE_FOR_TERMINAL_APPLICATION.get(app_state)
    if target is None:
        raise StateTransitionError(
            f"application {application.id} state={app_state.value} 不是终态 —— "
            "内容仍可能被裁决/重试应用，不得提前终结它的 request"
        )
    await repo.lock_room(application.room_id)
    primary_ids = sa.select(WorkpaperSyncOperation.id).where(
        WorkpaperSyncOperation.application_id == application.id
    )
    shell_request_ids = sa.select(WorkpaperSyncOperation.forcesave_request_id).where(
        WorkpaperSyncOperation.forcesave_request_id.is_not(None),
        sa.or_(
            WorkpaperSyncOperation.application_id == application.id,
            WorkpaperSyncOperation.duplicate_of_operation_id.in_(primary_ids),
        ),
    )
    session = repo.session
    rows = (
        (
            await session.execute(
                sa.select(WorkpaperForcesaveRequest)
                .where(
                    sa.or_(
                        WorkpaperForcesaveRequest.id == application.origin_request_id,
                        WorkpaperForcesaveRequest.id.in_(shell_request_ids),
                    )
                )
                .order_by(WorkpaperForcesaveRequest.request_sequence)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(timezone.utc)
    settled: list[uuid.UUID] = []
    for req in rows:
        if is_terminal("request", req.state):
            continue
        assert_transition("request", req.state, target)
        req.state = target.value
        req.finished_at = req.finished_at or now
        settled.append(req.id)
    if settled:
        await session.flush()
    return tuple(settled)
