"""文档级 AI 对话端点

POST /api/ai-chat/runs — 创建幂等 Chat Run（两阶段 API 第一阶段，Task 4）
POST /api/ai-chat/doc/{doc_type}/{doc_id}  — streaming 对话（复用 ai_service）
GET  /api/ai-chat/doc/{doc_type}/{doc_id}/history — 对话历史
POST /api/ai-chat/adopt — 采纳 AI 内容（server-authoritative 确认流，Task 7）

需求: 1.1, 4.1, 4.2, 5.3；dsh-agent-panel-integration Req 8.1/8.6–8.9
属性: D4（确认流门禁：AI 生成内容回写前必经 AIContentMustBeConfirmedRule）
      Property 22/32/33（采纳权威正文、审计只存 ID/hash、下游故障无假成功）
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, get_current_user_sse
from app.models.ai_models import (
    AIChatMessage,
    AIChatRun,
    ChatMessageStatus,
    ChatRole,
    ChatRunStatus,
)
from app.models.core import User
from app.services.ai_chat.adopt import (
    ADOPT_ERROR_HTTP_STATUS,
    ADOPT_ERROR_MESSAGE,
    ADOPT_LOG_FAILED,
    AdoptFailed,
    adopt_message,
)
from app.services.ai_chat.contracts import (
    GLOBAL_KNOWLEDGE_HOST_ID,
    AiChatAction,
    HostRef,
    HostType,
)
from app.services.ai_chat.native_engine import NATIVE_SYSTEM_POLICY
from app.services.ai_chat.host_context import (
    AuthorizedHostContext,
    HostContextResolver,
)
from app.services.ai_chat.run_contract import (
    ERROR_MESSAGE_ZH,
    RUN_EVENTS_URL_TEMPLATE,
    RUN_STARTED_EVENT_SEQ,
    TERMINAL_EVENT_BY_RUN_STATUS,
    ChatErrorCode,
    ChatEvent,
    ChatEventType,
    ChatRunAccepted,
    ChatRunRequest,
    event_seq,
    format_event_id,
)
from app.services.ai_chat.run_coordinator import (
    CancelOutcome,
    RunQuotaExceeded,
    get_coordinator,
)
from app.services.ai_chat.run_events import (
    encode_comment,
    encode_draining,
    encode_event,
    encode_heartbeat,
)
from app.services.ai_chat.run_service import ChatRunService
from app.services.ai_service import AIService
from app.services import doc_chat_persistence
from app.services.doc_ai_context_builder import ChatContext, ContextBuilder
from app.services.wp_visibility.denial import ExternalNotFound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-chat", tags=["doc-ai-chat"])


# ---------------------------------------------------------------------------
# 资源授权 + 可信宿主反查前置
# （Feature dsh-agent-panel-integration Task 1 / Req 2.1–2.8，Task 2 / Req 2.3+3.x）
#
# 每个 AI 端点在读取 label / 摘要 / 正文 / 索引片段 / 历史消息之前，必须先经
# ``HostContextResolver``：它内部按"解析最小资源标识 → ResourceAccessResolver 授权
# → 读 label"的固定顺序执行。客户端提交的 project_id / year / doc_id 只作一致性断言，
# 不一致返回 host_context_mismatch。拒绝一律在读取之前发生，对外统一不可枚举 404，
# 内部真实 denial code 写安全审计。
# ---------------------------------------------------------------------------


def _build_host_ref(
    doc_type: str, doc_id: str, project_id: str | None, year: int | None = None
) -> HostRef:
    """把路由参数收敛为受后端枚举约束的 ``HostRef``。

    未登记的 ``doc_type`` 与空 ``doc_id`` 一律映射为不可满足的宿主（后续判定必拒），
    不猜测资源类型、不回退到底稿 loader。无项目参数时使用显式全局知识 sentinel，
    绝不用空字符串伪装有效 project ID。
    """
    try:
        host_type = HostType(doc_type)
    except ValueError:
        raise ExternalNotFound() from None

    asserted_project = None
    if project_id:
        try:
            asserted_project = UUID(project_id)
        except (ValueError, TypeError):
            raise ExternalNotFound() from None

    if host_type is HostType.global_knowledge:
        # 受限全局知识模式：ID 用显式 sentinel。project 断言**照原样透传**——
        # 全局模式本就没有项目绑定，带 project 断言即客户端契约错误，
        # 由 HostContextResolver 显式判 host_context_mismatch，不静默丢弃（Req 2.3）。
        return HostRef(
            type=host_type,
            id=GLOBAL_KNOWLEDGE_HOST_ID,
            project_id_assertion=asserted_project,
            year_assertion=year,
        )
    return HostRef(
        type=host_type,
        id=doc_id or "",
        project_id_assertion=asserted_project,
        year_assertion=year,
    )


async def _authorize_doc_host(
    db: AsyncSession,
    current_user: User,
    *,
    doc_type: str,
    doc_id: str,
    project_id: str | None,
    action: AiChatAction,
    entrypoint: str,
    year: int | None = None,
) -> AuthorizedHostContext:
    """端点唯一的授权 + 宿主反查入口。

    返回的 ``AuthorizedHostContext`` 是下游（ContextBuilder / 会话定位 / 采纳）唯一可信的
    项目、年度、资源类型与资源 ID 来源；客户端传入的同名字段一律不再被下游消费。
    """
    host = _build_host_ref(doc_type, doc_id, project_id, year)
    resolver = HostContextResolver(db)
    return await resolver.enforce(current_user, host, action, entrypoint=entrypoint)


# ===========================================================================
# POST /api/ai-chat/runs — 创建幂等 Chat Run（Task 4）
#
# 两阶段 API 的第一阶段：本端点**只创建/返回 run**，不保持长连接、不调用模型。
# 第二阶段 `GET /runs/{run_id}/events`（Task 5）订阅事件；断线重连订阅原 run，
# 不重新 POST（Req 4.1）。
#
# 请求体的越权字段（engine / 权限 scope / 资源正文 / 客户端 message content）由
# `ChatRunRequest` 在解析期拒绝（Req 4.2）；HostContext 授权先于任何
# session / run / message 写入（Req 2.1，Property 1/2）。
# ===========================================================================


@router.post(
    "/runs",
    response_model=ChatRunAccepted,
    summary="创建幂等 Chat Run",
    response_description="run 标识、状态、能力快照、事件订阅地址与首个事件",
)
async def create_chat_run(
    req: ChatRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatRunAccepted:
    """创建（或幂等命中）一个 Chat Run。

    同一 ``(actor, session, idempotency_key)`` 重复提交返回**原 run**，不重复保存用户
    消息、不重复调用 engine（Req 4.6）；响应的 ``replayed=true`` 即表示命中既有 run。

    需求: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 10.2, 13.6
    属性: 6（会话与 Run 并发幂等）、7（Run 唯一终态）
    """
    creation = await ChatRunService(db).create_run(current_user, req)
    await db.commit()
    response = creation.to_response()

    # Task 5 / Design 第 2 步：**commit 之后**才入队 —— 提交前入队会让 executor 读到
    # 尚未可见的 run 行（另一个连接看不到未提交数据），租约与 mark_running 都会落空。
    try:
        await get_coordinator().submit(creation)
    except RunQuotaExceeded as quota:
        # 队列满：run 已被落成 error/rate_limited 终态并发出 quota 事件（Req 13.6）。
        # 这里把 typed 结果如实回给创建响应，而不是伪装成 queued 让前端白等。
        logger.warning(
            "[ai-chat] run %s 因队列已满被拒（queue_limit=%s active_limit=%s）",
            creation.run_id, quota.queue_limit, quota.active_limit,
        )
        response = response.model_copy(
            update={
                "status": ChatRunStatus.error,
                "error_code": ChatErrorCode.rate_limited,
            }
        )
    return response


# ===========================================================================
# GET /api/ai-chat/runs/{run_id}/events — SSE 回放 + 订阅（Task 5）
#
# 🔴 路由路径由 `RUN_EVENTS_URL_TEMPLATE` **派生**（不是照抄一遍字面量）：创建响应里
# 回给前端的 `events_url` 与这里注册的真实路径必须同源，否则前端拿到一个 404 地址。
# ===========================================================================

RUN_EVENTS_ROUTE = RUN_EVENTS_URL_TEMPLATE.removeprefix("/api/ai-chat")
RUN_CANCEL_ROUTE = RUN_EVENTS_ROUTE.removesuffix("/events") + "/cancel"


async def _load_owned_run(
    db: AsyncSession, run_id: UUID, actor_id: UUID
) -> tuple[ChatRunStatus, UUID, UUID, str | None]:
    """读取属于当前用户的 run（否则不可枚举 404）。

    授权判据是 ``actor_id`` 相等 —— run 的事件流里有模型正文与上下文清单，
    绝不能靠"知道 run_id 就能订阅"（Req 2.1/2.5）。
    """
    row = (
        await db.execute(
            sa.select(
                AIChatRun.status,
                AIChatRun.session_id,
                AIChatRun.request_id,
                AIChatRun.error_code,
                AIChatRun.actor_id,
            ).where(AIChatRun.id == run_id)
        )
    ).first()
    if row is None or row.actor_id != actor_id:
        raise ExternalNotFound()
    return (
        ChatRunStatus(row.status),
        row.session_id,
        row.request_id,
        row.error_code,
    )


async def _synthesize_terminal(
    db: AsyncSession,
    *,
    run_id: UUID,
    session_id: UUID,
    request_id: UUID,
    status: ChatRunStatus,
    error_code: str | None,
    after_seq: int,
) -> ChatEvent | None:
    """流里已无终态事件（TTL 过期 / 服务重启）时，从数据库状态**补发**一个。

    Req 4.9：重启后 active run 必须能看到可识别的中止状态。少了这一步，重连的客户端
    会永远等一个已经不存在的终态（表现为"转圈到天荒地老"）。

    ``after_seq`` 保证补发事件的 ID **大于**本次已回放的最后一条 —— 否则客户端的
    ``Last-Event-ID`` 会往回跳，下次重连把中间的事件又收一遍。

    ``done`` 的 ``message_id`` 从库里真实的 completed assistant 消息取（Req 4.4 要求
    server-issued）；取不到就不补发 done —— 宁可让客户端去拉 history，也不伪造消息 ID。
    """
    etype = TERMINAL_EVENT_BY_RUN_STATUS.get(status)
    if etype is None:
        return None
    message_id: UUID | None = None
    payload: dict[str, object] = {"replayed": True}
    if etype is ChatEventType.done:
        message_id = (
            await db.execute(
                sa.select(AIChatMessage.id)
                .where(
                    AIChatMessage.run_id == run_id,
                    AIChatMessage.role == ChatRole.assistant,
                    AIChatMessage.status == ChatMessageStatus.completed.value,
                )
                .order_by(AIChatMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if message_id is None:
            return None
    else:
        try:
            code = (
                ChatErrorCode(error_code)
                if error_code
                else ChatErrorCode.run_interrupted
            )
        except ValueError:
            code = ChatErrorCode.run_interrupted
        payload |= {"code": code.value, "message": ERROR_MESSAGE_ZH[code]}
    return ChatEvent(
        event_id=format_event_id(max(after_seq, RUN_STARTED_EVENT_SEQ) + 1),
        run_id=run_id,
        session_id=session_id,
        request_id=request_id,
        type=etype,
        timestamp=datetime.now(timezone.utc),
        message_id=message_id,
        payload=payload,
    )


@router.get(
    RUN_EVENTS_ROUTE,
    summary="订阅 Chat Run 事件（SSE，支持 Last-Event-ID 回放）",
)
async def stream_run_events(
    run_id: UUID,
    request: Request,
    last_event_id: str | None = Query(
        default=None, description="断线重连的续传点（等价于 Last-Event-ID 头）"
    ),
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_sse),
):
    """按 ``Last-Event-ID`` 回放并订阅后续事件，带心跳并接入 ``sse_registry`` drain。

    需求: 4.1（重连订阅原 run，不重新调用模型）、4.4、4.8（自定界帧 + 心跳）、
          4.9（drain 可识别中止）、4.12（回放来自有界 Redis Stream / 等价缓冲）
    属性: 9（SSE 任意分片与续传等价）
    """
    status, session_id, request_id, error_code = await _load_owned_run(
        db, run_id, current_user.id
    )
    resume_from = last_event_id_header or last_event_id
    stream = get_coordinator().stream

    # 已终态的 run：只回放，不挂长连接。若缓冲里已经没有终态事件（TTL 过期 / 重启），
    # 从数据库补一个可识别终态再关闭 —— 绝不让客户端空等（Req 4.9）。
    replay_only: list[ChatEvent] | None = None
    fallback_terminal: ChatEvent | None = None
    if status in TERMINAL_EVENT_BY_RUN_STATUS:
        replayed = await stream.history(run_id, resume_from)
        if not any(e.is_terminal for e in replayed):
            replay_only = replayed
            last_seq = (
                event_seq(replayed[-1].event_id)
                if replayed
                else (event_seq(resume_from) if resume_from else 0)
            )
            fallback_terminal = await _synthesize_terminal(
                db,
                run_id=run_id,
                session_id=session_id,
                request_id=request_id,
                status=status,
                error_code=error_code,
                after_seq=last_seq,
            )
            if fallback_terminal is None:
                # 无法诚实补发（如 done 但找不到 completed 消息）⇒ 只回放已有事件后关闭。
                replay_only = replayed

    from app.core.config import settings

    heartbeat = float(settings.AI_CHAT_SSE_HEARTBEAT_SECONDS)
    max_seconds = float(settings.AI_CHAT_SSE_MAX_SECONDS)

    async def event_generator() -> AsyncGenerator[str, None]:
        from app.core.sse_registry import sse_registry

        conn = sse_registry.register()
        try:
            # 先发一条注释帧：立刻打通代理缓冲，且不推进 Last-Event-ID。
            yield encode_comment(f"run {run_id} 已连接")
            if replay_only is not None:
                for ev in replay_only:
                    yield encode_event(ev)
                if fallback_terminal is not None:
                    yield encode_event(fallback_terminal)
                return
            async for item in stream.follow(
                run_id,
                after_event_id=resume_from,
                heartbeat_interval=heartbeat,
                max_seconds=max_seconds,
                stop=lambda: conn.is_closed,
            ):
                if conn.is_closed:
                    # Req 4.9：drain 帧**不带 id** ⇒ 客户端重连时仍从最后一条业务事件续传。
                    yield encode_draining()
                    return
                if item is None:
                    yield encode_heartbeat()
                    continue
                yield encode_event(item)
            if conn.is_closed:
                yield encode_draining()
        except asyncio.CancelledError:  # pragma: no cover - 客户端断开
            logger.debug("[ai-chat] run %s 的 SSE 连接被取消", run_id)
            raise
        finally:
            sse_registry.unregister(conn)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(RUN_CANCEL_ROUTE, summary="取消 Chat Run（幂等）")
async def cancel_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """幂等取消：重复调用不会产生第二个终态事件，已终态则原样返回。

    需求: 4.5、4.7（取消传播到 engine / 工具 / 子 Agent / 排队任务）
    属性: 7（终态恰好一个）、8（取消传播到全部后代）
    """
    outcome: CancelOutcome = await get_coordinator().cancel(
        db, run_id, actor_id=current_user.id
    )
    return outcome.as_response()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class DocChatRequest(BaseModel):
    """文档级对话请求"""
    query: str = Field(..., min_length=1, max_length=4000, description="用户提问")
    year: int = Field(..., description="审计年度")
    project_id: str = Field(..., description="项目 ID")
    extra_scopes: list[str] | None = Field(None, description="额外知识范围（文件夹 ID 列表）")


class AdoptHostRef(BaseModel):
    """采纳目标宿主（``HostRef`` 的请求体形态）。

    ``project_id`` / ``year`` 只是**一致性断言**：服务端从目标资源反查权威值，
    不一致即拒绝（Req 2.3）。
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., description="宿主类型（HostType 取值）")
    id: str = Field(..., min_length=1, description="宿主稳定 ID")
    project_id: str | None = Field(None, description="项目 ID（仅作一致性断言）")
    year: int | None = Field(None, description="审计年度（仅作一致性断言）")


