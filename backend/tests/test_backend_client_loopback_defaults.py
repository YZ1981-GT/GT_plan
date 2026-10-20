# -*- coding: utf-8 -*-
"""连本平台后端的客户端默认地址必须是 127.0.0.1（spec startup-prewarm-event-loop-unblocking Requirement 4）。

后端 uvicorn 只监听 IPv4（``0.0.0.0``）。Windows 上 ``localhost`` 先解析 ``::1``：现场实测建连
2043 / 2024 / 2024ms，``127.0.0.1`` 为 0–14ms。MCP server 每次工具调用新建 httpx.Client ⇒ 每次多等 2s；
前端模板用 localhost 则按模板新建的开发环境每个代理请求都多等 2s。
（Docker 发布的 PG / Redis / vLLM / OnlyOffice 双栈监听，没有这个问题，不在本守卫范围。）
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

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


def test_dsh_engine_spawns_mcp_against_ipv4_loopback_by_default(tmp_path: Path) -> None:
    """行为判据：真调写 Cordis 配置的函数，看 mcp-client 传给 MCP 的 AUDIT_API_BASE，以及模型转发地址。

    audit-data MCP 由 DSH 根进程的 mcp-client 按 Cordis 配置以 stdio 拉起
    （spec dsh-kb-ocr-local-first-routing D5），MCP 的 env 就在这份配置里。
    """
    import json

    from app.services.ai_chat import dsh_engine as D
    from app.services.ai_chat.dsh_model_bridge import DshModelRoute

    class _Cfg:
        model_name = "m"
        deployment = "local"
        identity = "chat|x|http://127.0.0.1:8100/v1|m"

    ctx = D.DshRunContext(
        run_id=uuid.uuid4(), principal_id=uuid.uuid4(), project_id=uuid.uuid4(), session_dir=tmp_path
    )
    ctx.model_route = DshModelRoute(_Cfg(), 32768)  # type: ignore[arg-type]
    config = json.loads(Path(D._write_platform_cordis_config(ctx)).read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in config}

    base = by_name["@deepseek-ai/dsh-mcp-client"]["config"]["env"]["AUDIT_API_BASE"]
    assert base.startswith("http://127.0.0.1:"), base
    llm_base = by_name["@deepseek-ai/dsh-llm-deepseek"]["config"]["baseURL"]
    assert llm_base.startswith("http://127.0.0.1:"), llm_base
