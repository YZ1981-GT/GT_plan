# Feature: dsh-agent-panel-integration — Task 5 run coordinator / SSE replay / 取消 / drain 守卫
"""``ChatRunCoordinator``、SSE 回放与续传、取消传播、服务 drain 与启动恢复的行为守卫。

Requirements: 4.1, 4.5, 4.7, 4.8, 4.9, 4.12（并覆盖 10.5 的 ``engine_unavailable``
与 13.6 的 typed quota 负载）
Properties:
  - **Property 7（Run 唯一终态）**：任意 run 的事件序列满足状态机，terminal event 恰好
    一个；注入 engine error 或 cancel 后，序列中不存在后续 ``done`` 或 completed
    assistant message。
    **Validates: Requirements 4.3, 4.5**
  - **Property 8（取消传播到全部后代）**：对运行中 native/DSH/tool/child-agent 的任意
    取消时点，cancel 最终传播到全部 descendants，取消确认后工具调用计数不再增加。
    **Validates: Requirements 4.7**
  - **Property 9（SSE 任意分片与续传等价）**：将同一 SSE 字节流按任意位置分片并混用
    CRLF/LF，客户端解析事件序列与未分片基线完全一致；按 Last-Event-ID 重连不丢失
    也不重复业务事件。
    **Validates: Requirements 4.8**

## 判据落在哪里

| 判据 | 落点 |
|---|---|
| 帧自定界 | 真实 ``encode_*`` 输出 + 规范参考客户端**逐字节分片**解析 |
| 续传不丢不重 | 真实 ``RunEventStream.history`` 在任意切点上的输出 == 期望尾段 |
| 一个 run 一个 executor | 两个不同 owner 的协调器**真并发**抢同一个 run（真实 PG 租约 CAS） |
| 队列满 | 真实有界队列 + 真实 ``quota`` 事件负载 + 真实 ``error/rate_limited`` 落库 |
| 终态恰好一个 | 真实 engine 替身在流中注入 error/cancel，查真实库状态与消息状态 |
| 取消传播 | engine / 工具 / 子 Agent 三层真实回调 + 工具调用计数在取消后不再增长 |
| drain | 真实 ``sse_registry.close_all()`` → 真实生成器产出 ``server_draining`` 帧 |
| 启动恢复 | 真实过期租约行 + 真实副作用判据（tool_calls / completed 消息） |
| 不逐 token 写行 | 200 个 delta 后 ``ai_chat_message`` 的**真实行数** |

## ``_ReferenceSseClient`` 是测试夹具，不是被测产物

它是按 WHATWG SSE 规范写的最小客户端解析器，用来**观察**服务端字节流。被测对象是
:mod:`app.services.ai_chat.run_events` 的编码器与回放逻辑：编码器少发帧尾空行、把裸换行
写进 ``data``、或给心跳/drain 帧加上 ``id``，都会让下面的判据变红。前端侧的解析器由
Task 8 拥有（``frontend/src/utils/sse.ts``），其 property 9 在该 Task 的 vitest 里覆盖。

## 夹具形态

- **提交型**（:func:`_collect`）：协调器的 executor 走**独立 session**，未提交的数据它看不见
  ⇒ 必须真提交。🔴 全部场景快照在**一次** ``asyncio.run`` 内取完（每个测试各自
  ``asyncio.run`` 会污染共享连接池）；清理 ID 在任何后续步骤**之前**登记；清理分独立事务。
- **纯内存**：SSE 帧编码与 ``RunEventStream``（Redis provider 返 None ⇒ 走等价有界镜像）
  不需要数据库，直接同步/``asyncio.run`` 断言。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from hypothesis import given, settings as hyp_settings, strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.ai_models import (
    AIChatRun,
    AIChatSession,
    AIChatToolCall,
    ChatEngineName,
    ChatMessageStatus,
    ChatRunStatus,
)
from app.models.base import ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote
from app.routers import doc_ai_chat as route_mod
from app.services.ai_chat.contracts import HostType
from app.services.ai_chat.run_contract import (
    RUN_EVENTS_URL_TEMPLATE,
    RUN_STARTED_EVENT_SEQ,
    ChatErrorCode,
    ChatEvent,
    ChatEventType,
    ChatRunRequest,
    capabilities_for,
    event_seq,
    format_event_id,
)
from app.services.ai_chat.run_coordinator import (
    CancelRegistry,
    CancelSignal,
    ChatRunCoordinator,
    RunExecution,
    RunLease,
    RunQuotaExceeded,
    cancel_key,
    lease_key,
)
from app.services.ai_chat.run_events import (
    DRAINING_EVENT_NAME,
    HEARTBEAT_COMMENT,
    LocalEventMirror,
    RunEventStream,
    encode_comment,
    encode_draining,
    encode_event,
    encode_frame,
    encode_heartbeat,
    stream_key,
)
from app.services.ai_chat.run_service import ChatRunService, RunEventSequencer

from ._fixtures import FIXTURE_AUDIT_YEAR, IS_PG

needs_pg = pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (租约 CAS / 终态竞争)")


# ===========================================================================
# 参考客户端解析器（测试夹具）
# ===========================================================================

_LINE_BREAK = re.compile(r"\r\n|\r|\n")


@dataclass
class ParsedEvent:
    event: str
    data: str
    last_event_id: str | None


class _ReferenceSseClient:
    """WHATWG SSE 规范的最小客户端解析器 —— **测试夹具**（见模块 docstring）。

    关键点（也是"任意分片等价"能成立的前提）：
    - 跨 chunk 保留缓冲，只有拿到完整行终止符才消费一行；
    - 缓冲末尾的裸 ``\\r`` 可能是被切开的 ``\\r\\n``，必须等下一片；
    - 空行 dispatch；``:`` 开头是注释（不 dispatch、不动 ``last_event_id``）；
    - data buffer 为空时**不** dispatch（规范如此，也是"心跳不是事件"的依据）。
    """

    def __init__(self) -> None:
        self._buf = ""
        self._data: list[str] = []
        self._event = ""
        self.last_event_id: str | None = None
        self.events: list[ParsedEvent] = []
        self.comments: list[str] = []

    def feed(self, chunk: str) -> None:
        self._buf += chunk
        while True:
            match = _LINE_BREAK.search(self._buf)
            if match is None:
                break
            if match.group(0) == "\r" and match.end() == len(self._buf):
                break  # 可能是被分片切开的 CRLF
            line = self._buf[: match.start()]
            self._buf = self._buf[match.end() :]
            self._process(line)

    def close(self) -> None:
        if self._buf:
            line, self._buf = self._buf, ""
            self._process(line)

    def _process(self, line: str) -> None:
        if line == "":
            self._dispatch()
            return
        if line.startswith(":"):
            self.comments.append(line[1:].lstrip())
            return
        field_name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field_name == "data":
            self._data.append(value)
        elif field_name == "event":
            self._event = value
        elif field_name == "id" and "\x00" not in value:
            self.last_event_id = value
        # retry / 未知字段：忽略

    def _dispatch(self) -> None:
        if not self._data:
            self._event = ""
            return
        self.events.append(
            ParsedEvent(
                event=self._event or "message",
                data="\n".join(self._data),
                last_event_id=self.last_event_id,
            )
        )
        self._data = []
        self._event = ""


def _parse(payload: str, *, splits: list[int] | None = None) -> _ReferenceSseClient:
    client = _ReferenceSseClient()
    if not splits:
        client.feed(payload)
    else:
        points = sorted({p for p in splits if 0 < p < len(payload)})
        prev = 0
        for p in points:
            client.feed(payload[prev:p])
            prev = p
        client.feed(payload[prev:])
    client.close()
    return client


# ===========================================================================
# 事件构造工具
# ===========================================================================


def _event(
    *,
    run_id: UUID,
    session_id: UUID,
    request_id: UUID,
    seq: int,
    etype: ChatEventType,
    payload: dict[str, Any] | None = None,
    message_id: UUID | None = None,
) -> ChatEvent:
    from app.services.ai_chat.run_contract import MESSAGE_BOUND_EVENT_TYPES

    if etype in MESSAGE_BOUND_EVENT_TYPES and message_id is None:
        message_id = uuid.uuid4()
    return ChatEvent(
        event_id=format_event_id(seq),
        run_id=run_id,
        session_id=session_id,
        request_id=request_id,
        type=etype,
        timestamp=datetime.now(timezone.utc),
        message_id=message_id,
        payload=payload or {},
    )


def _sample_sequence(count: int = 8) -> list[ChatEvent]:
    """一条典型 run 的事件序列（含终态）。"""
    run_id, session_id, request_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    message_id = uuid.uuid4()
    seq = RUN_STARTED_EVENT_SEQ
    out = [
        _event(
            run_id=run_id, session_id=session_id, request_id=request_id,
            seq=seq, etype=ChatEventType.run_started,
            payload={"engine": "native", "display_label": "货币资金 · 附注"},
        )
    ]
    seq += 1
    out.append(
        _event(
            run_id=run_id, session_id=session_id, request_id=request_id,
            seq=seq, etype=ChatEventType.context_ready,
            payload={"manifest": {"included": ["底稿 E1-1"], "trimmed": []}},
        )
    )
    for i in range(count):
        seq += 1
        out.append(
            _event(
                run_id=run_id, session_id=session_id, request_id=request_id,
                seq=seq, etype=ChatEventType.delta,
                # 正文刻意含换行、中文、引号、冒号与 "data:" 字样 —— 都是能把
                # 帧边界搞坏的字符（JSON 转义 + 多行 data 拆分必须两者都对）。
                payload={"text": f"第{i}段：\n银行存款 1,234.50 元\ndata: 假字段\n"},
                message_id=message_id,
            )
        )
    seq += 1
    out.append(
        _event(
            run_id=run_id, session_id=session_id, request_id=request_id,
            seq=seq, etype=ChatEventType.done,
            payload={"usage": {"total_tokens": 128}},
            message_id=message_id,
        )
    )
    return out


# ===========================================================================
# Req 4.8 / Property 9 前半：帧自定界 + 任意分片等价
# ===========================================================================


class TestSseFramingIsSelfDelimiting:
    """**Validates: Requirements 4.8**"""

    def test_every_frame_ends_with_blank_line(self):
        """每帧以空行结束；缺了它两条事件会被并成一条（只有分片时才暴露）。"""
        for ev in _sample_sequence(2):
            frame = encode_event(ev)
            assert frame.endswith("\n\n"), f"帧未以空行结束：{frame!r}"
            assert frame.count("\n\n") == 1, f"帧内出现多余空行（提前截断）：{frame!r}"

    def test_data_never_contains_raw_newline(self):
        """``data:`` 行内不得有裸换行 —— 半条 JSON 会被当成完整帧。"""
        for ev in _sample_sequence(3):
            body = encode_event(ev)
            for line in body.split("\n"):
                if line.startswith("data: "):
                    assert "\r" not in line

    def test_multi_line_payload_is_split_into_multiple_data_lines(self):
        """多行负载被拆成多个 ``data:`` 行，客户端按规范用 ``\\n`` 拼回原文。"""
        frame = encode_frame(data="第一行\n第二行\r\n第三行", event="delta", event_id="000000000009")
        assert frame.count("data: ") == 3, frame
        client = _parse(frame)
        assert len(client.events) == 1
        assert client.events[0].data == "第一行\n第二行\n第三行"

    def test_empty_payload_still_emits_a_data_line(self):
        """空负载也必须发 ``data: `` —— 否则客户端按规范不 dispatch，事件静默消失。"""
        frame = encode_frame(data="", event="quota", event_id="000000000003")
        assert "data: " in frame
        assert len(_parse(frame).events) == 1

    def test_heartbeat_and_comment_do_not_dispatch_or_move_last_event_id(self):
        """心跳是注释帧：不产生事件、不推进 ``Last-Event-ID``（Req 4.8）。"""
        events = _sample_sequence(1)
        payload = encode_event(events[0]) + encode_heartbeat() + encode_comment("x")
        client = _parse(payload)
        assert len(client.events) == 1
        assert client.last_event_id == events[0].event_id
        assert HEARTBEAT_COMMENT in client.comments

    def test_draining_frame_carries_no_id(self):
        """drain 帧**不带 id**（Req 4.9）。

        若它带 id，客户端会把它当业务事件推进 ``Last-Event-ID``，重连后**跳过**真正的
        下一条业务事件 —— 正是 Property 9 后半句要防的"丢事件"。
        """
        events = _sample_sequence(1)
        payload = encode_event(events[0]) + encode_draining()
        client = _parse(payload)
        assert [e.event for e in client.events] == [
            ChatEventType.run_started.value,
            DRAINING_EVENT_NAME,
        ]
        assert client.last_event_id == events[0].event_id, (
            "drain 帧推进了 Last-Event-ID —— 重连会丢掉下一条业务事件"
        )
        assert "id:" not in encode_draining()

    def test_frame_rejects_newline_in_id_or_event_name(self):
        """id / event 名含换行直接拒绝（会伪造出额外字段行，把一帧劈成两帧）。"""
        with pytest.raises(ValueError):
            encode_frame(data="x", event_id="1\n2")
        with pytest.raises(ValueError):
            encode_frame(data="x", event="de\nlta")


@hyp_settings(
    # 纯内存微秒级判据，且本 property 的价值**全部**在于遍历分片位置：
    # 仓库常用的 max_examples=5 只会探到极少数切点，等于没测。
    max_examples=60,
    deadline=None,
)
@given(
    splits=st.lists(st.integers(min_value=1, max_value=4000), min_size=0, max_size=40),
    use_crlf=st.booleans(),
)
def test_property9_arbitrary_fragmentation_parses_identically(splits, use_crlf):
    """**Property 9（前半）**：任意分片 + CRLF/LF 混用下，解析结果与未分片基线完全一致。

    **Validates: Requirements 4.8**

    ``use_crlf`` 模拟中间代理把行尾改写成 CRLF；分片点由 hypothesis 任意给出，
    可能正好落在 ``\\r`` 与 ``\\n`` 之间 —— 那是最典型的丢帧/多帧场景。
    """
    events = _sample_sequence(6)
    payload = "".join(encode_event(e) for e in events)
    payload = encode_comment("connected") + payload + encode_heartbeat()
    if use_crlf:
        payload = payload.replace("\n", "\r\n")

    baseline = _parse(payload)
    fragmented = _parse(payload, splits=splits)

    assert [ (e.event, e.data, e.last_event_id) for e in fragmented.events ] == [
        (e.event, e.data, e.last_event_id) for e in baseline.events
    ], f"分片解析与基线不一致（splits={splits[:8]}… crlf={use_crlf}）"
    assert [e.event for e in baseline.events] == [e.type.value for e in events]
    assert baseline.last_event_id == events[-1].event_id
    # 业务负载必须逐字还原（含中文、换行与 "data:" 字样）
    for parsed, original in zip(baseline.events, events, strict=True):
        assert parsed.data == original.model_dump_json()


# ===========================================================================
# Property 9 后半：Last-Event-ID 续传不丢不重
# ===========================================================================


def _mem_stream() -> RunEventStream:
    """强制走"等价有界缓冲"的事件流（Redis provider 恒 None）。

    Req 4.12 明文允许等价有界缓冲；这里用它让判据不依赖外部 Redis。真实 Redis Stream
    路径由 :class:`TestRedisStreamBackend` 单独覆盖（Redis 不可用则 skip）。
    """

    async def _no_redis() -> None:
        return None

    return RunEventStream(
        ttl_seconds=60,
        maxlen=512,
        mirror=LocalEventMirror(maxlen=512, max_runs=8, ttl_seconds=60),
        redis_provider=_no_redis,
    )


@hyp_settings(max_examples=40, deadline=None)
@given(cut=st.integers(min_value=0, max_value=9))
def test_property9_resume_by_last_event_id_loses_nothing_and_duplicates_nothing(cut):
    """**Property 9（后半）**：按任意切点用 ``Last-Event-ID`` 续传，尾段既不丢也不重。

    **Validates: Requirements 4.8**
    """
    events = _sample_sequence(8)  # run_started + context_ready + 8 delta + done = 11

    async def scenario() -> tuple[list[str], list[str]]:
        stream = _mem_stream()
        for ev in events:
            await stream.publish(ev)
        resume_from = events[cut].event_id
        tail = await stream.history(events[0].run_id, resume_from)
        full = await stream.history(events[0].run_id, None)
        return [e.event_id for e in tail], [e.event_id for e in full]

    tail_ids, full_ids = asyncio.run(scenario())
    expected = [e.event_id for e in events[cut + 1 :]]
    assert tail_ids == expected, f"续传尾段错位（cut={cut}）：{tail_ids} != {expected}"
    assert len(set(tail_ids)) == len(tail_ids), "续传出现重复事件"
    assert full_ids == [e.event_id for e in events], "不带 Last-Event-ID 时未回放全部事件"
    assert tail_ids == [i for i in full_ids if event_seq(i) > event_seq(events[cut].event_id)]


def test_stream_merges_backends_without_loss_or_duplication():
    """跨后端合并按序号去重：同一事件从 Redis 与本地镜像各来一份也只输出一次。

    **Validates: Requirements 4.12**（"Redis 中途掉线/恢复"不得造成丢失或重复）
    """
    events = _sample_sequence(3)

    async def scenario() -> list[str]:
        stream = _mem_stream()
        for ev in events:
            await stream.publish(ev)
            await stream.publish(ev)  # 同一事件重复发布（模拟双后端各存一份）
        got = await stream.history(events[0].run_id, None)
        return [e.event_id for e in got]

    ids = asyncio.run(scenario())
    assert ids == [e.event_id for e in events], ids


def test_local_mirror_is_bounded_by_maxlen_and_run_count():
    """等价缓冲**有界**：每 run 条数与 run 数都有上限（Req 4.12 / NFR-4）。"""
    mirror = LocalEventMirror(maxlen=4, max_runs=3, ttl_seconds=60)
    run_id, session_id, request_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for i in range(20):
        mirror.publish(
            _event(
                run_id=run_id, session_id=session_id, request_id=request_id,
                seq=RUN_STARTED_EVENT_SEQ + i, etype=ChatEventType.quota,
            )
        )
    assert len(mirror.history(run_id)) == 4, "每 run 的 ring buffer 未按 maxlen 设界"
    for _ in range(10):
        other = uuid.uuid4()
        mirror.publish(
            _event(
                run_id=other, session_id=session_id, request_id=request_id,
                seq=RUN_STARTED_EVENT_SEQ, etype=ChatEventType.quota,
            )
        )
    assert mirror.tracked_runs <= 3, f"run 数未设界：{mirror.tracked_runs}"


class _RecordingRedis:
    """真实 Redis 客户端的**透传记录代理**。

    为什么需要它：``MAXLEN ~`` 是 **approximate** 修剪（Redis 只在节点边界顺手裁剪），
    小流量下压根不会裁 —— 用 ``xlen`` 判"有没有设界"必然假绿。所以判据落在
    **我们发给 Redis 的命令参数**上：调用真的执行（不是 mock 掉），同时记录 kwargs。
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.xadd_calls: list[dict[str, Any]] = []
        self.expire_calls: list[tuple[str, int]] = []

    async def xadd(self, name: str, fields: dict[str, Any], **kwargs: Any) -> Any:
        self.xadd_calls.append({"name": name, **kwargs})
        return await self._inner.xadd(name, fields, **kwargs)

    async def expire(self, name: str, ttl: int) -> Any:
        self.expire_calls.append((name, ttl))
        return await self._inner.expire(name, ttl)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