class AdoptRequest(BaseModel):
    """采纳 AI 内容回写请求（Task 7：server-authoritative）。

    🔴 **不接受正文**。旧契约有 ``content`` 字段并被原样写进 ``ai_content_log``，
    等于让浏览器决定"AI 说过什么"。现在只提交 message ID + 宿主 + 目标 + 幂等键，
    正文由服务端按 message ID 从 ``ai_chat_message`` 读取（Req 8.1/8.6）。

    ``extra="forbid"``：客户端若仍发 ``content`` / ``confidence`` / ``project_id``
    等越权字段，直接 422 拒绝 —— 而不是被 pydantic 静默丢弃后让调用方以为生效。
    """

    model_config = ConfigDict(extra="forbid")

    message_id: UUID = Field(..., description="服务端签发的 assistant 消息 ID")
    host: AdoptHostRef = Field(..., description="采纳目标宿主")
    target_cell: str | None = Field(None, max_length=120, description="目标单元格引用")
    target_field: str | None = Field(None, max_length=120, description="目标字段名")
    idempotency_key: UUID = Field(..., description="客户端生成的幂等键")


# ---------------------------------------------------------------------------
# 对话历史：DB 持久化（doc_chat_persistence，替代原内存字典 _chat_history）
# ---------------------------------------------------------------------------

