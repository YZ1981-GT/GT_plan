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


@router.get("/since")
async def get_events_since(
    project_id: UUID,
    last_event_id: str | None = Query(default=None),
    since_timestamp: float | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """增量事件拉取 — 供前端 SSE 重连后拉取遗漏事件。

    参数：
    - last_event_id: 上次收到的事件 ID（Redis Stream message ID）
    - since_timestamp: 断连时间戳（unix seconds）

    返回断连期间的事件列表（最多 100 条），按时间 ASC 排序。

    Validates: Requirements 1.7, 11.3
    """
    from app.core.redis import redis_client

    events: list[dict] = []

    try:
        # 尝试从 Redis Stream 读取
        stream_key = "events:stream"

        if last_event_id:
            # 从指定 ID 之后读取
            start_id = last_event_id
        elif since_timestamp:
            # 将 unix timestamp 转为 Redis Stream ID 格式（ms-seq）
            start_id = f"{int(since_timestamp * 1000)}-0"
        else:
            # 默认取最近 60 秒的事件
            import time
            start_id = f"{int((time.time() - 60) * 1000)}-0"

        # XRANGE 从 start_id（exclusive）到最新，最多 100 条
        # 使用 "(" 前缀表示 exclusive（不含 start_id 本身）
        messages = await redis_client.xrange(
            stream_key,
            min=f"({start_id}" if last_event_id else start_id,
            max="+",
            count=100,
        )

        for msg_id, data in messages:
            # 过滤当前项目的事件
            event_project_id = data.get("project_id", "")
            if event_project_id and event_project_id != str(project_id):
                continue

            event_data = {
                "event_id": msg_id,
                "event_type": data.get("event_type", ""),
                "project_id": event_project_id,
                "year": int(data["year"]) if data.get("year") else None,
                "account_codes": json.loads(data.get("account_codes", "[]")) or None,
                "timestamp": int(msg_id.split("-")[0]) / 1000 if "-" in msg_id else None,
            }
            events.append(event_data)

    except Exception as e:
        logger.warning("get_events_since failed (Redis unavailable): %s", e)
        # Redis 不可用时返回空列表（降级）
        return []

    return events
