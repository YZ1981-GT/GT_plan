"""``ChatRunService`` · 幂等 run 创建与状态机 compare-and-set（Task 4）

Feature: dsh-agent-panel-integration
Requirements:
  - 4.1：两阶段 API 的第一阶段 —— 创建幂等 run（本服务），第二阶段订阅事件（Task 5）。
  - 4.2：请求体的越权字段由 :class:`~app.services.ai_chat.run_contract.ChatRunRequest`
    在解析期拒绝；本服务只消费已解析的可信字段。
  - 4.4：事件由本服务签发，携带单调 event ID 与 run/session/request ID。
  - 4.5：terminal event **恰好一个** —— 由数据库 compare-and-set 保证，
    且成功终态与 completed assistant 消息在**同一事务**内完成。
  - 4.6：同一 ``(actor_id, session_id, idempotency_key)`` 重复提交返回原 run，
    不重复保存用户消息、不重复调用 engine。
  - 10.2：engine 消费统一请求、产出统一事件；engine 名由服务端解析，请求不可覆盖。
Design: "Components and Interfaces → 5. Run Coordinator…"（第 1 步：事务内解析
  HostContext、upsert session、按三元组 upsert run、只保存一条 user message）。
Properties: 6（会话与 Run 并发幂等）、7（Run 唯一终态）

## 授权先于任何 upsert

``create_run`` 的第一件事是 ``HostContextResolver.enforce`` —— 拒绝在
session / run / message 任何写入之前发生（Property 1/2）。这也是为什么本服务
**不接受** project_id / year 参数：它们只能来自 ``AuthorizedHostContext``。

## 为什么"成功终态 + 消息"必须同一事务

先写 completed 消息、再 CAS 终态的写法有一个真实可复现的漏洞：并发 cancel 在两步
之间抢到终态 ⇒ run 落库 ``cancelled`` 而库里躺着一条 completed assistant 消息，
正是 Property 7 明令不允许的形态。:meth:`ChatRunService.finish_success` 把
"CAS running→done" 与"追加 completed 消息"放在同一事务里，CAS 失败即整体不写消息 ——
不变量由数据库原子性保证，不靠调用顺序自觉。

## 与 Task 5 / Task 6 的边界

本服务只提供**状态机与事件签发**。有界队列、Redis lease、Redis Stream 回放、
``Last-Event-ID`` 续传、drain 与取消端点属于 Task 5 的 ``ChatRunCoordinator``；
模型调用属于 Task 6 的 ``NativeEngine``。:class:`RunEventSequencer` 是 Task 5
用 Redis Stream ID 替换的接缝。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    CHAT_RUN_TERMINAL_STATUSES,
    AIChatMessage,
    AIChatRun,
    AIChatSession,
    ChatEngineName,
    ChatMessageStatus,
    ChatRole,
    ChatRunStatus,
)
from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import AiChatAction, AiChatDenialCode
from app.services.ai_chat.engine import resolve_engine
from app.services.ai_chat.host_context import (
    AuthorizedHostContext,
    HostContextResolver,
)
from app.services.ai_chat.persistence import (
    append_message,
    content_hash,
    find_session,
    upsert_run,
    upsert_session,
)
from app.services.ai_chat.run_contract import (
    ERROR_MESSAGE_ZH,
    MESSAGE_BOUND_EVENT_TYPES,
    NON_TERMINAL_RUN_STATUSES,
    RUN_STARTED_EVENT_SEQ,
    TERMINAL_EVENT_BY_RUN_STATUS,
    TERMINAL_EVENT_TYPES,
    ChatErrorCode,
    ChatEvent,
    ChatEventType,
    ChatRunAccepted,
    ChatRunRequest,
    EngineCapabilities,
    can_transition,
    capabilities_for,
    format_event_id,
    resolve_engine_name,
    run_events_url,
)
from app.services.wp_visibility.denial import ExternalNotFound

logger = logging.getLogger(__name__)

__all__ = [
    "RunEventSequencer",
    "ChatRunCreation",
    "ChatRunService",
    "RUN_CREATE_ENTRYPOINT",
]

#: 授权审计里标识"创建 run"这个入口（denial audit 的 entrypoint 取值）。
RUN_CREATE_ENTRYPOINT = "ai_chat.run_create"

#: 允许写入 completed assistant 消息的 run 状态。
#:
#: ``error`` / ``cancelled`` / ``interrupted`` 一律不允许（Req 4.5 / Property 7）；
#: ``queued`` 也不允许 —— 还没开跑就有回复只可能是接线错误。
_MESSAGE_WRITABLE_STATUSES: frozenset[ChatRunStatus] = frozenset(
    {ChatRunStatus.running, ChatRunStatus.done}
)


class RunEventSequencer:
    """per-run 单调事件序号来源。

    ``run_started`` 固定占用序号 :data:`RUN_STARTED_EVENT_SEQ`，故本序列从它之后开始，
    保证同一 run 内 event ID 严格单调（Req 4.4）。

    进程内实现，够用于"一个 run 只有一个 executor"的前提（Task 5 用 Redis lease 落实
    该前提）。Task 5 接入 Redis Stream 后可用 stream ID 替换本类 —— 接口只有
    :meth:`next` / :meth:`forget` 两个方法。
    """

    def __init__(self) -> None:
        self._seq: dict[UUID, int] = {}

    def next(self, run_id: UUID) -> int:
        nxt = self._seq.get(run_id, RUN_STARTED_EVENT_SEQ) + 1
        self._seq[run_id] = nxt
        return nxt

    def forget(self, run_id: UUID) -> None:
        """run 进入终态后释放计数（否则长期运行的进程里字典只增不减）。"""
        self._seq.pop(run_id, None)

    def seed(self, run_id: UUID, last_seq: int) -> None:
        """把计数对齐到**已发布**的最后一个序号（Task 5 的接缝落点）。

        Task 5 用 Redis Stream 里最后一条事件的 ``event_id`` 反解出 ``last_seq`` 再调用
        本方法：``interrupted → queued`` 重排后换进程接手同一个 run 时，序号必须从原来
        的位置续上。若仍从 1 开始，新事件的 ID 会与已发布事件**撞号** ⇒ 客户端按
        ``Last-Event-ID`` 续传时把新事件当旧事件丢掉（Req 4.4 的单调性正是为此）。

        只前进不后退：并发/乱序调用不会把计数拉回去。
        """
        current = self._seq.get(run_id, RUN_STARTED_EVENT_SEQ)
        self._seq[run_id] = max(current, int(last_seq), RUN_STARTED_EVENT_SEQ)


#: 默认序号来源。跨请求共享，因此同一 run 在同一进程内的事件序号连续。
_DEFAULT_SEQUENCER = RunEventSequencer()


@dataclass(frozen=True)
class ChatRunCreation:
    """run 创建结果的**值快照**（不持 ORM 对象）。

    刻意只存标量：调用方 commit 之后再访问 ORM 属性会触发懒加载，在同步段里就是
    ``MissingGreenlet``。快照在 flush 之后、commit 之前取好。
    """

    run_id: UUID
    session_id: UUID
    request_id: UUID
    status: ChatRunStatus
    error_code: ChatErrorCode | None
    engine: ChatEngineName
    capabilities: EngineCapabilities
    queued_at: datetime
    #: True = 本次调用是插入 run 的胜者 —— **唯一**可以调用 engine 的闸门（Req 4.6）。
    created: bool
    #: 仅创建者会写入 user message；重复请求为 None（不重复保存用户消息）。
    user_message_id: UUID | None
    host: AuthorizedHostContext
    request: ChatRunRequest

    @property
    def should_invoke_engine(self) -> bool:
        """Task 5 的 coordinator 只在此为 True 时把 run 放进执行队列。"""
        return self.created

    def run_started_event(self) -> ChatEvent:
        """该 run 的首个事件。**确定性可复现**：重复提交返回同一条。

        时间戳用 ``queued_at``（落库值）而不是"现在"，event ID 用固定序号 ——
        两者都保证重复请求拿到逐字相同的事件，客户端不会把它当新事件重复渲染。
        """
        return ChatEvent(
            event_id=format_event_id(RUN_STARTED_EVENT_SEQ),
            run_id=self.run_id,
            session_id=self.session_id,
            request_id=self.request_id,
            type=ChatEventType.run_started,
            timestamp=self.queued_at,
            payload={
                "engine": self.engine.value,
                "host_type": self.host.resource_type.value,
                "host_id": self.host.resource_id,
                "display_label": self.host.display_label,
                "project_id": str(self.host.project_id) if self.host.project_id else None,
                "year": self.host.year,
                "review_mode": self.request.review_mode,
                "project_tools_enabled": self.host.project_tools_enabled,
            },
        )

    def to_response(self) -> ChatRunAccepted:
        return ChatRunAccepted(
            run_id=self.run_id,
            session_id=self.session_id,
            request_id=self.request_id,
            status=self.status,
            error_code=self.error_code,
            engine=self.engine,
            capabilities=self.capabilities,
            events_url=run_events_url(self.run_id),
            replayed=not self.created,
            run_started=self.run_started_event(),
        )


@dataclass(frozen=True)
class _RunRow:
    """CAS / 事件签发需要的 run 列（每次从库里取新值，不用可能过期的 ORM 属性）。"""

    id: UUID
    session_id: UUID
    request_id: UUID
    status: ChatRunStatus
    error_code: str | None
    queued_at: datetime


class ChatRunService:
    """幂等 run 创建 + run 状态机 compare-and-set + 事件签发。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        access: ResourceAccessResolver | None = None,
        sequencer: RunEventSequencer | None = None,
    ) -> None:
        self._db = db
        self._access = access if access is not None else ResourceAccessResolver(db)
        self._hosts = HostContextResolver(db, access=self._access)
        self._sequencer = sequencer if sequencer is not None else _DEFAULT_SEQUENCER

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------
    async def create_run(
        self,
        user: Any,
        request: ChatRunRequest,
        *,
        request_id: UUID | None = None,
        entrypoint: str = RUN_CREATE_ENTRYPOINT,
    ) -> ChatRunCreation:
        """解析并授权 HostContext → upsert session → upsert run → 保存 user message。

        顺序不可调换：授权在任何写入之前（Property 1/2）。调用方负责 commit。

        :raises ExternalNotFound: 宿主授权失败、断言不一致，或客户端提交的
            ``session_id`` 与服务端定位结果不符（一律不可枚举 404）。
        """
        req_id = request_id or uuid4()

        # ① 过门用的动作只看**服务端配置**（Req 10.1）：配置为 DSH 时按写类 agent-run
        #    过门（更严），native 与既有 doc 对话一致用读类 read。
        #    真正生效的 engine 要等 host 反查出 project_id 才能判 allowlist，见 ③。
        configured = resolve_engine_name()
        action = (
            AiChatAction.agent_run
            if configured is ChatEngineName.dsh
            else AiChatAction.read
        )

        # ② 授权 + 服务端反查（拒绝 → 不可枚举 404 + denial audit）
        host = await self._hosts.enforce(
            user, request.host, action, entrypoint=entrypoint, request_id=str(req_id)
        )

        # ②b engine：Task 6 的 resolve_engine 在配置之上叠加 experimental feature flag
        #    与项目 allowlist（Req 10.6）。只会**收窄**（dsh → native），因此仍在 ①
        #    已过的更严门之内；反向放宽不存在。
        engine, gate_reason = resolve_engine(project_id=host.project_id)
        capabilities = capabilities_for(engine)
        if gate_reason is not None:
            logger.info(
                "run 创建：配置请求 %s，实际使用 %s（原因 %s）",
                configured.value, engine.value, gate_reason,
            )

        # ③ 客户端若提交 session_id，必须与服务端定位结果一致。
        #    先只读校验、再 upsert：否则伪造 session_id 的请求会留下一行会话副作用。
        if request.session_id is not None:
            existing = await find_session(
                self._db,
                user_id=host.principal_id,
                project_id=host.project_id,
                audit_year=host.year,
                host_type=host.resource_type,
                host_id=host.resource_id,
            )
            if existing is None or existing.id != request.session_id:
                await self._access.audit_denial(
                    principal_id=host.principal_id,
                    project_id=host.project_id,
                    denial_code=AiChatDenialCode.host_context_mismatch.value,
                    entrypoint=entrypoint,
                    action=action,
                    resource_type=None,
                    resource_id=str(request.session_id),
                    request_id=str(req_id),
                )
                raise ExternalNotFound()

        # ④ 会话：原子 upsert（Property 6 前半由 uq_ai_chat_session_user_key 保证）。
        #    review_mode 随服务端会话持久化（Req 9.5：不得只存无作用域 localStorage）。
        session, _ = await upsert_session(
            self._db,
            user_id=host.principal_id,
            project_id=host.project_id,
            audit_year=host.year,
            host_type=host.resource_type,
            host_id=host.resource_id,
            title=host.display_label,
            engine_preference=engine.value,
            review_mode=request.review_mode,
        )

        # ⑤ run：按 (actor_id, session_id, idempotency_key) 原子 upsert。
        run, created = await upsert_run(
            self._db,
            session_id=session.id,
            actor_id=host.principal_id,
            idempotency_key=str(request.idempotency_key),
            project_id=host.project_id,
            host_type=host.resource_type,
            host_id=host.resource_id,
            engine=engine,
            request_id=req_id,
            capability_snapshot=capabilities.model_dump(),
        )

        # ⑥ user message 只由创建者写入，且与 run 插入同一事务（Req 4.6）。
        user_message_id: UUID | None = None
        if created:
            message = await append_message(
                self._db,
                session,
                role=ChatRole.user,
                text=request.query,
                status=ChatMessageStatus.completed,
                run_id=run.id,
            )
            user_message_id = message.id

        # commit 前取好标量快照（commit 后访问 ORM 属性会触发懒加载）
        return ChatRunCreation(
            run_id=run.id,
            session_id=session.id,
            request_id=run.request_id,
            status=ChatRunStatus(run.status),
            error_code=ChatErrorCode(run.error_code) if run.error_code else None,
            engine=ChatEngineName(run.engine),
            capabilities=capabilities,
            queued_at=run.queued_at,
            created=created,
            user_message_id=user_message_id,
            host=host,
            request=request,
        )

    # ------------------------------------------------------------------
    # 状态机 compare-and-set
    # ------------------------------------------------------------------
    async def transition(
        self,
        *,
        run_id: UUID,
        new_status: ChatRunStatus,
        expected: Iterable[ChatRunStatus] | None = None,
        error_code: ChatErrorCode | None = None,
        usage: dict[str, Any] | None = None,
        latency_ms: int | None = None,
        lease_owner: str | None = None,
    ) -> bool:
        """把 run 状态 compare-and-set 到 ``new_status``，返回是否本次调用胜出。

        ``UPDATE … WHERE id = :id AND status IN (:expected)`` 是唯一判据：并发调用在
        PG 的行锁上排队，胜者提交后败者的 WHERE 会对**新版本行**重新求值（EvalPlanQual）
        而不再命中 ⇒ 影响行数为 0。因此"终态恰好一个"不依赖任何应用层判断。

        ``expected`` 缺省时由 :data:`ALLOWED_RUN_TRANSITIONS` 反推（所有能合法迁移到
        ``new_status`` 的前驱状态）—— 不在此处再抄一份状态图。
        """
        if expected is None:
            allowed_from = frozenset(
                s for s in ChatRunStatus if can_transition(s, new_status)
            )
        else:
            allowed_from = frozenset(expected)
            illegal = {s for s in allowed_from if not can_transition(s, new_status)}
            if illegal:
                raise ValueError(
                    f"非法迁移：{sorted(s.value for s in illegal)} → {new_status.value}"
                )
        if not allowed_from:
            raise ValueError(f"没有任何状态可迁移到 {new_status.value}")

        values: dict[str, Any] = {"status": new_status.value}
        if new_status is ChatRunStatus.running:
            # 已有 started_at 不覆盖（interrupted → queued → running 重排时保留首次开跑时刻）
            values["started_at"] = sa.func.coalesce(AIChatRun.started_at, sa.func.now())
        if new_status in CHAT_RUN_TERMINAL_STATUSES:
            values["finished_at"] = sa.func.now()
        if new_status is ChatRunStatus.cancelled:
            values["cancel_requested_at"] = sa.func.coalesce(
                AIChatRun.cancel_requested_at, sa.func.now()
            )
        if error_code is not None:
            values["error_code"] = error_code.value
        if usage is not None:
            values["usage"] = usage
        if latency_ms is not None:
            values["latency_ms"] = latency_ms
        if lease_owner is not None:
            values["lease_owner"] = lease_owner

        stmt = (
            sa.update(AIChatRun)
            .where(
                AIChatRun.id == run_id,
                AIChatRun.status.in_([s.value for s in allowed_from]),
            )
            .values(**values)
            .returning(AIChatRun.id)
        )
        won = (await self._db.execute(stmt)).scalar_one_or_none() is not None
        if not won:
            logger.debug(
                "run %s 迁移到 %s 未命中（当前状态已不在 %s）",
                run_id, new_status.value, sorted(s.value for s in allowed_from),
            )
        return won

    async def mark_running(self, run_id: UUID, *, lease_owner: str | None = None) -> bool:
        """queued/interrupted → running。返回是否本次调用取得执行权。"""
        return await self.transition(
            run_id=run_id, new_status=ChatRunStatus.running, lease_owner=lease_owner
        )

    # ------------------------------------------------------------------
    # 终态（恰好一个）
    # ------------------------------------------------------------------
    async def finish_success(
        self,
        *,
        session: AIChatSession,
        run_id: UUID,
        text: str,
        usage: dict[str, Any] | None = None,
        latency_ms: int | None = None,
        model_used: str | None = None,
        tokens_used: int | None = None,
        citations: Any = None,
        context_manifest: Any = None,
        draft_message_id: UUID | None = None,
    ) -> tuple[ChatEvent | None, AIChatMessage | None]:
        """成功终态：CAS → done 与 completed assistant 消息在**同一事务**内完成。

        CAS 未胜出（已被 error / cancelled 抢先）时返回 ``(None, None)`` 且
        **不写任何消息** —— Property 7 的"不存在 completed assistant message"由此成立。

        ``draft_message_id`` 非空时**提升**该草稿行为 completed，而不是插入新行
        （Task 5 的流式路径：``delta`` 事件已经携带草稿的 message_id，若定稿另插一行，
        前端手里的流式消息就永远等不到自己的 ``done``，历史里还会多出一条孤立草稿）。
        提升仍在 CAS 之后 —— CAS 落空即草稿保持 ``draft``，绝不会变成 completed。
        """
        won = await self.transition(
            run_id=run_id,
            new_status=ChatRunStatus.done,
            usage=usage,
            latency_ms=latency_ms,
        )
        if not won:
            return None, None

        if draft_message_id is not None:
            message = await self._promote_draft(
                draft_message_id,
                run_id=run_id,
                text=text,
                citations=citations,
                context_manifest=context_manifest,
                model_used=model_used,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )
        else:
            message = None
        if message is None:
            message = await append_message(
                self._db,
                session,
                role=ChatRole.assistant,
                text=text,
                status=ChatMessageStatus.completed,
                run_id=run_id,
                citations=citations,
                context_manifest=context_manifest,
                model_used=model_used,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )
        row = await self._load(run_id)
        event = self._build_event(
            row,
            TERMINAL_EVENT_BY_RUN_STATUS[ChatRunStatus.done],
            message_id=message.id,
            payload={"usage": usage or {}},
        )
        self._sequencer.forget(run_id)
        return event, message

    async def finish_error(
        self,
        *,
        run_id: UUID,
        error_code: ChatErrorCode,
        latency_ms: int | None = None,
        detail: str | None = None,
    ) -> ChatEvent | None:
        """失败终态。``error`` 必须带稳定 error code（Req 12.5）。

        ``detail`` 只进受控日志，**不**进事件负载 —— 内部 exception 细节不返回客户端。
        """
        if detail:
            logger.warning("run %s 失败 code=%s detail=%s", run_id, error_code.value, detail)
        won = await self.transition(
            run_id=run_id,
            new_status=ChatRunStatus.error,
            error_code=error_code,
            latency_ms=latency_ms,
        )
        if not won:
            return None
        row = await self._load(run_id)
        event = self._build_event(
            row,
            TERMINAL_EVENT_BY_RUN_STATUS[ChatRunStatus.error],
            payload={
                "code": error_code.value,
                "message": ERROR_MESSAGE_ZH[error_code],
            },
        )
        self._sequencer.forget(run_id)
        return event

    async def finish_cancelled(
        self, *, run_id: UUID, latency_ms: int | None = None
    ) -> ChatEvent | None:
        """取消终态。幂等：已取消的 run 再次调用返回 None（不重复发事件）。"""
        won = await self.transition(
            run_id=run_id,
            new_status=ChatRunStatus.cancelled,
            error_code=ChatErrorCode.run_cancelled,
            latency_ms=latency_ms,
        )
        if not won:
            return None
        row = await self._load(run_id)
        event = self._build_event(
            row,
            TERMINAL_EVENT_BY_RUN_STATUS[ChatRunStatus.cancelled],
            payload={
                "code": ChatErrorCode.run_cancelled.value,
                "message": ERROR_MESSAGE_ZH[ChatErrorCode.run_cancelled],
            },
        )
        self._sequencer.forget(run_id)
        return event

    # ------------------------------------------------------------------
    # 业务事件
    # ------------------------------------------------------------------
    async def emit(
        self,
        *,
        run_id: UUID,
        event_type: ChatEventType,
        payload: dict[str, Any] | None = None,
        message_id: UUID | None = None,
    ) -> ChatEvent | None:
        """签发一条**非终态**业务事件；run 已进终态时返回 None（Req 4.5）。

        终态事件必须走 ``finish_*``（它们才做 CAS）—— 这里显式拒绝，避免出现
        "绕过 CAS 发出第二个终态事件"这条路径。
        """
        if event_type in TERMINAL_EVENT_TYPES:
            raise ValueError(
                f"{event_type.value} 是终态事件，必须经 finish_* 的 compare-and-set 签发"
            )
        row = await self._load(run_id)
        if row.status not in NON_TERMINAL_RUN_STATUSES:
            logger.debug(
                "run %s 已处于终态 %s，拒绝追加 %s",
                run_id, row.status.value, event_type.value,
            )
            return None
        return self._build_event(
            row, event_type, message_id=message_id, payload=payload or {}
        )

    async def append_assistant_draft(
        self,
        *,
        session: AIChatSession,
        run_id: UUID,
        text: str,
    ) -> AIChatMessage | None:
        """写 assistant **草稿**（status=draft）。run 已进终态时拒绝。

        草稿供 Task 5 的节流更新使用；定稿一律经 :meth:`finish_success`
        （只有它能写 ``completed``）。
        """
        row = await self._load(run_id)
        if row.status not in _MESSAGE_WRITABLE_STATUSES:
            return None
        return await append_message(
            self._db,
            session,
            role=ChatRole.assistant,
            text=text,
            status=ChatMessageStatus.draft,
            run_id=run_id,
        )

    async def update_assistant_draft(
        self, *, message_id: UUID, text: str, run_id: UUID
    ) -> bool:
        """按节流窗口**原地更新**草稿正文（Design 第 4 步）。

        Req 4.12：``delta`` 走 Redis，数据库只保存摘要 —— 所以这里是 ``UPDATE`` 而不是
        每个窗口插一行。``WHERE status = 'draft'`` 保证已定稿/已失败的消息不会被后到的
        节流写覆盖（终态之后的写入一律无效，Property 7）。
        """
        result = await self._db.execute(
            sa.update(AIChatMessage)
            .where(
                AIChatMessage.id == message_id,
                AIChatMessage.run_id == run_id,
                AIChatMessage.status == ChatMessageStatus.draft.value,
            )
            .values(message_text=text, content_hash=content_hash(text))
            .returning(AIChatMessage.id)
        )
        return result.scalar_one_or_none() is not None

    async def settle_assistant_draft(
        self, *, message_id: UUID, run_id: UUID, status: ChatMessageStatus
    ) -> bool:
        """把草稿结算为 ``failed`` / ``cancelled``（error/cancel 终态的部分正文可见）。

        🔴 拒绝 ``completed``：定稿只能经 :meth:`finish_success` 的 compare-and-set
        —— 否则就出现了第二条终态路径（Property 7 明令终态恰好一个）。
        """
        if status is ChatMessageStatus.completed:
            raise ValueError(
                "completed 只能由 finish_success 的 compare-and-set 写入，"
                "不得经草稿结算旁路"
            )
        result = await self._db.execute(
            sa.update(AIChatMessage)
            .where(
                AIChatMessage.id == message_id,
                AIChatMessage.run_id == run_id,
                AIChatMessage.status == ChatMessageStatus.draft.value,
            )
            .values(status=status.value)
            .returning(AIChatMessage.id)
        )
        return result.scalar_one_or_none() is not None

    async def _promote_draft(
        self,
        message_id: UUID,
        *,
        run_id: UUID,
        text: str,
        citations: Any,
        context_manifest: Any,
        model_used: str | None,
        tokens_used: int | None,
        latency_ms: int | None,
    ) -> AIChatMessage | None:
        """草稿 → completed（同一行）。行不存在或已非 draft 时返回 None 由调用方兜底。"""
        values: dict[str, Any] = {
            "status": ChatMessageStatus.completed.value,
            "message_text": text,
            "content_hash": content_hash(text),
        }
        if citations is not None:
            values["referenced_sources"] = citations
        if context_manifest is not None:
            values["context_manifest"] = context_manifest
        if model_used is not None:
            values["model_used"] = model_used
        if tokens_used is not None:
            values["tokens_used"] = tokens_used
        if latency_ms is not None:
            values["latency_ms"] = latency_ms
        promoted = (
            await self._db.execute(
                sa.update(AIChatMessage)
                .where(
                    AIChatMessage.id == message_id,
                    AIChatMessage.run_id == run_id,
                    AIChatMessage.status == ChatMessageStatus.draft.value,
                )
                .values(**values)
                .returning(AIChatMessage.id)
            )
        ).scalar_one_or_none()
        if promoted is None:
            return None
        await self._db.flush()
        return (
            await self._db.execute(
                sa.select(AIChatMessage).where(AIChatMessage.id == promoted)
            )
        ).scalar_one()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    async def _load(self, run_id: UUID) -> _RunRow:
        row = (
            await self._db.execute(
                sa.select(
                    AIChatRun.id,
                    AIChatRun.session_id,
                    AIChatRun.request_id,
                    AIChatRun.status,
                    AIChatRun.error_code,
                    AIChatRun.queued_at,
                ).where(AIChatRun.id == run_id)
            )
        ).first()
        if row is None:
            raise LookupError(f"run {run_id} 不存在")
        return _RunRow(
            id=row.id,
            session_id=row.session_id,
            request_id=row.request_id,
            status=ChatRunStatus(row.status),
            error_code=row.error_code,
            queued_at=row.queued_at,
        )

    def _build_event(
        self,
        row: _RunRow,
        event_type: ChatEventType,
        *,
        message_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ChatEvent:
        if event_type in MESSAGE_BOUND_EVENT_TYPES and message_id is None:
            raise ValueError(f"{event_type.value} 必须携带 message_id")
        return ChatEvent(
            event_id=format_event_id(self._sequencer.next(row.id)),
            run_id=row.id,
            session_id=row.session_id,
            request_id=row.request_id,
            type=event_type,
            timestamp=_now(),
            message_id=message_id,
            payload=payload or {},
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)