class TestRedisStreamBackend:
    """真实 Redis Stream 路径：TTL、MAXLEN 与**跨实例**回放。

    **Validates: Requirements 4.12**

    判据落在"另一个 ``RunEventStream`` 实例（全新本地镜像）能读到事件"——
    这是"多 worker 部署下发布方与订阅方不同进程"的最小可执行等价物。

    🔴 客户端在场景内**自建并自关**，不用 ``app.core.redis`` 的模块级单例：那个单例的
    连接池会绑定第一个用过它的事件循环，被另一个 ``asyncio.run`` 碰过之后，本用例会
    收到 ``Event loop is closed`` 并被 ``get_redis`` 降级成 None ⇒ 判据变成假红
    （本会话实测踩过：曾在收集期用 ``asyncio.run`` 探测 Redis，污染了整个进程）。
    """

    def test_publish_is_readable_from_a_fresh_instance_with_ttl(self):
        events = _sample_sequence(2)

        async def scenario() -> dict[str, Any] | None:
            from redis.asyncio import from_url

            raw = from_url(app_settings.REDIS_URL, decode_responses=True)
            client = _RecordingRedis(raw)
            try:
                try:
                    await raw.ping()
                except Exception:  # noqa: BLE001
                    return None  # Redis 不可用 → 由调用方 skip

                async def provider() -> Any:
                    return client

                publisher = RunEventStream(
                    ttl_seconds=120, maxlen=64, redis_provider=provider
                )
                for ev in events:
                    await publisher.publish(ev)
                # 全新实例 + 全新本地镜像 ⇒ 读到的只可能来自 Redis
                reader = RunEventStream(
                    ttl_seconds=120,
                    maxlen=64,
                    mirror=LocalEventMirror(maxlen=64, max_runs=4, ttl_seconds=120),
                    redis_provider=provider,
                )
                replayed = await reader.history(events[0].run_id, None)
                tail = await reader.history(events[0].run_id, events[0].event_id)
                ttl = await client.ttl(stream_key(events[0].run_id))
                stream_len = await client.xlen(stream_key(events[0].run_id))
                await publisher.drop(events[0].run_id)
                after_drop = await reader.history(events[0].run_id, None)
                return {
                    "replayed": [e.event_id for e in replayed],
                    "tail": [e.event_id for e in tail],
                    "ttl": ttl,
                    "stream_len": stream_len,
                    "after_drop": [e.event_id for e in after_drop],
                    "xadd_maxlens": [c.get("maxlen") for c in client.xadd_calls],
                    "xadd_approximate": [
                        c.get("approximate") for c in client.xadd_calls
                    ],
                    "expire_ttls": [t for _k, t in client.expire_calls],
                }
            finally:
                await raw.aclose()

        got = asyncio.run(scenario())
        if got is None:
            pytest.skip("need Redis (Stream 回放)")
        assert got["replayed"] == [e.event_id for e in events], got
        assert got["tail"] == [e.event_id for e in events[1:]], got
        assert 0 < got["ttl"] <= 120, f"Stream 未设 TTL：{got['ttl']}"
        assert got["stream_len"] == len(events), got
        assert got["after_drop"] == [], "drop 未清掉 Stream"
        # 有界性判据落在**发出去的命令参数**上（approximate 修剪在小流量下不会真裁，
        # 用 xlen 判"有没有设界"必然假绿）。
        assert got["xadd_maxlens"] == [64] * len(events), (
            f"XADD 未携带有界 MAXLEN：{got['xadd_maxlens']}"
        )
        assert all(isinstance(m, int) and m > 0 for m in got["xadd_maxlens"])
        assert got["expire_ttls"] == [120] * len(events), (
            f"每次发布都必须刷新 TTL：{got['expire_ttls']}"
        )


# ===========================================================================
# 取消信号：传播语义（不依赖数据库的纯行为部分）
# ===========================================================================


class TestCancelSignalPropagation:
    """**Validates: Requirements 4.7**（Property 8 的传播语义层）"""

    def test_request_reaches_every_registered_descendant(self):
        run_id = uuid.uuid4()
        signal = CancelSignal(run_id)
        stopped: list[str] = []
        signal.add_callback(lambda: stopped.append("engine"))
        signal.add_callback(lambda: stopped.append("tool"))
        child = signal.child()
        child.add_callback(lambda: stopped.append("child-agent"))
        grandchild = child.child()
        grandchild.add_callback(lambda: stopped.append("mcp-process"))

        assert signal.request() is True
        assert signal.request() is False, "取消不幂等（第二次又传播了一轮）"
        assert sorted(stopped) == ["child-agent", "engine", "mcp-process", "tool"], stopped
        assert child.is_set and grandchild.is_set

    def test_descendant_registered_after_cancel_is_immediately_cancelled(self):
        """取消**之后**才登记/派生的后代必须立刻是取消态。

        这正是"cancel 与工具启动竞态"：少了这一步，取消瞬间正在启动的工具会照常执行，
        工具调用计数继续增长（Property 8 明令不得增长）。
        """
        signal = CancelSignal(uuid.uuid4())
        signal.request()
        late: list[str] = []
        signal.add_callback(lambda: late.append("late-tool"))
        late_child = signal.child()
        assert late == ["late-tool"], "取消后登记的回调没有被立刻执行"
        assert late_child.is_set, "取消后派生的子信号竟是未取消态"

    def test_callback_failure_does_not_stop_other_descendants(self):
        """一个后代停止失败不得阻断其余后代（否则一个异常留下一串残留进程）。"""
        signal = CancelSignal(uuid.uuid4())
        stopped: list[str] = []

        def boom() -> None:
            raise RuntimeError("kill failed")

        signal.add_callback(boom)
        signal.add_callback(lambda: stopped.append("second"))
        signal.request()
        assert stopped == ["second"]


# ===========================================================================
# 提交型场景：确定性 engine 替身 + 真实协调器
# ===========================================================================


async def _no_redis() -> None:
    return None


@dataclass
class _Step:
    """engine 脚本的一步。"""

    kind: str  # delta | tool | context | citation | error | done | cancelled | wait | sleep
    text: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    gate: asyncio.Event | None = None