_MAX_HISTORY_PER_DOC = 50


# ---------------------------------------------------------------------------
# POST /api/ai-chat/doc/{doc_type}/{doc_id} — streaming 对话
# ---------------------------------------------------------------------------

#: 平台政策 system prompt。单一真源 = ``ai_chat.native_engine.NATIVE_SYSTEM_POLICY``
#: （Task 6）。旧 POST 流与新 run 链路必须用同一条政策，否则同一个问题在两个入口得到
#: 风格不同的回答，"迁移完成"这件事就无法验证。
SYSTEM_PROMPT = NATIVE_SYSTEM_POLICY


@router.post("/doc/{doc_type}/{doc_id}")
async def doc_ai_chat(
    doc_type: str,
    doc_id: str,
    req: DocChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """文档级 AI 对话 — SSE streaming 响应

    复用 ContextBuilder 构建上下文 → ai_service streaming → 留痕。
    需求: 1.1, 5.3

    TODO [zero-downtime-deployment Task 8.1]: 接入 sse_registry
    - 进入 _stream_chat 时 register，退出时 unregister
    - from app.core.sse_registry import sse_registry
    """
    # ① 资源授权 + 宿主反查（先于任何 label / 正文 / 索引读取；
    #    拒绝 → 不可枚举 404 + denial audit；客户端断言不一致 → host_context_mismatch）
    host = await _authorize_doc_host(
        db,
        current_user,
        doc_type=doc_type,
        doc_id=doc_id,
        project_id=req.project_id,
        action=AiChatAction.read,
        entrypoint="ai_chat.doc_chat",
        year=req.year,
    )
    project_id = host.project_id
    if project_id is None:
        # 受限全局知识模式不提供项目级文档对话（项目工具禁用，不猜测最近项目）。
        raise ExternalNotFound()

    # ② 已授权范围内构建上下文；失败 fail-closed（Req 2.8：不得降级为空上下文继续调用模型）
    builder = ContextBuilder(db)
    try:
        context = await builder.build(
            host=host,
            query=req.query,
            user=current_user,
            extra_scopes=req.extra_scopes,
        )
    except Exception as e:
        logger.exception("ContextBuilder.build 失败（fail-closed，不降级为空上下文）: %s", e)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "context_build_failed",
                "message": "无法加载当前文档上下文，请稍后重试",
            },
        ) from e

    return StreamingResponse(
        # 会话定位一律用服务端 canonical 宿主标识（客户端可能传的是稳定 section key），
        # 保证同一宿主在不同入口拿到同一会话（Req 4.11 的前置）。
        _stream_chat(
            host.resource_type.value,
            host.resource_id,
            req.query,
            context,
            current_user,
            project_id,
        ),
        media_type="text/event-stream",
    )


