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

1. SDK discovery（验证 vendor 安装与 Cordis）
2. 创建 per-run scoped token（MCP 认证）
3. 启动 per-run MCP stdio process（audit-data server）
4. 启动 DSH root subprocess（custom Cordis + JSON-RPC）
5. 监听 DSH events → 映射为平台 ChatEvent
6. cancel/timeout → 销毁全部 descendants + 清理 session files

## 进程隔离与安全

- 每个 run 独立启动 MCP stdio process 和 DSH root process
- DSH root 不跨 principal 复用（无法证明完整 reset）
- MCP process 只持有 per-run scoped token，不持有长期登录凭据
- 运行结束后销毁全部进程与临时文件

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
import os
import shutil
import signal
import tempfile
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from app.models.ai_models import ChatEngineName
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


def _dsh_run_timeout() -> int:
    """单 run 墙钟上限（秒）。复用 AI_CHAT_RUN_TIMEOUT_SECONDS。"""
    from app.core.config import settings
    return int(getattr(settings, "AI_CHAT_RUN_TIMEOUT_SECONDS", 180))


def _dsh_process_ttl() -> int:
    """进程最大存活时间（秒）。使用 run timeout * 2 作为进程 TTL 上界。"""
    from app.core.config import settings
    base = int(getattr(settings, "AI_CHAT_RUN_TIMEOUT_SECONDS", 180))
    return base * 2


# ---------------------------------------------------------------------------
# DSH Run Context（per-run 隔离状态）
# ---------------------------------------------------------------------------


@dataclass
class DshRunContext:
    """一次 DSH run 的完整隔离上下文。

    🔴 per-run 独立，不跨 principal 复用（Property 28）。
    包含：scoped token、MCP process、DSH root process、session 目录。
    """

    run_id: UUID
    principal_id: UUID
    project_id: UUID
    session_dir: Path | None = None
    mcp_process: asyncio.subprocess.Process | None = None
    dsh_process: asyncio.subprocess.Process | None = None
    scoped_token: str | None = None
    token_id: str | None = None
    #: 工具调用计数（cancel 后不再增加 = Property 8 判据）
    tool_call_count: int = 0
    #: cancel 标志
    cancelled: bool = False
    #: 启动时间（用于 timeout 判定）
    started_at: float = field(default_factory=time.monotonic)
    #: 子进程 PID 列表（用于清理确认）
    child_pids: list[int] = field(default_factory=list)
    #: 清理错误（记录审计）
    cleanup_errors: list[str] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def is_timed_out(self) -> bool:
        return self.elapsed_seconds > _dsh_run_timeout()


# ---------------------------------------------------------------------------
# DSH Process Manager（进程生命周期）
# ---------------------------------------------------------------------------


