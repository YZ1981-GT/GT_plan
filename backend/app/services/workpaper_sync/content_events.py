# -*- coding: utf-8 -*-
"""`workpaper.content.updated` 的 **typed replay 投影**（消费侧读取面）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 35
Requirements 11.9 / 13.1 / 13.2 / 13.3；Property 52 / 53。

═══ 为什么需要这一层 ═══

Requirement 13.2 要求 "typed Redis replay SHALL 原样保留 `wp_id / revision /
operation_id / source / adapter_id / artifact_sha256` 及扩展字段，**不得丢失
`extra`**"。这条要求有两个读取面：

1. ``GET /api/projects/{pid}/events/stream``（SSE）—— 已经把整份 ``payload.extra``
   下发（见 ``app/routers/events.py``）；
2. ``GET /api/projects/{pid}/events/since``（断线补拉）—— **原来两处都错**：
   它读的 stream key 是自己写死的 ``"events:stream"``，而写入侧一直是
   :data:`app.services.event_bus.EVENT_STREAM_KEY`（``"audit:events"``），于是那条
   replay 路径**没有任何写入方**、恒返回空列表；即便读对了键，投影里也只有
   ``event_type/project_id/year/account_codes`` 四个扁平字段，``extra`` 整片丢掉。
   前端因此在 SSE 断线后拿不到 ``wp_id + revision``，AC 11.9 的去重与刷新无从恢复。

本模块把 "一条 Stream 条目 → 一条可消费的 replay 项" 做成**纯函数**，让上面这条
路径有一个可被逐项断言的单一真源。它刻意不 import Redis、不 import 任何 service：
判据可以直接喂一条 ``XADD`` 过的原始字段字典进去。

═══ 与 Task 16 的分工 ═══

Task 16 的 :mod:`app.services.workpaper_sync.outbox` 管 "什么时候发"（提交边界、
幂等闸门、失败重放）；:func:`app.services.event_bus.serialize_payload_for_stream`
管 "怎么写进 Stream"。本模块只管 "怎么读回来"，不复制那两侧的任何逻辑。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping
from uuid import UUID

from app.models.audit_platform_schemas import EventType
from app.services.event_bus import deserialize_payload_from_stream

logger = logging.getLogger(__name__)

#: 内容提交事件类型。前端 `WP_CONTENT_UPDATED_EVENT_NAME` 与它逐字对齐（守卫双向锁死）。
CONTENT_UPDATED_EVENT_TYPE = EventType.WORKPAPER_CONTENT_UPDATED

#: replay 项固定的键集。**扁平四键 + ``extra``**：前四个是既有消费方（enterprise-linkage
#: 的降级轮询）已经在读的，``extra`` 是 Requirement 13.2 新增且不可省的那一片。
REPLAY_ITEM_KEYS: tuple[str, ...] = (
    "event_id",
    "event_type",
    "project_id",
    "year",
    "account_codes",
    "timestamp",
    "extra",
)


def _stream_timestamp(msg_id: str) -> float | None:
    """Redis Stream message id 的毫秒段 → unix 秒。形态不对返回 ``None``。"""
    text = str(msg_id or "")
    head, _, _ = text.partition("-")
    if not head.isdigit():
        return None
    return int(head) / 1000


def replay_entry_projection(msg_id: str, data: Mapping[str, Any]) -> dict[str, Any] | None:
    """把一条 Stream 条目投影成 replay 项；无法解析时返回 ``None``。

    ``extra`` 逐键原样保留（Requirement 13.2）。**不做白名单裁剪**：裁剪等于在读取侧
    重新丢一次 ``extra``，而 Requirement 13.8 的字段级脱敏由
    :class:`app.services.workpaper_sync.redaction.RedactionPolicy` 在**写入**日志/
    evidence 时负责，不在这里二次实现（两处各写一份必然漂移）。

    Returns:
        ``None`` 表示这条条目连 ``EventPayload`` 都重建不出来。调用方**必须**把它记成
        显式丢弃计数，不得静默跳过 —— 那正是 Requirement 13.9 点名的不可观测形态。
    """
    try:
        payload = deserialize_payload_from_stream(dict(data))
    except Exception as exc:  # noqa: BLE001 - 形态异常是可预期输入，不是 bug
        logger.error(
            "content event replay: 无法解析 Stream 条目 msg_id=%s fields=%s: %s",
            msg_id,
            sorted(data.keys()) if isinstance(data, Mapping) else type(data).__name__,
            exc,
        )
        return None
    return {
        "event_id": str(msg_id),
        "event_type": payload.event_type.value,
        "project_id": str(payload.project_id) if payload.project_id else "",
        "year": payload.year,
        "account_codes": payload.account_codes,
        "timestamp": _stream_timestamp(msg_id),
        # 🔴 原样带出。旧实现整片丢掉，于是 `wp_id`/`revision` 在断线补拉后不可得。
        "extra": dict(payload.extra) if payload.extra else None,
    }


def belongs_to_project(item: Mapping[str, Any], project_id: UUID | str) -> bool:
    """该 replay 项是否属于 ``project_id``。

    判据取 ``project_id`` 顶层字段（``EventPayload.project_id`` 是必填路由字段）。
    空字符串视为**不属于**任何具体项目：把无归属事件下发到某个项目流等于跨项目泄露。
    """
    own = str(item.get("project_id") or "")
    if own == "":
        return False
    return own == str(project_id)


def content_update_dedupe_key(item: Mapping[str, Any]) -> str | None:
    """replay 项 → AC 11.9 的 ``wp_id + revision`` 去重键；不可去重时返回 ``None``。

    与前端 ``contentUpdateDedupeKey()`` **同一口径**（守卫双向比对）：业务键从
    ``extra`` 里取，键里**不含** ``operation_id`` —— 同一次 commit 既可能由 operation
    应用触发，也可能由纯表示升级触发（后者 ``operation_id`` 为 ``None``），把它放进键
    会让同一个 revision 被当成两条事实。
    """
    extra = item.get("extra")
    if not isinstance(extra, Mapping):
        return None
    wp_id = extra.get("wp_id")
    revision = extra.get("revision")
    if not isinstance(wp_id, str) or wp_id.strip() == "":
        return None
    if isinstance(revision, bool) or not isinstance(revision, int):
        return None
    return f"{wp_id}|{revision}"


def parse_stream_json(raw: str) -> dict[str, Any]:
    """判据辅助：把 :func:`serialize_payload_for_stream` 的输出解回 dict。

    存在的理由是让 "Stream 里写下去的那份 == outbox 行的 payload" 这条 Property 53
    断言可以逐项做，而不必在测试里重写一遍 pydantic 的序列化口径。
    """
    return json.loads(raw)
