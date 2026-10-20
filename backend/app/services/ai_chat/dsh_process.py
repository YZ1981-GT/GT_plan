"""DSH per-run 进程与上下文：会话目录、DSH 根进程启动 / 进程树终止、子进程 env 与 Cordis 配置写盘。

Feature: dsh-agent-panel-integration（Req 4.7 / 11.6 / 11.11 / 11.12）
spec dsh-kb-ocr-local-first-routing：

- Task 1：自 ``dsh_engine`` 拆出，``dsh_engine`` 保留同名再导出。
- Task 4：audit-data MCP 改由 DSH 的 mcp-client 按 Cordis 配置以 stdio 拉起（spec D5）—— 旧实现由平台
  另起一个 MCP 进程，它的 stdio 握在 Python 手里，DSH 根本连不上；env 还写成 ``MCP_SCOPED_TOKEN``，
  而 server.py 读 ``MCP_TOKEN``（spec D6）。
- 子进程 env 从零构造：不继承父进程（平台的数据库 / 密钥变量一个都不带），``DSH_HOME`` 指向本 run 的
  会话目录（不读写用户目录下的 ``.dsh``，spec D8），模型 Key 位置只放 run 转发令牌（ADR-DKR-001）。
- 终止按进程树：DSH 根进程 → mcp-client 拉起的 MCP 进程都在它下面。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services.ai_chat.engine import EngineFailure
from app.services.ai_chat.run_contract import ChatErrorCode

logger = logging.getLogger("app.services.ai_chat.dsh_engine")

#: node 闭包里 jsonrpc demo 的入口（vendor ``build-exe-for-python-sdk.ts`` 的 ENTRY_BIN）
_NODE_ENTRY = Path("node_modules") / "@deepseek-ai" / "dsh-sdk-jsonrpc-demo" / "lib" / "packaged-bin.js"
#: MCP 单次工具调用超时（毫秒）
_MCP_TOOL_TIMEOUT_MS = 60_000


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
    包含：MCP scoped token、模型转发令牌与选定候选、DSH 根进程、会话目录。
    """

    run_id: UUID
    principal_id: UUID
    project_id: UUID
    session_dir: Path | None = None
    dsh_process: asyncio.subprocess.Process | None = None
    scoped_token: str | None = None
    token_id: str | None = None
    #: 本 run 选定的模型（``dsh_model_bridge.DshModelRoute``），执行前探测得到，全程不换
    model_route: Any = None
    #: 模型转发令牌（子进程 env 里的 ``GT_DSH_LLM_TOKEN``）
    llm_token: str | None = None
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
    #: DSH 进程 stderr 末尾若干行（报错时附带，便于定位）与读取任务
    stderr_tail: list[str] = field(default_factory=list)
    stderr_task: asyncio.Task | None = None
    #: 协议层状态：本轮涉及的 session（根 + 子 Agent）、callId → 工具名、本步是否已流式输出、
    #: 根 session 的 turn/end 是否到达及失败原因、累计 token 用量
    session_tree: set[str] = field(default_factory=set)
    tool_calls: dict[str, tuple[str, int]] = field(default_factory=dict)
    step_streamed: bool = False
    turn_ended: bool = False
    turn_error: str | None = None
    token_usage: dict[str, int] = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def is_timed_out(self) -> bool:
        return self.elapsed_seconds > _dsh_run_timeout()

    @property
    def dsh_home(self) -> Path | None:
        return self.session_dir / "home" if self.session_dir else None


# ---------------------------------------------------------------------------
# DSH Process Manager（进程生命周期）
# ---------------------------------------------------------------------------


def _process_group_kwargs() -> dict[str, Any]:
    """让 DSH 根进程自成进程组：终止时连同 mcp-client 拉起的 MCP 进程一并结束。"""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def _drain_stderr(ctx: DshRunContext, stream: asyncio.StreamReader) -> None:
    """持续读走 stderr：不读的话管道写满（约 64 KB）后 DSH 进程会卡在写日志上。保留末尾用于报错。"""
    while True:
        line = await stream.readline()
        if not line:
            return
        ctx.stderr_tail.append(line.decode("utf-8", "replace").rstrip())
        del ctx.stderr_tail[:-40]


