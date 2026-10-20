"""audit-data MCP server 解包平台响应信封（spec dsh-kb-ocr-local-first-routing D11）。

平台 ``ResponseWrapperMiddleware`` 把 2xx JSON 包成 ``{code, message, data}``。server.py 旧实现直接
``response.json().get("result")`` ⇒ 每次工具调用都返回 ``{}``，工具级错误也被吞掉（2026-10-20 真实运行抓到：
DSH 调 wp_list 拿到 ``{}``，模型回答「项目没有底稿」）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SERVER = Path(__file__).resolve().parents[3] / "tools" / "audit-data-mcp" / "server.py"


@pytest.fixture(scope="module")
def server():
    spec = importlib.util.spec_from_file_location("_audit_data_mcp_server_under_test", SERVER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _client_returning(body: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/ai-chat/mcp/tools/call"
        return httpx.Response(status, content=json.dumps(body).encode(), headers={"content-type": "application/json"})

    return lambda: httpx.Client(base_url="http://127.0.0.1:9980", transport=httpx.MockTransport(handler))


def test_wrapped_success_returns_tool_result(server, monkeypatch) -> None:
    body = {"code": 200, "message": "success", "data": {
        "status": "ok", "result": {"items": [{"wp_code": "A1"}]}, "budget": {"remaining_calls": 49},
    }}
    monkeypatch.setattr(server, "_get_http_client", _client_returning(body))
    assert server._call_platform_tool("wp_list", {"limit": 3}) == {"items": [{"wp_code": "A1"}]}


def test_wrapped_tool_error_is_raised_not_swallowed(server, monkeypatch) -> None:
    body = {"code": 200, "message": "success", "data": {
        "status": "error", "error_code": "access_denied", "error_message": "无权访问该底稿", "budget": {},
    }}
    monkeypatch.setattr(server, "_get_http_client", _client_returning(body))
    with pytest.raises(RuntimeError, match="access_denied"):
        server._call_platform_tool("wp_read", {"wp_id": "x"})


def test_unwrapped_body_still_supported(server, monkeypatch) -> None:
    """跳过信封的部署（或未来端点不包装）照样可用。"""
    monkeypatch.setattr(server, "_get_http_client", _client_returning({"status": "ok", "result": {"n": 1}}))
    assert server._call_platform_tool("tb_query", {}) == {"n": 1}
