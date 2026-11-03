"""路由定义推迟到首次使用（spec backend-startup-and-request-overhead R1）。

FastAPI 每构造一条 ``APIRoute`` 都要做依赖分析、为每个参数 / 响应模型建 ``TypeAdapter``。本仓库 2550 条路由，
子路由装饰时构造一次、``include_router`` 复制时又构造一次，合计 5131 次约 5.9 s，占导入 ``app.main`` 的一半。

做法：``LazyAPIRoute`` 构造时在「推迟」标记下跑 FastAPI 自己的 ``APIRoute.__init__`` —— ``fastapi.routing`` 里几个
重函数在安装时被包成「标记打开时返回占位、否则调原函数」—— 于是路径正则、方法、名称、``unique_id``、响应模型
解析等轻属性仍由 FastAPI 自己算（不抄它的代码），跑完删掉重属性、记下构造参数。第一次读到重属性时用原参数在
标记关闭下再跑一遍完整构造，与立即构造逐行相同。``include_router`` 只读轻属性，子路由那一份永远不物化。

约束：物化前不得改写路由对象的属性（物化按原参数重算）。只在已验证的 FastAPI 版本上启用；
``GT_LAZY_ROUTES=0`` 关闭。
"""
from __future__ import annotations

import contextvars
import functools
import logging
import os
from typing import Any, Iterable

import fastapi
import fastapi.routing as _fr
from fastapi.routing import APIRoute, APIRouter

logger = logging.getLogger("audit_platform")

#: 已核对 ``APIRoute.__init__`` / ``include_router`` 源码并跑过等价判据的版本。升级 FastAPI 先在这里红。
VALIDATED_FASTAPI_VERSIONS = frozenset({"0.135.3"})

#: ``APIRoute.__init__`` 里由重函数结果得出的全部属性：推迟构造后删掉，第一次读取时才算。
HEAVY_ATTRS = frozenset({
    "response_field",
    "stream_item_field",
    "response_fields",
    "dependant",
    "_flat_dependant",
    "_embed_body_fields",
    "body_field",
    "is_sse_stream",
    "is_json_stream",
    "app",
})

#: 推迟构造期间返回占位的 ``fastapi.routing`` 模块级函数（``APIRoute.__init__`` 调用的全部重函数）。
WRAPPED_FUNCTIONS = (
    "create_model_field",
    "get_dependant",
    "get_parameterless_sub_dependant",
    "get_flat_dependant",
    "_should_embed_body_fields",
    "get_body_field",
    "get_request_handler",
    "request_response",
)

_LAZY_ARGS = "_gt_lazy_args"
_deferring: contextvars.ContextVar[bool] = contextvars.ContextVar("gt_lazy_route_deferring", default=False)
_installed = False


class _Placeholder:
    """推迟构造期间重函数的返回值：只满足 ``APIRoute.__init__`` 对它的用法，构造完连同所在属性一起删掉。"""

    __slots__ = ("dependencies", "body_params", "is_async_gen_callable", "is_gen_callable")

    def __init__(self) -> None:
        self.dependencies: list[Any] = []
        self.body_params: list[Any] = []
        self.is_async_gen_callable = False
        self.is_gen_callable = False

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("推迟构造的路由占位被调用（应先物化）")


def _wrap(orig: Any) -> Any:
    @functools.wraps(orig)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _deferring.get():
            return _Placeholder()
        return orig(*args, **kwargs)

    wrapper.__gt_lazy_wrapper__ = True  # type: ignore[attr-defined]
    return wrapper


class LazyAPIRoute(APIRoute):
    """轻属性构造时算，重属性第一次读取时算；物化后与 ``APIRoute`` 立即构造的结果相同。"""

    def __init__(self, path: str, endpoint: Any, **kwargs: Any) -> None:
        token = _deferring.set(True)
        try:
            APIRoute.__init__(self, path, endpoint, **kwargs)
            deferred_ok = True
        except Exception:  # noqa: BLE001 — 推迟构造失败就整条立即构造，真正的错误由那一次抛出
            deferred_ok = False
        finally:
            _deferring.reset(token)
        if not deferred_ok:
            self.__dict__.clear()
            APIRoute.__init__(self, path, endpoint, **kwargs)
            return
        for name in HEAVY_ATTRS:
            self.__dict__.pop(name, None)
        self.__dict__[_LAZY_ARGS] = (path, endpoint, kwargs)

    def __getattr__(self, name: str) -> Any:
        # 只在常规属性查找失败时调用：未物化的重属性走这里。
        if name in HEAVY_ATTRS and _LAZY_ARGS in self.__dict__:
            self.gt_materialize()
            return self.__dict__[name]
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    @property
    def gt_pending(self) -> bool:
        """还没物化。"""
        return _LAZY_ARGS in self.__dict__

    def gt_materialize(self) -> None:
        """用原构造参数跑一遍完整的 ``APIRoute.__init__``（已物化则什么都不做）。"""
        args = self.__dict__.pop(_LAZY_ARGS, None)
        if args is None:
            return
        path, endpoint, kwargs = args
        token = _deferring.set(False)  # 即使在别的路由推迟构造途中被读到，也要真算
        try:
            APIRoute.__init__(self, path, endpoint, **kwargs)
        except AttributeError as exc:
            self.__dict__[_LAZY_ARGS] = args
            # 不能原样抛 AttributeError：会被 hasattr / getattr 默认值吞掉，表现成「没有这个属性」
            raise RuntimeError(f"路由 {path} 物化失败：{exc}") from exc
        except BaseException:
            self.__dict__[_LAZY_ARGS] = args
            raise
        finally:
            _deferring.reset(token)


