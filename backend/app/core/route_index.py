"""路由按路径段建索引（spec backend-startup-and-request-overhead R3.2）。

Starlette ``Router.app`` 对每个请求从头逐条 ``route.matches``（正则）：本仓库 2551 条，排在后面的接口光找路由就要
约 0.8 ms。这里把路由按 ``path_format`` 的路径段建一棵前缀树，一次请求只对「可能匹配」的那几条调 ``matches``，
其余逻辑（FULL / PARTIAL 即 405 / 尾斜杠重定向 / ``default``）照抄 Starlette 0.52.1 ``Router.app``，按原顺序取第一条。

正确性：路由正则 = 字面文本与参数分组按格式顺序拼接；单段参数（str / int / float / uuid）不含 ``/``，所以格式里
第 k 段是整段字面时，能匹配的路径第 k 段必等于它。遇到可跨段的参数（path 转换器、未知转换器）之后不再对齐，
该路由从那一层起对任何后续路径都算候选；部分字面段（如 ``v{n}``）按通配处理；非路径路由（Host、自定义
``matches`` 的子类）对所有请求都是候选。候选是能匹配集合的超集，按原下标排序后逐条调 ``matches``，结果与逐条
扫描相同。

路由表换成 :class:`VersionedRoutes`（任何增删改都使版本号加一，下一次请求时重建索引）；``router.routes``
被整体换成普通列表时退回逐条扫描。只在已核对的 Starlette 版本上启用，``GT_ROUTE_INDEX=0`` 关闭。
"""
from __future__ import annotations

import logging
import os
from typing import Any

import starlette
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.convertors import FloatConvertor, IntegerConvertor, StringConvertor, UUIDConvertor
from starlette.datastructures import URL
from starlette.responses import RedirectResponse
from starlette.routing import Match, Mount, Route, Router, WebSocketRoute, get_route_path

logger = logging.getLogger("audit_platform")

#: 已核对 ``Router.app`` 源码（routing.py 第 718~766 行）并跑过等价判据的版本。
VALIDATED_STARLETTE_VERSIONS = frozenset({"0.52.1"})

#: ``matches`` 按 ``path_regex`` 匹配路径的实现；其他实现（Host、自定义子类）的路由对所有请求都是候选。
_PATH_MATCHES = frozenset({Route.matches, WebSocketRoute.matches, Mount.matches, APIRoute.matches,
                           APIWebSocketRoute.matches})
#: 正则不含 ``/`` 的转换器：整段参数只占一段。
_SINGLE_SEGMENT = (StringConvertor, IntegerConvertor, FloatConvertor, UUIDConvertor)


class VersionedRoutes(list):
    """路由表：任何增删改都把 ``version`` 加一。"""

    version: int = 0


def _bumping(name: str) -> Any:
    base = getattr(list, name)

    def method(self: VersionedRoutes, *args: Any, **kwargs: Any) -> Any:
        self.version += 1
        return base(self, *args, **kwargs)

    method.__name__ = name
    return method


for _name in ("append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse", "__setitem__",
              "__delitem__", "__iadd__", "__imul__"):
    setattr(VersionedRoutes, _name, _bumping(_name))


class _Node:
    __slots__ = ("literal", "param", "rest", "ends")

    def __init__(self) -> None:
        self.literal: dict[str, _Node] = {}
        self.param: _Node | None = None
        self.rest: list[int] = []  # 从这一层起可跨段：对之后任何路径都是候选
        self.ends: list[int] = []  # 格式在这一层结束


def _segments(route: Any) -> list[tuple[str, str]] | None:
    """格式的逐段分类：("lit", 文本) / ("param", "") / ("rest", "")；不能按路径段索引的返回 None。"""
    if type(route).matches not in _PATH_MATCHES:
        return None
    fmt = getattr(route, "path_format", None)
    convertors = getattr(route, "param_convertors", None)
    if not isinstance(fmt, str) or not fmt.startswith("/") or not isinstance(convertors, dict):
        return None
    out: list[tuple[str, str]] = []
    for seg in fmt.split("/")[1:]:
        if "{" not in seg:
            out.append(("lit", seg))
            continue
        names = [part.split("}", 1)[0] for part in seg.split("{")[1:]]
        if any(not isinstance(convertors.get(n), _SINGLE_SEGMENT) for n in names):
            out.append(("rest", ""))
            break
        out.append(("param", ""))
    return out