class _ScriptedEngine:
    """确定性 engine 替身（结构化满足 ``SupportsChatRun``）。

    刻意不 import Task 6 的模块：Task 6 与本 Task 并发开发，替身按 design 的
    ``run(request, cancel) -> AsyncIterator[ChatEvent]`` 同形实现即可。
    """

    def __init__(
        self,
        script: list[_Step],
        *,
        register_descendants: bool = False,
        ignores_cancel: bool = False,
    ) -> None:
        self._script = script
        self._register = register_descendants
        #: True = **完全不检查**取消信号（模拟不配合取消的真实 engine / 工具循环）。
        #: 用来验证"协调器自己也必须停"，而不是把不变量寄托在 engine 的自觉上。
        self._ignores_cancel = ignores_cancel
        self.started = asyncio.Event()
        self.stopped_marks: list[str] = []
        self.tool_calls = 0
        self.yielded = 0
        self.saw_cancel = False

    async def run(self, request, cancel: CancelSignal):
        self.started.set()
        if self._register:
            cancel.add_callback(lambda: self.stopped_marks.append("engine"))
            child = cancel.child()
            child.add_callback(lambda: self.stopped_marks.append("child-agent"))
        seq = 100
        for step in self._script:
            if cancel.is_set and not self._ignores_cancel:
                self.saw_cancel = True
                return
            if step.kind == "wait":
                assert step.gate is not None
                await step.gate.wait()
                continue
            if step.kind == "sleep":
                await asyncio.sleep(float(step.payload.get("seconds", 0.01)))
                continue
            seq += 1
            if step.kind == "delta":
                yield _event(
                    run_id=request.run_id, session_id=request.session_id,
                    request_id=request.request_id, seq=seq,
                    etype=ChatEventType.delta, payload={"text": step.text},
                )
            elif step.kind == "tool":
                self.tool_calls += 1
                yield _event(
                    run_id=request.run_id, session_id=request.session_id,
                    request_id=request.request_id, seq=seq,
                    etype=ChatEventType.tool_started,
                    payload={"tool": step.text or "wp_read", "call": self.tool_calls},
                )
                seq += 1
                yield _event(
                    run_id=request.run_id, session_id=request.session_id,
                    request_id=request.request_id, seq=seq,
                    etype=ChatEventType.tool_finished,
                    payload={"tool": step.text or "wp_read", "bytes": 128},
                )
            elif step.kind == "context":
                yield _event(
                    run_id=request.run_id, session_id=request.session_id,
                    request_id=request.request_id, seq=seq,
                    etype=ChatEventType.context_ready, payload=step.payload,
                )
            elif step.kind == "error":
                yield _event(
                    run_id=request.run_id, session_id=request.session_id,
                    request_id=request.request_id, seq=seq,
                    etype=ChatEventType.error, payload=step.payload,
                )
            elif step.kind == "done":
                yield _event(
                    run_id=request.run_id, session_id=request.session_id,
                    request_id=request.request_id, seq=seq,
                    etype=ChatEventType.done, payload=step.payload,
                )
            self.yielded += 1


def _coordinator(
    engine_obj: Any,
    db_engine,
    *,
    stream: RunEventStream | None = None,
    queue_limit: int = 8,
    max_active: int = 2,
    run_timeout: float = 20.0,
    draft_flush: float = 0.05,
    owner: str | None = None,
    sequencer: RunEventSequencer | None = None,
) -> ChatRunCoordinator:
    return ChatRunCoordinator(
        session_factory=lambda: AsyncSession(bind=db_engine),
        engine_provider=(lambda db, execution: engine_obj),
        stream=stream or _mem_stream(),
        cancels=CancelRegistry(redis_provider=_no_redis),
        lease=RunLease(ttl_seconds=30, redis_provider=_no_redis),
        sequencer=sequencer or RunEventSequencer(),
        max_active=max_active,
        queue_limit=queue_limit,
        run_timeout=run_timeout,
        draft_flush_seconds=draft_flush,
        remote_cancel_poll_seconds=0.05,
        owner=owner or f"test-{uuid.uuid4().hex[:6]}",
    )


async def _make_committed_fixture(db_engine) -> dict[str, Any]:
    """最小提交型夹具：manager 用户 + 项目成员 + 附注实例（note 宿主授权链）。"""
    async with AsyncSession(bind=db_engine) as db:
        user = User(
            username=f"ai_t5_{uuid.uuid4().hex[:10]}",
            email=f"{uuid.uuid4().hex[:12]}@ai-task5.example",
            hashed_password="x",
            role=UserRole("manager"),
            is_active=True,
        )
        db.add(user)
        await db.flush()
        project = Project(
            name=f"ai_t5_proj_{uuid.uuid4().hex[:8]}",
            client_name="Task5 协调器夹具",
            audit_year=FIXTURE_AUDIT_YEAR,
        )
        db.add(project)
        await db.flush()
        db.add(
            ProjectUser(
                project_id=project.id,
                user_id=user.id,
                role=ProjectUserRole.manager,
                scope_cycles="D",
            )
        )
        note = DisclosureNote(
            project_id=project.id,
            year=FIXTURE_AUDIT_YEAR,
            note_section="五、协调器夹具",
            section_title="货币资金",
            section_id=f"sec_{uuid.uuid4().hex[:8]}",
            text_content="附注正文",
        )
        db.add(note)
        await db.flush()
        ids = {"user_id": user.id, "project_id": project.id, "note_id": note.id}
        await db.commit()
    return ids


def _request(ids: dict[str, Any]) -> ChatRunRequest:
    return ChatRunRequest.model_validate(
        {
            "host": {
                "type": HostType.note.value,
                "id": str(ids["note_id"]),
                "project_id_assertion": str(ids["project_id"]),
                "year_assertion": FIXTURE_AUDIT_YEAR,
            },
            "query": "这段附注披露是否完整？",
            "idempotency_key": str(uuid.uuid4()),
        }
    )


async def _create_run(db_engine, ids: dict[str, Any]):
    async with AsyncSession(bind=db_engine) as db:
        user = await db.get(User, ids["user_id"])
        creation = await ChatRunService(db).create_run(user, _request(ids))
        await db.commit()
    return creation


async def _run_row(db_engine, run_id: UUID) -> dict[str, Any]:
    async with db_engine.begin() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT status, error_code, retry_count, lease_owner, "
                    "lease_expires_at, cancel_requested_at, latency_ms "
                    "FROM ai_chat_runs WHERE id = :r"
                ),
                {"r": run_id},
            )
        ).one()
        messages = (
            await conn.execute(
                sa.text(
                    "SELECT role::text AS role, status, message_text "
                    "FROM ai_chat_message WHERE run_id = :r ORDER BY seq"
                ),
                {"r": run_id},
            )
        ).mappings().all()
    return {
        "status": row.status,
        "error_code": row.error_code,
        "retry_count": row.retry_count,
        "lease_owner": row.lease_owner,
        "lease_expires_at": row.lease_expires_at,
        "cancel_requested_at": row.cancel_requested_at,
        "latency_ms": row.latency_ms,
        "messages": [dict(m) for m in messages],
    }


_TERMINAL_STATUS_VALUES = {
    ChatRunStatus.done.value,
    ChatRunStatus.error.value,
    ChatRunStatus.cancelled.value,
}


