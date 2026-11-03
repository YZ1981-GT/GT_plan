"""SSE 路由必须在返回 StreamingResponse 前释放数据库事务。

FastAPI 的 yield dependency 默认是 request scope；对无限流意味着直到浏览器关流才退出 ``get_db``，每条 SSE 会长期占用
一个 ``idle in transaction`` 的 PG 连接。这里钉住认证子依赖和两个现有 SSE 路由都显式使用 function scope。
"""
from __future__ import annotations

import inspect

from fastapi.params import Depends as DependsParam

from app.core.database import get_db
from app.deps import get_current_user_sse
from app.routers import doc_ai_chat, events


def _dependency(function, parameter: str) -> DependsParam:
    default = inspect.signature(function).parameters[parameter].default
    assert isinstance(default, DependsParam), (function.__name__, parameter, default)
    return default


def test_sse_auth_database_session_is_function_scoped() -> None:
    dependency = _dependency(get_current_user_sse, "db")
    assert dependency.dependency is get_db
    assert dependency.scope == "function"


def test_all_current_user_sse_routes_release_direct_database_session_before_streaming() -> None:
    modules = (events, doc_ai_chat)
    users = {
        (module.__name__, function.__name__): function
        for module in modules
        for _, function in inspect.getmembers(module, inspect.isfunction)
        if any(
            isinstance(parameter.default, DependsParam)
            and parameter.default.dependency is get_current_user_sse
            for parameter in inspect.signature(function).parameters.values()
        )
    }
    assert set(users) == {
        ("app.routers.events", "sse_stream"),
        ("app.routers.doc_ai_chat", "stream_run_events"),
    }
    for function in users.values():
        dependency = _dependency(function, "db")
        assert dependency.dependency is get_db
        assert dependency.scope == "function", function.__name__
