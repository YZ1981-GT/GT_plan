# -*- coding: utf-8 -*-
"""连本平台后端的客户端默认地址必须是 127.0.0.1（spec startup-prewarm-event-loop-unblocking Requirement 4）。

后端 uvicorn 只监听 IPv4（``0.0.0.0``）。Windows 上 ``localhost`` 先解析 ``::1``：现场实测建连
2043 / 2024 / 2024ms，``127.0.0.1`` 为 0–14ms。MCP server 每次工具调用新建 httpx.Client ⇒ 每次多等 2s；
前端模板用 localhost 则按模板新建的开发环境每个代理请求都多等 2s。
（Docker 发布的 PG / Redis / vLLM / OnlyOffice 双栈监听，没有这个问题，不在本守卫范围。）
"""
from __future__ import annotations

import ast
import asyncio
import uuid
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]


def test_frontend_env_example_uses_ipv4_loopback() -> None:
    text = (REPO / "audit-platform" / "frontend" / ".env.example").read_text(encoding="utf-8")
    values = dict(
        line.split("=", 1) for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    )
    assert values.get("VITE_API_BASE_URL") == "http://127.0.0.1:9980", values


def test_audit_data_mcp_server_default_base_is_ipv4_loopback() -> None:
    """AST 取 `os.environ.get("AUDIT_API_BASE", <默认>)` 的默认值（注释 / docstring 不参与）。"""
    tree = ast.parse((REPO / "tools" / "audit-data-mcp" / "server.py").read_text(encoding="utf-8"))
    defaults = [
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) == 2
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "AUDIT_API_BASE"
        and isinstance(node.args[1], ast.Constant)
    ]
    assert defaults == ["http://127.0.0.1:9980"], defaults


def test_dsh_engine_spawns_mcp_against_ipv4_loopback_by_default() -> None:
    """行为判据：真调 `spawn_mcp_process`（子进程创建打桩），看传给 MCP 的 AUDIT_API_BASE。"""
    from app.services.ai_chat import dsh_engine as D

    captured: dict[str, str] = {}

    class _Proc:
        pid = None

    async def fake_exec(*_args, env=None, **_kwargs):
        captured.update(env or {})
        return _Proc()

    ctx = D.DshRunContext(run_id=uuid.uuid4(), principal_id=uuid.uuid4(), project_id=uuid.uuid4())
    with patch.object(D.asyncio, "create_subprocess_exec", fake_exec):
        asyncio.run(D.DshProcessManager.spawn_mcp_process(ctx, mcp_server_path="server.py"))

    base = captured.get("AUDIT_API_BASE", "")
    assert base.startswith("http://127.0.0.1:"), base