async def _stream_chat(
    doc_type: str,
    doc_id: str,
    query: str,
    context: ChatContext,
    user: User,
    project_id: UUID,
) -> AsyncGenerator[str, None]:
    """SSE streaming 生成器：构建 messages → ai_service streaming → 收集完整回复 → 留痕

    ⚠️ 自建独立 session：FastAPI 在端点 return StreamingResponse 时即关闭 get_db
    的请求级 session，而本生成器在 response 返回后才被 ASGI 消费执行——若复用请求
    session，commit 会作用在已关闭 session 上（历史写入时序不可控，紧随的 GET
    history 读到 0 条）。故用独立 async_session 管理完整事务。
    """
    from app.core.database import async_session

    async with async_session() as db:
        # 获取/创建文档级会话 + 读历史（DB 持久化）
        session = await doc_chat_persistence.get_or_create_session(
            db, doc_type, doc_id, user.id, project_id
        )
        history = await doc_chat_persistence.get_history(
            db, doc_type, doc_id, user.id, limit=_MAX_HISTORY_PER_DOC
        )

        # 构建 LLM messages
        messages = _build_messages(doc_type, doc_id, query, context, history)

        # 记录用户消息到 DB + 提交（确保用户消息先落库）
        await doc_chat_persistence.append_message(db, session, "user", query)
        await db.commit()

        # 发送引用来源（作为第一个 SSE 事件）
        if context.citations:
            citations_data = [
                {
                    "source_type": c.source_type,
                    "source_id": c.source_id,
                    "source_name": c.source_name,
                    "paragraph_index": c.paragraph_index,
                    "doc_version": c.doc_version,
                    "is_stale": c.is_stale,
                }
                for c in context.citations
            ]
            yield f"data: {json.dumps({'type': 'citations', 'data': citations_data}, ensure_ascii=False)}\n\n"

        # 流式调用 ai_service
        ai_service = AIService(db)
        full_response = ""

        try:
            stream_gen = await ai_service.chat_completion(
                messages=messages,
                stream=True,
                temperature=0.3,
            )
            async for chunk in stream_gen:
                full_response += chunk
                yield f"data: {json.dumps({'type': 'content', 'data': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("doc_ai_chat streaming 失败")
            yield f"data: {json.dumps({'type': 'error', 'data': f'AI 服务暂不可用: {e}'}, ensure_ascii=False)}\n\n"

        # 记录助手回复到 DB + 提交
        if full_response:
            await doc_chat_persistence.append_message(db, session, "assistant", full_response)
        await db.commit()

        # 发送完成事件
        yield f"data: {json.dumps({'type': 'done', 'data': {'token_estimate': context.token_estimate}}, ensure_ascii=False)}\n\n"