async def _await_terminal(db_engine, run_id: UUID, *, timeout: float = 20.0) -> str:
    """轮询到 run 落终态（超时则返回当时状态，让断言给出真实差异而不是 hang）。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        row = await _run_row(db_engine, run_id)
        if row["status"] in _TERMINAL_STATUS_VALUES:
            return row["status"]
        await asyncio.sleep(0.05)
    return (await _run_row(db_engine, run_id))["status"]


# ---------------------------------------------------------------------------
# 场景
# ---------------------------------------------------------------------------


async def _scenario_happy_path(db_engine, ids) -> dict[str, Any]:
    """成功链路 + 不逐 token 写行（Req 4.12）+ 事件单调。"""
    deltas = 200
    engine_double = _ScriptedEngine(
        [_Step(kind="context", payload={"manifest": {"included": ["附注"]}})]
        + [_Step(kind="delta", text=f"片段{i} ") for i in range(deltas)]
        + [_Step(kind="done", payload={"usage": {"total_tokens": 321}})]
    )
    stream = _mem_stream()
    coordinator = _coordinator(engine_double, db_engine, stream=stream, draft_flush=0.0)
    creation = await _create_run(db_engine, ids)
    await coordinator.submit(creation)
    status = await _await_terminal(db_engine, creation.run_id)
    await coordinator.shutdown()
    events = await stream.history(creation.run_id, None)
    row = await _run_row(db_engine, creation.run_id)
    return {
        "status": status,
        "row": row,
        "event_types": [e.type.value for e in events],
        "event_seqs": [event_seq(e.event_id) for e in events],
        "delta_event_count": sum(1 for e in events if e.type is ChatEventType.delta),
        "delta_message_ids": sorted(
            {str(e.message_id) for e in events if e.type is ChatEventType.delta}
        ),
        "done_message_id": next(
            (str(e.message_id) for e in events if e.type is ChatEventType.done), None
        ),
        "assistant_rows": [m for m in row["messages"] if m["role"] == "assistant"],
        "expected_deltas": deltas,
    }


async def _scenario_queue_quota(db_engine, ids) -> dict[str, Any]:
    """队列满 → typed quota 事件 + error/rate_limited 终态（Req 13.6）。"""
    gate = asyncio.Event()
    slow = _ScriptedEngine(
        [_Step(kind="delta", text="开始"), _Step(kind="wait", gate=gate),
         _Step(kind="done", payload={})]
    )
    stream = _mem_stream()
    # max_active=1 且 queue_limit=1：第一个 run 被 worker 取走并卡在 gate，
    # 第二个占满队列，第三个必然撞上界。
    coordinator = _coordinator(
        slow, db_engine, stream=stream, max_active=1, queue_limit=1
    )
    first = await _create_run(db_engine, ids)
    await coordinator.submit(first)
    await asyncio.wait_for(slow.started.wait(), timeout=10)
    second = await _create_run(db_engine, ids)
    await coordinator.submit(second)
    third = await _create_run(db_engine, ids)
    quota_error: RunQuotaExceeded | None = None
    try:
        await coordinator.submit(third)
    except RunQuotaExceeded as exc:
        quota_error = exc
    third_events = await stream.history(third.run_id, None)
    third_row = await _run_row(db_engine, third.run_id)
    gate.set()
    await _await_terminal(db_engine, first.run_id)
    await coordinator.shutdown()
    quota_events = [e for e in third_events if e.type is ChatEventType.quota]
    return {
        "raised": quota_error is not None,
        "payload": quota_error.payload() if quota_error else None,
        "retry_after": quota_error.retry_after if quota_error else None,
        "third_event_types": [e.type.value for e in third_events],
        "quota_payload_keys": sorted(quota_events[0].payload) if quota_events else [],
        "third_status": third_row["status"],
        "third_error_code": third_row["error_code"],
        "third_assistant_rows": sum(
            1 for m in third_row["messages"] if m["role"] == "assistant"
        ),
        "first_status": (await _run_row(db_engine, first.run_id))["status"],
    }


async def _scenario_single_executor(db_engine, ids) -> dict[str, Any]:
    """两个 owner 真并发抢同一个 run：只有一个能执行（Design 第 2 步）。"""
    creation = await _create_run(db_engine, ids)
    engine_a = _ScriptedEngine(
        [_Step(kind="delta", text="A"), _Step(kind="sleep", payload={"seconds": 0.2}),
         _Step(kind="done", payload={})]
    )
    engine_b = _ScriptedEngine(
        [_Step(kind="delta", text="B"), _Step(kind="sleep", payload={"seconds": 0.2}),
         _Step(kind="done", payload={})]
    )
    stream = _mem_stream()
    a = _coordinator(engine_a, db_engine, stream=stream, owner="owner-A")
    b = _coordinator(engine_b, db_engine, stream=stream, owner="owner-B")
    execution = RunExecution.from_creation(creation)
    # 直接并发驱动同一个 execution：这才是"两个 worker 抢同一个 run"的最小等价物
    # （经 submit 各自入队只会让两个协调器各跑自己队列里的副本，测不到租约）。
    await asyncio.gather(a._execute(execution), b._execute(execution))
    status = await _await_terminal(db_engine, creation.run_id)
    await a.shutdown()
    await b.shutdown()
    row = await _run_row(db_engine, creation.run_id)
    events = await stream.history(creation.run_id, None)
    return {
        "status": status,
        "engines_started": sum(
            1 for e in (engine_a, engine_b) if e.started.is_set()
        ),
        "terminal_event_count": sum(1 for e in events if e.is_terminal),
        "assistant_rows": sum(
            1 for m in row["messages"] if m["role"] == "assistant"
        ),
        "lease_owner": row["lease_owner"],
    }


async def _scenario_engine_error(db_engine, ids) -> dict[str, Any]:
    """engine 先报 error 再给 done：done 必须不被签发（Property 7）。"""
    engine_double = _ScriptedEngine(
        [
            _Step(kind="delta", text="部分正文"),
            _Step(kind="error", payload={"code": ChatErrorCode.engine_unavailable.value}),
            _Step(kind="done", payload={"usage": {"total_tokens": 9}}),
        ]
    )
    stream = _mem_stream()
    coordinator = _coordinator(engine_double, db_engine, stream=stream)
    creation = await _create_run(db_engine, ids)
    await coordinator.submit(creation)
    status = await _await_terminal(db_engine, creation.run_id)
    await coordinator.shutdown()
    events = await stream.history(creation.run_id, None)
    row = await _run_row(db_engine, creation.run_id)
    return {
        "status": status,
        "error_code": row["error_code"],
        "event_types": [e.type.value for e in events],
        "terminal_event_count": sum(1 for e in events if e.is_terminal),
        "done_count": sum(1 for e in events if e.type is ChatEventType.done),
        "completed_assistant": sum(
            1
            for m in row["messages"]
            if m["role"] == "assistant" and m["status"] == ChatMessageStatus.completed.value
        ),
        "assistant_statuses": [
            m["status"] for m in row["messages"] if m["role"] == "assistant"
        ],
    }


async def _scenario_external_terminal_race(db_engine, ids) -> dict[str, Any]:
    """engine 还在流式输出时，**外部**抢先落 error 终态（跨进程终态门）。"""
    gate = asyncio.Event()
    engine_double = _ScriptedEngine(
        [
            _Step(kind="delta", text="先来一段"),
            _Step(kind="wait", gate=gate),
            _Step(kind="delta", text="终态之后的一段"),
            _Step(kind="done", payload={}),
        ]
    )
    stream = _mem_stream()
    coordinator = _coordinator(engine_double, db_engine, stream=stream)
    creation = await _create_run(db_engine, ids)
    await coordinator.submit(creation)
    # 等第一条 delta 真的进流，确保 run 已 running
    for _ in range(200):
        if any(
            e.type is ChatEventType.delta
            for e in await stream.history(creation.run_id, None)
        ):
            break
        await asyncio.sleep(0.02)
    # 🔴 带外签发终态必须复用协调器的序号来源并先对齐（否则新事件与已发布事件撞号，
    #    按序号去重后终态被静默丢掉 —— 跨进程取消就是这个形态，本判据实测抓到过）。
    await coordinator._seed_sequencer(creation.run_id)
    async with AsyncSession(bind=db_engine) as db:
        svc = ChatRunService(db, sequencer=coordinator.sequencer)
        external = await svc.finish_error(
            run_id=creation.run_id, error_code=ChatErrorCode.rate_limited
        )
        await db.commit()
    if external is not None:
        await stream.publish(external)
    gate.set()
    status = await _await_terminal(db_engine, creation.run_id)
    await coordinator.shutdown()
    events = await stream.history(creation.run_id, None)
    row = await _run_row(db_engine, creation.run_id)
    return {
        "status": status,
        "error_code": row["error_code"],
        "terminal_event_count": sum(1 for e in events if e.is_terminal),
        "done_count": sum(1 for e in events if e.type is ChatEventType.done),
        "completed_assistant": sum(
            1
            for m in row["messages"]
            if m["role"] == "assistant" and m["status"] == ChatMessageStatus.completed.value
        ),
        "delta_after_terminal": sum(
            1
            for e in events
            if e.type is ChatEventType.delta
            and event_seq(e.event_id) > event_seq(external.event_id)
        )
        if external is not None
        else -1,
    }


async def _scenario_cancel_with_tools(db_engine, ids) -> dict[str, Any]:
    """取消传播到 engine / 子 Agent / 工具，且取消后工具计数不再增长（Property 8）。"""
    # 工具之间插入 sleep：给取消一个真实的插入时点（否则整条脚本瞬间跑完，
    # "取消后不再增长"就成了空断言）。
    script: list[_Step] = []
    total_tools = 60
    for i in range(total_tools):
        script.append(_Step(kind="tool", text=f"wp_read_{i}"))
        script.append(_Step(kind="sleep", payload={"seconds": 0.03}))
    script.append(_Step(kind="done", payload={}))
    engine_double = _ScriptedEngine(script, register_descendants=True)
    stream = _mem_stream()
    coordinator = _coordinator(engine_double, db_engine, stream=stream)
    creation = await _create_run(db_engine, ids)
    await coordinator.submit(creation)
    for _ in range(300):
        if engine_double.tool_calls >= 2:
            break
        await asyncio.sleep(0.02)
    tools_at_cancel = engine_double.tool_calls
    async with AsyncSession(bind=db_engine) as db:
        outcome = await coordinator.cancel(db, creation.run_id, actor_id=ids["user_id"])
    status = await _await_terminal(db_engine, creation.run_id)
    tools_after = engine_double.tool_calls
    await asyncio.sleep(0.2)
    tools_settled = engine_double.tool_calls
    async with AsyncSession(bind=db_engine) as db:
        second = await coordinator.cancel(db, creation.run_id, actor_id=ids["user_id"])
    await coordinator.shutdown()
    events = await stream.history(creation.run_id, None)
    row = await _run_row(db_engine, creation.run_id)
    return {
        "status": status,
        "outcome": outcome.as_response(),
        "second_outcome": second.as_response(),
        "tools_at_cancel": tools_at_cancel,
        "tools_after_terminal": tools_after,
        "tools_settled": tools_settled,
        "stopped_marks": sorted(set(engine_double.stopped_marks)),
        "terminal_event_count": sum(1 for e in events if e.is_terminal),
        "terminal_types": [e.type.value for e in events if e.is_terminal],
        "done_count": sum(1 for e in events if e.type is ChatEventType.done),
        "completed_assistant": sum(
            1
            for m in row["messages"]
            if m["role"] == "assistant" and m["status"] == ChatMessageStatus.completed.value
        ),
        "cancel_requested_at_set": row["cancel_requested_at"] is not None,
        "error_code": row["error_code"],
        "coordinator_tool_calls": coordinator.tool_call_count(creation.run_id),
        "total_tools_in_script": total_tools,
    }


async def _scenario_cancel_while_queued(db_engine, ids) -> dict[str, Any]:
    """排队中的 run 被取消：不得开跑（Req 4.7 明确排队任务也要收到取消）。"""
    gate = asyncio.Event()
    blocker = _ScriptedEngine([_Step(kind="wait", gate=gate), _Step(kind="done", payload={})])
    queued_engine = _ScriptedEngine([_Step(kind="delta", text="不该被执行")])

    engines: dict[UUID, Any] = {}

    stream = _mem_stream()
    coordinator = ChatRunCoordinator(
        session_factory=lambda: AsyncSession(bind=db_engine),
        engine_provider=lambda db, execution: engines[execution.run_id],
        stream=stream,
        cancels=CancelRegistry(redis_provider=_no_redis),
        lease=RunLease(ttl_seconds=30, redis_provider=_no_redis),
        max_active=1,
        queue_limit=4,
        run_timeout=20.0,
        draft_flush_seconds=0.05,
        remote_cancel_poll_seconds=0.05,
        owner="owner-queued",
    )
    first = await _create_run(db_engine, ids)
    engines[first.run_id] = blocker
    await coordinator.submit(first)
    await asyncio.wait_for(blocker.started.wait(), timeout=10)
    waiting = await _create_run(db_engine, ids)
    engines[waiting.run_id] = queued_engine
    await coordinator.submit(waiting)
    async with AsyncSession(bind=db_engine) as db:
        outcome = await coordinator.cancel(db, waiting.run_id, actor_id=ids["user_id"])
    gate.set()
    first_status = await _await_terminal(db_engine, first.run_id)
    waiting_status = await _await_terminal(db_engine, waiting.run_id)
    await coordinator.shutdown()
    row = await _run_row(db_engine, waiting.run_id)
    return {
        "outcome": outcome.as_response(),
        "waiting_status": waiting_status,
        "first_status": first_status,
        "queued_engine_started": queued_engine.started.is_set(),
        "queued_engine_yielded": queued_engine.yielded,
        "assistant_rows": sum(1 for m in row["messages"] if m["role"] == "assistant"),
        "error_code": row["error_code"],
    }


async def _scenario_cross_worker_cancel(db_engine, ids) -> dict[str, Any]:
    """另一个 worker 处理取消：带外签发的终态事件不得与已发布事件撞号后被去重吃掉。

    这是**真实抓到过**的缺陷形态，不是假想：执行 run 的 worker 已经发布到序号 N，
    处理 ``POST /cancel`` 的是另一个进程，它的序号从头开始 ⇒ cancelled 事件拿到一个
    早已用过的 ID ⇒ :meth:`RunEventStream.history` 按序号去重把它丢掉 ⇒ 客户端点了
    取消却永远等不到终态。
    """
    creation = await _create_run(db_engine, ids)
    stream = _mem_stream()
    # 模拟"执行 worker 已经发布了 1..5"：run_started + 4 条 delta。
    published = [creation.run_started_event()]
    message_id = uuid.uuid4()
    for seq in range(RUN_STARTED_EVENT_SEQ + 1, RUN_STARTED_EVENT_SEQ + 5):
        published.append(
            _event(
                run_id=creation.run_id,
                session_id=creation.session_id,
                request_id=creation.request_id,
                seq=seq,
                etype=ChatEventType.delta,
                payload={"text": f"已发布片段 {seq}"},
                message_id=message_id,
            )
        )
    for ev in published:
        await stream.publish(ev)

    # 另一个"worker"：全新协调器 ⇒ 全新序号来源（它从未为该 run 发过事件）。
    other_worker = _coordinator(
        _ScriptedEngine([_Step(kind="done", payload={})]),
        db_engine,
        stream=stream,
        owner="owner-other-worker",
    )
    async with AsyncSession(bind=db_engine) as db:
        outcome = await other_worker.cancel(db, creation.run_id, actor_id=ids["user_id"])
    await other_worker.shutdown()

    events = await stream.history(creation.run_id, None)
    terminal = [e for e in events if e.is_terminal]
    row = await _run_row(db_engine, creation.run_id)
    return {
        "outcome": outcome.as_response(),
        "db_status": row["status"],
        "published_max_seq": max(event_seq(e.event_id) for e in published),
        "terminal_count": len(terminal),
        "terminal_seq": event_seq(terminal[0].event_id) if terminal else None,
        "terminal_type": terminal[0].type.value if terminal else None,
        "all_seqs": [event_seq(e.event_id) for e in events],
    }


async def _scenario_reconnect(db_engine, ids) -> dict[str, Any]:
    """断流 → 按 Last-Event-ID 重连：不丢不重，且不重新调用 engine（Req 4.1）。"""
    engine_double = _ScriptedEngine(
        [_Step(kind="delta", text=f"段{i} ") for i in range(6)]
        + [_Step(kind="done", payload={"usage": {"total_tokens": 12}})]
    )
    stream = _mem_stream()
    coordinator = _coordinator(engine_double, db_engine, stream=stream)
    creation = await _create_run(db_engine, ids)
    await coordinator.submit(creation)
    await _await_terminal(db_engine, creation.run_id)
    await coordinator.shutdown()

    all_events = await stream.history(creation.run_id, None)
    # 客户端"只收到前 3 条就断了"
    seen = all_events[:3]
    resume = seen[-1].event_id
    tail = await stream.history(creation.run_id, resume)
    return {
        "engine_invocations": 1 if engine_double.started.is_set() else 0,
        "engine_yielded": engine_double.yielded,
        "all_ids": [e.event_id for e in all_events],
        "seen_ids": [e.event_id for e in seen],
        "tail_ids": [e.event_id for e in tail],
        "union_matches": [e.event_id for e in seen] + [e.event_id for e in tail]
        == [e.event_id for e in all_events],
        "terminal_in_tail": any(e.is_terminal for e in tail),
    }


async def _scenario_drain(db_engine, ids) -> dict[str, Any]:
    """服务 drain：真实 ``sse_registry.close_all()`` → 生成器产出 ``server_draining``。"""
    from app.core.sse_registry import sse_registry

    events = _sample_sequence(2)
    stream = _mem_stream()
    for ev in events[:2]:
        await stream.publish(ev)
    run_id = events[0].run_id

    conn = sse_registry.register()
    frames: list[str] = []

    async def consume() -> None:
        try:
            frames.append(encode_comment(f"run {run_id} 已连接"))
            async for item in stream.follow(
                run_id,
                after_event_id=None,
                heartbeat_interval=0.05,
                poll_interval=0.02,
                max_seconds=5.0,
                stop=lambda: conn.is_closed,
            ):
                if conn.is_closed:
                    frames.append(encode_draining())
                    return
                frames.append(encode_heartbeat() if item is None else encode_event(item))
        finally:
            sse_registry.unregister(conn)

    task = asyncio.create_task(consume())
    # 等到"两条事件都发完 + 至少一次空转心跳"才 drain：只等事件会让心跳判据变成空断言。
    for _ in range(300):
        if any(HEARTBEAT_COMMENT in f for f in frames) and len(frames) >= 3:
            break
        await asyncio.sleep(0.02)
    await sse_registry.close_all()
    await asyncio.wait_for(task, timeout=5)

    payload = "".join(frames)
    client = _parse(payload)
    return {
        "frames": len(frames),
        "has_draining": any(e.event == DRAINING_EVENT_NAME for e in client.events),
        "last_event_id": client.last_event_id,
        "expected_last_event_id": events[1].event_id,
        "heartbeats": client.comments.count(HEARTBEAT_COMMENT),
        "registry_active": sse_registry.active_count,
        "event_names": [e.event for e in client.events],
    }


async def _scenario_recovery(db_engine, ids) -> dict[str, Any]:
    """启动恢复：无副作用 → 重排并真的重跑；有副作用/超重试上限 → interrupted → error。"""
    stream = _mem_stream()
    reran = _ScriptedEngine(
        [_Step(kind="delta", text="重排后的回答"), _Step(kind="done", payload={})]
    )
    coordinator = _coordinator(reran, db_engine, stream=stream)

    async def make_expired_running(*, retry_count: int, with_tool: bool):
        creation = await _create_run(db_engine, ids)
        async with AsyncSession(bind=db_engine) as db:
            assert await ChatRunService(db).mark_running(
                creation.run_id, lease_owner="dead-owner"
            )
            await db.execute(
                sa.update(AIChatRun)
                .where(AIChatRun.id == creation.run_id)
                .values(
                    lease_owner="dead-owner",
                    lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                    retry_count=retry_count,
                )
            )
            if with_tool:
                db.add(
                    AIChatToolCall(
                        run_id=creation.run_id,
                        tool_call_id=f"call_{uuid.uuid4().hex[:8]}",
                        tool_name="wp_read",
                        arg_hash="a" * 64,
                        status="finished",
                    )
                )
            await db.commit()
        return creation

    fresh = await make_expired_running(retry_count=0, with_tool=False)
    with_tool = await make_expired_running(retry_count=0, with_tool=True)
    exhausted = await make_expired_running(
        retry_count=int(app_settings.AI_CHAT_RUN_MAX_RETRIES), with_tool=False
    )

    async with AsyncSession(bind=db_engine) as db:
        report = await coordinator.recover_lease_expired_runs(db)

    rows = {
        "fresh": await _run_row(db_engine, fresh.run_id),
        "with_tool": await _run_row(db_engine, with_tool.run_id),
        "exhausted": await _run_row(db_engine, exhausted.run_id),
    }
    redispatched = await coordinator.redispatch([fresh.run_id])
    rerun_status = await _await_terminal(db_engine, fresh.run_id)
    await coordinator.shutdown()
    rerun_row = await _run_row(db_engine, fresh.run_id)
    return {
        "report": report.as_dict(),
        "requeued_ids": [str(r) for r in report.requeued],
        "fresh_id": str(fresh.run_id),
        "with_tool_id": str(with_tool.run_id),
        "exhausted_id": str(exhausted.run_id),
        "rows": {
            k: {
                "status": v["status"],
                "error_code": v["error_code"],
                "retry_count": v["retry_count"],
                "lease_owner": v["lease_owner"],
            }
            for k, v in rows.items()
        },
        "redispatched": [str(r) for r in redispatched],
        "rerun_status": rerun_status,
        "rerun_completed_assistant": sum(
            1
            for m in rerun_row["messages"]
            if m["role"] == "assistant" and m["status"] == ChatMessageStatus.completed.value
        ),
        "rerun_event_seqs": [
            event_seq(e.event_id) for e in await stream.history(fresh.run_id, None)
        ],
    }


async def _scenario_lease_isolation(db_engine, ids) -> dict[str, Any]:
    """租约本身的两条判据（不借 ``mark_running`` 的 CAS 兜底）。

    🔴 为什么必须**单独**测租约：``mark_running`` 的状态 CAS 会把"两个 executor"挡住，
    于是任何只看"engine 起了几次"的判据在租约被放宽后**依然绿**（变异检验实测：
    放宽租约过期条件、甚至完全无视租约，两条 engine 仍然只起一次）。
    真正只有租约能防的是"抢到执行权之前的那段工作"与"过期接管"，故这里直接判租约。
    """
    creation = await _create_run(db_engine, ids)
    lease = RunLease(ttl_seconds=30, redis_provider=_no_redis)

    # ① 两个 owner 并发 acquire 同一个 run → 恰好一个拿到 grant
    async def try_acquire(owner: str):
        async with AsyncSession(bind=db_engine) as db:
            grant = await lease.acquire(db, creation.run_id, owner)
            await db.commit()
            return owner if grant is not None else None

    winners = [
        w
        for w in await asyncio.gather(
            try_acquire("lease-owner-1"), try_acquire("lease-owner-2")
        )
        if w is not None
    ]

    # ② 租约**未过期**时第三方仍被拒（防"把过期判据放宽成存在判据"）
    async with AsyncSession(bind=db_engine) as db:
        third = await lease.acquire(db, creation.run_id, "lease-owner-3")
        await db.commit()

    # ③ 租约过期后可被接管（反假绿控制：不能靠"永远拒绝"通过上面两条）
    async with AsyncSession(bind=db_engine) as db:
        await db.execute(
            sa.update(AIChatRun)
            .where(AIChatRun.id == creation.run_id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await db.commit()
    async with AsyncSession(bind=db_engine) as db:
        takeover = await lease.acquire(db, creation.run_id, "lease-owner-4")
        await db.commit()

    # ④ 协调器在租约被他人持有时必须**放弃执行**（run 仍是 queued，engine 不许起）
    blocked_engine = _ScriptedEngine(
        [_Step(kind="delta", text="不该被执行"), _Step(kind="done", payload={})]
    )
    other = _coordinator(
        blocked_engine, db_engine, stream=_mem_stream(), owner="lease-owner-5"
    )
    await other._execute(RunExecution.from_creation(creation))
    await other.shutdown()
    row = await _run_row(db_engine, creation.run_id)
    return {
        "concurrent_winners": winners,
        "third_refused": third is None,
        "takeover_after_expiry": takeover is not None,
        "blocked_engine_started": blocked_engine.started.is_set(),
        "blocked_engine_yielded": blocked_engine.yielded,
        "status_after_blocked_attempt": row["status"],
        "lease_owner_after": row["lease_owner"],
    }


async def _scenario_uncooperative_engine_cancel(db_engine, ids) -> dict[str, Any]:
    """engine **不配合**取消时，协调器自己必须停止签发事件并落取消终态。

    🔴 之前的取消判据用的是"会检查 cancel 的替身"，于是协调器主循环里的取消检查被删掉
    也照样绿（变异检验实测 GREEN）。真实 engine（尤其 DSH 的工具循环）不保证每步都查，
    所以这条不变量必须由协调器独立成立。
    """
    total_tools = 80
    script: list[_Step] = []
    for i in range(total_tools):
        script.append(_Step(kind="tool", text=f"stubborn_{i}"))
        script.append(_Step(kind="sleep", payload={"seconds": 0.02}))
    script.append(_Step(kind="done", payload={}))
    engine_double = _ScriptedEngine(script, ignores_cancel=True)
    stream = _mem_stream()
    coordinator = _coordinator(engine_double, db_engine, stream=stream)
    creation = await _create_run(db_engine, ids)
    await coordinator.submit(creation)
    for _ in range(300):
        if engine_double.tool_calls >= 2:
            break
        await asyncio.sleep(0.02)
    async with AsyncSession(bind=db_engine) as db:
        await coordinator.cancel(db, creation.run_id, actor_id=ids["user_id"])
    status = await _await_terminal(db_engine, creation.run_id)
    events_at_terminal = len(await stream.history(creation.run_id, None))
    await asyncio.sleep(0.3)
    events_after = len(await stream.history(creation.run_id, None))
    await coordinator.shutdown()
    events = await stream.history(creation.run_id, None)
    row = await _run_row(db_engine, creation.run_id)
    return {
        "status": status,
        "events_at_terminal": events_at_terminal,
        "events_after_settle": events_after,
        "total_tools_in_script": total_tools,
        "terminal_count": sum(1 for e in events if e.is_terminal),
        "terminal_types": [e.type.value for e in events if e.is_terminal],
        "tool_started_events": sum(
            1 for e in events if e.type is ChatEventType.tool_started
        ),
        "completed_assistant": sum(
            1
            for m in row["messages"]
            if m["role"] == "assistant" and m["status"] == ChatMessageStatus.completed.value
        ),
    }


async def _scenario_remote_marker_blocks_execution(db_engine, ids) -> dict[str, Any]:
    """跨进程取消标记先到、数据库状态还没改：executor 也必须不开跑（Req 4.7）。

    形态来自真实故障：处理 ``POST /cancel`` 的进程设了标记后崩溃（或它的提交尚未可见），
    执行进程若只看数据库状态就会把一个已被用户取消的 run 完整跑一遍。
    """
    creation = await _create_run(db_engine, ids)
    engine_double = _ScriptedEngine(
        [_Step(kind="delta", text="不该被执行"), _Step(kind="done", payload={})]
    )
    marker: set[str] = {str(creation.run_id)}

    class _MarkedRegistry(CancelRegistry):
        """只把"远端标记"这一件事替成确定性来源，其余走真实实现。"""

        async def is_marked_remote(self, run_id: UUID) -> bool:  # noqa: D401
            return str(run_id) in marker

        async def mark_remote(self, run_id: UUID) -> None:
            marker.add(str(run_id))

        async def clear_remote(self, run_id: UUID) -> None:
            marker.discard(str(run_id))

    stream = _mem_stream()
    coordinator = ChatRunCoordinator(
        session_factory=lambda: AsyncSession(bind=db_engine),
        engine_provider=lambda db, execution: engine_double,
        stream=stream,
        cancels=_MarkedRegistry(redis_provider=_no_redis),
        lease=RunLease(ttl_seconds=30, redis_provider=_no_redis),
        max_active=1,
        queue_limit=4,
        draft_flush_seconds=0.05,
        remote_cancel_poll_seconds=0.05,
        owner="owner-marker",
    )
    await coordinator._execute(RunExecution.from_creation(creation))
    await coordinator.shutdown()
    row = await _run_row(db_engine, creation.run_id)
    events = await stream.history(creation.run_id, None)
    return {
        "engine_started": engine_double.started.is_set(),
        "engine_yielded": engine_double.yielded,
        "status": row["status"],
        "error_code": row["error_code"],
        "assistant_rows": sum(1 for m in row["messages"] if m["role"] == "assistant"),
        "terminal_types": [e.type.value for e in events if e.is_terminal],
    }


async def _scenario_engine_yields_nothing(db_engine, ids) -> dict[str, Any]:
    """engine 一个事件都不产出且不给终态 ⇒ typed error，**不得**按成功定稿（Req 12.9）。"""
    engine_double = _ScriptedEngine([])
    stream = _mem_stream()
    coordinator = _coordinator(engine_double, db_engine, stream=stream)
    creation = await _create_run(db_engine, ids)
    await coordinator.submit(creation)
    status = await _await_terminal(db_engine, creation.run_id)
    await coordinator.shutdown()
    row = await _run_row(db_engine, creation.run_id)
    events = await stream.history(creation.run_id, None)
    return {
        "status": status,
        "error_code": row["error_code"],
        "assistant_rows": sum(1 for m in row["messages"] if m["role"] == "assistant"),
        "terminal_types": [e.type.value for e in events if e.is_terminal],
        "done_count": sum(1 for e in events if e.type is ChatEventType.done),
    }


async def _scenario_draft_settlement_rules(db_engine, ids) -> dict[str, Any]:
    """草稿结算的两条硬规则（直接判 ``ChatRunService``，不绕协调器）。

    ① ``settle_assistant_draft`` 拒绝写 ``completed`` —— 否则就有了**第二条**终态写入
       路径，Property 7 唯一的保证（那次 CAS）失效。
    ② 已结算（failed/cancelled）的草稿**不得**被后到的 ``finish_success`` 复活成
       completed —— 这正是 ``_promote_draft`` 的 ``status == 'draft'`` 谓词在守的东西。
    """
    creation = await _create_run(db_engine, ids)
    async with AsyncSession(bind=db_engine, expire_on_commit=False) as db:
        svc = ChatRunService(db)
        session_obj = await db.get(AIChatSession, creation.session_id)
        assert await svc.mark_running(creation.run_id)
        draft = await svc.append_assistant_draft(
            session=session_obj, run_id=creation.run_id, text="半截正文"
        )
        assert draft is not None
        draft_id = draft.id
        await db.commit()

        refused_completed = False
        try:
            await svc.settle_assistant_draft(
                message_id=draft_id,
                run_id=creation.run_id,
                status=ChatMessageStatus.completed,
            )
        except ValueError:
            refused_completed = True

        settled = await svc.settle_assistant_draft(
            message_id=draft_id,
            run_id=creation.run_id,
            status=ChatMessageStatus.cancelled,
        )
        await db.commit()

        # 结算之后再让 finish_success 胜出（真实竞态里 CAS 与结算的先后不由代码顺序保证）
        event, message = await svc.finish_success(
            session=session_obj,
            run_id=creation.run_id,
            text="定稿正文",
            draft_message_id=draft_id,
        )
        await db.commit()
        won = event is not None
        new_message_id = message.id if message is not None else None

    row = await _run_row(db_engine, creation.run_id)
    statuses = {
        m["status"]: m["message_text"] for m in row["messages"] if m["role"] == "assistant"
    }
    async with db_engine.begin() as conn:
        settled_status = (
            await conn.execute(
                sa.text("SELECT status FROM ai_chat_message WHERE id = :m"),
                {"m": draft_id},
            )
        ).scalar_one()
    return {
        "refused_completed": refused_completed,
        "settled_ok": settled,
        "finish_success_won": won,
        "settled_row_status": settled_status,
        "new_message_is_distinct": new_message_id is not None
        and new_message_id != draft_id,
        "assistant_statuses": sorted(statuses),
        "completed_count": sum(
            1
            for m in row["messages"]
            if m["role"] == "assistant" and m["status"] == ChatMessageStatus.completed.value
        ),
    }


async def _scenario_engine_unavailable(db_engine, ids) -> dict[str, Any]:
    """engine 缺失（Task 6 未就绪 / provider 抛错）⇒ typed error，不假成功（Req 10.5）。"""
    stream = _mem_stream()

    def broken_provider(db, execution):
        raise ImportError("engine 模块尚未就绪")

    coordinator = ChatRunCoordinator(
        session_factory=lambda: AsyncSession(bind=db_engine),
        engine_provider=broken_provider,
        stream=stream,
        cancels=CancelRegistry(redis_provider=_no_redis),
        lease=RunLease(ttl_seconds=30, redis_provider=_no_redis),
        max_active=1,
        queue_limit=4,
        owner="owner-noengine",
    )
    creation = await _create_run(db_engine, ids)
    await coordinator.submit(creation)
    status = await _await_terminal(db_engine, creation.run_id)
    await coordinator.shutdown()
    row = await _run_row(db_engine, creation.run_id)
    events = await stream.history(creation.run_id, None)
    return {
        "status": status,
        "error_code": row["error_code"],
        "assistant_rows": sum(1 for m in row["messages"] if m["role"] == "assistant"),
        "terminal_types": [e.type.value for e in events if e.is_terminal],
        "error_message_is_chinese": bool(
            re.search(
                r"[\u4e00-\u9fff]",
                next(
                    (
                        str(e.payload.get("message", ""))
                        for e in events
                        if e.type is ChatEventType.error
                    ),
                    "",
                ),
            )
        ),
    }


async def _scenario_idempotent_submit(db_engine, ids) -> dict[str, Any]:
    """幂等命中的 run 不入队、不调用 engine（Req 4.6 与协调器的接线）。"""
    engine_double = _ScriptedEngine([_Step(kind="delta", text="x"), _Step(kind="done")])
    coordinator = _coordinator(engine_double, db_engine, stream=_mem_stream())
    req = _request(ids)
    async with AsyncSession(bind=db_engine) as db:
        user = await db.get(User, ids["user_id"])
        first = await ChatRunService(db).create_run(user, req)
        await db.commit()
    async with AsyncSession(bind=db_engine) as db:
        user = await db.get(User, ids["user_id"])
        replay = await ChatRunService(db).create_run(user, req)
        await db.commit()
    accepted_first = await coordinator.submit(first)
    accepted_replay = await coordinator.submit(replay)
    await _await_terminal(db_engine, first.run_id)
    await coordinator.shutdown()
    return {
        "first_accepted": accepted_first is not None,
        "replay_accepted": accepted_replay is not None,
        "same_run": first.run_id == replay.run_id,
        "engine_started_once": engine_double.started.is_set(),
    }


async def _collect() -> dict[str, Any]:
    """一次 ``asyncio.run`` 取完全部提交型场景快照。"""
    db_engine = create_async_engine(
        app_settings.DATABASE_URL, pool_size=20, max_overflow=10
    )
    cleanup: dict[str, Any] = {}
    try:
        ids = await _make_committed_fixture(db_engine)
        # 🔴 清理登记在任何后续步骤之前：中途异常时 finally 才拿得到 ID。
        cleanup.update(ids)
        snapshot: dict[str, Any] = {"ids": {k: str(v) for k, v in ids.items()}}
        snapshot["happy"] = await _scenario_happy_path(db_engine, ids)
        snapshot["quota"] = await _scenario_queue_quota(db_engine, ids)
        snapshot["lease"] = await _scenario_single_executor(db_engine, ids)
        snapshot["lease_isolation"] = await _scenario_lease_isolation(db_engine, ids)
        snapshot["engine_error"] = await _scenario_engine_error(db_engine, ids)
        snapshot["race"] = await _scenario_external_terminal_race(db_engine, ids)
        snapshot["cancel"] = await _scenario_cancel_with_tools(db_engine, ids)
        snapshot["cancel_queued"] = await _scenario_cancel_while_queued(db_engine, ids)
        snapshot["stubborn_cancel"] = await _scenario_uncooperative_engine_cancel(
            db_engine, ids
        )
        snapshot["remote_marker"] = await _scenario_remote_marker_blocks_execution(
            db_engine, ids
        )
        snapshot["cross_worker"] = await _scenario_cross_worker_cancel(db_engine, ids)
        snapshot["reconnect"] = await _scenario_reconnect(db_engine, ids)
        snapshot["drain"] = await _scenario_drain(db_engine, ids)
        snapshot["recovery"] = await _scenario_recovery(db_engine, ids)
        snapshot["no_engine"] = await _scenario_engine_unavailable(db_engine, ids)
        snapshot["silent_engine"] = await _scenario_engine_yields_nothing(db_engine, ids)
        snapshot["draft_rules"] = await _scenario_draft_settlement_rules(db_engine, ids)
        snapshot["idempotent"] = await _scenario_idempotent_submit(db_engine, ids)
        return snapshot
    finally:
        uid = cleanup.get("user_id")
        pid = cleanup.get("project_id")
        stmts: list[tuple[str, dict[str, Any]]] = []
        if uid:
            stmts += [
                (
                    "DELETE FROM ai_chat_tool_calls WHERE run_id IN "
                    "(SELECT id FROM ai_chat_runs WHERE actor_id = :u)",
                    {"u": uid},
                ),
                (
                    "DELETE FROM ai_chat_message WHERE session_id IN "
                    "(SELECT id FROM ai_chat_session WHERE user_id = :u)",
                    {"u": uid},
                ),
                ("DELETE FROM ai_chat_runs WHERE actor_id = :u", {"u": uid}),
                ("DELETE FROM ai_chat_session WHERE user_id = :u", {"u": uid}),
            ]
        if pid:
            stmts += [
                ("DELETE FROM disclosure_notes WHERE project_id = :p", {"p": pid}),
                ("DELETE FROM project_users WHERE project_id = :p", {"p": pid}),
            ]
        if uid:
            stmts.append(
                (
                    "DELETE FROM wp_access_security_outbox WHERE actor_user_id = :u",
                    {"u": uid},
                )
            )
        if pid:
            stmts.append(("DELETE FROM projects WHERE id = :p", {"p": pid}))
        if uid:
            stmts.append(("DELETE FROM users WHERE id = :u", {"u": uid}))

        # 🔴 每条一个独立事务：一个事务里全清时任一步失败会把前面的清理一起回滚。
        for sql, params in stmts:
            try:
                async with db_engine.begin() as conn:
                    await conn.execute(sa.text(sql), params)
            except Exception as exc:  # noqa: BLE001
                print(f"[cleanup] {sql[:60]}… 失败: {type(exc).__name__}: {exc}")

        leftovers: dict[str, int] = {}
        try:
            async with db_engine.begin() as conn:
                for table, col, val in (
                    ("ai_chat_session", "user_id", uid),
                    ("ai_chat_runs", "actor_id", uid),
                    ("disclosure_notes", "project_id", pid),
                    ("users", "id", uid),
                    ("projects", "id", pid),
                ):
                    if val is None:
                        continue
                    leftovers[table] = (
                        await conn.execute(
                            sa.text(f"SELECT count(*) FROM {table} WHERE {col} = :v"),
                            {"v": val},
                        )
                    ).scalar_one()
        except Exception as exc:  # noqa: BLE001
            print(f"[cleanup] 复核失败: {type(exc).__name__}: {exc}")
        if any(leftovers.values()):
            print(f"[cleanup] ⚠️ 仍有残留（需人工清理）: {leftovers}")
        await db_engine.dispose()


@pytest.fixture(scope="module")
def coordinated() -> dict[str, Any]:
    if not IS_PG:
        pytest.skip("need PostgreSQL (协调器执行链路)")
    return asyncio.run(_collect())


# ===========================================================================
# 断言：成功链路与 Req 4.12
# ===========================================================================


@needs_pg
class TestHappyPathAndNoRowPerToken:
    """**Validates: Requirements 4.1, 4.4, 4.12**"""

    def test_run_completes_and_publishes_monotonic_events(self, coordinated):
        h = coordinated["happy"]
        assert h["status"] == ChatRunStatus.done.value, h["row"]
        assert h["event_types"][0] == ChatEventType.run_started.value
        assert h["event_types"][-1] == ChatEventType.done.value
        assert h["event_seqs"] == sorted(h["event_seqs"]), "event ID 非单调"
        assert len(set(h["event_seqs"])) == len(h["event_seqs"]), "event ID 有重复"
        assert h["delta_event_count"] == h["expected_deltas"], (
            f"delta 事件数 {h['delta_event_count']} != {h['expected_deltas']}"
        )

    def test_two_hundred_deltas_do_not_create_two_hundred_message_rows(self, coordinated):
        """Req 4.12：``delta`` 走事件流，数据库只保留 run/message 摘要。

        判据是**真实行数**：200 个 delta 之后该 run 名下的 assistant 消息恰好 1 行
        （草稿被原地提升为 completed），user 消息 1 行。若实现改成"每个节流窗口 append
        一行"或"逐 token 写行"，这里立刻变红。
        """
        h = coordinated["happy"]
        assert len(h["assistant_rows"]) == 1, (
            f"200 个 delta 产生了 {len(h['assistant_rows'])} 行 assistant 消息"
        )
        assert h["assistant_rows"][0]["status"] == ChatMessageStatus.completed.value
        assert len(h["row"]["messages"]) == 2, (
            f"该 run 的消息行数应为 2（user+assistant），实际 {len(h['row']['messages'])}"
        )
        assert h["row"]["latency_ms"] is not None, "成功终态未记录 latency"

    def test_delta_and_done_share_one_server_issued_message_id(self, coordinated):
        """全部 delta 与 done 绑定**同一条**服务端消息（Req 4.4）。

        若定稿另插一行、message_id 变了，前端手里的流式消息永远等不到自己的 ``done``。
        """
        h = coordinated["happy"]
        assert len(h["delta_message_ids"]) == 1, (
            f"delta 绑定了多个 message_id：{h['delta_message_ids']}"
        )
        assert h["done_message_id"] == h["delta_message_ids"][0], (
            f"done 的 message_id 与 delta 不一致：{h['done_message_id']}"
        )

    def test_lease_is_released_after_terminal(self, coordinated):
        assert coordinated["happy"]["row"]["lease_owner"] is None, "终态后租约未释放"

    def test_idempotent_replay_is_not_enqueued(self, coordinated):
        i = coordinated["idempotent"]
        assert i["same_run"] is True
        assert i["first_accepted"] is True
        assert i["replay_accepted"] is False, "幂等命中的 run 又被入队（会重复调用 engine）"


# ===========================================================================
# 断言：有界队列与 typed quota（Req 13.6）
# ===========================================================================


@needs_pg
class TestBoundedQueueQuota:
    """**Validates: Requirements 4.1, 13.6**"""

    def test_queue_full_raises_typed_quota_with_retry_after(self, coordinated):
        q = coordinated["quota"]
        assert q["raised"] is True, "队列满时未抛出 typed quota error（无界堆积）"
        payload = q["payload"]
        assert {"retry_after", "remaining", "reset"} <= set(payload), payload
        assert payload["code"] == ChatErrorCode.rate_limited.value
        assert re.search(r"[\u4e00-\u9fff]", payload["message"]), payload["message"]
        assert q["retry_after"] >= 1

    def test_over_quota_run_ends_as_typed_error_with_quota_event(self, coordinated):
        """超限的 run 走**同一条**终态路径落 ``error/rate_limited``，并先发 ``quota`` 事件。"""
        q = coordinated["quota"]
        assert ChatEventType.quota.value in q["third_event_types"], q["third_event_types"]
        assert q["third_status"] == ChatRunStatus.error.value
        assert q["third_error_code"] == ChatErrorCode.rate_limited.value
        assert q["third_assistant_rows"] == 0, "被限流的 run 竟写了 assistant 消息"
        assert {"retry_after", "remaining", "reset"} <= set(q["quota_payload_keys"]), (
            q["quota_payload_keys"]
        )

    def test_in_flight_run_still_finishes(self, coordinated):
        """反假绿：限流不能把正在跑的 run 一起搞死。"""
        assert coordinated["quota"]["first_status"] == ChatRunStatus.done.value


# ===========================================================================
# 断言：一个 run 恰好一个 executor
# ===========================================================================


@needs_pg
class TestExactlyOneExecutor:
    """**Validates: Requirements 4.1, 4.5**（Design 第 2 步）"""

    def test_two_owners_racing_one_run_yield_one_execution(self, coordinated):
        lease = coordinated["lease"]
        assert lease["engines_started"] == 1, (
            f"{lease['engines_started']} 个 engine 同时执行了同一个 run"
        )
        assert lease["terminal_event_count"] == 1, lease
        assert lease["assistant_rows"] == 1, (
            f"同一个 run 产生了 {lease['assistant_rows']} 条 assistant 消息"
        )
        assert lease["status"] == ChatRunStatus.done.value
        assert lease["lease_owner"] is None

    def test_lease_itself_grants_to_exactly_one_owner(self, coordinated):
        """直接判租约：并发只有一个 grant，未过期时第三方被拒，过期后可接管。

        🔴 上一条（"engine 只起一次"）**不足以**守住租约：``mark_running`` 的状态 CAS
        会替它挡住第二个 executor，于是租约被放宽甚至完全无视时上一条依然绿
        （变异检验实测两条 GREEN）。租约真正独占负责的是"取得执行权之前的工作"
        与"过期接管"，所以必须单独判。
        """
        iso = coordinated["lease_isolation"]
        assert len(iso["concurrent_winners"]) == 1, (
            f"并发 acquire 出现 {len(iso['concurrent_winners'])} 个持有者："
            f"{iso['concurrent_winners']}"
        )
        assert iso["third_refused"] is True, (
            "租约未过期时第三方竟拿到了执行权（过期判据被放宽成存在判据？）"
        )
        assert iso["takeover_after_expiry"] is True, (
            "租约过期后无法接管 ⇒ 崩溃留下的 run 永远没人捡（反假绿控制）"
        )

    def test_coordinator_refuses_to_execute_without_the_lease(self, coordinated):
        """租约被他人持有时协调器放弃执行：engine 不起、run 保持 queued。"""
        iso = coordinated["lease_isolation"]
        assert iso["blocked_engine_started"] is False, (
            "无租约仍然执行 ⇒ 租约退化成一句没人看的日志"
        )
        assert iso["blocked_engine_yielded"] == 0
        assert iso["status_after_blocked_attempt"] == ChatRunStatus.queued.value, (
            f"无租约的执行尝试改动了 run 状态：{iso['status_after_blocked_attempt']}"
        )


# ===========================================================================
# 断言：Property 7（终态恰好一个）
# ===========================================================================


@needs_pg
class TestSingleTerminalThroughCoordinator:
    """**Validates: Requirements 4.5**（Property 7）"""

    def test_engine_error_then_done_yields_only_error(self, coordinated):
        e = coordinated["engine_error"]
        assert e["status"] == ChatRunStatus.error.value
        assert e["error_code"] == ChatErrorCode.engine_unavailable.value
        assert e["terminal_event_count"] == 1, e["event_types"]
        assert e["done_count"] == 0, "error 之后仍签发了 done"
        assert e["completed_assistant"] == 0, (
            "error 终态下存在 completed assistant 消息（Property 7 明令不存在）"
        )
        assert e["assistant_statuses"] == [ChatMessageStatus.failed.value], (
            f"部分正文的草稿状态应结算为 failed：{e['assistant_statuses']}"
        )

    def test_external_terminal_stops_engine_events(self, coordinated):
        """外部抢先落终态后：不再有 delta、不再有 done、无 completed 消息。"""
        r = coordinated["race"]
        assert r["status"] == ChatRunStatus.error.value
        assert r["error_code"] == ChatErrorCode.rate_limited.value
        assert r["terminal_event_count"] == 1, r
        assert r["done_count"] == 0
        assert r["completed_assistant"] == 0
        assert r["delta_after_terminal"] == 0, (
            f"终态之后仍签发了 {r['delta_after_terminal']} 条 delta"
        )


# ===========================================================================
# 断言：Property 8（取消传播）
# ===========================================================================


@needs_pg
class TestCancelPropagationEndToEnd:
    """**Validates: Requirements 4.7**（Property 8）"""

    def test_cancel_reaches_engine_and_child_and_freezes_tool_calls(self, coordinated):
        c = coordinated["cancel"]
        assert c["status"] == ChatRunStatus.cancelled.value, c
        assert c["stopped_marks"] == ["child-agent", "engine"], (
            f"取消未传播到全部后代：{c['stopped_marks']}"
        )
        assert c["tools_at_cancel"] >= 2, c
        assert c["tools_settled"] == c["tools_after_terminal"], (
            f"取消确认后工具调用仍在增长："
            f"{c['tools_after_terminal']} → {c['tools_settled']}"
        )
        # 脚本里有 60 次工具调用；取消若没传播，计数会一路跑到 60。
        assert c["tools_settled"] < c["total_tools_in_script"], (
            f"取消未生效，工具调用跑到了 {c['tools_settled']}/"
            f"{c['total_tools_in_script']}"
        )
        assert c["tools_settled"] - c["tools_at_cancel"] <= 2, (
            f"取消后工具调用又增长了 {c['tools_settled'] - c['tools_at_cancel']} 次"
        )
        assert c["coordinator_tool_calls"] >= 2

    def test_cancel_produces_exactly_one_terminal_and_no_completed_message(self, coordinated):
        c = coordinated["cancel"]
        assert c["terminal_event_count"] == 1, c["terminal_types"]
        assert c["terminal_types"] == [ChatEventType.cancelled.value]
        assert c["done_count"] == 0
        assert c["completed_assistant"] == 0
        assert c["cancel_requested_at_set"] is True, "取消未记录 cancel_requested_at"
        assert c["error_code"] == ChatErrorCode.run_cancelled.value

    def test_cancel_is_idempotent_and_terminal_safe(self, coordinated):
        """重复取消不产生第二个终态；已终态时如实回报"无需取消"。"""
        c = coordinated["cancel"]
        assert c["outcome"]["cancel_requested"] is True
        assert c["second_outcome"]["already_terminal"] is True
        assert c["second_outcome"]["cancel_requested"] is False
        assert re.search(r"[\u4e00-\u9fff]", c["second_outcome"]["message"])

    def test_uncooperative_engine_is_still_stopped_by_the_coordinator(self, coordinated):
        """engine 不检查取消时，协调器自己必须停止签发并落取消终态。

        **Validates: Requirements 4.7**（Property 8）

        🔴 用"会检查取消的替身"测出来的绿是假绿：协调器主循环里的取消检查被删掉后
        依然全绿（变异检验实测）。真实 engine（DSH 的工具循环、第三方 SDK）不保证每步
        都查，所以这条不变量必须由协调器独立成立。
        """
        s = coordinated["stubborn_cancel"]
        assert s["status"] == ChatRunStatus.cancelled.value, s
        assert s["terminal_count"] == 1, s["terminal_types"]
        assert s["terminal_types"] == [ChatEventType.cancelled.value]
        assert s["events_after_settle"] == s["events_at_terminal"], (
            f"取消落定后事件仍在增加：{s['events_at_terminal']} → "
            f"{s['events_after_settle']}"
        )
        assert s["tool_started_events"] < s["total_tools_in_script"], (
            f"取消后仍签发了全部 {s['tool_started_events']} 条 tool_started"
        )
        assert s["completed_assistant"] == 0

    def test_remote_cancel_marker_alone_blocks_execution(self, coordinated):
        """只有跨进程取消标记（数据库状态还没改）也必须拦住执行。

        **Validates: Requirements 4.7**
        """
        m = coordinated["remote_marker"]
        assert m["engine_started"] is False, (
            "已被远端标记取消的 run 仍被完整执行（Req 4.7 要求排队任务也收到取消）"
        )
        assert m["engine_yielded"] == 0
        assert m["status"] == ChatRunStatus.cancelled.value, m
        assert m["error_code"] == ChatErrorCode.run_cancelled.value
        assert m["assistant_rows"] == 0
        assert m["terminal_types"] == [ChatEventType.cancelled.value]

    def test_cross_worker_cancel_event_is_not_swallowed_by_dedup(self, coordinated):
        """另一个 worker 签发的 cancelled 事件必须真的到达客户端。

        **Validates: Requirements 4.4, 4.7**

        判据是**序号严格大于已发布的最大序号** —— 只断言"库里状态是 cancelled"抓不到
        这个缺陷：状态确实变了，丢掉的只是那条事件，用户看到的就是"点了取消还在转圈"。
        """
        x = coordinated["cross_worker"]
        assert x["db_status"] == ChatRunStatus.cancelled.value, x
        assert x["terminal_count"] == 1, (
            f"带外签发的终态事件没进流（序号撞号后被去重吃掉）：{x}"
        )
        assert x["terminal_type"] == ChatEventType.cancelled.value
        assert x["terminal_seq"] > x["published_max_seq"], (
            f"终态事件序号 {x['terminal_seq']} 未超过已发布的 "
            f"{x['published_max_seq']} ⇒ 与旧事件撞号"
        )
        assert len(set(x["all_seqs"])) == len(x["all_seqs"]), (
            f"事件序号有重复：{x['all_seqs']}"
        )
        assert x["outcome"]["cancel_requested"] is True

    def test_queued_run_cancel_never_starts_engine(self, coordinated):
        q = coordinated["cancel_queued"]
        assert q["waiting_status"] == ChatRunStatus.cancelled.value, q
        assert q["queued_engine_yielded"] == 0, (
            f"排队中被取消的 run 仍产出了 {q['queued_engine_yielded']} 个事件"
        )
        assert q["assistant_rows"] == 0
        assert q["error_code"] == ChatErrorCode.run_cancelled.value
        assert q["first_status"] == ChatRunStatus.done.value, "取消排队项影响了在跑的 run"


# ===========================================================================
# 断言：断流重连 与 drain
# ===========================================================================


@needs_pg
class TestReconnectAndDrain:
    """**Validates: Requirements 4.1, 4.8, 4.9**（Property 9 后半）"""

    def test_reconnect_replays_tail_without_reinvoking_engine(self, coordinated):
        r = coordinated["reconnect"]
        assert r["engine_invocations"] == 1, "重连重新调用了 engine（Req 4.1 明令禁止）"
        assert r["union_matches"] is True, (
            f"续传拼接后与完整序列不一致：seen={r['seen_ids']} tail={r['tail_ids']}"
        )
        assert not set(r["seen_ids"]) & set(r["tail_ids"]), "续传重复下发了已收事件"
        assert r["terminal_in_tail"] is True, "续传尾段缺终态事件（客户端会永远等）"

    def test_drain_emits_identifiable_abort_frame_without_id(self, coordinated):
        d = coordinated["drain"]
        assert d["has_draining"] is True, d["event_names"]
        assert d["last_event_id"] == d["expected_last_event_id"], (
            "drain 帧推进了 Last-Event-ID —— 重连会丢事件"
        )
        assert d["registry_active"] == 0, "drain 后仍有活跃 SSE 连接登记"
        assert d["heartbeats"] >= 1, "空转期间没有心跳（连接会被代理掐断）"


# ===========================================================================
# 断言：启动恢复
# ===========================================================================


@needs_pg
class TestStartupRecovery:
    """**Validates: Requirements 4.9**（Design 第 7 步）"""

    def test_side_effect_free_run_is_requeued_and_actually_reruns(self, coordinated):
        rec = coordinated["recovery"]
        assert rec["fresh_id"] in rec["requeued_ids"], rec["report"]
        assert rec["rows"]["fresh"]["retry_count"] == 1, rec["rows"]["fresh"]
        assert rec["rows"]["fresh"]["lease_owner"] is None
        assert rec["fresh_id"] in rec["redispatched"], "重排后没有真的重新执行"
        assert rec["rerun_status"] == ChatRunStatus.done.value
        assert rec["rerun_completed_assistant"] == 1
        assert rec["rerun_event_seqs"] == sorted(rec["rerun_event_seqs"]), (
            "重排后事件序号回退/乱序 —— 续传会丢事件"
        )
        assert len(set(rec["rerun_event_seqs"])) == len(rec["rerun_event_seqs"]), (
            f"重排后事件序号撞号：{rec['rerun_event_seqs']}"
        )

    def test_run_with_external_side_effects_is_not_requeued(self, coordinated):
        """有工具调用记录 ⇒ 重跑可能重复产生外部影响 ⇒ 只能标中断。"""
        rec = coordinated["recovery"]
        assert rec["with_tool_id"] not in rec["requeued_ids"], rec["report"]
        assert rec["rows"]["with_tool"]["status"] == ChatRunStatus.error.value
        assert (
            rec["rows"]["with_tool"]["error_code"] == ChatErrorCode.run_interrupted.value
        )
        assert rec["rows"]["with_tool"]["retry_count"] == 0

    def test_retry_limit_is_enforced(self, coordinated):
        rec = coordinated["recovery"]
        assert rec["exhausted_id"] not in rec["requeued_ids"], rec["report"]
        assert rec["rows"]["exhausted"]["status"] == ChatRunStatus.error.value
        assert (
            rec["rows"]["exhausted"]["error_code"] == ChatErrorCode.run_interrupted.value
        )

    def test_report_counts_are_consistent(self, coordinated):
        rec = coordinated["recovery"]
        report = rec["report"]
        assert report["scanned"] >= 3, report
        assert len(report["requeued"]) + len(report["failed"]) + len(
            report["skipped"]
        ) == report["scanned"], report


# ===========================================================================
# 断言：engine 不可用（Req 10.5）
# ===========================================================================


@needs_pg
class TestEngineUnavailable:
    """**Validates: Requirements 4.5**（并覆盖 Req 10.5：不静默回落）"""

    def test_broken_engine_provider_yields_typed_error(self, coordinated):
        n = coordinated["no_engine"]
        assert n["status"] == ChatRunStatus.error.value
        assert n["error_code"] == ChatErrorCode.engine_unavailable.value
        assert n["terminal_types"] == [ChatEventType.error.value]
        assert n["assistant_rows"] == 0, "engine 不可用却写了 assistant 消息（假成功）"
        assert n["error_message_is_chinese"] is True

    def test_silent_engine_does_not_produce_success(self, coordinated):
        """engine 一个字都没产出 ⇒ typed error，**不得**写空的成功回复。

        **Validates: Requirements 4.5**（Req 12.9：fail-soft 空结果不得产生 success 终态）

        🔴 补这条是因为"provider 抛错"那条判据走的是更早的分支，engine 静默返回这条
        路径没有任何判据覆盖 —— 把"无正文也按成功定稿"写进去也照样全绿（实测 GREEN）。
        """
        s = coordinated["silent_engine"]
        assert s["status"] == ChatRunStatus.error.value, s
        assert s["error_code"] == ChatErrorCode.engine_unavailable.value
        assert s["done_count"] == 0, "空回复竟发出了 done"
        assert s["terminal_types"] == [ChatEventType.error.value]
        assert s["assistant_rows"] == 0, "空回复竟写了一条 assistant 消息"


@needs_pg
class TestDraftSettlementRules:
    """草稿结算的两条硬规则（终态写入路径唯一性的组成部分）。

    **Validates: Requirements 4.5**（Property 7）
    """

    def test_settle_refuses_to_write_completed(self, coordinated):
        """``settle_assistant_draft`` 拒绝 ``completed`` —— 否则多出第二条终态写入路径。"""
        d = coordinated["draft_rules"]
        assert d["refused_completed"] is True, (
            "草稿结算竟允许写 completed ⇒ compare-and-set 不再是唯一定稿路径"
        )
        assert d["settled_ok"] is True, "合法结算（cancelled）反而失败（反假绿控制）"

    def test_promotion_never_resurrects_a_settled_draft(self, coordinated):
        """已结算的草稿不得被后到的 ``finish_success`` 复活成 completed。

        这正是 ``_promote_draft`` 的 ``status == 'draft'`` 谓词在守的东西：去掉它，
        一条已经标为 cancelled 的部分正文会被改写成"成功回复"。
        """
        d = coordinated["draft_rules"]
        assert d["finish_success_won"] is True, "CAS 未胜出，本判据前提不成立"
        assert d["settled_row_status"] == ChatMessageStatus.cancelled.value, (
            f"已结算草稿被复活成 {d['settled_row_status']}"
        )
        assert d["new_message_is_distinct"] is True, (
            "定稿没有另起一行 ⇒ 说明复用了那条已结算的草稿"
        )
        assert d["completed_count"] == 1, (
            f"completed assistant 消息应恰好 1 条，实际 {d['completed_count']}"
        )


# ===========================================================================
# 路由契约（events / cancel）
# ===========================================================================


class TestRouteContract:
    """**Validates: Requirements 4.1, 4.7**"""

    def test_events_route_is_derived_from_the_url_template(self):
        """真实注册的路径 == 创建响应里回给客户端的 ``events_url`` 模板。

        Task 4 的守卫只断言模板与 design 一致；这里补上"模板 ↔ 真实路由"那一边 ——
        两侧分别写字面量时，前端拿到的会是一个 404 地址。
        """
        paths = {r.path for r in route_mod.router.routes if getattr(r, "path", None)}
        assert RUN_EVENTS_URL_TEMPLATE in paths, sorted(paths)
        assert route_mod.RUN_EVENTS_ROUTE == RUN_EVENTS_URL_TEMPLATE.removeprefix(
            "/api/ai-chat"
        )
        assert "/api/ai-chat" + route_mod.RUN_CANCEL_ROUTE in paths, sorted(paths)

    def test_events_route_uses_sse_capable_auth(self):
        """事件流用 SSE 专用鉴权（``EventSource`` 无法设置 Authorization 头）。"""
        import inspect

        sig = inspect.signature(route_mod.stream_run_events)
        deps = [
            getattr(p.default, "dependency", None)
            for p in sig.parameters.values()
            if p.default is not inspect.Parameter.empty
        ]
        from app.deps import get_current_user_sse

        assert get_current_user_sse in deps, "事件流未使用 SSE 鉴权依赖"
        assert "last_event_id" in sig.parameters
        assert any(
            getattr(p.default, "alias", None) == "Last-Event-ID"
            for p in sig.parameters.values()
            if p.default is not inspect.Parameter.empty
        ), "未接收 Last-Event-ID 头（浏览器自动重连只发头不发 query）"


@needs_pg
def test_events_route_denies_other_users_run():
    """别人的 run 不可订阅（不可枚举 404）—— 事件流里有模型正文与上下文清单。

    **Validates: Requirements 4.1**（Req 2.1/2.5 在事件流上的复用）

    自建提交型夹具：模块级 ``coordinated`` 的行在快照取完后已被清理，不能借用。
    """
    from app.services.wp_visibility.denial import ExternalNotFound

    async def scenario() -> dict[str, Any]:
        db_engine = create_async_engine(app_settings.DATABASE_URL)
        cleanup: dict[str, Any] = {}
        try:
            ids = await _make_committed_fixture(db_engine)
            cleanup.update(ids)
            async with AsyncSession(bind=db_engine) as db:
                outsider = User(
                    username=f"ai_t5_out_{uuid.uuid4().hex[:8]}",
                    email=f"{uuid.uuid4().hex[:12]}@ai-task5-out.example",
                    hashed_password="x",
                    role=UserRole("auditor"),
                    is_active=True,
                )
                db.add(outsider)
                await db.flush()
                cleanup["outsider_id"] = outsider.id
                await db.commit()
            creation = await _create_run(db_engine, ids)

            results: dict[str, Any] = {}
            async with AsyncSession(bind=db_engine) as db:
                try:
                    await route_mod._load_owned_run(
                        db, creation.run_id, cleanup["outsider_id"]
                    )
                    results["denied"] = False
                except ExternalNotFound:
                    results["denied"] = True
            async with AsyncSession(bind=db_engine) as db:
                status, *_ = await route_mod._load_owned_run(
                    db, creation.run_id, ids["user_id"]
                )
                results["owner_ok"] = status is ChatRunStatus.queued
            async with AsyncSession(bind=db_engine) as db:
                try:
                    await route_mod._load_owned_run(db, uuid.uuid4(), ids["user_id"])
                    results["missing_denied"] = False
                except ExternalNotFound:
                    results["missing_denied"] = True
            return results
        finally:
            uid = cleanup.get("user_id")
            pid = cleanup.get("project_id")
            oid = cleanup.get("outsider_id")
            stmts: list[tuple[str, dict[str, Any]]] = []
            if uid:
                stmts += [
                    (
                        "DELETE FROM ai_chat_message WHERE session_id IN "
                        "(SELECT id FROM ai_chat_session WHERE user_id = :u)",
                        {"u": uid},
                    ),
                    ("DELETE FROM ai_chat_runs WHERE actor_id = :u", {"u": uid}),
                    ("DELETE FROM ai_chat_session WHERE user_id = :u", {"u": uid}),
                ]
            if pid:
                stmts += [
                    ("DELETE FROM disclosure_notes WHERE project_id = :p", {"p": pid}),
                    ("DELETE FROM project_users WHERE project_id = :p", {"p": pid}),
                    ("DELETE FROM projects WHERE id = :p", {"p": pid}),
                ]
            for key in ("user_id", "outsider_id"):
                val = cleanup.get(key)
                if val:
                    stmts.append(("DELETE FROM users WHERE id = :u", {"u": val}))
            _ = oid
            for sql, params in stmts:
                try:
                    async with db_engine.begin() as conn:
                        await conn.execute(sa.text(sql), params)
                except Exception as exc:  # noqa: BLE001
                    print(f"[cleanup] {sql[:60]}… 失败: {type(exc).__name__}: {exc}")
            await db_engine.dispose()

    got = asyncio.run(scenario())
    assert got["denied"] is True, "别的用户竟能订阅这个 run 的事件流"
    assert got["owner_ok"] is True, "run 主人反而被拒（反假绿控制）"
    assert got["missing_denied"] is True, "不存在的 run 未按不可枚举语义拒绝"


def test_redis_keys_are_namespaced_per_run():
    """三个 Redis key 各自按 run 命名空间隔离（不同 run 不互相干扰）。"""
    a, b = uuid.uuid4(), uuid.uuid4()
    assert stream_key(a) == f"ai-chat:run:{a}"
    assert lease_key(a).startswith(f"ai-chat:run:{a}")
    assert cancel_key(a).startswith(f"ai-chat:run:{a}")
    for fn in (stream_key, lease_key, cancel_key):
        assert fn(a) != fn(b)


def test_sequencer_seed_only_moves_forward():
    """``seed`` 只前进不后退（重排接手时不撞号，也不被乱序调用拉回去）。"""
    seq = RunEventSequencer()
    run_id = uuid.uuid4()
    seq.seed(run_id, 40)
    assert seq.next(run_id) == 41
    seq.seed(run_id, 5)
    assert seq.next(run_id) == 42, "seed 把计数拉回去了 ⇒ 事件 ID 会撞号"
    seq.seed(run_id, 0)
    assert seq.next(run_id) == 43


def test_capabilities_snapshot_is_available_for_execution_context():
    """执行上下文携带 capability 快照（engine 与审计都从这里读，不各自假设）。"""
    assert "capabilities" in RunExecution.__dataclass_fields__
    assert capabilities_for(ChatEngineName.native).local_only is True


# ===========================================================================
# engine 接缝：默认 provider 与 Task 6 的 engine 模块真实对接
# ===========================================================================


def test_default_engine_provider_really_binds_to_the_engine_module():
    """默认 provider **真的构造出** engine 实例，而不是"符号名存在"。

    **Validates: Requirements 4.5**（并守住 Req 10.5 的反面）

    🔴 这条判据存在的理由是 fail-open：``_resolve_engine`` 把任何异常吞成
    ``engine_unavailable``（这是 Req 10.5 要求的语义 —— 不静默回落到别的链路），
    于是"函数名/签名对不上"会表现为**每个 run 都以 typed error 结束**而不是崩溃。
    只 grep ``build_engine`` 这个名字抓不到签名漂移；这里真调一次并断言拿到的对象
    满足协调器唯一需要的协议。

    Task 6 尚未落地 engine 模块时自动跳过（并发开发期的合法状态）。
    """
    from app.services.ai_chat.run_coordinator import (
        SupportsChatRun,
        _default_engine_provider,
    )

    try:
        import app.services.ai_chat.engine  # noqa: F401
    except ImportError:
        pytest.skip("Task 6 的 engine 模块尚未就绪")

    engine_obj = _default_engine_provider(None, None)
    assert engine_obj is not None, (
        "engine 模块存在却构造不出 engine ⇒ 所有 run 都会以 engine_unavailable 结束"
    )
    assert isinstance(engine_obj, SupportsChatRun), (
        f"{type(engine_obj).__name__} 不满足协调器消费的 run(request, cancel) 协议"
    )


def test_engine_request_coercion_accepts_a_real_run_execution():
    """Task 6 的 ``AuthorizedChatRunRequest.coerce`` 能吃下**真实** ``RunExecution``。

    两个模块互相不 import 对方的类型（会循环），全靠字段同名同义。因此这条契约必须
    由**真实对象**验证：我这边改个字段名，engine 侧会在第一次 run 时 AttributeError，
    再被 coordinator 的 ``except Exception`` 吞成 engine_unavailable（假绿的典型形态）。
    """
    try:
        from app.services.ai_chat.engine import AuthorizedChatRunRequest
    except ImportError:
        pytest.skip("Task 6 的 engine 模块尚未就绪")

    from app.services.ai_chat.host_context import AuthorizedHostContext

    host = AuthorizedHostContext(
        principal_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        year=FIXTURE_AUDIT_YEAR,
        resource_type=HostType.note,
        resource_id=str(uuid.uuid4()),
        display_label="货币资金 · 附注",
        permission_binding="project",
        allowed_actions=frozenset({"read"}),
    )
    execution = RunExecution(
        run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        actor_id=host.principal_id,
        host=host,
        request=ChatRunRequest.model_validate(
            {
                "host": {"type": HostType.note.value, "id": host.resource_id},
                "query": "这段附注披露是否完整？",
                "idempotency_key": str(uuid.uuid4()),
            }
        ),
        engine=ChatEngineName.native,
        capabilities=capabilities_for(ChatEngineName.native),
    )
    coerced = AuthorizedChatRunRequest.coerce(execution)
    assert coerced.run_id == execution.run_id
    assert coerced.session_id == execution.session_id
    assert coerced.request_id == execution.request_id
    assert coerced.host is host
    assert coerced.query == execution.request.query
    assert coerced.engine is ChatEngineName.native