class DshProcessManager:
    """管理 per-run 的 DSH 根进程（audit-data MCP 由它的 mcp-client 拉起，同属一棵进程树）。

    🔴 设计约束：
    - 每个 run 独立进程，不复用（Property 28：跨用户隔离）
    - 进程不监听 TCP 端口（Property 27：MCP 零监听）
    - 子进程 env 从零构造，不继承长期凭据
    - cleanup 失败记录审计和指标，不静默
    """

    @staticmethod
    def runtime_entry(vendor_root: Path) -> Path:
        """vendor node 运行时闭包里的 JSON-RPC 入口（Windows 只有 node 载体，exe 只构建 linux / macOS）。"""
        return (
            vendor_root / "python" / "sdk-runtime" / "src" / "deepseek_harness_runtime"
            / "runtime" / "node" / _NODE_ENTRY
        )

    @staticmethod
    async def spawn_dsh_root(
        ctx: DshRunContext,
        *,
        cordis_config_path: str | None = None,
    ) -> asyncio.subprocess.Process:
        """启动 per-run DSH 根进程（custom Cordis：无 bash / fs-write 工具，模型经平台环回转发）。"""
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

        node_path = shutil.which("node")
        if not node_path:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                "Node.js 未安装（DSH JSON-RPC server 需要 Node.js）",
            )
        node_bin_js = DshProcessManager.runtime_entry(DSH_VENDOR_ROOT)
        if not node_bin_js.is_file():
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH node 运行时闭包不存在: {node_bin_js}（在 pin 版本的 vendor 检出里构建，"
                "步骤见 docs/reference/llm-provider-configuration.md「DSH 运行时」）",
            )

        config_path = cordis_config_path or _write_platform_cordis_config(ctx)
        env = _build_dsh_env(
            cordis_config=config_path,
            session_dir=str(ctx.session_dir) if ctx.session_dir else "",
            llm_token=ctx.llm_token or "",
        )

        try:
            process = await asyncio.create_subprocess_exec(
                node_path, str(node_bin_js),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(ctx.session_dir) if ctx.session_dir else None,
                # vendor 每条 JSON-RPC 消息一行；session.event 可能带整段工具结果，放宽单行上限
                limit=16 * 1024 * 1024,
                **_process_group_kwargs(),
            )
        except (OSError, FileNotFoundError) as exc:
            raise EngineFailure(
                ChatErrorCode.engine_unavailable,
                f"DSH root process 启动失败: {exc}",
            ) from exc
        ctx.dsh_process = process
        if process.pid:
            ctx.child_pids.append(process.pid)
        if process.stderr is not None:
            ctx.stderr_task = asyncio.create_task(_drain_stderr(ctx, process.stderr))
        logger.info("run %s DSH root process 已启动 (pid=%s)", ctx.run_id, process.pid)
        return process

    @staticmethod
    async def terminate_all(ctx: DshRunContext) -> None:
        """终止 DSH 根进程及其后代（含 MCP）+ 清理 session 文件。

        🔴 顺序：进程树 → session 文件。失败不阻断（记录到 ctx.cleanup_errors），后续审计可重试。
        优雅退出（JSON-RPC ``shutdown``）由协议层在此之前尝试。
        """
        proc = ctx.dsh_process
        if proc is not None and proc.returncode is None:
            await _terminate_tree(ctx, proc)
        task = getattr(ctx, "stderr_task", None)
        if task is not None and not task.done():
            task.cancel()

        if ctx.session_dir and ctx.session_dir.exists():
            try:
                shutil.rmtree(ctx.session_dir, ignore_errors=False)
                logger.info("run %s session 目录已清理: %s", ctx.run_id, ctx.session_dir)
            except (OSError, PermissionError) as exc:
                ctx.cleanup_errors.append(f"session 目录清理失败: {exc}")

        if ctx.cleanup_errors:
            logger.warning(
                "run %s 清理有 %d 项失败: %s",
                ctx.run_id, len(ctx.cleanup_errors), ctx.cleanup_errors,
            )


async def _terminate_tree(ctx: DshRunContext, proc: asyncio.subprocess.Process) -> None:
    """Windows 用 ``taskkill /T``（TerminateProcess 不连带子进程）；POSIX 向进程组发信号。"""
    try:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(proc.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), timeout=10.0)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except (asyncio.TimeoutError, ProcessLookupError, OSError) as exc:
        ctx.cleanup_errors.append(f"DSH 进程树终止失败: {exc}")
        try:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass


# ---------------------------------------------------------------------------
# 子进程 env 与 Cordis 配置
# ---------------------------------------------------------------------------


