# -*- coding: utf-8 -*-
"""application 事件流的失败真因投影（只读）。

从 `wp_sync_router.py` 抽出：那个文件在 whitelist 硬上限上（3639 / cap 3640），
而本修改必须加一个端点。行为逐字未变。

为什么必须从事件流读：`apply_durable_incoming` 在 durable 之后刻意不抛（AC 5.7/5.8），
失败只表现为 `result.result`，落库落在
`working_paper_content_application_event.error_code` 上；
`working_paper_sync_operation.error_code` 在这条路径上恒为 NULL。

中文说明取后端已有的单源词表，不在前端再抄一份码→文案的映射；
查不到登记时不编，只回码本身。
"""
from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa

from app.services.workpaper_sync.failure_wording import describe_sync_failure_code


async def application_failure_facts(
    svc: Any, *, application_id: uuid.UUID
) -> dict[str, Any]:
    """读最近一条带 error_code 的 application 事件，返回三个字段。

    与原 router 实现逐字等价（包括 `order_by(sequence_no.desc()).limit(1)` 的取法）。
    """
    from app.models.workpaper_sync_models import WorkpaperContentApplicationEvent

    row = (
        await svc.session.execute(
            sa.select(
                WorkpaperContentApplicationEvent.error_code,
                WorkpaperContentApplicationEvent.to_state,
            )
            .where(
                WorkpaperContentApplicationEvent.application_id == application_id,
                WorkpaperContentApplicationEvent.error_code.isnot(None),
            )
            .order_by(WorkpaperContentApplicationEvent.sequence_no.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return {
            "application_error_code": None,
            "application_error_stage": None,
            "application_error_message": None,
        }
    code = str(row[0])
    return {
        "application_error_code": code,
        "application_error_stage": (None if row[1] is None else str(row[1])),
        "application_error_message": describe_sync_failure_code(code),
    }
