"""统一 ``ChatEngine`` 契约 · engine 选择（Task 6）

Feature: dsh-agent-panel-integration
Requirements:
  - 10.1：engine 只由**服务端配置 + 服务端 feature flag**决定，默认 ``native``；
    客户端不能通过请求体覆盖（``ChatRunRequest`` 里根本没有 engine 字段）。
    :func:`resolve_engine` 在 Task 4 的 :func:`resolve_engine_name` 之上叠加
    experimental flag 与项目 allowlist。
  - 10.2：engine 消费统一 :class:`AuthorizedChatRunRequest` 并产出统一
    :class:`~app.services.ai_chat.run_contract.ChatEvent`，而不是裸字符串流；
    native 与 DSH 遵守同一 terminal / cancel / usage / audit 语义。
  - 10.3：每个 engine 发布 capability manifest —— 且必须**直接返回**
    :data:`~app.services.ai_chat.run_contract.CAPABILITIES_BY_ENGINE` 的表项
    （见下"为什么 capabilities 不许各写一份"）。
  - 10.5：DSH 侧任一步失败以 ``engine_unavailable`` 结束，**不**静默回落 native
    后返回成功内容（Task 28 实现；本模块只提供 typed 失败通道）。
  - 12.9 / Property 33：下游故障不产生假成功 —— 本模块把"失败"表达为**抛异常**
    （:class:`EngineFailure`），而不是返回一个"没内容的成功"。
Design: "Components and Interfaces → 12. Engine Contract"
Properties: 7（Run 唯一终态）、24（引擎能力与 UI 一致）、33（下游故障不产生假成功）

## 边界：engine 不碰持久化，也不发终态事件

Task 4 的 :class:`~app.services.ai_chat.run_service.ChatRunService` 已经拥有
``finish_success`` / ``finish_error`` / ``finish_cancelled`` 的数据库
compare-and-set，并把"成功终态"与"completed assistant 消息"放在同一事务里。
因此 engine 的职责边界被刻意收窄成：

* **只产出非终态事件**（``context_ready`` / ``citation`` / ``delta`` / ``quota`` /
  ``tool_*``）—— :func:`assert_non_terminal` 在签发处硬拦，engine 从**结构上**
  就无法发出 ``done`` / ``error`` / ``cancelled``；
* **不写任何消息行**（engine 模块里没有 ``append_message`` 之类的调用）；
* 成功时把正文 / model / usage / latency 记到 :class:`EngineOutcome`，由调用方
  （Task 5 coordinator）交给 ``finish_success``；
* 失败时**抛** :class:`EngineFailure`（带稳定 error code），由调用方交给
  ``finish_error``；取消抛 :class:`EngineCancelled`，交给 ``finish_cancelled``。

这样 Property 7（终态恰好一个）与 Property 33（不产生 success terminal）在 engine
层是**结构性**成立的，而不是靠"记得别发 done"这种自觉。

🔴 为什么失败一定是抛异常而不是返回：``except Exception`` 把接线错误吞成 WARNING
是本仓库最贵的失败模式。若 engine 把失败写进 outcome 后正常 ``return``，任何忘记检查
``outcome.failure`` 的调用方都会把它当成"空回复的成功"落库。抛异常让漏检必然炸。

## 为什么 capabilities 不许各写一份

Task 4 的 ``CAPABILITIES_BY_ENGINE`` 已经是 capability manifest 的单一真源，并且
留下了明确契约：``ChatEngine.capabilities()`` 必须返回与该表**相等**的 manifest 或
直接返回表项。两处独立手写就是"声明支持而实际不支持"的标准形态（Req 10.4 的
前端禁用逻辑会据此放开一个后端根本不支持的入口）。:func:`capabilities_of` 是
本模块提供的唯一实现方式，两个 engine 都用它。

## Task 5 的注入接缝

Task 5 的 ``ChatRunCoordinator`` 通过三个接缝消费 engine，全部是**构造/调用参数**，
不需要改本模块：

1. ``engine = build_engine(engine_name, db=db)``（或直接构造 ``NativeEngine``）；
2. ``cancel``：任意满足 :class:`CancelSignal` 的对象（Redis cancel 标志、
   ``asyncio.Event`` 包装、或 :data:`NEVER_CANCELLED`）；
3. ``events``：任意满足 :class:`EventIdSource` 的对象。Task 4 的
   ``RunEventSequencer`` 已经结构性满足它（守卫用 ``isinstance`` 断言），
   Task 5 换成 Redis Stream ID 时也只要满足这两个方法。

**本模块刻意不 import ``run_service``** —— ``run_service`` 需要 import
:func:`resolve_engine`，反向再 import 就是循环。所以 :class:`EventIdSource` 只声明
协议，默认实现 :class:`SequentialEventIds` 与 ``RunEventSequencer`` 语义一致。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from app.models.ai_models import ChatEngineName
from app.services.ai_chat.host_context import AuthorizedHostContext
from app.services.ai_chat.run_contract import (
    TERMINAL_EVENT_TYPES,
    ChatErrorCode,
    ChatEvent,
    ChatEventType,
    EngineCapabilities,
    capabilities_for,
    format_event_id,
    resolve_engine_name,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CancelSignal",
    "is_cancel_requested",
    "NEVER_CANCELLED",
    "EventCancelSignal",
    "EventIdSource",
    "SequentialEventIds",
    "EngineFailure",
    "EngineCancelled",
    "EngineOutcome",
    "EngineStream",
    "AuthorizedChatRunRequest",
    "ChatEngine",
    "capabilities_of",
    "assert_non_terminal",
    "build_event",
    "build_terminal_intent",
    "build_engine",
    "drain",
    "resolve_engine",
    "dsh_project_allowlist",
    "ENGINE_GATE_REASON_ZH",
]


# ---------------------------------------------------------------------------
# 取消信号（Task 5 用 Redis 标志实现同一协议）
# ---------------------------------------------------------------------------


@runtime_checkable
class CancelSignal(Protocol):
    """取消信号的 canonical 形态。``async`` 是刻意的：跨进程实现要查 Redis。

    同步实现（``asyncio.Event``）包装成 async 是零成本的；反过来则不行 ——
    若协议是同步的，跨进程实现只能阻塞事件循环或改协议。
    """

    async def is_cancelled(self) -> bool: ...


#: 认不出的取消信号形态时的 fail-closed 说明。
#:
#: 抽成常量是为了让 ``raise`` 落在**单行**上 —— 变异检验要能把这一行整行替换掉来验证
#: 「认不出的形态是否真的被拒绝」；跨行的 raise 被整行替换后是 SyntaxError，
#: pytest 报的是文件级 collection ERROR，判定会落成 WRONG-TEST 而不是 RED（本会话实测）。
_UNKNOWN_CANCEL_SHAPE = (
    "取消信号形态无法识别：{kind} 既没有 is_cancelled 也没有 is_set —— "
    "拒绝在无法感知取消的情况下执行"
)


async def is_cancel_requested(cancel: Any) -> bool:
    """读取取消状态，**同时兼容三种同义形态**。

    🔴 存在的理由是一次真实的接线冲突，不是防御性冗余：Task 5 的
    ``run_coordinator.CancelSignal`` 用 ``is_set``（bool property）表达取消，而本模块的
    canonical 协议用 ``async is_cancelled()``。engine 若只认后者，coordinator 传进来的
    信号会在第一次检查时 ``AttributeError`` —— 被 coordinator 的 ``except Exception``
    吞成 ``engine_unavailable``，表现是"AI 一直不回答但没有任何错误"，
    而 Volar / pytest / 静态检查全绿。所以这里显式接受：

    ==============================  ============================================
    ``async is_cancelled()``        本模块 canonical 形态
    ``is_set`` （bool property）    Task 5 的 ``CancelSignal``
    ``is_set()``（callable）        裸 ``asyncio.Event``
    ==============================  ============================================

    ``None`` 视为"不支持取消"（False）。形态完全不认识时抛 :class:`EngineFailure`
    —— 不能当成"没取消"继续跑（那会让取消请求静默失效，Req 4.7）。
    """
    if cancel is None:
        return False

    probe = getattr(cancel, "is_cancelled", None)
    if probe is not None:
        result = probe()
        if asyncio.iscoroutine(result):
            return bool(await result)
        return bool(result)

    flag = getattr(cancel, "is_set", None)
    if flag is not None:
        if callable(flag):
            return bool(flag())
        return bool(flag)

    detail = _UNKNOWN_CANCEL_SHAPE.format(kind=type(cancel).__name__)
    raise EngineFailure(ChatErrorCode.engine_unavailable, detail)


class _NeverCancelled:
    """恒不取消。用于"本次调用不支持取消"的场景（如同步补偿任务）与守卫基线。"""

    async def is_cancelled(self) -> bool:
        return False

    def __repr__(self) -> str:  # pragma: no cover — 仅调试可读性
        return "NEVER_CANCELLED"


#: 单例：恒不取消。
NEVER_CANCELLED: CancelSignal = _NeverCancelled()


class EventCancelSignal:
    """``asyncio.Event`` 包装。进程内取消（同一 worker 内的 coordinator ↔ engine）。"""

    def __init__(self, event: asyncio.Event | None = None) -> None:
        self._event = event if event is not None else asyncio.Event()

    @property
    def event(self) -> asyncio.Event:
        return self._event

    def cancel(self) -> None:
        self._event.set()

    async def is_cancelled(self) -> bool:
        return self._event.is_set()


# ---------------------------------------------------------------------------
# 事件 ID 来源（Task 5 用 Redis Stream ID 替换）
# ---------------------------------------------------------------------------


@runtime_checkable
class EventIdSource(Protocol):
    """per-run 单调事件序号来源。

    与 Task 4 的 ``RunEventSequencer`` **同形**（守卫用 ``isinstance`` 双向锁死），
    因此 coordinator 可以把自己那一个直接传进来，engine 内不再各自计数 ——
    否则同一 run 的事件序号会被两个计数器交叉签发，``Last-Event-ID`` 续传必错。
    """

    def next(self, run_id: UUID) -> int: ...

    def forget(self, run_id: UUID) -> None: ...


class SequentialEventIds:
    """进程内单调序号（默认实现）。语义与 ``RunEventSequencer`` 一致。

    ``run_started`` 由 Task 4 占用序号 1，故本序列从 2 起。
    """

    #: ``run_started`` 的固定序号（与 ``run_contract.RUN_STARTED_EVENT_SEQ`` 一致）。
    FIRST_ENGINE_SEQ = 2

    def __init__(self) -> None:
        self._seq: dict[UUID, int] = {}

    def next(self, run_id: UUID) -> int:
        nxt = self._seq.get(run_id, self.FIRST_ENGINE_SEQ - 1) + 1
        self._seq[run_id] = nxt
        return nxt

    def forget(self, run_id: UUID) -> None:
        self._seq.pop(run_id, None)


# ---------------------------------------------------------------------------
# 失败通道（Req 12.5 / 12.9）
# ---------------------------------------------------------------------------


class EngineFailure(Exception):
    """engine 执行失败。``code`` 是对外稳定 error code；``detail`` 只进受控日志。

    调用方把它交给 ``ChatRunService.finish_error(error_code=exc.code)``。
    **不要**把 ``detail`` 放进事件负载 —— 内部 exception 细节不返回客户端（Req 12.5）。
    """

    def __init__(self, code: ChatErrorCode, detail: str = "") -> None:
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail


class EngineCancelled(EngineFailure):
    """用户取消。调用方交给 ``ChatRunService.finish_cancelled()``（不是 finish_error）。

    单独一个类型而不是靠比较 code：取消不是故障，审计与指标口径都不同
    （Req 4.7 的 cancel latency vs Req 12.8 的 error rate）。
    """

    def __init__(self, detail: str = "") -> None:
        super().__init__(ChatErrorCode.run_cancelled, detail)


# ---------------------------------------------------------------------------
# 执行结果
# ---------------------------------------------------------------------------


@dataclass
class EngineOutcome:
    """一次 engine 执行的结果快照（由 :class:`EngineStream` 持有，per-run 独立）。

    刻意**不放在 engine 实例上**：engine 是可共享的无状态对象，把结果挂实例上会在
    并发 run 之间串数据（最难复现的一类）。

    成功后调用方用它调 ``finish_success``：

    .. code-block:: python

        stream = engine.run(request, cancel)
        async for event in stream:
            await publish(event)
        out = stream.outcome
        await runs.finish_success(
            session=session, run_id=request.run_id, text=out.text,
            usage=out.usage, latency_ms=out.latency_ms,
            model_used=out.model, tokens_used=out.tokens_used,
            citations=out.citations,
        )
    """

    #: 完整 assistant 正文（由 delta 拼接）。失败时保持为止的片段，**不得**落库。
    text: str = ""
    #: 实际使用的模型名（Req 4.10 的 history metadata）。
    model: str | None = None
    #: 用量。``source`` 明确标注 ``reported``（模型回报）或 ``estimated``（服务端估算），
    #: 不把估算值伪装成精确值。
    usage: dict[str, Any] = field(default_factory=dict)
    #: 端到端耗时（含上下文构建）。
    latency_ms: int = 0
    #: 引用来源（写入 ``ai_chat_message.referenced_sources``）。
    citations: list[dict[str, Any]] = field(default_factory=list)
    #: Context Manifest（Task 14 扩展为完整 included/trimmed/denied/unavailable 清单）。
    context_manifest: dict[str, Any] | None = None
    #: 已签发的 delta 条数（守卫用："真的流过内容"而不是"函数没抛异常"）。
    delta_count: int = 0
    #: 失败快照。**同时**会被抛出 —— 这里只是给审计/指标一个不用 catch 的读点。
    failure: EngineFailure | None = None

    @property
    def tokens_used(self) -> int | None:
        value = self.usage.get("total_tokens")
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def succeeded(self) -> bool:
        return self.failure is None and bool(self.text)


class EngineStream:
    """``AsyncIterator[ChatEvent]`` + 本次执行的 :class:`EngineOutcome`。

    存在的理由：design 把 ``run()`` 的签名冻结为 ``run(request, cancel) ->
    AsyncIterator[ChatEvent]``，而调用方还需要拿到正文 / model / usage / latency
    去调 ``finish_success``。把结果塞进最后一个事件的 payload 会污染事件协议
    （``done`` 是终态事件，engine 不许发）；挂在 engine 实例上会在并发 run 间串数据。
    于是返回值同时是迭代器与结果句柄 —— 签名不变，结果 per-run 隔离。
    """

    def __init__(
        self,
        factory: Callable[[EngineOutcome], AsyncIterator[ChatEvent]],
    ) -> None:
        self.outcome = EngineOutcome()
        self._iter = factory(self.outcome).__aiter__()

    def __aiter__(self) -> AsyncIterator[ChatEvent]:
        return self

    async def __anext__(self) -> ChatEvent:
        return await self._iter.__anext__()

    async def aclose(self) -> None:
        """提前中止时释放底层 async generator（否则 GC 期才 throw GeneratorExit）。"""
        closer = getattr(self._iter, "aclose", None)
        if closer is not None:
            await closer()


# ---------------------------------------------------------------------------
# 已授权请求（engine 的唯一输入）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizedChatRunRequest:
    """engine 的输入：**全部字段都已由服务端解析/授权**。

    与客户端提交的 ``ChatRunRequest`` 的区别正是本 spec 的核心不变量：

    ==================  ====================================================
    ``ChatRunRequest``  客户端提交：host **引用**、query、mention **ID**、幂等键
    本类                服务端解析后：``AuthorizedHostContext``、服务端选定的
                        engine 与 capability 快照、服务端签发的 message ID
    ==================  ====================================================

    ``engine`` 字段的值只能来自 :func:`resolve_engine` —— Property 24 要求"请求体中
    任意 engine 字段都不影响服务端选择"，而 ``ChatRunRequest`` 连该字段都不存在
    （``PRIVILEGED_REQUEST_FIELDS`` 会点名拒绝）。

    ``assistant_message_id`` 是**服务端签发**的（Req 4.4）：``delta`` / ``citation``
    是消息相关事件，必须在流开始前就有 message ID，否则前端无法把片段挂到正确消息上。

    🔴 Task 5 hand-off：coordinator 必须让最终落库的 assistant 消息使用**同一个**
    ``assistant_message_id``（今日 ``persistence.append_message`` 自行生成 ID，需要它
    接受显式 ID）。否则 ``delta`` 事件引用的 message ID 与 history 返回的 ID 不一致，
    前端刷新后会看到"两条消息"。本模块不改 Task 4 的 persistence 以免与并发任务冲突。
    """

    run_id: UUID
    session_id: UUID
    request_id: UUID
    host: AuthorizedHostContext
    query: str
    engine: ChatEngineName
    capabilities: EngineCapabilities
    #: 服务端签发的 assistant message ID（delta / citation 事件的 message_id）。
    assistant_message_id: UUID
    #: 已认证的用户对象。ContextBuilder 的知识库权限过滤需要它
    #: （``KnowledgeAccessPolicy.resolve_subject``），不是客户端可控字段。
    principal: Any = None
    review_mode: bool = False
    sheet_name: str | None = None

    @classmethod
    def from_creation(
        cls,
        creation: Any,
        *,
        principal: Any = None,
        assistant_message_id: UUID | None = None,
    ) -> AuthorizedChatRunRequest:
        """从 Task 4 的 ``ChatRunCreation`` 构造（Task 5 coordinator 的入口）。

        ``creation`` 用 duck typing 而不是 import ``ChatRunCreation``：那会把
        ``run_service`` 拉进 import 图，而 ``run_service`` 需要 import 本模块的
        :func:`resolve_engine` ⇒ 循环。守卫用真实 ``ChatRunCreation`` 对象调用本方法，
        所以"字段名对不对"是被真实执行验证的，不是靠注释保证。
        """
        return cls(
            run_id=creation.run_id,
            session_id=creation.session_id,
            request_id=creation.request_id,
            host=creation.host,
            query=creation.request.query,
            engine=creation.engine,
            capabilities=creation.capabilities,
            assistant_message_id=assistant_message_id or uuid4(),
            principal=principal,
            review_mode=creation.request.review_mode,
            sheet_name=creation.request.sheet_name,
        )

    @classmethod
    def coerce(
        cls,
        obj: Any,
        *,
        principal: Any = None,
        assistant_message_id: UUID | None = None,
    ) -> AuthorizedChatRunRequest:
        """把调用方给的"请求对象"归一成本类型。

        Task 5 的 coordinator 调 ``engine.run(execution, signal)``，其中 ``execution``
        是 ``run_coordinator.RunExecution``（字段：``run_id`` / ``session_id`` /
        ``request_id`` / ``host`` / ``request``(ChatRunRequest) / ``engine`` /
        ``capabilities``），与 ``ChatRunCreation`` 的相关字段同名同义 —— 所以
        :meth:`from_creation` 对两者都成立，归一只需一次 ``isinstance`` 分流。

        🔴 不用 ``isinstance(obj, RunExecution)`` 判定，也不 import 那个类：
        ``run_coordinator`` 会 import 本模块（``build_engine``），反向 import 即循环。
        守卫用**真实** ``RunExecution`` 与真实 ``ChatRunCreation`` 各调一次本方法，
        因此"字段名对不对"由真实执行验证，不靠注释。
        """
        if isinstance(obj, cls):
            return obj
        return cls.from_creation(
            obj, principal=principal, assistant_message_id=assistant_message_id
        )


# ---------------------------------------------------------------------------
# ChatEngine 协议
# ---------------------------------------------------------------------------


@runtime_checkable
class ChatEngine(Protocol):
    """两种 engine 的统一契约（Design "12. Engine Contract"）。

    ``run`` 声明为**普通** ``def`` 返回 ``AsyncIterator``（design 里写作
    ``async def ... -> AsyncIterator``）—— 二者在调用点等价于
    ``async for ev in engine.run(...)``，但若协议声明为 ``async def``，调用方就得先
    ``await engine.run(...)`` 再迭代，与 design 给出的用法自相矛盾。实现返回
    :class:`EngineStream`（既是迭代器又带 outcome）。
    """

    #: engine 名。capability manifest 由它查表得到，不许另写一份。
    name: ChatEngineName

    async def capabilities(self) -> EngineCapabilities: ...

    def run(
        self,
        request: AuthorizedChatRunRequest,
        cancel: CancelSignal,
    ) -> AsyncIterator[ChatEvent]: ...


async def capabilities_of(engine_name: ChatEngineName) -> EngineCapabilities:
    """capability manifest 的唯一取法：**直接返回** Task 4 的表项。

    两个 engine 的 ``capabilities()`` 都只调本函数。若各自手写一份 manifest，
    表里写 ``tools=False`` 而 engine 自称 ``tools=True`` 这种漂移就只能靠人眼发现，
    而后果是前端放开一个后端不支持的入口（Req 10.3/10.4）。
    """
    return capabilities_for(engine_name)


def assert_non_terminal(event_type: ChatEventType) -> None:
    """业务事件必须是非终态（终态只能经 :func:`build_terminal_intent`）。"""
    if event_type in TERMINAL_EVENT_TYPES:
        raise EngineFailure(
            ChatErrorCode.engine_unavailable,
            f"{event_type.value} 是终态事件，engine 只能作为**意图**产出它"
            "（build_terminal_intent），真正的终态由 ChatRunService.finish_* 的"
            "compare-and-set 签发",
        )


def _event(
    request: AuthorizedChatRunRequest,
    events: EventIdSource,
    event_type: ChatEventType,
    payload: dict[str, Any] | None,
    message_id: UUID | None,
) -> ChatEvent:
    return ChatEvent(
        event_id=format_event_id(events.next(request.run_id)),
        run_id=request.run_id,
        session_id=request.session_id,
        request_id=request.request_id,
        type=event_type,
        timestamp=datetime.now(timezone.utc),
        message_id=message_id,
        payload=payload or {},
    )


def build_event(
    request: AuthorizedChatRunRequest,
    events: EventIdSource,
    event_type: ChatEventType,
    *,
    payload: dict[str, Any] | None = None,
    message_id: UUID | None = None,
) -> ChatEvent:
    """签发一条 engine **业务**事件（非终态；message 相关事件须带服务端 message ID）。"""
    assert_non_terminal(event_type)
    return _event(request, events, event_type, payload, message_id)


def build_terminal_intent(
    request: AuthorizedChatRunRequest,
    events: EventIdSource,
    event_type: ChatEventType,
    *,
    payload: dict[str, Any] | None = None,
    message_id: UUID | None = None,
) -> ChatEvent:
    """签发一条终态**意图**事件。

    ## 为什么是"意图"而不是终态本身（Property 7）

    engine 产出的终态事件**永远不会被直接发布到 SSE**。Task 5 的 coordinator 收到它
    之后只做映射：``done`` → ``ChatRunService.finish_success``、``cancelled`` →
    ``finish_cancelled``、其余 → ``finish_error(payload["code"])``；真正对外可见的终态
    事件由 ``finish_*`` 在数据库 compare-and-set **胜出后**重新签发。因此

    * 终态恰好一个 —— 由 CAS 保证，engine 发几次意图都改变不了；
    * "库里 error、流里 done"不可能出现 —— 两者同源于同一次 CAS。

    ## 为什么 engine 必须有这条通道

    typed error code（``context_build_failed`` 与 ``engine_unavailable`` 是两种完全不同
    的排障方向）、``usage``、以及"这是取消不是故障"这三件事，只有 engine 知道。
    没有意图通道时 coordinator 只能把一切异常压成 ``engine_unavailable``，
    Req 12.5 的稳定 error code 与 Req 4.7 的取消语义都会丢。

    ⚠️ 失败意图（``error`` / ``cancelled``）必须**紧跟一次异常抛出**
    （:class:`EngineFailure` / :class:`EngineCancelled`）：只 yield 不抛，任何不解读
    意图事件的调用方（例如只统计 delta 的测试替身）都会把失败当成"内容较短的成功"。
    抛异常让漏解读必然炸 —— Property 33 的兜底。
    """
    if event_type not in TERMINAL_EVENT_TYPES:
        raise EngineFailure(
            ChatErrorCode.engine_unavailable,
            f"{event_type.value} 不是终态事件，应经 build_event 签发",
        )
    return _event(request, events, event_type, payload, message_id)


# ---------------------------------------------------------------------------
# engine 选择：服务端配置 + feature flag + 项目 allowlist（Req 10.1 / 10.6）
# ---------------------------------------------------------------------------

#: 降级原因 → 中文说明（NFR-5；前端从 ``/capabilities`` 拿到后展示，不复制常量）。
ENGINE_GATE_REASON_ZH: dict[str, str] = {
    "configured_native": "当前服务端配置使用平台原生引擎。",
    "experimental_disabled": "DSH 多步 Agent 属实验特性，尚未在本服务端启用。",
    "project_not_allowlisted": "DSH 多步 Agent 尚未对当前项目开放，本次使用平台原生引擎。",
    "no_project_binding": "当前页面无项目上下文，DSH 多步 Agent 不可用。",
}


def dsh_project_allowlist() -> frozenset[UUID]:
    """DSH 项目 allowlist（服务端配置，逗号分隔 UUID）。

    非法 UUID **跳过并记 WARNING**：allowlist 写错一个字符不应该让整张名单失效
    （那会让已验收项目突然掉回 native 且无人察觉），但也不能当成通配。
    """
    from app.core.config import settings

    raw = getattr(settings, "AI_DSH_PROJECT_ALLOWLIST", "") or ""
    allowed: set[UUID] = set()
    for token in str(raw).replace(";", ",").split(","):
        candidate = token.strip()
        if not candidate:
            continue
        try:
            allowed.add(UUID(candidate))
        except ValueError:
            logger.warning(
                "AI_DSH_PROJECT_ALLOWLIST 含非法 UUID %r，已跳过该项", candidate
            )
    return frozenset(allowed)


def resolve_engine(
    *, project_id: UUID | None = None
) -> tuple[ChatEngineName, str | None]:
    """服务端决定本次 run 的 engine，返回 ``(engine, gate_reason)``。

    三层门（任一不满足即 native），全部只读服务端状态：

    1. **配置**：``AI_CHAT_ENGINE``（Task 4 的 :func:`resolve_engine_name`，
       非法取值已在那里回落 native）；
    2. **experimental feature flag**：``AI_DSH_ENABLED``（Req 10.6：未通过运行时
       安全验收前不得对全部项目开放）；
    3. **项目 allowlist**：``AI_DSH_PROJECT_ALLOWLIST``（Task 30 逐项目放开）。

    🔴 这里的"回落 native"与 Req 10.5 禁止的"静默回落"是**两件不同的事**：

    * 本函数是**配置门** —— DSH 压根没被启用/授权，本次执行从一开始就是 native，
      run 的 ``engine`` 列与 capability 快照都如实记 native，前端据此禁用工具入口。
      Task 30 明文要求"未验收项目保持 native"。
    * Req 10.5 禁止的是**运行期降级** —— 已经选定 DSH、DSH 启动/handshake/MCP/
      本地模型检查失败后偷偷改用 native 并返回成功内容。那条由 Task 28 的
      ``DshEngine`` 以 ``engine_unavailable`` 终态实现，本模块不提供任何回落路径。

    ``gate_reason`` 非 None 表示"配置想要 DSH 但被门拦下"，供审计与
    ``/capabilities`` 的中文原因使用（:data:`ENGINE_GATE_REASON_ZH`）。
    """
    from app.core.config import settings

    configured = resolve_engine_name()
    if configured is not ChatEngineName.dsh:
        return configured, None

    if not bool(getattr(settings, "AI_DSH_ENABLED", False)):
        logger.info("AI_CHAT_ENGINE=dsh 但 AI_DSH_ENABLED=False，本次使用 native")
        return ChatEngineName.native, "experimental_disabled"

    if project_id is None:
        logger.info("AI_CHAT_ENGINE=dsh 但当前宿主无项目绑定，本次使用 native")
        return ChatEngineName.native, "no_project_binding"

    allowlist = dsh_project_allowlist()
    if project_id not in allowlist:
        logger.info(
            "AI_CHAT_ENGINE=dsh 但项目 %s 不在 allowlist（共 %d 项），本次使用 native",
            project_id,
            len(allowlist),
        )
        return ChatEngineName.native, "project_not_allowlisted"

    return ChatEngineName.dsh, None


def build_engine(
    db: Any,
    execution: Any = None,
    *,
    events: EventIdSource | None = None,
) -> ChatEngine:
    """按服务端选定的 engine 名构造实例。

    🔴 签名 ``(db, execution)`` 是 Task 5 已落地的 ``EngineProvider`` 契约
    （``run_coordinator._default_engine_provider`` 就是 ``builder(db, execution)``）。
    换成别的形状不会报错，只会让 coordinator 的 ``except Exception`` 把它吞成
    ``engine_unavailable`` —— 表现是"AI 永远不回答且无错误"，而所有静态检查都绿。
    改本函数签名前先看那处调用点。

    engine 名从 ``execution.engine`` 取（``RunExecution`` / ``ChatRunCreation`` 同名字段），
    缺失时按 :func:`resolve_engine` 的服务端结论走。

    实现类**惰性 import**：``native_engine`` 需要 import 本模块的协议与失败类型，
    在模块顶层反向 import 就是循环。Task 28 在此增加 ``dsh`` 分支。

    未登记的 engine 抛 ``engine_unavailable`` 而**不**回落 native：Req 10.5 明令
    DSH 不可用时不得静默换成 native 后返回成功内容。配置门（flag / allowlist）在
    :func:`resolve_engine` 里已经把"未启用"表达成 native，能走到这里说明服务端真的
    选定了该 engine，此时缺实现是硬故障。
    """
    engine_name = getattr(execution, "engine", None)
    if not isinstance(engine_name, ChatEngineName):
        engine_name, _ = resolve_engine(
            project_id=getattr(getattr(execution, "host", None), "project_id", None)
        )
    if engine_name is ChatEngineName.native:
        from app.services.ai_chat.native_engine import build_native_engine

        return build_native_engine(db, events=events)
    if engine_name is ChatEngineName.dsh:
        from app.services.ai_chat.dsh_engine import build_dsh_engine

        return build_dsh_engine(db, events=events)
    raise EngineFailure(
        ChatErrorCode.engine_unavailable,
        f"engine {engine_name.value} 尚未登记实现（不回落 native）",
    )


async def drain(
    stream: AsyncIterator[ChatEvent],
    sink: Callable[[ChatEvent], Awaitable[None]] | None = None,
) -> list[ChatEvent]:
    """把 engine 事件流跑完并返回事件列表（守卫与简单调用方用）。

    刻意不做任何终态处理 —— 终态属于 ``ChatRunService``。异常原样上抛。
    """
    collected: list[ChatEvent] = []
    async for event in stream:
        collected.append(event)
        if sink is not None:
            await sink(event)
    return collected