class RouteIndex:
    def __init__(self, routes: list[Any]) -> None:
        self.root = _Node()
        self.anywhere: list[int] = []
        for i, route in enumerate(routes):
            segs = _segments(route)
            if segs is None:
                self.anywhere.append(i)
                continue
            node = self.root
            for kind, text in segs:
                if kind == "rest":
                    node.rest.append(i)
                    break
                if kind == "lit":
                    node = node.literal.setdefault(text, _Node())
                else:
                    node.param = node.param or _Node()
                    node = node.param
            else:
                node.ends.append(i)

    def candidates(self, route_path: str) -> list[int]:
        """可能匹配 ``route_path`` 的路由下标（升序）。"""
        found = list(self.anywhere)
        if route_path.startswith("/"):
            self._walk(self.root, route_path.split("/")[1:], 0, found)
        found.sort()
        return found

    def _walk(self, node: _Node, parts: list[str], depth: int, found: list[int]) -> None:
        found.extend(node.rest)
        if depth == len(parts):
            found.extend(node.ends)
            return
        child = node.literal.get(parts[depth])
        if child is not None:
            self._walk(child, parts, depth + 1, found)
        if node.param is not None:
            self._walk(node.param, parts, depth + 1, found)


def _index_of(router: Router, cache: dict[str, Any]) -> RouteIndex | None:
    routes = router.routes
    if not isinstance(routes, VersionedRoutes):
        return None  # 被整体换成了普通列表：改不改都看不出来，退回逐条扫描
    key = (id(routes), routes.version, len(routes))
    if cache.get("key") != key:
        cache["index"] = RouteIndex(routes)
        cache["key"] = key
    return cache["index"]


def make_indexed_app(router: Router) -> Any:
    """与 ``Router.app`` 相同的分派，只是候选路由来自索引。"""
    cache: dict[str, Any] = {}

    async def app(scope: Any, receive: Any, send: Any) -> None:
        assert scope["type"] in ("http", "websocket", "lifespan")
        if "router" not in scope:
            scope["router"] = router
        if scope["type"] == "lifespan":
            await router.lifespan(scope, receive, send)
            return
        routes = router.routes
        index = _index_of(router, cache)
        order = range(len(routes)) if index is None else index.candidates(get_route_path(scope))
        partial = None
        partial_scope: Any = None
        for i in order:
            route = routes[i]
            match, child_scope = route.matches(scope)
            if match == Match.FULL:
                scope.update(child_scope)
                await route.handle(scope, receive, send)
                return
            elif match == Match.PARTIAL and partial is None:
                partial = route
                partial_scope = child_scope
        if partial is not None:
            scope.update(partial_scope)
            await partial.handle(scope, receive, send)
            return
        route_path = get_route_path(scope)
        if scope["type"] == "http" and router.redirect_slashes and route_path != "/":
            redirect_scope = dict(scope)
            if route_path.endswith("/"):
                redirect_scope["path"] = redirect_scope["path"].rstrip("/")
            else:
                redirect_scope["path"] = redirect_scope["path"] + "/"
            again = range(len(routes)) if index is None else index.candidates(get_route_path(redirect_scope))
            for i in again:
                match, child_scope = routes[i].matches(redirect_scope)
                if match != Match.NONE:
                    response = RedirectResponse(url=str(URL(scope=redirect_scope)))
                    await response(scope, receive, send)
                    return
        await router.default(scope, receive, send)

    app.__gt_route_index__ = cache  # type: ignore[attr-defined]
    return app


def install_route_index(router: Router) -> bool:
    """在全部路由注册之后调用。返回是否启用。"""
    if os.environ.get("GT_ROUTE_INDEX", "1") == "0":
        logger.info("[route-index] GT_ROUTE_INDEX=0：路由按逐条扫描匹配")
        return False
    if starlette.__version__ not in VALIDATED_STARLETTE_VERSIONS:
        logger.warning("[route-index] Starlette %s 未核对（已核对 %s），路由按逐条扫描匹配",
                       starlette.__version__, sorted(VALIDATED_STARLETTE_VERSIONS))
        return False
    if getattr(router.middleware_stack, "__gt_route_index__", None) is not None:
        return True
    if router.middleware_stack != router.app:
        logger.warning("[route-index] router 带了自己的中间件，不替换分派")
        return False
    if not isinstance(router.routes, VersionedRoutes):
        router.routes = VersionedRoutes(router.routes)
    indexed = make_indexed_app(router)
    _index_of(router, indexed.__gt_route_index__)  # 安装时就建好（约 10 ms），不让第一个请求付
    router.middleware_stack = indexed
    return True
