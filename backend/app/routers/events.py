"""事件 SSE 推送 API

试算表更新完成后通过 SSE 通知前端刷新。

Validates: Requirements 10.1
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from app.models.core import User
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/events",
    tags=["events"],
)


@router.get("/stream")
async def sse_stream(
    project_id: UUID,
    year: int = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    """SSE 事件流：客户端订阅后接收试算表更新等事件通知

    前端使用 EventSource 连接此端点，收到事件后刷新试算表数据。
    """

    async def event_generator():
        queue = event_bus.create_sse_queue()
        try:
            # 发送初始连接确认
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

            while True:
                try:
                    # Wait for events with a 30s heartbeat timeout
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield f": heartbeat\n\n"
                    continue

                if payload is None:
                    # Shutdown signal
                    break

                # Filter by project_id (and optionally year)
                if str(payload.project_id) != str(project_id):
                    continue
                if year is not None and payload.year is not None and payload.year != year:
                    continue

                # Build SSE event data
                event_data = {
                    "event_type": payload.event_type.value,
                    "project_id": str(payload.project_id),
                    "year": payload.year,
                    "account_codes": payload.account_codes,
                    "entry_group_id": str(payload.entry_group_id) if payload.entry_group_id else None,
                    "batch_id": str(payload.batch_id) if payload.batch_id else None,
                    "extra": payload.extra if payload.extra else None,
                }
                yield f"event: {payload.event_type.value}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        except asyncio.CancelledError:
            logger.info("SSE stream cancelled for project %s", project_id)
        finally:
            event_bus.remove_sse_queue(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