def is_enabled() -> bool:
    """推迟路由已安装（新建的 APIRouter 默认用 ``LazyAPIRoute``）。"""
    return _installed


def install_wrappers() -> None:
    """把 ``fastapi.routing`` 的重函数包一层（只在推迟标记打开时返回占位，其余时候原样调用）。重复调用无副作用。"""
    for name in WRAPPED_FUNCTIONS:
        current = getattr(_fr, name)
        if not getattr(current, "__gt_lazy_wrapper__", False):
            setattr(_fr, name, _wrap(current))


def install_lazy_api_routes() -> bool:
    """在导入任何路由模块之前调用：此后新建的 APIRouter 默认用 ``LazyAPIRoute``。返回是否启用。重复调用无副作用。"""
    global _installed
    if _installed:
        return True
    if os.environ.get("GT_LAZY_ROUTES", "1") == "0":
        logger.info("[lazy-routes] GT_LAZY_ROUTES=0：路由按立即构造")
        return False
    if fastapi.__version__ not in VALIDATED_FASTAPI_VERSIONS:
        logger.warning(
            "[lazy-routes] FastAPI %s 未验证推迟构造（已验证 %s），路由按立即构造",
            fastapi.__version__, sorted(VALIDATED_FASTAPI_VERSIONS),
        )
        return False
    kwdefaults = APIRouter.__init__.__kwdefaults__
    if kwdefaults is None or "route_class" not in kwdefaults:
        logger.warning("[lazy-routes] APIRouter.__init__ 没有 route_class 关键字默认值，路由按立即构造")
        return False
    install_wrappers()
    kwdefaults["route_class"] = LazyAPIRoute
    _installed = True
    return True


def pending_routes(routes: Iterable[Any]) -> list[LazyAPIRoute]:
    """还没物化的路由（按原顺序）。"""
    return [r for r in routes if isinstance(r, LazyAPIRoute) and r.gt_pending]


async def verify_in_background(
    routes: list[Any],
    *,
    delay_s: float,
    interval_s: float,
    on_progress: Any = None,
) -> list[tuple[str, str]]:
    """启动后低强度逐条物化；与预热 / 事件恢复 / OpenAPI / GC 串行。"""
    import asyncio

    from app.core.gc_tuning import heavy_phase

    await asyncio.sleep(delay_s)
    async with heavy_phase("lazy-route-verification"):
        todo = pending_routes(routes)
        failures: list[tuple[str, str]] = []
        for i, route in enumerate(todo, start=1):
            if route.gt_pending:
                try:
                    route.gt_materialize()
                except Exception as exc:  # noqa: BLE001 — 逐条收集
                    failures.append((getattr(route, "path", "?"), f"{type(exc).__name__}: {exc}"[:300]))
                    logger.error(
                        "[lazy-routes] 路由定义错误 %s %s：%s",
                        sorted(getattr(route, "methods", []) or []),
                        getattr(route, "path", "?"),
                        exc,
                    )
            if on_progress is not None and i % 500 == 0:
                on_progress(i, len(todo), failures, False)
            await asyncio.sleep(interval_s)
        if on_progress is not None:
            on_progress(len(todo), len(todo), failures, True)
        return failures


def schedule_background_verification(app: Any, worker_tasks: list, report: Any) -> bool:
    """启动任务 ``verify_lazy_routes`` 的实现：排一个后台核验任务（进 ``worker_tasks``，关闭时随 worker 取消）。

    进度与结果经 ``report(status, detail)`` 回写启动报告。没有应用对象或推迟路由未启用时不排，返回 False。
    """
    import asyncio

    if app is None or not is_enabled():
        return False

    def _progress(done: int, total: int, failures: list, finished: bool) -> None:
        head = "；".join(f"{p} {e}" for p, e in failures[:3])
        report("failed" if failures else "ok",
               f"后台物化{'完成' if finished else '进行中'} {done}/{total}，失败 {len(failures)}" + (f"：{head}" if head else ""))

    delay_s = float(os.getenv("GT_LAZY_ROUTES_VERIFY_DELAY", "60"))
    worker_tasks.append(asyncio.create_task(
        verify_in_background(app.router.routes, delay_s=delay_s, interval_s=0.01, on_progress=_progress)))
    return True


def materialize_all(routes: Iterable[Any]) -> list[tuple[str, str]]:
    """物化全部未物化的路由，返回失败清单 ``[(路径, 错误摘要)]``（不抛出）。"""
    failures: list[tuple[str, str]] = []
    for route in pending_routes(routes):
        try:
            route.gt_materialize()
        except Exception as exc:  # noqa: BLE001 — 逐条收集，供启动报告 / 判据使用
            failures.append((getattr(route, "path", "?"), f"{type(exc).__name__}: {exc}"[:300]))
    return failures
