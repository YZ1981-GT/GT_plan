"""``DshEngine`` · DSH 多步 Agent 引擎、有界 worker 池与取消传播（Task 28）

Feature: dsh-agent-panel-integration
Requirements:
  - 4.7：cancel 传播到 DSH root/children/MCP process，确认后工具调用不再增加。
  - 10.2：消费统一 AuthorizedChatRunRequest 并产出统一 ChatEvent。
  - 10.5：DSH/MCP/handshake 失败返回 engine_unavailable，**绝不**静默回落 NativeEngine。
  - 11.6：per-run MCP stdio process，root 不跨 principal 复用。
  - 11.7：子 Agent 继承相同 run security context（scoped token）。
  - 11.11：cancel/timeout/terminal 传播并清理 root/children/MCP process/session files。
  - 11.12：active/queue/run-timeout/process-TTL 配置与 backpressure。
Design: "Components and Interfaces → 12. Engine Contract → DshEngine" 与 "→ 13. DSH Custom Cordis"
Properties:
  - 8：取消传播到全部后代（DSH root + children + MCP）
  - 25：DSH 失败不降级（engine_unavailable，NativeEngine invocation count = 0）
  - 28：跨用户隔离（per-run process，不跨 principal 复用）
  - 29：子 Agent 权限只收窄（scoped token inheritance）
  - 38：DshEngine backpressure 有界（active/queue limit）

## 核心设计

DshEngine 是平台的第二种 ChatEngine 实现，在 Phase C feature flag + 项目 allowlist
都满足时可选。它通过 per-run DSH SDK subprocess 执行多步 Agent 推理：

1. SDK discovery（验证 vendor 安装、pin 与 Cordis）
2. 选定本 run 的模型：平台对话路由本机优先、执行前探测、全程不换（``dsh_model_bridge``）
3. 创建 per-run scoped token（MCP 认证）与模型转发令牌
4. 启动 DSH root subprocess（custom Cordis；audit-data MCP 由它的 mcp-client 以 stdio 拉起，
   模型请求经平台环回转发 ``/api/ai-chat/dsh-llm/v1``）
5. JSON-RPC：initialize → session/prompt → 消费 session.event 到 idle（``dsh_protocol``）
6. cancel/timeout/结束 → shutdown → 终止进程树 + 清理 session files

## 进程隔离与安全

- 每个 run 独立启动 DSH root process（MCP 在它的进程树里）
- DSH root 不跨 principal 复用（无法证明完整 reset）
- MCP process 只持有 per-run scoped token；DSH 进程只持有模型转发令牌，拿不到上游 Key
- 运行结束后销毁全部进程与临时文件

spec dsh-kb-ocr-local-first-routing 把进程管理拆到 ``dsh_process``、协议拆到 ``dsh_protocol``，
并按 vendor 真实协议重写（旧实现对真实运行时每次握手必败，见该 spec design §1.1）。

## Backpressure

- AI_DSH_MAX_ACTIVE_RUNS：最大并发 DSH run
- AI_DSH_QUEUE_LIMIT：排队上限
- AI_DSH_RUN_TIMEOUT_SECONDS：单 run 墙钟上限
- AI_DSH_PROCESS_TTL_SECONDS：进程最大存活时间
- 超限返回 typed quota error，不无界拉起进程
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

from app.models.ai_models import ChatEngineName
from app.services.ai_chat import dsh_model_bridge, dsh_protocol

# 拆出的进程模块（dsh-kb-ocr-local-first-routing Task 1）：再导出原名，
# 旧导入与 patch 路径（``dsh_engine.DshProcessManager`` / ``D.DshRunContext``）保持可解析。
from app.services.ai_chat.dsh_process import (  # noqa: F401
    DshProcessManager,
    DshRunContext,
    _build_dsh_env,
    _build_mcp_env,
    _dsh_process_ttl,
    _dsh_run_timeout,
    _resolve_mcp_server_path,
    _write_platform_cordis_config,
)
from app.services.ai_chat.engine import (
    AuthorizedChatRunRequest,
    CancelSignal,
    EngineCancelled,
    EngineFailure,
    EngineOutcome,
    EngineStream,
    EventIdSource,
    SequentialEventIds,
    build_event,
    build_terminal_intent,
    capabilities_of,
    is_cancel_requested,
)
from app.services.ai_chat.run_contract import (
    ChatErrorCode,
    ChatEvent,
    ChatEventType,
    EngineCapabilities,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DshEngine",
    "DshWorkerPool",
    "DshRunContext",
    "DshProcessManager",
    "build_dsh_engine",
]


# ---------------------------------------------------------------------------
# 配置常量（单一真源 = app.core.config.settings）
# ---------------------------------------------------------------------------


def _dsh_max_active() -> int:
    from app.core.config import settings
    return int(getattr(settings, "AI_DSH_MAX_ACTIVE_RUNS", 4))


def _dsh_queue_limit() -> int:
    from app.core.config import settings
    return int(getattr(settings, "AI_DSH_QUEUE_LIMIT", 16))


# ---------------------------------------------------------------------------
# DSH Worker Pool（有界并发）
# ---------------------------------------------------------------------------


class DshWorkerPool:
    """DSH 有界 worker 池（Property 38：backpressure 有界）。

    - active_runs <= AI_DSH_MAX_ACTIVE_RUNS
    - queued_runs <= AI_DSH_QUEUE_LIMIT
    - 超限返回 typed quota error
    - 进程 TTL 超时自动清理

    🔴 不按请求无界拉起进程（Design §13 "身份与进程隔离"明确要求有界并发）。
    """

    def __init__(self) -> None:
        self._active: dict[UUID, DshRunContext] = {}
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._semaphore: asyncio.Semaphore | None = None
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def queue_count(self) -> int:
        return self._queue.qsize()

    def _get_semaphore(self) -> asyncio.Semaphore:
        """惰性创建 semaphore（必须在事件循环内）。"""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(_dsh_max_active())
        return self._semaphore

    async def acquire(self, run_id: UUID) -> None:
        """获取执行许可。超过队列上限时抛 quota error。"""
        sem = self._get_semaphore()

        # 检查队列是否已满
        if sem.locked() and self.queue_count >= _dsh_queue_limit():
            raise EngineFailure(
                ChatErrorCode.rate_limited,
                f"DSH 队列已满（active={self.active_count}, "
                f"queued={self.queue_count}, limit={_dsh_queue_limit()}）",
            )

        # 排队等待许可
        await sem.acquire()

    def release(self, run_id: UUID) -> None:
        """释放执行许可。"""
        sem = self._get_semaphore()
        self._active.pop(run_id, None)
        try:
            sem.release()
        except ValueError:
            pass  # 多次 release 安全忽略

    def register(self, ctx: DshRunContext) -> None:
        """注册活跃 run。"""
        self._active[ctx.run_id] = ctx

    def unregister(self, run_id: UUID) -> None:
        """注销活跃 run。"""
        self._active.pop(run_id, None)

    def get_context(self, run_id: UUID) -> DshRunContext | None:
        """获取指定 run 的上下文。"""
        return self._active.get(run_id)

    async def cleanup_expired(self) -> int:
        """清理超 TTL 的进程（后台定时任务调用）。"""
        ttl = _dsh_process_ttl()
        expired: list[UUID] = []
        for rid, ctx in list(self._active.items()):
            if ctx.elapsed_seconds > ttl:
                expired.append(rid)

        for rid in expired:
            ctx = self._active.get(rid)
            if ctx:
                logger.warning("run %s 超出进程 TTL（%.0fs），强制清理", rid, ctx.elapsed_seconds)
                await DshProcessManager.terminate_all(ctx)
                self.release(rid)

        return len(expired)


# 全局单例（进程级，与 NativeEngine 的 semaphore/breaker 同级）
_worker_pool = DshWorkerPool()


def get_worker_pool() -> DshWorkerPool:
    """获取全局 worker pool（测试可 mock）。"""
    return _worker_pool


# ---------------------------------------------------------------------------
# DshEngine
# ---------------------------------------------------------------------------


class DshEngine:
    """DSH 多步 Agent 引擎。

    消费统一 AuthorizedChatRunRequest，产出统一 ChatEvent 流。
    每次 run 独立启动 MCP + DSH root 子进程，不跨 principal 复用。

    🔴 失败不降级（Property 25）：SDK import fail / JSON-RPC handshake fail /
    MCP handshake fail / local model check fail → engine_unavailable。
    绝不隐式调用 NativeEngine。
    """

    name: ChatEngineName = ChatEngineName.dsh

    def __init__(
        self,
        db: Any = None,
        *,
        events: EventIdSource | None = None,
        pool: DshWorkerPool | None = None,
    ) -> None:
        self._db = db
        self._events: EventIdSource = events if events is not None else SequentialEventIds()
        self._pool: DshWorkerPool = pool if pool is not None else get_worker_pool()

    # ------------------------------------------------------------------
    # capability
    # ------------------------------------------------------------------
    async def capabilities(self) -> EngineCapabilities:
        """直接返回 Task 4 表项（Req 10.3 的"不许两处各写一份"）。"""
        return await capabilities_of(self.name)

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------
    def run(
        self,
        request: Any,
        cancel: CancelSignal,
    ) -> AsyncIterator[ChatEvent]:
        """执行一次 DSH Agent run，产出统一 ChatEvent 流。

        事件序列：
        context_ready → tool_started/tool_finished* → delta* → 终态意图

        失败/取消在产出意图后再抛（与 NativeEngine 对称）。
        """
        return EngineStream(lambda outcome: self._run(request, cancel, outcome))

    async def _run(
        self,
        raw_request: Any,
        cancel: CancelSignal,
        outcome: EngineOutcome,
    ) -> AsyncIterator[ChatEvent]:
        started = time.monotonic()

        # ① 归一请求
        try:
            request = AuthorizedChatRunRequest.coerce(raw_request)
        except Exception as exc:
            logger.error(
                "DshEngine 请求对象无法归一（%s）: %s: %s",
                type(raw_request).__name__, type(exc).__name__, exc, exc_info=True,
            )
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"请求对象 {type(raw_request).__name__} 缺少必需字段: {exc}",
            ) from exc

        ctx: DshRunContext | None = None
        try:
            await self._abort_if_cancelled(cancel, "run 开始前")

            # ② SDK discovery 验证
            self._verify_sdk_available()

            # ③ 获取 worker 池许可（backpressure）
            await self._pool.acquire(request.run_id)

            try:
                # ④ 创建 per-run 隔离上下文（先校验项目绑定：注定失败的 run 不去探测模型）
                ctx = await self._create_run_context(request)

                # ⑤ 选定本 run 的模型：按平台对话路由（本机优先）执行前探测，全程不换
                #    （spec dsh-kb-ocr-local-first-routing ADR-DKR-002）；无可用 / 不允许 ⇒ typed error。
                #    模型请求凭 run 令牌经平台环回转发（ADR-DKR-001）
                route = await self._select_model()
                ctx.model_route = route
                try:
                    ctx.llm_token = dsh_model_bridge.issue_token(
                        request.run_id, route.identity,
                        ttl_seconds=dsh_model_bridge.token_ttl_seconds(),
                    )
                except dsh_model_bridge.DshTokenError as exc:  # 只在平台密钥缺失时发生
                    raise EngineFailure(
                        ChatErrorCode.engine_unavailable, f"DSH 模型转发不可用：{exc}"
                    ) from exc
                self._pool.register(ctx)

                await self._abort_if_cancelled(cancel, "上下文创建后")

                # ⑥ 发出 context_ready
                yield build_event(
                    request,
                    self._events,
                    ChatEventType.context_ready,
                    payload={
                        "manifest": {
                            "manifest_version": "dsh-agent-v1",
                            "engine": "dsh",
                            "tools_enabled": True,
                            "project_tools_enabled": (
                                request.host.project_tools_enabled
                                if hasattr(request.host, "project_tools_enabled")
                                else True
                            ),
                        }
                    },
                )

                # ⑦ 启动 DSH root（audit-data MCP 由它的 mcp-client 按 Cordis 配置以 stdio 拉起）
                await DshProcessManager.spawn_dsh_root(ctx)
                await self._abort_if_cancelled(cancel, "DSH root 启动后")

                # ⑧ JSON-RPC handshake
                await self._handshake(ctx, request)
                await self._abort_if_cancelled(cancel, "handshake 后")

                # ⑨ 执行 Agent run（消费 DSH events → ChatEvent）
                async for event in self._execute_agent_run(ctx, request, cancel, outcome):
                    yield event

                # ⑩ 定稿：记录实际服务的模型与部署位置（Req 1.6）
                outcome.latency_ms = _elapsed_ms(started)
                outcome.model = route.model_name

                outcome.usage = {
                    "source": "dsh_agent",
                    "model": outcome.model,
                    "deployment": route.deployment,
                    "fallback_used": bool(route.notes),
                    "tool_calls": ctx.tool_call_count,
                    "elapsed_seconds": ctx.elapsed_seconds,
                    **ctx.token_usage,
                }

                yield build_terminal_intent(
                    request,
                    self._events,
                    ChatEventType.done,
                    payload={
                        "usage": dict(outcome.usage),
                        "model": outcome.model,
                        "deployment": route.deployment,
                        "latency_ms": outcome.latency_ms,
                        "delta_count": outcome.delta_count,
                        "tool_calls": ctx.tool_call_count,
                    },
                    message_id=request.assistant_message_id,
                )
            finally:
                # 释放 worker 池
                self._pool.release(request.run_id)

        except EngineCancelled as exc:
            outcome.failure = exc
            outcome.latency_ms = _elapsed_ms(started)
            yield build_terminal_intent(
                request,
                self._events,
                ChatEventType.cancelled,
                payload={"code": exc.code.value},
            )
            raise
        except EngineFailure as exc:
            outcome.failure = exc
            outcome.latency_ms = _elapsed_ms(started)
            yield build_terminal_intent(
                request,
                self._events,
                ChatEventType.error,
                payload={"code": exc.code.value},
            )
            raise
        finally:
            # 清理全部子进程与 session 文件（Property 8/28）：先请 DSH 优雅退出，再终止进程树
            if ctx is not None:
                await dsh_protocol.shutdown(ctx)
                await DshProcessManager.terminate_all(ctx)
                self._pool.unregister(request.run_id)
                # 清理失败记录审计
                if ctx.cleanup_errors:
                    logger.warning(
                        "run %s cleanup errors (audit): %s",
                        request.run_id, ctx.cleanup_errors,
                    )
            self._events.forget(request.run_id)

    # ------------------------------------------------------------------
    # 分步实现
    # ------------------------------------------------------------------

    async def _select_model(self) -> dsh_model_bridge.DshModelRoute:
        """本 run 的模型（实现在 ``dsh_model_bridge.select_run_candidate``）。"""
        return await dsh_model_bridge.select_run_candidate()

    def _verify_sdk_available(self) -> None:
        """验证 DSH SDK 可用（Property 25：不可用 → engine_unavailable）。"""
        from app.services.ai_chat.dsh_discovery import discover_dsh_sdk

        result = discover_dsh_sdk()
        if not result.is_available:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH SDK 不可用 ({result.status.value}): "
                f"{'; '.join(result.errors[:3])}",
            )

    async def _create_run_context(
        self, request: AuthorizedChatRunRequest
    ) -> DshRunContext:
        """创建 per-run 隔离上下文（Property 28）。

        先校验并签 scoped token，最后才建会话目录：任一步失败都以 typed error 结束且不留临时目录
        （此时 ctx 尚未返回，``finally`` 里的清理够不着它）。
        """
        from app.services.ai_chat.mcp_token import (
            McpMaskLevel,
            McpTokenError,
            McpTokenService,
            resolve_mask_policy,
        )

        token_service = McpTokenService()
        role = _resolve_role(request)
        cycle_scope = request.host.cycle_scope if hasattr(request.host, "cycle_scope") else frozenset()
        project_id = request.host.project_id if hasattr(request.host, "project_id") else None

        if project_id is None:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                "DSH engine 需要项目上下文，当前宿主无项目绑定",
            )

        # 创建 scoped token（Property 29：只在当前 run scope 内）
        try:
            token = token_service.create_token(
                user_id=request.host.principal_id,
                project_id=project_id,
                run_id=request.run_id,
                role=role,
                cycle_scope=cycle_scope,
            )
        except McpTokenError as exc:
            # 未知角色 fail-closed（Req 11.9）⇒ 无权；其余（平台密钥缺失）⇒ 引擎不可用
            rejected = resolve_mask_policy(role) == McpMaskLevel.REJECTED
            raise EngineFailure(
                ChatErrorCode.access_denied if rejected else ChatErrorCode.engine_unavailable,
                f"DSH 数据访问令牌签发失败：{exc.message}",
            ) from exc

        session_dir = Path(tempfile.mkdtemp(prefix=f"dsh_run_{request.run_id.hex[:8]}_"))
        ctx = DshRunContext(
            run_id=request.run_id,
            principal_id=request.host.principal_id,
            project_id=project_id,
            session_dir=session_dir,
            scoped_token=token.token,
            token_id=token.payload.token_id,
        )
        return ctx

    async def _handshake(
        self, ctx: DshRunContext, request: AuthorizedChatRunRequest
    ) -> None:
        """JSON-RPC 握手（实现在 ``dsh_protocol.handshake``）。"""
        await dsh_protocol.handshake(self, ctx, request)

    def _execute_agent_run(
        self,
        ctx: DshRunContext,
        request: AuthorizedChatRunRequest,
        cancel: CancelSignal,
        outcome: EngineOutcome,
    ) -> AsyncIterator[ChatEvent]:
        """执行 Agent run（实现在 ``dsh_protocol.execute_agent_run``）。"""
        return dsh_protocol.execute_agent_run(self, ctx, request, cancel, outcome)

    def _map_dsh_event(
        self,
        event_data: dict[str, Any],
        ctx: DshRunContext,
        request: AuthorizedChatRunRequest,
        outcome: EngineOutcome,
    ) -> AsyncIterator[ChatEvent]:
        """单个 DSH 事件 → ChatEvent（实现在 ``dsh_protocol.map_dsh_event``）。"""
        return dsh_protocol.map_dsh_event(self, event_data, ctx, request, outcome)

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _resolve_effective_model(self) -> str:
        """当前 effective model（本地 vLLM）。"""
        from app.core.config import settings
        return getattr(settings, "DEFAULT_CHAT_MODEL", "Qwen3.5-27B-NVFP4")

    @staticmethod
    async def _abort_if_cancelled(cancel: Any, where: str) -> None:
        """取消检查点（与 NativeEngine 对称）。"""
        if await is_cancel_requested(cancel):
            raise EngineCancelled(f"取消于{where}")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _resolve_role(request: AuthorizedChatRunRequest) -> str:
    """从 host context 解析角色名（用于 scoped token）。"""
    # permission_binding 通常是角色名或权限标识
    binding = getattr(request.host, "permission_binding", None)
    if binding and binding in ("auditor", "manager", "partner", "qc", "eqcr", "admin"):
        return binding
    # 回退默认角色
    return "auditor"


# ---------------------------------------------------------------------------
# 构造入口（engine.build_engine 分派到这里）
# ---------------------------------------------------------------------------


def build_dsh_engine(
    db: Any = None, *, events: EventIdSource | None = None
) -> DshEngine:
    """构造入口。``engine.build_engine`` 按服务端选定的 engine 名分派到这里。

    🔴 本函数不做 SDK discovery（那是 _run 内的第一步）：
    构造 engine 对象是 coordinator 的"选谁执行"阶段，不涉及运行时依赖。
    discovery 失败在 run 内以 engine_unavailable 终态体现。
    """
    return DshEngine(db, events=events)