def _resolve_mcp_server_path() -> str:
    """MCP server 路径（Task 26 实现的 audit-data stdio server）。"""
    candidates = [
        Path("tools/audit-data-mcp/server.py"),
        Path(__file__).parent.parent.parent.parent.parent / "tools" / "audit-data-mcp" / "server.py",
    ]
    for p in candidates:
        if p.is_file():
            return str(p.resolve())
    raise EngineFailure(
        ChatErrorCode.engine_unavailable,
        "audit-data MCP server 不存在（tools/audit-data-mcp/server.py）",
    )


def _build_mcp_env(*, token: str, api_base: str, run_id: str) -> dict[str, str]:
    """audit-data MCP 进程的 env（由 mcp-client 合并到它清洗过的父 env 上）。

    🔴 变量名必须是 server.py 读取的 ``MCP_TOKEN``（旧实现写 ``MCP_SCOPED_TOKEN``，工具调用全部无凭据）。
    只注入必要变量，不从父进程全量继承。
    """
    env: dict[str, str] = {
        "AUDIT_API_BASE": api_base,
        "MCP_TOKEN": token,
        "MCP_RUN_ID": run_id,
        "PYTHONIOENCODING": "utf-8",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # Windows 必需
    }
    python_home = os.environ.get("PYTHONHOME", "")
    if python_home:
        env["PYTHONHOME"] = python_home
    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    if virtual_env:
        env["VIRTUAL_ENV"] = virtual_env
    return env


def _build_dsh_env(*, cordis_config: str, session_dir: str, llm_token: str) -> dict[str, str]:
    """DSH 根进程 env：从零构造；``DSH_HOME`` / 临时目录都落在本 run 的会话目录下。"""
    from app.services.ai_chat.dsh_model_bridge import TOKEN_ENV

    root = Path(session_dir) if session_dir else Path(tempfile.gettempdir())
    tmp = root / "tmp"
    home = root / "home"
    for directory in (tmp, home):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "DSH_CORDIS_CONFIG": cordis_config,
        "DSH_CWD": str(root),
        "DSH_SESSION_ROOT": str(root / "sessions"),
        "DSH_HOME": str(home),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "NODE_ENV": "production",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "APPDATA": os.environ.get("APPDATA", ""),  # Node.js on Windows
        TOKEN_ENV: llm_token,
    }


def _write_platform_cordis_config(ctx: DshRunContext) -> str:
    """把本 run 的 Cordis 配置写进会话目录（模型经平台环回转发 + mcp-client stdio 拉起 MCP）。

    写盘内容不含上游模型 Key（Key 只在平台进程内）；MCP scoped token 随会话目录在 run 结束时删除。
    """
    from app.core.config import settings
    from app.services.ai_chat.dsh_cordis_policy import (
        build_platform_cordis_config,
        validate_cordis_services,
    )
    from app.services.ai_chat.dsh_model_bridge import TOKEN_ENV, forward_base_url

    route = ctx.model_route
    if route is None:
        raise EngineFailure(ChatErrorCode.engine_unavailable, "DSH run 尚未选定模型")
    session_dir = ctx.session_dir or Path(tempfile.mkdtemp(prefix="dsh_cfg_"))
    home = session_dir / "home"
    home.mkdir(parents=True, exist_ok=True)
    mcp_server = {
        "transport": "stdio",
        "serverName": "audit",
        "command": sys.executable,
        "args": [_resolve_mcp_server_path(), "--stdio"],
        "env": _build_mcp_env(
            token=ctx.scoped_token or "",
            # 127.0.0.1 而非 localhost：后端只监听 IPv4，Windows 上 localhost 先试 ::1 每次多等约 2s
            api_base=f"http://127.0.0.1:{getattr(settings, 'PORT', 9980)}",
            run_id=str(ctx.run_id),
        ),
        "cwd": str(session_dir),
        "toolCallTimeoutMs": _MCP_TOOL_TIMEOUT_MS,
        "failOnStartupError": True,
        "reconnect": {"enabled": False},
    }
    config = build_platform_cordis_config(
        llm_base_url=forward_base_url(),
        llm_api_key_env=TOKEN_ENV,
        model=route.model_name,
        context_window=route.context_window,
        max_output_tokens=route.max_output_tokens,
        mcp_server=mcp_server,
        session_root=str(session_dir / "sessions"),
        dsh_home=str(home),
    )
    errors = validate_cordis_services(config)
    if errors:
        raise EngineFailure(
            ChatErrorCode.engine_unavailable, "DSH Cordis 配置校验失败：" + "；".join(errors)
        )
    config_path = session_dir / "cordis.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(config_path)
