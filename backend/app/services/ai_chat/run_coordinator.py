"""``ChatRunCoordinator`` · 有界执行队列、租约、取消传播与启动恢复（Task 5）

Feature: dsh-agent-panel-integration
Requirements:
  - 4.1：两阶段 API —— ``POST /runs`` 创建幂等 run 后由本协调器**排队执行**；
    客户端断线重连订阅原 run，绝不重新调用 engine。
  - 4.5：一个 run 只能进入一个终态。本模块**不新写状态机**：所有终态一律经
    :class:`~app.services.ai_chat.run_service.ChatRunService` 的 ``finish_*``
    compare-and-set。
  - 4.7：取消传播到 engine / 工具 / 子 Agent / 排队任务；取消确认后不再发生工具调用
    或 assistant 消息追加。
  - 4.8：SSE 分片/心跳/多行 data 由 :mod:`app.services.ai_chat.run_events` 的自定界帧保证。
  - 4.9：接入平台 ``sse_registry`` drain；服务停机时 active run 收到可识别中止状态，
    重启后由启动恢复标为 ``interrupted`` 或按策略重排。
  - 4.12：``delta`` 走 Redis Stream / 等价有界缓冲；数据库只写 run/message/tool 摘要
    —— assistant 草稿按**节流窗口原地更新**，不逐 token 插行。
  - 13.6：队列满返回 typed quota error，负载含 ``retry_after`` / ``remaining`` / ``reset``。
Design: "Components and Interfaces → 5. Run Coordinator、SSE Replay 与取消" 的七步。
Properties: 7（Run 唯一终态）、8（取消传播到全部后代）、9（SSE 任意分片与续传等价）

## 一个 run 恰好一个 executor：两道闸

1. **有界队列 + active 上限**（进程内）：``asyncio.Queue(maxsize=AI_CHAT_QUEUE_LIMIT)``
   加 ``AI_CHAT_MAX_ACTIVE_RUNS`` 个 worker。队列满 ⇒ :class:`RunQuotaExceeded`
   ⇒ ``quota`` 事件 + ``error/rate_limited`` 终态（不是无界堆积，也不是静默丢弃）。
2. **租约**（跨进程）：Redis ``SET NX EX`` 快闸 + **数据库 compare-and-set 权威闸**。
   两者都过才算取得执行权。

为什么权威闸在数据库而不是 Redis：``ai_chat_runs.lease_owner`` / ``lease_expires_at``
是 V147 已有的**持久**列，启动恢复扫描读的就是它们。若只用 Redis，进程崩溃 + Redis 也被
清空后，那些 running 行就再没有任何线索可被接管（Design 第 7 步会无从下手）。
Redis 闸的价值是"多 worker 抢同一个 run 时少一次数据库往返"，掉线时降级不影响正确性
—— 这正是 Design "Redis lease **或等价原子租约**"里的等价物。

## engine 接缝（Task 6 并发在做，本模块不实现 engine）

本模块只通过 :class:`SupportsChatRun` 结构化协议消费 engine：

```python
async def run(self, request, cancel) -> AsyncIterator[ChatEvent]
```

与 Design "12. Engine Contract" 的 ``ChatEngine.run(request, cancel)`` 逐字同形。
刻意**不 import** Task 6 的模块：

- 它还不存在时，本模块必须能编译、能被守卫用确定性测试替身驱动；
- 它落地后，``ChatEngine`` 自然满足本协议（结构化子类型），无需改这里。

``engine_provider`` 为 None（或 Task 6 模块缺失）时，run 以
``ChatErrorCode.engine_unavailable`` 终止 —— **不静默成功、不回落到另一条链路**
（Req 10.5）。这段 import 失败必须记 ERROR 日志：把它吞成 WARNING 就是典型的
fail-open（表现为"AI 一直不回答但没有任何错误"）。

## 事件签发的单一权威

engine 产出的事件只被当作**意图**：非终态事件经 ``ChatRunService.emit`` 重新签发
（拿到单调 event ID，并在每次签发前复查终态门），终态意图映射到 ``finish_success`` /
``finish_error`` / ``finish_cancelled``。因此：

- 事件 ID 单调且与 ``Last-Event-ID`` 同源（Req 4.4）；
- "终态之后不再有业务事件"由 ``emit`` 的门与数据库状态共同保证，跨进程有效；
- engine 无法绕过 CAS 制造第二个终态（Property 7）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIChatMessage,
    AIChatRun,
    AIChatSession,
    AIChatToolCall,
    ChatEngineName,
    ChatMessageStatus,
    ChatRunStatus,
)
from app.services.ai_chat.host_context import (
    AuthorizedHostContext,
    HostContextResolver,
)
from app.services.ai_chat.run_contract import (
    ERROR_MESSAGE_ZH,
    TERMINAL_EVENT_TYPES,
    ChatErrorCode,
    ChatEvent,
    ChatEventType,
    ChatRunRequest,
    EngineCapabilities,
    capabilities_for,
    event_seq,
)
from app.services.ai_chat.run_events import RunEventStream, get_event_stream
from app.services.ai_chat.run_service import (
    ChatRunCreation,
    ChatRunService,
    RunEventSequencer,
)
from app.services.ai_chat.audit import audit_run_started, audit_run_terminal, audit_tool_started, audit_tool_finished
from app.services.ai_chat.metrics import (
    inc_run_status,
    observe_queue_wait,
    observe_run_latency,
    inc_tokens,
    observe_cancel_latency,
    set_active_runs,
    set_queued_runs,
)

logger = logging.getLogger(__name__)

__all__ = [
    "RunQuotaExceeded",
    "CancelSignal",
    "CancelRegistry",
    "CancelOutcome",
    "SupportsChatRun",
    "EngineProvider",
    "RunExecution",
    "RunLease",
    "LeaseGrant",
    "RecoveryReport",
    "ChatRunCoordinator",
    "get_coordinator",
    "reset_coordinator",
    "cancel_key",
    "lease_key",
]


def lease_key(run_id: UUID | str) -> str:
    return f"ai-chat:run:{run_id}:lease"


def cancel_key(run_id: UUID | str) -> str:
    return f"ai-chat:run:{run_id}:cancel"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _owner_id() -> str:
    """本进程的租约持有者标识（主机 + PID + 随机段，跨重启不复用）。"""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# 配额（Req 13.6）
# ---------------------------------------------------------------------------


class RunQuotaExceeded(Exception):
    """有界队列已满 —— typed quota error（不是 500，也不是静默丢弃）。"""

    def __init__(
        self,
        *,
        retry_after: int,
        remaining: int,
        queue_limit: int,
        active_limit: int,
    ) -> None:
        self.retry_after = int(retry_after)
        self.remaining = int(remaining)
        self.queue_limit = int(queue_limit)
        self.active_limit = int(active_limit)
        self.code = ChatErrorCode.rate_limited
        super().__init__(ERROR_MESSAGE_ZH[ChatErrorCode.rate_limited])

    def payload(self) -> dict[str, Any]:
        """``quota`` 事件负载：前端据此显示中文倒计时并保留草稿（Req 13.6）。"""
        return {
            "code": self.code.value,
            "message": ERROR_MESSAGE_ZH[self.code],
            "retry_after": self.retry_after,
            "remaining": self.remaining,
            "reset": (_now() + timedelta(seconds=self.retry_after)).isoformat(),
            "queue_limit": self.queue_limit,
            "active_limit": self.active_limit,
        }


# ---------------------------------------------------------------------------
# 取消（Req 4.7 / Property 8）
# ---------------------------------------------------------------------------


class CancelSignal:
    """一次 run 的取消信号，可挂任意数量后代（engine / 工具 / 子 Agent / MCP 进程）。

    Property 8 的落点：:meth:`request` 一次性把信号推到**全部**已登记后代。后代自己再
    登记的后代（子 Agent 的工具）通过 :meth:`child` 派生 —— 派生信号在父信号已取消时
    **立即**为已取消状态，避免"取消发生在派生之前 ⇒ 新后代仍然开跑"这个窗口。
    """

    def __init__(self, run_id: UUID, *, parent: CancelSignal | None = None) -> None:
        self.run_id = run_id
        self._event = asyncio.Event()
        self._callbacks: list[Callable[[], Any]] = []
        self._reason: str | None = None
        self._children: list[CancelSignal] = []
        if parent is not None:
            parent._children.append(self)
            if parent.is_set:
                # 🔴 父已取消 ⇒ 新派生的后代一出生就是取消态。少了这一步，
                # "cancel 与工具启动竞态"时新工具会照常执行（Property 8 明令后续
                # 工具调用计数不再增长）。
                self.request(reason=parent.reason or "parent_cancelled")

    # -- 状态 -----------------------------------------------------------
    @property
    def is_set(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    async def wait(self) -> None:
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        if self.is_set:
            raise asyncio.CancelledError(f"run {self.run_id} 已取消")

    # -- 传播 -----------------------------------------------------------
    def add_callback(self, callback: Callable[[], Any]) -> None:
        """登记后代的停止动作（工具中止、子进程 kill、MCP 关闭…）。

        已取消时**立即**执行 —— 否则后到的登记者永远收不到那次取消。
        """
        self._callbacks.append(callback)
        if self.is_set:
            self._invoke(callback)

    def child(self) -> CancelSignal:
        """派生后代信号（子 Agent / 工具用）。"""
        return CancelSignal(self.run_id, parent=self)

    def request(self, *, reason: str = "user_cancelled") -> bool:
        """请求取消。返回 True 表示本次调用是首次（幂等：重复调用返回 False）。"""
        if self.is_set:
            return False
        self._reason = reason
        self._event.set()
        for cb in list(self._callbacks):
            self._invoke(cb)
        for child in list(self._children):
            child.request(reason=reason)
        return True

    @staticmethod
    def _invoke(callback: Callable[[], Any]) -> None:
        try:
            result = callback()
        except Exception:  # noqa: BLE001
            # 🔴 记 ERROR 而不是 WARNING/pass：取消回调失败意味着某个后代**没有**被停掉
            # （残留子进程 / 继续跑的工具），是必须被看见的故障，不是可忽略的噪声。
            logger.error("[ai-chat] 取消回调执行失败（后代可能未停止）", exc_info=True)
            return
        if asyncio.iscoroutine(result):
            # 异步停止动作：调度出去并保留引用，避免 "coroutine never awaited"。
            with contextlib.suppress(RuntimeError):
                task = asyncio.get_running_loop().create_task(result)
                _PENDING_CANCEL_TASKS.add(task)
                task.add_done_callback(_PENDING_CANCEL_TASKS.discard)


#: 异步取消回调的强引用集合（否则 task 可能在完成前被 GC）。
_PENDING_CANCEL_TASKS: set[asyncio.Task] = set()


@dataclass(frozen=True)
class CancelOutcome:
    """``POST /runs/{id}/cancel`` 的结果（幂等：重复调用返回同一形态）。"""

    run_id: UUID
    status: ChatRunStatus
    cancel_requested: bool
    already_terminal: bool
    signalled_locally: bool

    def as_response(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "status": self.status.value,
            "cancel_requested": self.cancel_requested,
            "already_terminal": self.already_terminal,
            "message": (
                "本次回答已结束，无需取消。"
                if self.already_terminal
                else "已请求取消，正在停止本次回答。"
            ),
        }


class CancelRegistry:
    """进程内 run → :class:`CancelSignal` 映射 + 跨进程 Redis 取消标记。

    取消请求可能落在**没有** executor 的进程上（多 worker 部署）。因此：
    ``request`` 既设 Redis 标记，也尝试进程内直投；executor 侧另起 watcher 轮询该标记
    （见 :meth:`ChatRunCoordinator._watch_remote_cancel`）。
    """

    def __init__(
        self,
        *,
        redis_provider: Callable[[], Awaitable[Any]] | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        if redis_provider is None:
            from app.core.redis import get_redis

            redis_provider = get_redis
        self._redis_provider = redis_provider
        self._signals: dict[UUID, CancelSignal] = {}
        if ttl_seconds is None:
            from app.core.config import settings

            ttl_seconds = int(settings.AI_CHAT_EVENT_STREAM_TTL_SECONDS)
        self._ttl = int(ttl_seconds)

    def register(self, run_id: UUID) -> CancelSignal:
        signal = self._signals.get(run_id)
        if signal is None:
            signal = CancelSignal(run_id)
            self._signals[run_id] = signal
        return signal

    def get(self, run_id: UUID) -> CancelSignal | None:
        return self._signals.get(run_id)

    def release(self, run_id: UUID) -> None:
        self._signals.pop(run_id, None)

    async def _redis(self) -> Any:
        try:
            return await self._redis_provider()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ai-chat] 取消标记无法写入 Redis（仅进程内生效）：%s", exc)
            return None

    async def mark_remote(self, run_id: UUID) -> None:
        client = await self._redis()
        if client is None:
            return
        try:
            await client.set(cancel_key(run_id), "1", ex=self._ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ai-chat] 写取消标记失败（仅进程内生效）：%s", exc)

    async def is_marked_remote(self, run_id: UUID) -> bool:
        client = await self._redis()
        if client is None:
            return False
        try:
            return bool(await client.exists(cancel_key(run_id)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ai-chat] 读取消标记失败：%s", exc)
            return False

    async def clear_remote(self, run_id: UUID) -> None:
        client = await self._redis()
        if client is None:
            return
        with contextlib.suppress(Exception):
            await client.delete(cancel_key(run_id))

    async def request(self, run_id: UUID) -> bool:
        """跨进程 + 进程内一起请求取消，返回是否命中了本进程的 executor。"""
        await self.mark_remote(run_id)
        signal = self._signals.get(run_id)
        if signal is None:
            return False
        signal.request()
        return True


# ---------------------------------------------------------------------------
# engine 接缝（Task 6 拥有实现）
# ---------------------------------------------------------------------------


@runtime_checkable
class SupportsChatRun(Protocol):
    """本协调器对 engine 的**全部**要求（Design "12. Engine Contract" 同形）。

    Task 6 的 ``ChatEngine`` 结构化满足它；守卫用确定性替身实现它。
    """

    def run(
        self, request: Any, cancel: CancelSignal
    ) -> AsyncIterator[ChatEvent]:  # pragma: no cover - 协议声明
        ...


#: engine 工厂：``(db, execution) -> engine``。返回 None ⇒ ``engine_unavailable``。
EngineProvider = Callable[[AsyncSession, "RunExecution"], Any]


@dataclass(frozen=True)
class RunExecution:
    """一次执行所需的可信输入（交给 engine 的 ``request``）。

    Task 6 的 ``AuthorizedChatRunRequest`` 落地后可直接消费本对象或包装它 —— 关键是
    ``host`` 已经是 :class:`AuthorizedHostContext`（服务端反查 + 授权后的结果），
    engine 不需要、也不允许再从客户端字段推断项目/年度/资源。
    """

    run_id: UUID
    session_id: UUID
    request_id: UUID
    actor_id: UUID
    host: AuthorizedHostContext
    request: ChatRunRequest
    engine: ChatEngineName
    capabilities: EngineCapabilities
    retry_count: int = 0
    #: 进程内入队时刻（monotonic），用于度量队列等待时间（Req 12.8）
    queued_at_mono: float = field(default_factory=time.monotonic)

    @classmethod
    def from_creation(cls, creation: ChatRunCreation) -> RunExecution:
        return cls(
            run_id=creation.run_id,
            session_id=creation.session_id,
            request_id=creation.request_id,
            actor_id=creation.host.principal_id,
            host=creation.host,
            request=creation.request,
            engine=creation.engine,
            capabilities=creation.capabilities,
        )


# ---------------------------------------------------------------------------
# 租约（Design 第 2 步）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeaseGrant:
    run_id: UUID
    owner: str
    expires_at: datetime


class RunLease:
    """执行租约：Redis ``SET NX`` 快闸 + 数据库 compare-and-set 权威闸。"""

    def __init__(
        self,
        *,
        ttl_seconds: int | None = None,
        redis_provider: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        from app.core.config import settings

        self._ttl = int(
            ttl_seconds if ttl_seconds is not None else settings.AI_CHAT_LEASE_TTL_SECONDS
        )
        if redis_provider is None:
            from app.core.redis import get_redis

            redis_provider = get_redis
        self._redis_provider = redis_provider

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    async def _redis(self) -> Any:
        try:
            return await self._redis_provider()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ai-chat] 租约 Redis 快闸不可用，仅用数据库租约：%s", exc)
            return None

    async def acquire(
        self, db: AsyncSession, run_id: UUID, owner: str
    ) -> LeaseGrant | None:
        """取得执行权。两道闸都过才返回 grant；任一未过返回 None。

        数据库闸的 WHERE 同时要求：
        - run 仍处于可执行状态（queued / interrupted / running —— running 是同进程续跑
          或前任租约过期后接管）；
        - 租约为空、已过期，或**本来就是自己的**（重入安全）。

        并发调用在 PG 行锁上排队，胜者提交后败者的 WHERE 对新版本行重新求值 ⇒ 0 行。
        """
        client = await self._redis()
        redis_held = False
        if client is not None:
            try:
                redis_held = bool(
                    await client.set(lease_key(run_id), owner, nx=True, ex=self._ttl)
                )
                if not redis_held:
                    current = await client.get(lease_key(run_id))
                    if current == owner:
                        redis_held = True
                        await client.expire(lease_key(run_id), self._ttl)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[ai-chat] 租约快闸异常，降级为纯数据库租约：%s", exc)
                client = None
            if client is not None and not redis_held:
                logger.debug("run %s 的租约已被其他 executor 持有（Redis 快闸）", run_id)
                return None

        expires_at = _now() + timedelta(seconds=self._ttl)
        won = (
            await db.execute(
                sa.update(AIChatRun)
                .where(
                    AIChatRun.id == run_id,
                    AIChatRun.status.in_(
                        [
                            ChatRunStatus.queued.value,
                            ChatRunStatus.interrupted.value,
                            ChatRunStatus.running.value,
                        ]
                    ),
                    sa.or_(
                        AIChatRun.lease_owner.is_(None),
                        AIChatRun.lease_owner == owner,
                        AIChatRun.lease_expires_at.is_(None),
                        AIChatRun.lease_expires_at <= sa.func.now(),
                    ),
                )
                .values(lease_owner=owner, lease_expires_at=expires_at)
                .returning(AIChatRun.id)
            )
        ).scalar_one_or_none()
        if won is None:
            if client is not None and redis_held:
                # 数据库闸没过 ⇒ 把快闸还回去，否则真正的持有者会被挡住到 TTL。
                await self._release_redis(run_id, owner)
            return None
        return LeaseGrant(run_id=run_id, owner=owner, expires_at=expires_at)

    async def renew(self, db: AsyncSession, run_id: UUID, owner: str) -> bool:
        expires_at = _now() + timedelta(seconds=self._ttl)
        won = (
            await db.execute(
                sa.update(AIChatRun)
                .where(AIChatRun.id == run_id, AIChatRun.lease_owner == owner)
                .values(lease_expires_at=expires_at)
                .returning(AIChatRun.id)
            )
        ).scalar_one_or_none()
        client = await self._redis()
        if client is not None:
            with contextlib.suppress(Exception):
                if await client.get(lease_key(run_id)) == owner:
                    await client.expire(lease_key(run_id), self._ttl)
        return won is not None

    async def release(self, db: AsyncSession, run_id: UUID, owner: str) -> None:
        await db.execute(
            sa.update(AIChatRun)
            .where(AIChatRun.id == run_id, AIChatRun.lease_owner == owner)
            .values(lease_owner=None, lease_expires_at=None)
        )
        await self._release_redis(run_id, owner)

    async def _release_redis(self, run_id: UUID, owner: str) -> None:
        client = await self._redis()
        if client is None:
            return
        with contextlib.suppress(Exception):
            if await client.get(lease_key(run_id)) == owner:
                await client.delete(lease_key(run_id))


# ---------------------------------------------------------------------------
# 启动恢复（Design 第 7 步）
# ---------------------------------------------------------------------------


@dataclass
class RecoveryReport:
    scanned: int = 0
    requeued: list[UUID] = field(default_factory=list)
    failed: list[UUID] = field(default_factory=list)
    skipped: list[UUID] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "requeued": [str(r) for r in self.requeued],
            "failed": [str(r) for r in self.failed],
            "skipped": [str(r) for r in self.skipped],
        }


# ---------------------------------------------------------------------------
# 协调器
# ---------------------------------------------------------------------------


class ChatRunCoordinator:
    """有界队列 + 租约 + 事件流 + 取消 + 恢复。"""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any] | None = None,
        engine_provider: EngineProvider | None = None,
        stream: RunEventStream | None = None,
        cancels: CancelRegistry | None = None,
        lease: RunLease | None = None,
        sequencer: RunEventSequencer | None = None,
        max_active: int | None = None,
        queue_limit: int | None = None,
        run_timeout: float | None = None,
        draft_flush_seconds: float | None = None,
        remote_cancel_poll_seconds: float = 0.5,
        owner: str | None = None,
    ) -> None:
        from app.core.config import settings

        if session_factory is None:
            from app.core.database import async_session

            session_factory = async_session
        self._session_factory = session_factory
        self._engine_provider = engine_provider
        self._stream = stream or get_event_stream()
        self._cancels = cancels or CancelRegistry()
        self._lease = lease or RunLease()
        self._sequencer = sequencer or RunEventSequencer()
        self._max_active = int(
            max_active if max_active is not None else settings.AI_CHAT_MAX_ACTIVE_RUNS
        )
        self._queue_limit = int(
            queue_limit if queue_limit is not None else settings.AI_CHAT_QUEUE_LIMIT
        )
        self._run_timeout = float(
            run_timeout
            if run_timeout is not None
            else settings.AI_CHAT_RUN_TIMEOUT_SECONDS
        )
        self._draft_flush = float(
            draft_flush_seconds
            if draft_flush_seconds is not None
            else settings.AI_CHAT_DRAFT_FLUSH_SECONDS
        )
        self._retry_after = int(settings.AI_CHAT_QUOTA_RETRY_AFTER_SECONDS)
        self._max_retries = int(settings.AI_CHAT_RUN_MAX_RETRIES)
        self._remote_cancel_poll = float(remote_cancel_poll_seconds)
        self._owner = owner or _owner_id()
        self._queue: asyncio.Queue[RunExecution] = asyncio.Queue(
            maxsize=self._queue_limit
        )
        self._workers: list[asyncio.Task] = []
        self._active: set[UUID] = set()
        self._closing = False
        #: 工具调用计数（Property 8 的可观测量：取消确认后不得再增长）。
        self._tool_calls: dict[UUID, int] = {}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @property
    def owner(self) -> str:
        return self._owner

    @property
    def stream(self) -> RunEventStream:
        return self._stream

    @property
    def cancels(self) -> CancelRegistry:
        return self._cancels

    @property
    def sequencer(self) -> RunEventSequencer:
        """本协调器的序号来源。

        🔴 任何**带外**为某个 run 签发事件的代码（取消端点、配额拒绝、恢复扫描）都必须
        用它，并在签发前 :meth:`_seed_sequencer` —— 否则新事件的 ID 会与已发布事件撞号，
        而 :meth:`RunEventStream.history` 按序号去重 ⇒ 那条事件被静默丢掉。
        跨进程取消正是这个形态：另一个进程的序号从头开始，取消事件拿到 ID 2，
        客户端永远收不到终态（表现为点了取消却一直转圈）。
        """
        return self._sequencer

    @property
    def queued(self) -> int:
        return self._queue.qsize()

    @property
    def active(self) -> int:
        return len(self._active)

    def tool_call_count(self, run_id: UUID) -> int:
        return self._tool_calls.get(run_id, 0)

    def start(self) -> None:
        """启动 worker（幂等）。"""
        self._closing = False
        self._workers = [w for w in self._workers if not w.done()]
        while len(self._workers) < self._max_active:
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def shutdown(self, *, drain_timeout: float = 5.0) -> None:
        """停止接单并等待在跑的 run 收尾（drain）。"""
        self._closing = True
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        deadline = time.monotonic() + drain_timeout
        while self._active and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

    # ------------------------------------------------------------------
    # 入队（Design 第 2 步）
    # ------------------------------------------------------------------
    async def submit(self, creation: ChatRunCreation) -> RunExecution | None:
        """把新建的 run 放入有界队列。

        只有 ``creation.should_invoke_engine`` 为真（本次调用是 upsert 的胜者）才入队
        —— 重复提交的幂等请求绝不重复调用 engine（Req 4.6）。

        :raises RunQuotaExceeded: 队列已满。抛出前已把 ``quota`` 事件与
            ``error/rate_limited`` 终态落定，客户端从 SSE 也能看到 typed 原因。
        """
        if not creation.should_invoke_engine:
            return None
        execution = RunExecution.from_creation(creation)
        # run_started 必须进流：客户端不带 Last-Event-ID 连上来时也要能拿到第一条
        # （创建响应里那条与流里这条逐字相同 —— 序号固定、时间戳取 queued_at）。
        await self._stream.publish(creation.run_started_event())

        # 🔴 哈希链审计：run started（Req 12.6 — EVERY run 有 started event）
        try:
            async with self._session_factory() as audit_db:
                await audit_run_started(
                    audit_db,
                    user_id=creation.host.principal_id,
                    project_id=creation.host.project_id,
                    run_id=creation.run_id,
                    engine=creation.engine.value,
                    host_type=creation.host.resource_type.value if creation.host.resource_type else None,
                )
                await audit_db.commit()
        except Exception:  # noqa: BLE001
            logger.warning("[ai-chat] audit_run_started 写入失败 run=%s（不阻断执行）", creation.run_id)

        self.start()
        try:
            self._queue.put_nowait(execution)
        except asyncio.QueueFull:
            quota = RunQuotaExceeded(
                retry_after=self._retry_after,
                remaining=0,
                queue_limit=self._queue_limit,
                active_limit=self._max_active,
            )
            await self._reject_over_quota(execution, quota)
            raise quota from None
        return execution

    async def _reject_over_quota(
        self, execution: RunExecution, quota: RunQuotaExceeded
    ) -> None:
        """队列满：先发 ``quota`` 事件，再走**同一条**终态路径落 ``error/rate_limited``。"""
        await self._seed_sequencer(execution.run_id)
        async with self._session_factory() as db:
            svc = ChatRunService(db, sequencer=self._sequencer)
            quota_event = await svc.emit(
                run_id=execution.run_id,
                event_type=ChatEventType.quota,
                payload=quota.payload(),
            )
            if quota_event is not None:
                await self._stream.publish(quota_event)
            terminal = await svc.finish_error(
                run_id=execution.run_id,
                error_code=ChatErrorCode.rate_limited,
                detail=f"queue_limit={quota.queue_limit} active_limit={quota.active_limit}",
            )
            await db.commit()
        if terminal is not None:
            await self._stream.publish(terminal)

    # ------------------------------------------------------------------
    # worker
    # ------------------------------------------------------------------
    async def _worker_loop(self) -> None:
        while not self._closing:
            try:
                execution = await self._queue.get()
            except asyncio.CancelledError:
                return
            try:
                await self._execute(execution)
            except asyncio.CancelledError:
                # worker 被 drain 取消：run 保持 running，租约到期后由启动恢复接管
                # （Req 4.9：重启后标 interrupted 或按策略重排）。
                raise
            except Exception:  # noqa: BLE001
                logger.exception("[ai-chat] run %s 执行异常", execution.run_id)
            finally:
                self._queue.task_done()

    async def _execute(self, execution: RunExecution) -> None:
        run_id = execution.run_id
        signal = self._cancels.register(run_id)
        if await self._cancels.is_marked_remote(run_id):
            # 排队期间已被取消（Req 4.7：排队任务也要收到取消）。
            signal.request(reason="cancelled_while_queued")

        async with self._session_factory() as db:
            grant = await self._lease.acquire(db, run_id, self._owner)
            await db.commit()
            if grant is None:
                logger.info("run %s 已有其他 executor 持有租约，本次放弃", run_id)
                return

        self._active.add(run_id)
        # 🔴 Metrics（Req 12.8）：更新 active/queued gauge + 记录队列等待
        set_active_runs(len(self._active))
        set_queued_runs(self._queue.qsize())
        observe_queue_wait(time.monotonic() - execution.queued_at_mono)
        watcher = asyncio.create_task(self._watch_remote_cancel(run_id, signal))
        started = time.monotonic()
        try:
            async with self._session_factory() as db:
                svc = ChatRunService(db, sequencer=self._sequencer)
                await self._seed_sequencer(run_id)
                if not await svc.mark_running(run_id, lease_owner=self._owner):
                    # queued/interrupted 之外（已取消或已终态）⇒ 不执行、不发事件。
                    await db.commit()
                    logger.info("run %s 无法进入 running（可能已取消/已终态）", run_id)
                    return
                await db.commit()

                if signal.is_set:
                    await self._finish_cancelled(svc, db, run_id, started, execution_engine=execution.engine.value)
                    return

                await self._drive_engine(svc, db, execution, signal, started)
        finally:
            # 🔴 同步清理必须排在任何 await 之前：drain 时本任务已被 cancel，
            # finally 里的第一个 await 会立刻再抛 CancelledError，其后的语句不会执行。
            self._active.discard(run_id)
            self._sequencer.forget(run_id)
            # 🔴 Metrics（Req 12.8）：active/queued gauge 更新
            set_active_runs(len(self._active))
            set_queued_runs(self._queue.qsize())
            watcher.cancel()
            try:
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher
                async with self._session_factory() as db:
                    await self._lease.release(db, run_id, self._owner)
                    await db.commit()
                await self._cancels.clear_remote(run_id)
            finally:
                self._cancels.release(run_id)

    async def _seed_sequencer(self, run_id: UUID) -> None:
        """把序号对齐到流里已发布的最后一条（重排换进程接手时不撞号）。"""
        history = await self._stream.history(run_id)
        if history:
            self._sequencer.seed(run_id, event_seq(history[-1].event_id))

    async def _watch_remote_cancel(self, run_id: UUID, signal: CancelSignal) -> None:
        """轮询跨进程取消标记（取消请求可能落在别的 worker 上）。"""
        try:
            while not signal.is_set:
                await asyncio.sleep(self._remote_cancel_poll)
                if await self._cancels.is_marked_remote(run_id):
                    signal.request(reason="remote_cancelled")
                    return
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------------
    # engine 驱动（Design 第 3/4 步）
    # ------------------------------------------------------------------
    async def _drive_engine(
        self,
        svc: ChatRunService,
        db: AsyncSession,
        execution: RunExecution,
        signal: CancelSignal,
        started: float,
    ) -> None:
        run_id = execution.run_id
        engine = self._resolve_engine(db, execution)
        if engine is None:
            await self._finish_error(
                svc,
                db,
                run_id,
                ChatErrorCode.engine_unavailable,
                started,
                detail="engine_provider 未注入或 engine 模块不可用",
                execution_engine=execution.engine.value,
            )
            return

        session_obj = await db.get(AIChatSession, execution.session_id)
        if session_obj is None:  # pragma: no cover - 外键保证存在
            await self._finish_error(
                svc, db, run_id, ChatErrorCode.context_build_failed, started,
                detail="会话行缺失",
                execution_engine=execution.engine.value,
            )
            return

        text_parts: list[str] = []
        draft_id: UUID | None = None
        last_flush = time.monotonic()
        usage: dict[str, Any] = {}
        model_used: str | None = None
        citations: Any = None
        context_manifest: Any = None
        terminal_seen = False

        stream_iter = engine.run(execution, signal)
        try:
            async with asyncio.timeout(self._run_timeout):
                async for raw in stream_iter:
                    if signal.is_set:
                        break
                    etype = raw.type
                    if etype is ChatEventType.run_started:
                        continue  # 已在 submit 时发布，不重复
                    if etype is ChatEventType.delta:
                        chunk = str(raw.payload.get("text", ""))
                        text_parts.append(chunk)
                        if draft_id is None:
                            draft = await svc.append_assistant_draft(
                                session=session_obj,
                                run_id=run_id,
                                text="".join(text_parts),
                            )
                            if draft is None:
                                break  # 终态已落定（Property 7）
                            draft_id = draft.id
                            await db.commit()
                            last_flush = time.monotonic()
                        event = await svc.emit(
                            run_id=run_id,
                            event_type=ChatEventType.delta,
                            payload={"text": chunk},
                            message_id=draft_id,
                        )
                        if event is None:
                            break
                        await self._stream.publish(event)
                        now = time.monotonic()
                        if now - last_flush >= self._draft_flush:
                            # 节流：DB 只按窗口原地更新草稿，不逐 token 插行（Req 4.12）。
                            await svc.update_assistant_draft(
                                message_id=draft_id,
                                run_id=run_id,
                                text="".join(text_parts),
                            )
                            await db.commit()
                            last_flush = now
                        continue

                    if etype in (ChatEventType.tool_started, ChatEventType.tool_finished):
                        if etype is ChatEventType.tool_started:
                            self._tool_calls[run_id] = self._tool_calls.get(run_id, 0) + 1
                        event = await svc.emit(
                            run_id=run_id, event_type=etype, payload=dict(raw.payload)
                        )
                        if event is None:
                            break
                        await self._stream.publish(event)
                        # 🔴 哈希链审计：tool call started/finished（Property 32 / Req 12.6）
                        try:
                            async with self._session_factory() as audit_db:
                                tool_call_id = raw.payload.get("tool_call_id", "")
                                tool_name = raw.payload.get("tool_name", "")
                                if etype is ChatEventType.tool_started:
                                    await audit_tool_started(
                                        audit_db,
                                        user_id=execution.actor_id,
                                        project_id=execution.project_id,
                                        run_id=run_id,
                                        tool_call_id=tool_call_id,
                                        tool_name=tool_name,
                                    )
                                else:
                                    await audit_tool_finished(
                                        audit_db,
                                        user_id=execution.actor_id,
                                        project_id=execution.project_id,
                                        run_id=run_id,
                                        tool_call_id=tool_call_id,
                                        tool_name=tool_name,
                                        status=raw.payload.get("status", "finished"),
                                        result_bytes=raw.payload.get("result_bytes", 0),
                                        duration_ms=raw.payload.get("duration_ms", 0),
                                        error_code=raw.payload.get("error_code"),
                                    )
                                await audit_db.commit()
                        except Exception:  # noqa: BLE001
                            logger.warning(
                                "[ai-chat] audit_tool_%s 写入失败 run=%s（不阻断执行）",
                                "started" if etype is ChatEventType.tool_started else "finished",
                                run_id,
                            )
                        continue

                    if etype is ChatEventType.citation:
                        citations = raw.payload.get("citations", citations)
                        event = await svc.emit(
                            run_id=run_id,
                            event_type=ChatEventType.citation,
                            payload=dict(raw.payload),
                            message_id=draft_id or raw.message_id,
                        )
                        if event is None:
                            break
                        await self._stream.publish(event)
                        continue

                    if etype in (ChatEventType.context_ready, ChatEventType.quota):
                        if etype is ChatEventType.context_ready:
                            context_manifest = raw.payload.get(
                                "manifest", context_manifest
                            )
                        event = await svc.emit(
                            run_id=run_id, event_type=etype, payload=dict(raw.payload)
                        )
                        if event is None:
                            break
                        await self._stream.publish(event)
                        continue

                    if etype in TERMINAL_EVENT_TYPES:
                        terminal_seen = True
                        await self._finish_from_engine(
                            svc,
                            db,
                            execution,
                            session_obj,
                            raw,
                            text="".join(text_parts),
                            draft_id=draft_id,
                            usage=dict(raw.payload.get("usage") or usage),
                            model_used=model_used,
                            citations=citations,
                            context_manifest=context_manifest,
                            started=started,
                        )
                        return
        except TimeoutError:
            await self._settle_draft(svc, draft_id, run_id, ChatMessageStatus.failed)
            await self._finish_error(
                svc, db, run_id, ChatErrorCode.engine_unavailable, started,
                detail=f"run 超过 {self._run_timeout}s 墙钟上限",
                execution_engine=execution.engine.value,
            )
            return
        except asyncio.CancelledError:
            # drain / 显式取消：不在此处落终态（drain 时留给启动恢复；
            # 取消由下面的 signal 分支处理）。
            raise
        except Exception as exc:  # noqa: BLE001
            await self._settle_draft(svc, draft_id, run_id, ChatMessageStatus.failed)
            await self._finish_error(
                svc, db, run_id, ChatErrorCode.engine_unavailable, started,
                detail=f"{type(exc).__name__}: {exc}",
                execution_engine=execution.engine.value,
            )
            return
        finally:
            aclose = getattr(stream_iter, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()

        if signal.is_set:
            await self._settle_draft(svc, draft_id, run_id, ChatMessageStatus.cancelled)
            await self._finish_cancelled(svc, db, run_id, started, execution_engine=execution.engine.value)
            return
        if terminal_seen:  # pragma: no cover - 上面已 return
            return
        # engine 迭代自然结束但没给终态：有正文按成功定稿，无正文按 typed error
        # （Req 12.9：fail-soft 占位/空结果不得产生 success 终态）。
        if text_parts:
            await self._finish_success(
                svc,
                db,
                run_id,
                session_obj,
                text="".join(text_parts),
                draft_id=draft_id,
                usage=usage,
                model_used=model_used,
                citations=citations,
                context_manifest=context_manifest,
                started=started,
                execution_engine=execution.engine.value,
            )
        else:
            await self._finish_error(
                svc, db, run_id, ChatErrorCode.engine_unavailable, started,
                detail="engine 未产出任何内容且未给出终态",
                execution_engine=execution.engine.value,
            )

    def _resolve_engine(self, db: AsyncSession, execution: RunExecution) -> Any:
        """取 engine 实例。

        缺省 provider 会尝试 Task 6 的 ``app.services.ai_chat.engine``；模块不存在或
        构造失败一律返回 None ⇒ 调用方落 ``engine_unavailable``（Req 10.5：
        不静默回落到另一条链路）。失败记 **ERROR** —— 吞成 WARNING 就是 fail-open。
        """
        provider = self._engine_provider
        if provider is None:
            provider = _default_engine_provider
        try:
            return provider(db, execution)
        except Exception:  # noqa: BLE001
            logger.error(
                "[ai-chat] engine 解析失败，run %s 将以 engine_unavailable 结束",
                execution.run_id,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # 终态（全部经 ChatRunService 的 CAS —— 不存在第二条终态路径）
    # ------------------------------------------------------------------
    async def _finish_from_engine(
        self,
        svc: ChatRunService,
        db: AsyncSession,
        execution: RunExecution,
        session_obj: AIChatSession,
        raw: ChatEvent,
        *,
        text: str,
        draft_id: UUID | None,
        usage: dict[str, Any],
        model_used: str | None,
        citations: Any,
        context_manifest: Any,
        started: float,
    ) -> None:
        run_id = execution.run_id
        if raw.type is ChatEventType.done:
            await self._finish_success(
                svc, db, run_id, session_obj,
                text=text,
                draft_id=draft_id,
                usage=usage,
                model_used=model_used,
                citations=citations,
                context_manifest=context_manifest,
                started=started,
                execution_engine=execution.engine.value,
            )
            return
        if raw.type is ChatEventType.cancelled:
            await self._settle_draft(svc, draft_id, run_id, ChatMessageStatus.cancelled)
            await self._finish_cancelled(svc, db, run_id, started, execution_engine=execution.engine.value)
            return
        code = _error_code_from_payload(raw.payload)
        await self._settle_draft(svc, draft_id, run_id, ChatMessageStatus.failed)
        await self._finish_error(svc, db, run_id, code, started, detail="engine 报错", execution_engine=execution.engine.value)

    async def _finish_success(
        self,
        svc: ChatRunService,
        db: AsyncSession,
        run_id: UUID,
        session_obj: AIChatSession,
        *,
        text: str,
        draft_id: UUID | None,
        usage: dict[str, Any],
        model_used: str | None,
        citations: Any,
        context_manifest: Any,
        started: float,
        execution_engine: str | None = None,
    ) -> bool:
        """返回 CAS 是否胜出。落空即说明已被 error/cancelled 抢先（Property 7）。"""
        event, _message = await svc.finish_success(
            session=session_obj,
            run_id=run_id,
            text=text,
            usage=usage or None,
            latency_ms=_elapsed_ms(started),
            model_used=model_used,
            citations=citations,
            context_manifest=context_manifest,
            draft_message_id=draft_id,
        )
        if event is None:
            # 终态已被抢先：草稿绝不能停在 draft（历史里会挂一条永不定稿的消息）。
            await self._settle_draft(svc, draft_id, run_id, ChatMessageStatus.failed)
        await db.commit()
        if event is not None:
            await self._stream.publish(event)
            # 🔴 哈希链审计：run done（Req 12.6）
            await self._audit_terminal(
                run_id=run_id, status="done", latency_ms=_elapsed_ms(started),
                tokens_total=_extract_tokens(usage),
            )
            # 🔴 Metrics（Req 12.8）：run latency + status counter + tokens
            latency_s = (time.monotonic() - started)
            inc_run_status(execution_engine or "native", "done")
            observe_run_latency(execution_engine or "native", "done", latency_s)
            if usage:
                inc_tokens(
                    execution_engine or "native",
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )
        return event is not None

    async def _finish_error(
        self,
        svc: ChatRunService,
        db: AsyncSession,
        run_id: UUID,
        code: ChatErrorCode,
        started: float,
        *,
        detail: str | None = None,
        execution_engine: str | None = None,
    ) -> None:
        event = await svc.finish_error(
            run_id=run_id,
            error_code=code,
            latency_ms=_elapsed_ms(started),
            detail=detail,
        )
        await db.commit()
        if event is not None:
            await self._stream.publish(event)
            # 🔴 哈希链审计：run error（Req 12.6）
            await self._audit_terminal(
                run_id=run_id, status="error", error_code=code.value,
                latency_ms=_elapsed_ms(started),
            )
            # 🔴 Metrics（Req 12.8）
            inc_run_status(execution_engine or "native", "error")
            observe_run_latency(execution_engine or "native", "error", time.monotonic() - started)

    async def _finish_cancelled(
        self, svc: ChatRunService, db: AsyncSession, run_id: UUID, started: float,
        *, execution_engine: str | None = None,
    ) -> None:
        event = await svc.finish_cancelled(
            run_id=run_id, latency_ms=_elapsed_ms(started)
        )
        await db.commit()
        if event is not None:
            await self._stream.publish(event)
            # 🔴 哈希链审计：run cancelled（Req 12.6）
            await self._audit_terminal(
                run_id=run_id, status="cancelled", latency_ms=_elapsed_ms(started),
            )
            # 🔴 Metrics（Req 12.8）
            inc_run_status(execution_engine or "native", "cancelled")
            observe_run_latency(execution_engine or "native", "cancelled", time.monotonic() - started)
            observe_cancel_latency(time.monotonic() - started)

    async def _audit_terminal(
        self,
        *,
        run_id: UUID,
        status: str,
        error_code: str | None = None,
        latency_ms: int | None = None,
        tokens_total: int | None = None,
    ) -> None:
        """终态审计写入（独立 session，不影响已 commit 的主事务）。"""
        try:
            async with self._session_factory() as audit_db:
                # 查 run 的 actor_id / project_id / engine 用于审计
                row = (
                    await audit_db.execute(
                        sa.select(
                            AIChatRun.actor_id,
                            AIChatRun.project_id,
                            AIChatRun.engine,
                        ).where(AIChatRun.id == run_id)
                    )
                ).one_or_none()
                if row is not None:
                    await audit_run_terminal(
                        audit_db,
                        user_id=row.actor_id,
                        project_id=row.project_id,
                        run_id=run_id,
                        status=status,
                        engine=row.engine or "native",
                        error_code=error_code,
                        latency_ms=latency_ms,
                        tokens_total=tokens_total,
                    )
                    await audit_db.commit()
        except Exception:  # noqa: BLE001
            logger.warning("[ai-chat] audit_run_terminal 写入失败 run=%s status=%s", run_id, status)

    async def _settle_draft(
        self,
        svc: ChatRunService,
        draft_id: UUID | None,
        run_id: UUID,
        status: ChatMessageStatus,
    ) -> None:
        if draft_id is None:
            return
        with contextlib.suppress(Exception):
            await svc.settle_assistant_draft(
                message_id=draft_id, run_id=run_id, status=status
            )

    # ------------------------------------------------------------------
    # 取消端点（Design 第 6 步）
    # ------------------------------------------------------------------
    async def cancel(
        self, db: AsyncSession, run_id: UUID, *, actor_id: UUID
    ) -> CancelOutcome:
        """幂等取消。

        - 已终态 ⇒ 原样返回状态，**不发**任何业务事件（Req 4.5）。
        - ``queued``（还没 executor）⇒ 直接落 ``cancelled`` 终态并发事件。
        - ``running`` ⇒ 记录 ``cancel_requested_at`` + 设跨进程标记 + 直投本进程信号；
          真正的终态由 executor 落（它才知道 engine/工具/子 Agent 都停了）。
        """
        row = (
            await db.execute(
                sa.select(AIChatRun.status, AIChatRun.actor_id).where(
                    AIChatRun.id == run_id
                )
            )
        ).first()
        if row is None or row.actor_id != actor_id:
            from app.services.wp_visibility.denial import ExternalNotFound

            raise ExternalNotFound()

        status = ChatRunStatus(row.status)
        if status in (
            ChatRunStatus.done,
            ChatRunStatus.error,
            ChatRunStatus.cancelled,
        ):
            return CancelOutcome(
                run_id=run_id,
                status=status,
                cancel_requested=False,
                already_terminal=True,
                signalled_locally=False,
            )

        await db.execute(
            sa.update(AIChatRun)
            .where(
                AIChatRun.id == run_id,
                AIChatRun.status.in_(
                    [
                        ChatRunStatus.queued.value,
                        ChatRunStatus.running.value,
                        ChatRunStatus.interrupted.value,
                    ]
                ),
            )
            .values(
                cancel_requested_at=sa.func.coalesce(
                    AIChatRun.cancel_requested_at, sa.func.now()
                )
            )
        )
        signalled = await self._cancels.request(run_id)

        if status is ChatRunStatus.queued and not signalled:
            # 带外签发终态前必须对齐序号：本进程可能从未为该 run 发过事件，
            # 序号会从 2 开始重来并与已发布事件撞号（去重后终态被丢掉）。
            await self._seed_sequencer(run_id)
            svc = ChatRunService(db, sequencer=self._sequencer)
            event = await svc.finish_cancelled(run_id=run_id)
            await db.commit()
            if event is not None:
                await self._stream.publish(event)
            final = ChatRunStatus.cancelled if event is not None else status
            return CancelOutcome(
                run_id=run_id,
                status=final,
                cancel_requested=True,
                already_terminal=False,
                signalled_locally=False,
            )

        await db.commit()
        return CancelOutcome(
            run_id=run_id,
            status=status,
            cancel_requested=True,
            already_terminal=False,
            signalled_locally=signalled,
        )

    # ------------------------------------------------------------------
    # 启动恢复（Design 第 7 步）
    # ------------------------------------------------------------------
    async def recover_lease_expired_runs(
        self, db: AsyncSession, *, limit: int = 200
    ) -> RecoveryReport:
        """扫描租约过期的 ``running`` run，按"无外部副作用 + retry limit"重排或标失败。

        判据是**真实副作用**而不是"跑了多久"：
        - 有工具调用记录 ⇒ 重跑可能重复产生外部影响 ⇒ 不重排；
        - 已有 completed assistant 消息 ⇒ 用户已看到答案 ⇒ 不重排；
        - ``retry_count`` 已达上限 ⇒ 不重排（避免崩溃循环无限重跑）。

        不重排的一律走 ``running → interrupted → error(run_interrupted)``，让用户看到
        "服务重启导致本次回答中断"的中文原因，而不是永远转圈（Req 4.9 / 12.4）。
        """
        report = RecoveryReport()
        rows = (
            await db.execute(
                sa.select(
                    AIChatRun.id,
                    AIChatRun.retry_count,
                    AIChatRun.session_id,
                )
                .where(
                    AIChatRun.status == ChatRunStatus.running.value,
                    AIChatRun.lease_expires_at.isnot(None),
                    AIChatRun.lease_expires_at <= sa.func.now(),
                )
                .order_by(AIChatRun.queued_at.asc())
                .limit(limit)
            )
        ).all()
        report.scanned = len(rows)
        svc = ChatRunService(db, sequencer=self._sequencer)

        for row in rows:
            run_id = row.id
            # 恢复扫描也是带外签发（interrupted → error 会发一条 error 事件）。
            await self._seed_sequencer(run_id)
            if not await svc.transition(
                run_id=run_id, new_status=ChatRunStatus.interrupted
            ):
                report.skipped.append(run_id)
                continue
            side_effects = await self._has_external_side_effects(db, run_id)
            can_retry = (
                not side_effects and int(row.retry_count or 0) < self._max_retries
            )
            if can_retry:
                await db.execute(
                    sa.update(AIChatRun)
                    .where(AIChatRun.id == run_id)
                    .values(
                        retry_count=AIChatRun.retry_count + 1,
                        lease_owner=None,
                        lease_expires_at=None,
                    )
                )
                if await svc.transition(
                    run_id=run_id, new_status=ChatRunStatus.queued
                ):
                    report.requeued.append(run_id)
                else:  # pragma: no cover - 并发抢先
                    report.skipped.append(run_id)
                continue
            event = await svc.finish_error(
                run_id=run_id,
                error_code=ChatErrorCode.run_interrupted,
                detail=(
                    "lease 过期且存在外部副作用或已达重排上限"
                    if side_effects
                    else "lease 过期且已达重排上限"
                ),
            )
            await db.execute(
                sa.update(AIChatRun)
                .where(AIChatRun.id == run_id)
                .values(lease_owner=None, lease_expires_at=None)
            )
            report.failed.append(run_id)
            if event is not None:
                await self._stream.publish(event)
        await db.commit()
        if report.scanned:
            logger.warning("[ai-chat] 启动恢复扫描结果：%s", report.as_dict())
        return report

    @staticmethod
    async def _has_external_side_effects(db: AsyncSession, run_id: UUID) -> bool:
        tool_calls = (
            await db.execute(
                sa.select(sa.func.count())
                .select_from(AIChatToolCall)
                .where(AIChatToolCall.run_id == run_id)
            )
        ).scalar_one()
        if tool_calls:
            return True
        completed = (
            await db.execute(
                sa.select(sa.func.count())
                .select_from(AIChatMessage)
                .where(
                    AIChatMessage.run_id == run_id,
                    AIChatMessage.status == ChatMessageStatus.completed.value,
                    AIChatMessage.role == "assistant",
                )
            )
        ).scalar_one()
        return bool(completed)

    # ------------------------------------------------------------------
    # 重排后的重新执行（恢复链路的下半段）
    # ------------------------------------------------------------------
    async def redispatch(self, run_ids: Sequence[UUID]) -> list[UUID]:
        """把重排回 ``queued`` 的 run 重新入队（重建可信执行上下文并**重新授权**）。

        重排不是"把状态改回去就完了"：换进程接手时必须重新解析 HostContext 并再次
        授权 —— 期间用户权限可能已被收回（Req 2.1 明确一切读取前置授权）。
        """
        accepted: list[UUID] = []
        for run_id in run_ids:
            try:
                async with self._session_factory() as db:
                    execution = await self._rebuild_execution(db, run_id)
                if execution is None:
                    continue
                self.start()
                self._queue.put_nowait(execution)
                accepted.append(run_id)
            except asyncio.QueueFull:
                logger.warning("[ai-chat] 队列已满，run %s 本轮不重排", run_id)
            except Exception:  # noqa: BLE001
                logger.error("[ai-chat] run %s 重排失败", run_id, exc_info=True)
        return accepted

    async def _rebuild_execution(
        self, db: AsyncSession, run_id: UUID
    ) -> RunExecution | None:
        from app.models.core import User
        from app.services.ai_chat.contracts import AiChatAction, HostRef, HostType

        row = (
            await db.execute(
                sa.select(
                    AIChatRun.id,
                    AIChatRun.session_id,
                    AIChatRun.request_id,
                    AIChatRun.actor_id,
                    AIChatRun.host_type,
                    AIChatRun.host_id,
                    AIChatRun.project_id,
                    AIChatRun.engine,
                    AIChatRun.status,
                    AIChatRun.retry_count,
                ).where(AIChatRun.id == run_id)
            )
        ).first()
        if row is None or row.status != ChatRunStatus.queued.value:
            return None
        query = (
            await db.execute(
                sa.select(AIChatMessage.message_text)
                .where(AIChatMessage.run_id == run_id, AIChatMessage.role == "user")
                .order_by(AIChatMessage.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not query:
            logger.warning("[ai-chat] run %s 无 user message，无法重排", run_id)
            return None
        user = await db.get(User, row.actor_id)
        if user is None:  # pragma: no cover - 外键保证存在
            return None
        host_ref = HostRef(type=HostType(row.host_type), id=row.host_id)
        host = await HostContextResolver(db).enforce(
            user,
            host_ref,
            AiChatAction.read,
            entrypoint="ai_chat.run_recover",
            request_id=str(row.request_id),
        )
        engine = ChatEngineName(row.engine)
        request = ChatRunRequest.model_validate(
            {
                "host": {"type": host.resource_type.value, "id": host.resource_id},
                "query": query,
                "idempotency_key": str(uuid4()),
            }
        )
        return RunExecution(
            run_id=row.id,
            session_id=row.session_id,
            request_id=row.request_id,
            actor_id=row.actor_id,
            host=host,
            request=request,
            engine=engine,
            capabilities=capabilities_for(engine),
            retry_count=int(row.retry_count or 0),
        )


def _error_code_from_payload(payload: dict[str, Any]) -> ChatErrorCode:
    """engine 的 error 负载 → 稳定 error code（未登记取值一律 engine_unavailable）。"""
    raw = payload.get("code")
    if isinstance(raw, ChatErrorCode):
        return raw
    try:
        return ChatErrorCode(str(raw))
    except ValueError:
        return ChatErrorCode.engine_unavailable


def _extract_tokens(usage: dict[str, Any] | None) -> int | None:
    """从 usage dict 提取总 token 数（只存计数，不存内容 — Req 12.7）。"""
    if not usage:
        return None
    return (
        (usage.get("total_tokens") or 0)
        or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
        or None
    )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _default_engine_provider(db: AsyncSession, execution: RunExecution) -> Any:
    """默认 engine 解析：交给 Task 6 的 engine 模块；缺失即 None（typed error）。

    🔴 这里**故意不 import** 具体 engine 类型：Task 6 与本 Task 并发开发，硬依赖会让
    两边互相阻塞。约定是 ``app.services.ai_chat.engine`` 暴露
    ``build_engine(db, execution)`` 或 ``resolve_engine(db)``（二者取其一即可）。
    """
    try:
        from app.services.ai_chat import engine as engine_mod  # type: ignore[attr-defined]
    except ImportError:
        logger.error(
            "[ai-chat] engine 模块尚未就绪（Task 6），run %s 以 engine_unavailable 结束",
            execution.run_id,
        )
        return None
    builder = getattr(engine_mod, "build_engine", None)
    if builder is not None:
        return builder(db, execution)
    resolver = getattr(engine_mod, "resolve_engine", None)
    if resolver is not None:
        return resolver(db)
    logger.error(
        "[ai-chat] engine 模块未暴露 build_engine/resolve_engine，run %s 无法执行",
        execution.run_id,
    )
    return None


_COORDINATOR: ChatRunCoordinator | None = None


def get_coordinator() -> ChatRunCoordinator:
    """进程级单例（路由与启动恢复必须共享同一队列、租约与事件流）。"""
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = ChatRunCoordinator()
    return _COORDINATOR


def reset_coordinator() -> None:
    """测试用：丢弃单例（避免跨用例共享队列/worker）。"""
    global _COORDINATOR
    _COORDINATOR = None