def _build_messages(
    doc_type: str,
    doc_id: str,
    query: str,
    context: ChatContext,
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """构建 LLM 消息列表（system + context + history + user）"""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # 注入上下文
    context_parts: list[str] = []
    if context.project_summary:
        context_parts.append(f"【项目信息】\n{context.project_summary}")
    if context.doc_excerpt:
        context_parts.append(f"【当前文档内容】\n{context.doc_excerpt}")
    if context.knowledge_hits:
        knowledge_text = "\n\n".join(
            f"【{hit.source_name or hit.source_type}】\n{hit.content}"
            for hit in context.knowledge_hits[:5]
        )
        context_parts.append(f"【关联知识】\n{knowledge_text}")

    if context_parts:
        messages.append({
            "role": "system",
            "content": "\n\n".join(context_parts),
        })

    # 添加历史消息（最近 10 轮）
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # 当前用户消息
    messages.append({"role": "user", "content": query})

    return messages


# ---------------------------------------------------------------------------
# GET /api/ai-chat/doc/{doc_type}/{doc_id}/history — 对话历史
# ---------------------------------------------------------------------------


@router.get("/doc/{doc_type}/{doc_id}/history")
async def get_chat_history(
    doc_type: str,
    doc_id: str,
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取文档级对话历史（DB 持久化，重启不丢）

    需求: 5.2（本地缓存断网可查历史）
    授权: Req 2.1/2.4 —— 与对话/清除/采纳使用同一 ResourceAccessResolver 决策，
    拒绝在读取任何历史消息之前发生。
    """
    host = await _authorize_doc_host(
        db,
        current_user,
        doc_type=doc_type,
        doc_id=doc_id,
        project_id=project_id,
        action=AiChatAction.history,
        entrypoint="ai_chat.history",
    )
    history = await doc_chat_persistence.get_history(
        db,
        host.resource_type.value,
        host.resource_id,
        current_user.id,
        limit=_MAX_HISTORY_PER_DOC,
    )
    return {"messages": history, "total": len(history)}


@router.delete("/doc/{doc_type}/{doc_id}/history")
async def clear_chat_history(
    doc_type: str,
    doc_id: str,
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清除文档级对话历史（前端 clearHistory 调用，DB 持久化清除）

    授权: Req 2.1/2.4 —— 与对话/历史/采纳同一决策，拒绝先于任何清除副作用。
    """
    host = await _authorize_doc_host(
        db,
        current_user,
        doc_type=doc_type,
        doc_id=doc_id,
        project_id=project_id,
        action=AiChatAction.clear,
        entrypoint="ai_chat.clear",
    )
    cleared = await doc_chat_persistence.clear_history(
        db, host.resource_type.value, host.resource_id, current_user.id
    )
    await db.commit()
    return {"success": True, "cleared": cleared}


# ---------------------------------------------------------------------------
# POST /api/ai-chat/adopt — 采纳 AI 内容回写（走确认流）
# ---------------------------------------------------------------------------


@router.post("/adopt")
async def adopt_ai_content(
    req: AdoptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """采纳 AI 生成内容 — server-authoritative + 幂等 + fail-closed（Task 7）

    三段式：

    1. **授权 + 宿主反查**（Req 2.1/2.3/8.8）：``adopt`` 在 Task 1 已登记为写宿主动作，
       经 ``workpaper.ai_generate`` 写入口 + ``ai_generate``/``ai_confirm`` capability；
       QC/EQCR 默认只读因此在此被拒。客户端 ``host.project_id`` 只作一致性断言。
    2. **权威正文**（Req 8.1/8.6）：按 message ID 从 ``ai_chat_message`` 读取 completed
       assistant 正文与服务端 ``content_hash``，并校验 message→run→session→actor→
       HostContext 整条归属链。请求体里**没有** content 字段可供篡改。
    3. **fail-closed 写入**（Req 8.7/8.9）：收据幂等 + ``wrap_ai_output_with_log``；
       log ID 为空、行不存在、审计或 commit 失败 ⇒ 全部回滚并返回 ``adopt_log_failed``。
       只有拿到真实 log ID 才返回"已进入确认流"。

    Requirements: 8.1, 8.6, 8.7, 8.8, 8.9
    Properties: 22（权威正文与失败回滚）、32（审计只存 ID/hash）、33（无假成功）
    """
    host = await _authorize_doc_host(
        db,
        current_user,
        doc_type=req.host.type,
        doc_id=req.host.id,
        project_id=req.host.project_id,
        action=AiChatAction.adopt,
        entrypoint="ai_chat.adopt",
        year=req.host.year,
    )
    try:
        outcome = await adopt_message(
            db,
            actor_id=current_user.id,
            host=host,
            message_id=req.message_id,
            idempotency_key=req.idempotency_key,
            target_cell=req.target_cell,
            target_field=req.target_field,
        )
    except AdoptFailed as exc:
        # 下游失败绝不产生成功文案（Property 33）；内部异常细节只进日志（Req 12.5）。
        raise HTTPException(
            status_code=ADOPT_ERROR_HTTP_STATUS.get(exc.code, 503),
            detail={
                "code": exc.code,
                "message": ADOPT_ERROR_MESSAGE.get(
                    exc.code, ADOPT_ERROR_MESSAGE[ADOPT_LOG_FAILED]
                ),
            },
        ) from exc

    return outcome.as_response()


# ===========================================================================
# GET /api/ai-chat/mentionable — Mention 聚合搜索（Task 14 / Req 5.2–5.9）
#
# 前端 ChatMentionPicker 发起 @-search，服务端在 ResourceAccessResolver 后统一返回
# {type, id, label, sublabel, jump_route}。搜索失败/超时/能力不可用与成功空结果
# 使用不同的 type_status 信号（Req 5.6）。
# ===========================================================================


class MentionableQuery(BaseModel):
    """mentionable 搜索请求参数。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field("", max_length=200, description="搜索关键词")
    type_filter: str | None = Field(None, max_length=50, description="资源类型过滤")
    limit: int = Field(10, ge=1, le=50, description="每类型最大返回数")


class MentionableItem(BaseModel):
    """单条 mention 搜索结果。"""

    type: str
    id: str
    label: str
    sublabel: str = ""
    jump_route: str = ""


class MentionableResponse(BaseModel):
    """mentionable 搜索响应。"""

    items: list[MentionableItem]
    type_status: dict[str, str] = Field(
        default_factory=dict,
        description="各类型搜索状态: success/empty/error/unavailable/timeout",
    )


@router.get(
    "/mentionable",
    response_model=MentionableResponse,
    summary="Mention 聚合搜索",
    response_description="授权过滤后的可引用资源列表（含状态信号）",
)
async def search_mentionable(
    query: str = Query("", max_length=200, description="搜索关键词"),
    type_filter: str | None = Query(None, max_length=50, description="资源类型过滤"),
    limit: int = Query(10, ge=1, le=50, description="每类型最大返回数"),
    host_type: str = Query(..., description="当前宿主类型"),
    host_id: str = Query(..., max_length=128, description="当前宿主 ID"),
    project_id: str | None = Query(None, description="项目 ID 断言"),
    year: int | None = Query(None, description="年度断言"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MentionableResponse:
    """执行 mention 聚合搜索。

    需求: 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 5.9
    属性: Property 11（搜索结果已授权）、12（label 由服务端加载）、14（预算策略感知）

    流程：
    1. 解析并授权当前宿主（与 /runs 同一 HostContextResolver 入口）
    2. 调用 MentionSearchService 并行搜索各类型
    3. 经 ResourceAccessResolver.filter_visible_resources 过滤
    4. 返回授权后的 label / sublabel / jump_route
    """
    # ① 授权当前宿主
    host = await _authorize_doc_host(
        db,
        current_user,
        doc_type=host_type,
        doc_id=host_id,
        project_id=project_id,
        action=AiChatAction.search,
        entrypoint="ai_chat.mentionable",
        year=year,
    )

    # ② 聚合搜索
    from app.services.ai_chat.mention_service import MentionSearchService

    service = MentionSearchService(db)
    result = await service.search(
        user=current_user,
        host=host,
        query=query,
        type_filter=type_filter,
        limit=limit,
    )

    # ③ 转为响应模型
    items = [
        MentionableItem(
            type=c.type,
            id=c.id,
            label=c.label,
            sublabel=c.sublabel,
            jump_route=c.jump_route,
        )
        for c in result.items
    ]

    return MentionableResponse(
        items=items,
        type_status=result.type_status,
    )


# ===========================================================================
# POST /api/ai-chat/attachments — 会话附件安全上传（Task 16 / Req 7.2–7.9）
# DELETE /api/ai-chat/attachments/{attachment_id} — 删除附件
# ===========================================================================


class AttachmentUploadResponse(BaseModel):
    """附件上传响应（只返回 ID 和状态，Req 7.2）。"""

    attachment_id: str
    status: str  # created / replayed
    replayed: bool = False
    ocr_status: str = "pending"


@router.post(
    "/attachments",
    response_model=AttachmentUploadResponse,
    summary="上传会话附件",
    response_description="附件 ID、状态与 OCR 初始状态",
)
async def upload_attachment(
    request: Request,
    session_id: UUID = Query(..., description="当前会话 ID"),
    host_type: str = Query(..., description="当前宿主类型"),
    host_id: str = Query(..., max_length=128, description="当前宿主 ID"),
    project_id: str | None = Query(None, description="项目 ID 断言"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachmentUploadResponse:
    """安全上传会话附件。

    需求: 7.2, 7.3, 7.4, 7.7, 7.8
    属性: Property 18（安全校验）、19（OCR 状态机）、20（ownership 绑定）

    校验顺序：
    1. 宿主授权（upload 动作）
    2. 文件安全校验（扩展名/MIME/大小/像素/页数/数量）
    3. 幂等 upsert（SHA-256 去重）
    4. 写入文件系统（随机命名）
    """
    from app.services.ai_chat.attachment_service import (
        AttachmentService,
        AttachmentValidationError,
    )

    # ① 授权
    await _authorize_doc_host(
        db,
        current_user,
        doc_type=host_type,
        doc_id=host_id,
        project_id=project_id,
        action=AiChatAction.upload,
        entrypoint="ai_chat.attachment_upload",
    )

    # ② 读取上传文件
    form = await request.form()
    upload_file = form.get("file")
    if upload_file is None:
        raise HTTPException(status_code=400, detail={"code": "no_file", "message": "请选择文件"})

    content = await upload_file.read()
    original_name = getattr(upload_file, "filename", "") or "unnamed"
    mime_type = getattr(upload_file, "content_type", "") or "application/octet-stream"

    # ③ 上传
    service = AttachmentService(db)
    try:
        result = await service.upload(
            owner_id=current_user.id,
            project_id=UUID(project_id) if project_id else None,
            session_id=session_id,
            file_content=content,
            original_name=original_name,
            mime_type=mime_type,
        )
    except AttachmentValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    await db.commit()
    return AttachmentUploadResponse(**result.as_dict())


@router.delete(
    "/attachments/{attachment_id}",
    summary="删除会话附件",
)
async def delete_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """删除用户自己的会话附件。"""
    from app.services.ai_chat.attachment_service import AttachmentService

    service = AttachmentService(db)
    deleted = await service.delete_attachment(attachment_id, owner_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="附件不存在或无权删除")
    await db.commit()
    return {"deleted": True}


# ===========================================================================
# POST /api/ai-chat/notes — 幂等项目笔记转存（Task 18 / Req 8.1–8.9）
# ===========================================================================


class NoteSaveRequestBody(BaseModel):
    """笔记转存请求体。"""

    model_config = ConfigDict(extra="forbid")

    message_ids: list[UUID] = Field(
        ..., min_length=1, max_length=20, description="completed assistant message IDs"
    )
    name: str = Field(..., min_length=1, max_length=200, description="用户确认的笔记名称")
    host_type: str = Field(..., description="当前宿主类型")
    host_id: str = Field(..., max_length=128, description="当前宿主 ID")
    project_id: str | None = Field(None, description="项目 ID 断言")
    year: int | None = Field(None, description="年度断言")
    idempotency_key: str = Field(
        ..., min_length=1, max_length=128, description="幂等键（防重复转存）"
    )
    session_id: UUID = Field(..., description="当前会话 ID")


class NoteSaveResponseBody(BaseModel):
    """笔记转存响应。"""

    document_id: str
    folder_id: str
    name: str
    replayed: bool = False
    jump_route: str = ""


@router.post(
    "/notes",
    response_model=NoteSaveResponseBody,
    summary="项目笔记转存",
    response_description="新建文档 ID、文件夹 ID 和跳转路由",
)
async def save_ai_note(
    req: NoteSaveRequestBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteSaveResponseBody:
    """将 AI 对话内容转存为项目笔记。

    需求: 8.1, 8.2, 8.3, 8.4, 8.8, 8.9
    属性: Property 21（幂等收据）、32（哈希链审计）

    流程：
    1. 授权宿主（note_create 动作）
    2. claim_action_receipt 防重
    3. 从 DB 读取 completed assistant 正文（服务端权威来源）
    4. 定位/创建目标文件夹
    5. 写入 KnowledgeDocument
    6. settle receipt
    """
    from app.services.ai_chat.note_service import NoteSaveFailed, save_note

    # ① 授权
    host = await _authorize_doc_host(
        db,
        current_user,
        doc_type=req.host_type,
        doc_id=req.host_id,
        project_id=req.project_id,
        action=AiChatAction.note_create,
        entrypoint="ai_chat.note_save",
        year=req.year,
    )

    # ② 执行转存
    try:
        result = await save_note(
            db,
            user=current_user,
            actor_id=current_user.id,
            host=host,
            session_id=req.session_id,
            message_ids=req.message_ids,
            name=req.name,
            idempotency_key=req.idempotency_key,
        )
    except NoteSaveFailed as exc:
        raise HTTPException(
            status_code=422 if exc.code != "internal_error" else 503,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    await db.commit()
    return NoteSaveResponseBody(**result.as_dict())


# ===========================================================================
# GET /api/ai-chat/review-prompt — 复核模式预览（Task 20 / Req 9.1–9.6）
#
# 只返回 source_level/tips/checklist/risk_areas/version，**不**返回正文。
# ===========================================================================


class ReviewPromptPreviewResponse(BaseModel):
    """复核模式预览响应（不含正文，Req 9.2）。"""

    enabled: bool
    source_level: str = ""
    tips: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    risk_areas: list[dict[str, str]] = Field(default_factory=list)
    version: str = ""
    wp_code: str = ""
    sheet_name: str = ""


@router.get(
    "/review-prompt",
    response_model=ReviewPromptPreviewResponse,
    summary="复核模式提示词预览",
    response_description="source_level/tips/checklist/risk_areas/version（不含正文）",
)
async def get_review_prompt_preview(
    host_type: str = Query(..., description="当前宿主类型"),
    host_id: str = Query(..., max_length=128, description="当前宿主 ID"),
    project_id: str | None = Query(None, description="项目 ID 断言"),
    year: int | None = Query(None, description="年度断言"),
    sheet_name: str | None = Query(None, max_length=200, description="目标 sheet 名"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewPromptPreviewResponse:
    """获取复核模式提示词预览。

    需求: 9.1, 9.2, 9.4, 9.5
    属性: Property 23（复核模式独立于引擎）、24（引擎行为一致性）

    仅 workpaper 宿主可用；非 workpaper 返回 enabled=False。
    prompt 加载失败返回 typed error（Req 9.5），不静默降级。
    """
    from app.services.ai_chat.review_mode import (
        ReviewModeFailed,
        resolve_review_mode,
    )

    # ① 授权
    host = await _authorize_doc_host(
        db,
        current_user,
        doc_type=host_type,
        doc_id=host_id,
        project_id=project_id,
        action=AiChatAction.review,
        entrypoint="ai_chat.review_prompt",
        year=year,
    )

    # ② 解析复核模式
    try:
        ctx = await resolve_review_mode(
            db, host=host, review_mode=True, sheet_name=sheet_name,
        )
    except ReviewModeFailed as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    if ctx is None:
        return ReviewPromptPreviewResponse(enabled=False)

    return ReviewPromptPreviewResponse(
        enabled=True,
        source_level=ctx.source_level,
        tips=ctx.tips,
        checklist=ctx.checklist,
        risk_areas=ctx.risk_areas,
        version=ctx.version,
        wp_code=ctx.wp_code,
        sheet_name=ctx.sheet_name or "",
    )


# ===========================================================================
# GET /api/ai-chat/metrics — AI Chat 指标端点（Task 12 / Req 12.8）
#
# 🔴 独立端点，不走 ResponseWrapperMiddleware（直接返回 prometheus text format）。
# 用于内部可观测：active/queued runs、latency、tokens、denials、attachment bytes 等。
# ===========================================================================


@router.get(
    "/metrics",
    summary="AI Chat 结构化指标（prometheus text format）",
    tags=["ai-chat-metrics"],
    include_in_schema=False,  # 内部端点，不需暴露到 OpenAPI
)
async def ai_chat_metrics():
    """暴露 AI Chat Run 相关 Prometheus 指标。

    不含 token 正文、完整正文、附件内容或未脱敏上下文（Req 12.7）。
    """
    from starlette.responses import Response as StarletteResponse

    from app.services.ai_chat.metrics import render_ai_chat_metrics

    body, content_type = render_ai_chat_metrics()
    return StarletteResponse(content=body, media_type=content_type)


# ===========================================================================
# GET /api/ai-chat/quota — 配额信息端点（Task 12 / Req 13.7）
#
# 前端从此端点获取服务端配额单一真源，不复制常量（NFR-2）。
# ===========================================================================


class QuotaInfoResponse(BaseModel):
    """配额信息响应。"""

    rate_limit_per_minute: int
    max_active_runs: int
    max_attachments_per_run: int
    max_context_tokens: int
    mcp_max_calls_per_run: int
    mcp_max_bytes_per_call: int
    dsh_enabled: bool


@router.get(
    "/quota",
    response_model=QuotaInfoResponse,
    summary="获取 AI Chat 配额配置（服务端单一真源）",
)
async def get_quota_info(
    current_user: User = Depends(get_current_user),
):
    """返回当前生效的配额配置（Req 13.7：前端展示值来自此端点，不复制常量）。"""
    from app.core.config import settings

    return QuotaInfoResponse(
        rate_limit_per_minute=settings.AI_CHAT_RATE_LIMIT_PER_MINUTE,
        max_active_runs=settings.AI_CHAT_MAX_ACTIVE_RUNS,
        max_attachments_per_run=settings.AI_CHAT_MAX_ATTACHMENTS_PER_RUN,
        max_context_tokens=settings.AI_CHAT_MAX_CONTEXT_TOKENS,
        mcp_max_calls_per_run=settings.AI_MCP_MAX_CALLS_PER_RUN,
        mcp_max_bytes_per_call=settings.AI_MCP_MAX_BYTES_PER_CALL,
        dsh_enabled=settings.AI_DSH_ENABLED,
    )


# ===========================================================================
# GET /api/ai-chat/capabilities — 引擎能力查询（Task 30 / Req 10.1–10.6, 12.1–12.4）
#
# 前端据此禁用不支持的入口（tools/subagents）并显示中文原因（Req 10.4）。
# 响应包含 engine 选择结果、完整 capability manifest、各服务健康与 gate reason。
# 🔴 不接受请求体 engine 字段（Req 10.1 / Property 24）。
# ===========================================================================


@router.get(
    "/capabilities",
    summary="查询当前 AI 引擎能力与服务健康",
    response_description="引擎能力 manifest、禁用原因与各服务健康状态",
)
async def get_ai_capabilities(
    project_id: str | None = Query(None, description="项目 ID（精确判断 DSH allowlist）"),
    current_user: User = Depends(get_current_user),
):
    """返回当前服务端配置下的引擎能力。

    需求: 10.1（服务端决定 engine）、10.3（capability manifest）、10.4（禁用入口 + 中文原因）、
          10.5（DSH 失败不降级）、10.6（experimental flag）、12.1（local-only 验证）、
          12.2（cloud → local_only_violation）、12.4（各服务 typed error）
    属性: 24（引擎能力与 UI 一致）、25（DSH 失败不降级）、26（Cordis 与工具目录受控）
    """
    from app.services.ai_chat.capability_endpoint import (
        CapabilityResponse,
        get_capabilities,
    )

    parsed_project_id: UUID | None = None
    if project_id:
        try:
            parsed_project_id = UUID(project_id)
        except (ValueError, TypeError):
            pass  # 无效 project_id → 按无项目处理（DSH gate 回落 native）

    result = get_capabilities(project_id=parsed_project_id)
    return result
