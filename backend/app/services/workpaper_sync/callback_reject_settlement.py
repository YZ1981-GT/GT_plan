# -*- coding: utf-8 -*-
"""强制保存回调在 durable 之前被拒时，就地终结它绑定的 request + operation shell。

spec: d2-skeleton-slot-reuse-and-writeback-speed · R4

═══ 为什么需要（2026-10-23 真栈实测）═══

status 6 的回调在下载 / 隔离阶段被拒（`working_paper_callback_delivery.state=rejected`、
回 OO `{"error":1}`）后，OnlyOffice 不会重投；而它绑定的 forcesave request 停在 `frozen`、
operation shell 停在 `created`：

* 前端一直显示「已发送强制保存，等待 OnlyOffice 回传文件」并每 500ms 轮询，永不结束；
* `leave_participant` 因「该 participant 还有未终结 request」恒回 409，lease 挂到过期。

处置与 `RequestApplicationService.terminate_without_callback`（CS 明确「不会再有 callback」）
同一语义：shell → `rejected`（先 append-only event 再投影，带下载 / 隔离的 error_code），
request → `terminal`。只在状态机允许的边上动，否则原样不动（幂等、不越权）。
只处理 `kind=forcesave`：close_capture 归 close barrier 仲裁，不在这里改。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.services.workpaper_sync.models import (
    OPERATION_EDGES,
    REQUEST_EDGES,
    ActorType,
    OperationState,
    RequestState,
)

logger = logging.getLogger(__name__)

__all__ = ["settle_forcesave_after_pre_durable_rejection"]

_STAGE = "callback_pre_durable_rejected"


async def settle_forcesave_after_pre_durable_rejection(
    *, repo: Any, request: Any, shell: Any, error_code: str | None
) -> bool:
    """返回是否改动了 request / shell。只 flush 不 commit（commit 由 callback 路由负责）。"""
    if request is None or str(getattr(request, "kind", "")) != "forcesave":
        return False
    code = str(error_code or "callback_pre_durable_rejected")[:60]
    now = datetime.now(timezone.utc)
    changed = False
    if shell is not None:
        op_state = OperationState(shell.state)
        if OperationState.rejected in OPERATION_EDGES.get(op_state, frozenset()):
            await repo.append_operation_event(
                operation_id=shell.id,
                from_state=op_state,
                to_state=OperationState.rejected,
                stage=_STAGE,
                actor_type=ActorType.system,
                error_code=code,
            )
            shell.state = OperationState.rejected.value
            shell.error_code = code
            shell.error_stage = _STAGE
            shell.finished_at = now
            changed = True
    req_state = RequestState(request.state)
    if RequestState.terminal in REQUEST_EDGES.get(req_state, frozenset()):
        request.state = RequestState.terminal.value
        request.finished_at = request.finished_at or now
        changed = True
    if changed:
        await repo.session.flush()
    logger.warning(
        "强制保存回调在 durable 之前被拒（%s）：request=%s %s→%s，operation=%s %s",
        code,
        getattr(request, "id", None),
        req_state.value,
        request.state,
        getattr(shell, "id", None),
        getattr(shell, "state", None),
    )
    return changed