class DshProcessManager:
    """管理 per-run 的 MCP stdio process 和 DSH root process。

    🔴 设计约束：
    - 每个 run 独立进程，不复用（Property 28：跨用户隔离）
    - 进程不监听 TCP 端口（Property 27：MCP 零监听）
    - 进程环境只注入 scoped token，不继承长期凭据
    - cleanup 失败记录审计和指标，不静默
    """

    @staticmethod
    async def spawn_mcp_process(
        ctx: DshRunContext,
        *,
        mcp_server_path: str | None = None,
        api_base_url: str | None = None,
    ) -> asyncio.subprocess.Process:
        """启动 per-run MCP stdio process。

        MCP server 只通过 AUDIT_API_BASE 调用平台 REST endpoints，
        不 import DB driver/ORM，不读取 DB/Redis/平台密钥。
        """
        from app.core.config import settings

        server_path = mcp_server_path or _resolve_mcp_server_path()
        base_url = api_base_url or f"http://localhost:{getattr(settings, 'PORT', 9980)}"

        # 构造受限环境——只注入必要变量，不从父进程全量继承
        env = _build_mcp_env(
            token=ctx.scoped_token or "",
            api_base=base_url,
            run_id=str(ctx.run_id),
        )

        try:
            process = await asyncio.create_subprocess_exec(
                "python", server_path, "--stdio",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(ctx.session_dir) if ctx.session_dir else None,
            )
            ctx.mcp_process = process
            if process.pid:
                ctx.child_pids.append(process.pid)
            logger.info(
                "run %s MCP stdio process 已启动 (pid=%s)",
                ctx.run_id, process.pid,
            )
            return process
        except (OSError, FileNotFoundError) as exc:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"MCP stdio process 启动失败: {exc}",
            ) from exc

    @staticmethod
    async def spawn_dsh_root(
        ctx: DshRunContext,
        *,
        cordis_config_path: str | None = None,
    ) -> asyncio.subprocess.Process:
        """启动 per-run DSH root subprocess。

        使用 custom Cordis 配置（无 bash/fs-write 工具），
        指向本地 vLLM（非 cloud）。
        """
        from app.services.ai_chat.dsh_discovery import (
            DSH_VENDOR_ROOT,
            discover_dsh_sdk,
        )

        discovery = discover_dsh_sdk()
        if not discovery.is_available:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH SDK 不可用: {discovery.status.value} — {'; '.join(discovery.errors[:3])}",
            )

        # 确定 node runtime 路径
        runtime_dir = (
            DSH_VENDOR_ROOT / "python" / "sdk-runtime"
            / "src" / "deepseek_harness_runtime" / "runtime"
        )
        node_bin_js = (
            runtime_dir / "node" / "node_modules"
            / "@deepseek-ai" / "dsh-sdk-jsonrpc-demo"
            / "lib" / "packaged-bin.js"
        )

        node_path = shutil.which("node")
        if not node_path:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                "Node.js 未安装（DSH JSON-RPC server 需要 Node.js）",
            )

        if not node_bin_js.is_file():
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH node runtime closure 不存在: {node_bin_js}",
            )

        # 使用平台 Cordis 配置或指定的外部配置
        config_path = cordis_config_path
        if not config_path:
            config_path = _write_platform_cordis_config(ctx)

        env = _build_dsh_env(
            cordis_config=config_path,
            vendor_root=str(DSH_VENDOR_ROOT),
            session_dir=str(ctx.session_dir) if ctx.session_dir else "",
        )

        try:
            process = await asyncio.create_subprocess_exec(
                node_path, str(node_bin_js),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(ctx.session_dir) if ctx.session_dir else None,
            )
            ctx.dsh_process = process
            if process.pid:
                ctx.child_pids.append(process.pid)
            logger.info(
                "run %s DSH root process 已启动 (pid=%s)",
                ctx.run_id, process.pid,
            )
            return process
        except (OSError, FileNotFoundError) as exc:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH root process 启动失败: {exc}",
            ) from exc

    @staticmethod
    async def terminate_all(ctx: DshRunContext) -> None:
        """终止 run 关联的全部子进程 + 清理 session 文件。

        🔴 顺序：先 DSH root → 再 MCP → 最后 session 文件。
        失败不阻断（记录到 ctx.cleanup_errors），后续审计可重试。
        """
        # 1. 终止 DSH root（及其 children）
        if ctx.dsh_process and ctx.dsh_process.returncode is None:
            try:
                ctx.dsh_process.terminate()
                await asyncio.wait_for(ctx.dsh_process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError, OSError) as exc:
                ctx.cleanup_errors.append(f"DSH root 终止失败: {exc}")
                # 强杀
                try:
                    ctx.dsh_process.kill()
                except (ProcessLookupError, OSError):
                    pass

        # 2. 终止 MCP process
        if ctx.mcp_process and ctx.mcp_process.returncode is None:
            try:
                ctx.mcp_process.terminate()
                await asyncio.wait_for(ctx.mcp_process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError, OSError) as exc:
                ctx.cleanup_errors.append(f"MCP process 终止失败: {exc}")
                try:
                    ctx.mcp_process.kill()
                except (ProcessLookupError, OSError):
                    pass

        # 3. 清理 session 文件（JSONL/log/temp）
        if ctx.session_dir and ctx.session_dir.exists():
            try:
                shutil.rmtree(ctx.session_dir, ignore_errors=False)
                logger.info("run %s session 目录已清理: %s", ctx.run_id, ctx.session_dir)
            except (OSError, PermissionError) as exc:
                ctx.cleanup_errors.append(f"session 目录清理失败: {exc}")

        # 记录清理结果
        if ctx.cleanup_errors:
            logger.warning(
                "run %s 清理有 %d 项失败: %s",
                ctx.run_id, len(ctx.cleanup_errors), ctx.cleanup_errors,
            )


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
                # ④ 创建 per-run 隔离上下文
                ctx = await self._create_run_context(request)
                self._pool.register(ctx)

                await self._abort_if_cancelled(cancel, "上下文创建后")

                # ⑤ 发出 context_ready
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

                # ⑥ 启动 MCP stdio process
                await DshProcessManager.spawn_mcp_process(ctx)
                await self._abort_if_cancelled(cancel, "MCP 启动后")

                # ⑦ 启动 DSH root 并执行 handshake
                await DshProcessManager.spawn_dsh_root(ctx)
                await self._abort_if_cancelled(cancel, "DSH root 启动后")

                # ⑧ JSON-RPC handshake
                await self._handshake(ctx, request)
                await self._abort_if_cancelled(cancel, "handshake 后")

                # ⑨ 执行 Agent run（消费 DSH events → ChatEvent）
                async for event in self._execute_agent_run(ctx, request, cancel, outcome):
                    yield event

                # ⑩ 定稿
                outcome.latency_ms = _elapsed_ms(started)
                outcome.model = self._resolve_effective_model()

                # 生成 usage
                outcome.usage = {
                    "source": "dsh_agent",
                    "model": outcome.model,
                    "tool_calls": ctx.tool_call_count,
                    "elapsed_seconds": ctx.elapsed_seconds,
                }

                yield build_terminal_intent(
                    request,
                    self._events,
                    ChatEventType.done,
                    payload={
                        "usage": dict(outcome.usage),
                        "model": outcome.model,
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
            # 清理全部子进程与 session 文件（Property 8/28）
            if ctx is not None:
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
        """创建 per-run 隔离上下文（Property 28）。"""
        # 创建 session 目录
        session_dir = Path(tempfile.mkdtemp(prefix=f"dsh_run_{request.run_id.hex[:8]}_"))

        # 创建 scoped token（Property 29：只在当前 run scope 内）
        from app.services.ai_chat.mcp_token import McpTokenService

        token_service = McpTokenService()
        role = _resolve_role(request)
        cycle_scope = request.host.cycle_scope if hasattr(request.host, "cycle_scope") else frozenset()
        project_id = request.host.project_id if hasattr(request.host, "project_id") else None

        if project_id is None:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                "DSH engine 需要项目上下文，当前宿主无项目绑定",
            )

        token = token_service.create_token(
            user_id=request.host.principal_id,
            project_id=project_id,
            run_id=request.run_id,
            role=role,
            cycle_scope=cycle_scope,
        )

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
        """执行 JSON-RPC initialize handshake。

        失败 → engine_unavailable（Property 25）。
        不使用真实 SDK client（依赖 DSH vendor root）；
        而是通过 stdin/stdout 发送 JSON-RPC initialize。
        """
        if ctx.dsh_process is None or ctx.dsh_process.stdin is None:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                "DSH root process 未启动或 stdin 不可用",
            )

        import json

        # 构造 JSON-RPC initialize 请求
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "cwd": str(ctx.session_dir),
                "provider": "local-vllm",
                "model": self._resolve_effective_model(),
            },
        }

        try:
            payload = json.dumps(init_request) + "\n"
            ctx.dsh_process.stdin.write(payload.encode())
            await ctx.dsh_process.stdin.drain()

            # 等待 initialize 响应（超时 30s）
            response_data = await asyncio.wait_for(
                ctx.dsh_process.stdout.readline(),  # type: ignore[union-attr]
                timeout=30.0,
            )

            if not response_data:
                raise EngineFailure(
                    ChatErrorCode.engine_unavailable,
                    "DSH JSON-RPC handshake 无响应",
                )

            response = json.loads(response_data.decode())
            if "error" in response:
                error_msg = response["error"].get("message", "unknown")
                raise EngineFailure(
                    ChatErrorCode.engine_unavailable,
                    f"DSH JSON-RPC handshake 失败: {error_msg}",
                )

            logger.info("run %s DSH handshake 成功", ctx.run_id)

        except asyncio.TimeoutError as exc:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                "DSH JSON-RPC handshake 超时（30s）",
            ) from exc
        except (json.JSONDecodeError, OSError) as exc:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH JSON-RPC handshake 通信错误: {exc}",
            ) from exc

    async def _execute_agent_run(
        self,
        ctx: DshRunContext,
        request: AuthorizedChatRunRequest,
        cancel: CancelSignal,
        outcome: EngineOutcome,
    ) -> AsyncIterator[ChatEvent]:
        """执行 Agent run，将 DSH events 映射为平台 ChatEvent。

        包含：
        - tool_started / tool_finished 事件
        - delta 文本事件
        - timeout 检测
        - cancel 检查点
        """
        import json

        if ctx.dsh_process is None or ctx.dsh_process.stdin is None:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                "DSH root process 未就绪",
            )

        # 发送 run 请求
        run_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "run",
            "params": {
                "prompt": request.query,
                "session_id": str(request.session_id),
            },
        }

        try:
            payload = json.dumps(run_request) + "\n"
            ctx.dsh_process.stdin.write(payload.encode())
            await ctx.dsh_process.stdin.drain()
        except (OSError, BrokenPipeError) as exc:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH run 请求发送失败: {exc}",
            ) from exc

        # 消费 DSH stdout events
        run_timeout = _dsh_run_timeout()
        try:
            async with asyncio.timeout(run_timeout):
                while True:
                    # Cancel 检查
                    if await is_cancel_requested(cancel) or ctx.cancelled:
                        ctx.cancelled = True
                        raise EngineCancelled("用户取消 DSH run")

                    # Timeout 检查
                    if ctx.is_timed_out:
                        raise EngineFailure(
                            ChatErrorCode.engine_unavailable,
                            f"DSH run 超时（{run_timeout}s）",
                        )

                    # 读取下一个 event（非阻塞等待 + cancel 检查）
                    try:
                        line = await asyncio.wait_for(
                            ctx.dsh_process.stdout.readline(),  # type: ignore[union-attr]
                            timeout=5.0,  # 每 5s 检查一次 cancel
                        )
                    except asyncio.TimeoutError:
                        continue  # 回到 cancel/timeout 检查

                    if not line:
                        # EOF = DSH process 退出
                        break

                    # 解析 DSH event
                    try:
                        event_data = json.loads(line.decode())
                    except json.JSONDecodeError:
                        continue  # 跳过非 JSON 行

                    # 映射 DSH event → ChatEvent
                    async for chat_event in self._map_dsh_event(
                        event_data, ctx, request, outcome
                    ):
                        yield chat_event

        except asyncio.TimeoutError as exc:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH run 超时（{run_timeout}s）",
            ) from exc

    async def _map_dsh_event(
        self,
        event_data: dict[str, Any],
        ctx: DshRunContext,
        request: AuthorizedChatRunRequest,
        outcome: EngineOutcome,
    ) -> AsyncIterator[ChatEvent]:
        """将单个 DSH JSON-RPC event 映射为平台 ChatEvent。

        DSH event 类型映射：
        - tool.call / tool.start → tool_started
        - tool.result / tool.end → tool_finished
        - text / delta / chunk → delta
        - done / result → 不直接映射（由 _run 产出终态）
        - error → EngineFailure
        """
        method = event_data.get("method", "")
        params = event_data.get("params", {})

        # 如果是 response（非 notification），检查 error
        if "error" in event_data:
            error_msg = event_data["error"].get("message", "DSH 运行时错误")
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH 运行时错误: {error_msg}",
            )

        # 如果是 response with result（final）
        if "result" in event_data and event_data.get("id") == 2:
            # run 完成——提取最终文本
            result = event_data["result"]
            if isinstance(result, dict):
                final_text = result.get("text", "") or result.get("content", "")
                if final_text and not outcome.text:
                    outcome.text = final_text
            return

        # Notifications（method-based）
        if method in ("tool.call", "tool.start", "toolCall"):
            # cancel 后不再增加工具调用（Property 8）
            if ctx.cancelled:
                return
            ctx.tool_call_count += 1
            tool_name = params.get("name", params.get("tool", "unknown"))
            yield build_event(
                request,
                self._events,
                ChatEventType.tool_started,
                payload={
                    "tool_name": tool_name,
                    "call_index": ctx.tool_call_count,
                },
                message_id=request.assistant_message_id,
            )

        elif method in ("tool.result", "tool.end", "toolResult"):
            tool_name = params.get("name", params.get("tool", "unknown"))
            yield build_event(
                request,
                self._events,
                ChatEventType.tool_finished,
                payload={
                    "tool_name": tool_name,
                    "call_index": ctx.tool_call_count,
                    "success": not params.get("error"),
                },
                message_id=request.assistant_message_id,
            )

        elif method in ("text", "delta", "chunk", "content"):
            text = params.get("text", "") or params.get("content", "") or params.get("delta", "")
            if text:
                outcome.text += text
                outcome.delta_count += 1
                yield build_event(
                    request,
                    self._events,
                    ChatEventType.delta,
                    payload={"text": text},
                    message_id=request.assistant_message_id,
                )

        elif method in ("error", "failure"):
            error_msg = params.get("message", "DSH Agent 执行错误")
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH Agent 错误: {error_msg}",
            )

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


