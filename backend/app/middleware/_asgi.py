"""纯 ASGI 中间件的公共小件（spec backend-startup-and-request-overhead R3.1）。

``BaseHTTPMiddleware`` 每个请求要建内存流 + 任务组、并把响应改成流式；本目录的中间件改成直接包 ``send``，
判定口径与原来逐项相同：路径见 :func:`request_path`，请求头按 Starlette ``Headers`` 大小写不敏感地取第一项。
"""
from __future__ import annotations

from urllib.parse import urlsplit

from starlette.types import Scope

# 这些字符会被 urlsplit 当成分隔符或删掉：路径里出现时 ``request.url.path`` 与 ``scope["path"]`` 不同，照原口径重算
_URL_SENSITIVE = ("?", "#", "\t", "\r", "\n")
_PATH_CACHE_KEY = "_gt_request_path"


def request_path(scope: Scope) -> str:
    """中间件判定用的请求路径。Host 头正常时与 ``Request(scope).url.path``（原 ``BaseHTTPMiddleware`` 版本的口径）
    逐字相同；常见路径不建 URL 对象。同一请求的多个中间件共享 ``scope``，结果缓存在
    ``scope['_gt_request_path']``，写请求不再由 Observability / AuditLog / Inflight 各算一次。

    原口径把 Host 头拼进 URL 再拆，畸形 Host 头会带偏路径：``Host: x?`` 让路径变空（限流认不出 LLM 端点），
    ``Host: x/api/health?`` 让写操作的路径变成 ``/api/health``（不记审计日志），``Host: [`` 直接抛异常（500）。
    这里重算时固定用一个正常的主机名，只保留路径本身带来的差别（design §7）。
    """
    cached = scope.get(_PATH_CACHE_KEY)
    if isinstance(cached, str):
        return cached
    path: str = scope["path"]
    if path.startswith("/") and not any(c in path for c in _URL_SENSITIVE):
        result = path
    else:
        try:
            result = urlsplit("http://h" + path).path
        except ValueError:  # 如路径 "[x"：退回原始路径，交给路由（404）
            result = path
    scope[_PATH_CACHE_KEY] = result
    return result
