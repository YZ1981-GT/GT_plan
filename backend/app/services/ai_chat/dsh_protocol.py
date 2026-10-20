"""DSH JSON-RPC 协议：握手、单轮执行、事件映射与优雅退出（对齐 vendor 真实实现）。

vendor 协议（``packages/sdk/protocol/src/types.ts``，pin 提交 9a226f1077）：

- 请求只有三个：``initialize`` / ``session/prompt`` / ``shutdown``，换行分隔的 JSON-RPC 2.0。
- 输出全部是通知：``session.event``（``{sessionId, event:{type, data}}``，会话日志事件）、
  ``session.status``（``idle`` / ``running``）、``subagent.started`` / ``subagent.finished``。
- 一轮结束 = 本 session 的 ``session.status`` 回到 idle（vendor Python SDK ``Session.run`` 同一判据）。

旧实现发 ``method: "run"`` 并按臆造的 ``tool.call`` / ``text`` 映射，且 ``initialize`` 用了未注册的
provider 名 —— 对真实运行时每次握手必败（spec dsh-kb-ocr-local-first-routing D2~D4）。

``DshEngine`` 保留 ``_handshake`` / ``_execute_agent_run`` / ``_map_dsh_event`` 三个方法委托到这里；
第一个参数 ``engine`` 即该引擎实例（取事件 id 源）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.services.ai_chat.dsh_cordis_policy import DSH_LLM_PROVIDER
from app.services.ai_chat.dsh_process import DshRunContext, _dsh_run_timeout
from app.services.ai_chat.engine import (
    AuthorizedChatRunRequest,
    CancelSignal,
    EngineCancelled,
    EngineFailure,
    EngineOutcome,
    build_event,
    is_cancel_requested,
)
from app.services.ai_chat.run_contract import (
    ChatErrorCode,
    ChatEvent,
    ChatEventType,
)

logger = logging.getLogger("app.services.ai_chat.dsh_engine")

_INIT_ID = "init"
_PROMPT_ID = "prompt"
_SHUTDOWN_ID = "shutdown"
_HANDSHAKE_TIMEOUT = 30.0
#: 每隔多久回到循环顶部检查取消 / 超时
_POLL_SECONDS = 1.0
#: 一轮正常结束的 turn/end 原因（max-tokens 由 sdk-jsonrpc-server 的 maxTokensAsSuccess 视作成功）
_OK_TURN_END = frozenset({"completed", "max-tokens"})
#: MCP 工具在模型侧的名字是 ``mcp__<serverName>__<原名>``
_MCP_PREFIX = "mcp__audit__"


def session_id_for(request: AuthorizedChatRunRequest) -> str:
    """DSH 侧的 session id：每个 run 一个（进程本就 per-run，不复用）。"""
    return f"run-{request.run_id.hex}"


def _diagnostics(ctx: DshRunContext) -> str:
    tail = [line for line in ctx.stderr_tail[-5:] if line]
    return f"（stderr：{' | '.join(tail)[:600]}）" if tail else ""


async def _send(ctx: DshRunContext, message: dict[str, Any]) -> None:
    proc = ctx.dsh_process
    if proc is None or proc.stdin is None:
        raise EngineFailure(ChatErrorCode.engine_unavailable, "DSH root process 未启动或 stdin 不可用")
    try:
        # ASCII 转义：线上只有 7 位字符，与对端 stdin 的解码设置无关（中文问题原样往返）
        proc.stdin.write((json.dumps(message) + "\n").encode("ascii"))
        await proc.stdin.drain()
    except (OSError, BrokenPipeError, ConnectionResetError) as exc:
        raise EngineFailure(
            ChatErrorCode.engine_unavailable, f"DSH 请求发送失败: {exc}{_diagnostics(ctx)}"
        ) from exc


async def _next_message(ctx: DshRunContext, timeout: float) -> dict[str, Any] | None:
    """读下一条 JSON 消息；超时返回 ``{}``，进程退出（EOF）返回 None，非 JSON 行跳过。"""
    proc = ctx.dsh_process
    if proc is None or proc.stdout is None:
        return None
    try:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
    except asyncio.TimeoutError:
        return {}
    except (asyncio.LimitOverrunError, ValueError) as exc:
        raise EngineFailure(ChatErrorCode.engine_unavailable, f"DSH 输出行过长: {exc}") from exc
    if not line:
        return None
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        return {}
    return message if isinstance(message, dict) else {}


def _rpc_error(message: dict[str, Any]) -> str:
    error = message.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "JSON-RPC error")
    return str(error)


async def handshake(engine, ctx: DshRunContext, request: AuthorizedChatRunRequest) -> None:
    """``initialize``：provider 用 vendor 唯一注册的路由名，模型 = 本 run 选定的候选。

    失败 → engine_unavailable（Property 25：不降级到 native）。
    """
    route = ctx.model_route
    model = route.model_name if route is not None else engine._resolve_effective_model()
    await _send(ctx, {
        "jsonrpc": "2.0",
        "id": _INIT_ID,
        "method": "initialize",
        "params": {"cwd": str(ctx.session_dir), "provider": DSH_LLM_PROVIDER, "model": model},
    })
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _HANDSHAKE_TIMEOUT
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH JSON-RPC handshake 超时（{int(_HANDSHAKE_TIMEOUT)}s）{_diagnostics(ctx)}",
            )
        message = await _next_message(ctx, remaining)
        if message is None:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH JSON-RPC handshake 无响应（进程已退出）{_diagnostics(ctx)}",
            )
        if message.get("id") != _INIT_ID:
            continue
        if "error" in message:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH JSON-RPC handshake 失败: {_rpc_error(message)}",
            )
        logger.info("run %s DSH handshake 成功（模型 %s）", ctx.run_id, model)
        return


async def execute_agent_run(
    engine,
    ctx: DshRunContext,
    request: AuthorizedChatRunRequest,
    cancel: CancelSignal,
    outcome: EngineOutcome,
) -> AsyncIterator[ChatEvent]:
    """发一轮 ``session/prompt``，把本 session（及其子 Agent）的事件映射为平台 ChatEvent。

    结束条件：本 session ``session.status`` 回到 idle。``turn/end`` 为 error / aborted / blocked
    ⇒ engine_unavailable（运行中失败不换候选，ADR-DKR-002）。
    """
    session_id = session_id_for(request)
    ctx.session_tree = {session_id}
    await _send(ctx, {
        "jsonrpc": "2.0",
        "id": _PROMPT_ID,
        "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "contentBlocks": [{"type": "text", "text": request.query}],
        },
    })
    run_timeout = _dsh_run_timeout()
    accepted = False
    while True:
        if ctx.cancelled or await is_cancel_requested(cancel):
            ctx.cancelled = True
            raise EngineCancelled("用户取消 DSH run")
        if ctx.is_timed_out:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable, f"DSH run 超时（{run_timeout}s）"
            )
        message = await _next_message(ctx, _POLL_SECONDS)
        if message is None:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH 进程提前退出{_diagnostics(ctx)}",
            )
        if not message:
            continue
        if message.get("id") == _PROMPT_ID:
            if "error" in message:
                raise EngineFailure(
                    ChatErrorCode.engine_unavailable,
                    f"DSH session/prompt 失败: {_rpc_error(message)}",
                )
            accepted = True
            continue
        method = message.get("method")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "subagent.started":
            if params.get("parentSessionId") in ctx.session_tree and params.get("childSessionId"):
                ctx.session_tree.add(str(params["childSessionId"]))
            continue
        if method == "session.event" and params.get("sessionId") in ctx.session_tree:
            async for event in engine._map_dsh_event(params, ctx, request, outcome):
                yield event
            continue
        if (
            method == "session.status"
            and params.get("sessionId") == session_id
            and params.get("status") == "idle"
            and accepted
            and ctx.turn_ended
        ):
            break
    if ctx.turn_error:
        raise EngineFailure(ChatErrorCode.engine_unavailable, f"DSH 模型调用失败: {ctx.turn_error}")


def _text_of(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "".join(
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _failure_text(reason: dict[str, Any]) -> str:
    error = reason.get("error") if isinstance(reason.get("error"), dict) else {}
    message = str(error.get("message") or reason.get("kind") or "未知原因")
    status = error.get("status")
    return f"{message}（HTTP {status}）" if status else message


async def map_dsh_event(
    engine,
    params: dict[str, Any],
    ctx: DshRunContext,
    request: AuthorizedChatRunRequest,
    outcome: EngineOutcome,
) -> AsyncIterator[ChatEvent]:
    """单个 ``session.event`` → ChatEvent。

    - 根 session 的 ``assistant/chunk`` text-delta → ``delta``（子 Agent 的正文不当作最终回答）；
    - ``tool/call`` → ``tool_started``；``tool/result`` → ``tool_finished``（cancel 后不再计数，Property 8）；
    - ``assistant/message``：本步没收到 chunk 时用定稿文本兜底；记 usage；
    - 根 session 的 ``turn/end``：completed / max-tokens 视为成功，其余记为失败原因。
    """
    event = params.get("event") if isinstance(params.get("event"), dict) else {}
    kind = event.get("type")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    is_root = params.get("sessionId") == session_id_for(request)

    if kind == "assistant/chunk" and is_root:
        chunk = data.get("chunk") if isinstance(data.get("chunk"), dict) else {}
        if chunk.get("type") == "text-delta" and chunk.get("text"):
            text = str(chunk["text"])
            outcome.text += text
            outcome.delta_count += 1
            ctx.step_streamed = True
            yield build_event(
                request, engine._events, ChatEventType.delta,
                payload={"text": text}, message_id=request.assistant_message_id,
            )
    elif kind == "assistant/message":
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        if is_root and not ctx.step_streamed:
            text = _text_of(message.get("content"))
            if text:
                outcome.text += text
                outcome.delta_count += 1
                yield build_event(
                    request, engine._events, ChatEventType.delta,
                    payload={"text": text}, message_id=request.assistant_message_id,
                )
        if is_root:
            ctx.step_streamed = False
            usage = data.get("usage")
            if isinstance(usage, dict):
                for key in ("inputTokens", "outputTokens"):
                    if isinstance(usage.get(key), int):
                        ctx.token_usage[key] = ctx.token_usage.get(key, 0) + usage[key]
    elif kind == "tool/call":
        if ctx.cancelled:
            return
        ctx.tool_call_count += 1
        name = str(data.get("name") or "unknown")
        ctx.tool_calls[str(data.get("callId") or ctx.tool_call_count)] = (name, ctx.tool_call_count)
        yield build_event(
            request, engine._events, ChatEventType.tool_started,
            payload={
                "tool_name": name.removeprefix(_MCP_PREFIX),
                "call_index": ctx.tool_call_count,
            },
            message_id=request.assistant_message_id,
        )
    elif kind == "tool/result":
        # 真实形状（2026-10-20 抓包）：data.message.source.callId，结果块 content[].toolCallId / isError
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        source = message.get("source") if isinstance(message.get("source"), dict) else {}
        blocks = [b for b in message.get("content") or [] if isinstance(b, dict)]
        call_id = str(
            source.get("callId")
            or next((b.get("toolCallId") for b in blocks if b.get("toolCallId")), "")
        )
        # 并行工具调用时结果晚于下一个 call 到达：序号按 callId 取发起时的值
        name, index = ctx.tool_calls.get(call_id, ("unknown", ctx.tool_call_count))
        failed = bool(data.get("error")) or any(b.get("isError") for b in blocks)
        yield build_event(
            request, engine._events, ChatEventType.tool_finished,
            payload={
                "tool_name": name.removeprefix(_MCP_PREFIX),
                "call_index": index,
                "success": not failed,
            },
            message_id=request.assistant_message_id,
        )
    elif kind == "turn/end" and is_root:
        ctx.turn_ended = True
        reason = data.get("reason") if isinstance(data.get("reason"), dict) else {}
        if reason.get("kind") not in _OK_TURN_END:
            ctx.turn_error = _failure_text(reason)


async def shutdown(ctx: DshRunContext, timeout: float = 3.0) -> None:
    """优雅退出：发 ``shutdown`` 等回执（失败不抛，随后由进程树终止兜底）。"""
    proc = ctx.dsh_process
    if proc is None or proc.returncode is not None or proc.stdin is None:
        return
    try:
        await _send(ctx, {"jsonrpc": "2.0", "id": _SHUTDOWN_ID, "method": "shutdown"})
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            message = await _next_message(ctx, max(0.05, deadline - loop.time()))
            if message is None or message.get("id") == _SHUTDOWN_ID:
                return
    except EngineFailure:
        return