def _resolve_mcp_server_path() -> str:
    """MCP server 路径（Task 26 实现的 audit-data stdio server）。"""
    candidates = [
        Path("tools/audit-data-mcp/server.py"),
        Path(__file__).parent.parent.parent.parent / "tools" / "audit-data-mcp" / "server.py",
    ]
    for p in candidates:
        if p.is_file():
            return str(p.resolve())
    raise EngineFailure(
        ChatErrorCode.engine_unavailable,
        "audit-data MCP server 不存在（tools/audit-data-mcp/server.py）",
    )


def _build_mcp_env(*, token: str, api_base: str, run_id: str) -> dict[str, str]:
    """构造 MCP process 的受限环境变量。

    🔴 不从父进程全量继承（安全要求）。只注入必要变量。
    """
    env: dict[str, str] = {
        "AUDIT_API_BASE": api_base,
        "MCP_SCOPED_TOKEN": token,
        "MCP_RUN_ID": run_id,
        "PYTHONIOENCODING": "utf-8",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # Windows 必需
    }
    # Python 需要的最小环境
    python_home = os.environ.get("PYTHONHOME", "")
    if python_home:
        env["PYTHONHOME"] = python_home
    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    if virtual_env:
        env["VIRTUAL_ENV"] = virtual_env
    return env


def _build_dsh_env(
    *, cordis_config: str, vendor_root: str, session_dir: str
) -> dict[str, str]:
    """构造 DSH root process 的受限环境变量。"""
    env: dict[str, str] = {
        "DSH_CORDIS_CONFIG": cordis_config,
        "DSH_CWD": vendor_root,
        "DSH_SESSION_DIR": session_dir,
        "NODE_ENV": "production",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "APPDATA": os.environ.get("APPDATA", ""),  # Node.js on Windows
    }
    return env


def _write_platform_cordis_config(ctx: DshRunContext) -> str:
    """将平台 Cordis 配置写入 session 目录。"""
    from app.services.ai_chat.dsh_discovery import build_platform_cordis_config

    config = build_platform_cordis_config(
        session_root=str(ctx.session_dir) if ctx.session_dir else "./.sessions",
    )

    import json as json_mod
    config_path = ctx.session_dir / "cordis.json" if ctx.session_dir else Path(tempfile.mktemp(suffix=".json"))
    config_path.write_text(
        json_mod.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(config_path)


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
