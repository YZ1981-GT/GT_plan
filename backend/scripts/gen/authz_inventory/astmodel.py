"""源码静态扫描的数据模型（``astscan`` 产出、``gates`` 消费；design §4.12「函数级识别用 AST」）。

问题种类（``Issue.kind``）是中文常量，原样出现在报错里：未识别依赖、级别无法静态确定、不支持的写法、
登记表与实现不一致。哪些问题致命由调用方决定（附注清册全部致命，需求 1.7）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .routes import DeclaredRoute

UNKNOWN_DEPENDENCY = "未识别依赖"
LEVEL_UNDETERMINED = "级别无法静态确定"
UNSUPPORTED = "不支持的写法"
REGISTRY_MISMATCH = "登记表与实现不一致"
DEPENDS_MARKERS = frozenset({"Depends", "Security"})
PARAM_MARKERS = frozenset({"Query", "Path", "Body", "Header", "Cookie", "File", "Form"})  # 请求参数，非依赖
ROUTE_VERBS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace", "api_route"})


class ParseFailure(Exception):
    """文件无法解析（需求 1.7 / 9.8 的失败条件）。"""


@dataclass(frozen=True)
class Issue:
    kind: str  # UNKNOWN_DEPENDENCY / LEVEL_UNDETERMINED / UNSUPPORTED / REGISTRY_MISMATCH
    file: str
    function: str
    name: str
    detail: str = ""

    def message(self) -> str:
        return f"{self.file}::{self.function}：{self.kind}「{self.name}」" + (f"——{self.detail}" if self.detail else "")


@dataclass(frozen=True)
class Val:
    """静态取值。kind：literal（origin 为 literal / constant / default）/ param（参数名）/ member（A.b）/ unknown。"""

    kind: str
    value: Any = None
    origin: str = "literal"


@dataclass(frozen=True)
class Site:
    """函数体内一处门禁或同文件辅助函数调用（ordinal 为该函数内按源码先后的序号，从 1 起）。

    门禁工厂的返回值先赋给局部变量、再 ``await 变量(...)`` 的，记在调用变量的位置，实参取自工厂调用，
    ``via_variable`` 为该变量名。"""

    kind: str  # gate / helper
    name: str
    ordinal: int
    conditional: bool
    awaited: bool
    args: tuple[Val, ...]
    kwargs: tuple[tuple[str, Val], ...]
    star: bool
    via_variable: str | None = None


@dataclass(frozen=True)
class Decl:
    """一处依赖声明：签名参数默认值（param 为参数名）或 dependencies= 列表元素（param 为 None）。"""

    param: str | None
    name: str
    kind: str  # gate / local（本文件函数）/ unknown / bad
    args: tuple[Val, ...] = ()
    kwargs: tuple[tuple[str, Val], ...] = ()
    detail: str = ""


@dataclass
class Unit:
    """一个函数定义（模块级、类方法或嵌套函数；嵌套的 qualname 带 ``.<locals>.``）。"""

    qualname: str
    is_async: bool
    params: tuple[str, ...]
    positional: tuple[str, ...]
    defaults: dict[str, Val] = field(default_factory=dict)
    sites: list[Site] = field(default_factory=list)
    decls: list[Decl] = field(default_factory=list)  # 签名参数上的依赖声明
    markers: list[str] = field(default_factory=list)  # 签名里的请求参数标记（Query / File …）
    signature_kinds: set[str] = field(default_factory=set)  # upload_file / background_tasks / db_session
    signature_issues: list[Issue] = field(default_factory=list)
    body_issues: list[Issue] = field(default_factory=list)
    stub: tuple[str, ...] | None = None  # 函数体只抛出时各 raise 的错误（HTTP 501 / NotImplementedError …）


@dataclass
class ModuleInfo:
    file: str
    module: str
    imports: dict[str, str]  # 本地名 → 原名（含函数体内的延迟导入）
    constants: dict[str, Any]  # 模块级唯一绑定的字面量常量
    toplevel: set[str]
    registry: Mapping[str, Any]  # 门禁登记表（gates.REGISTRY）
    units: dict[str, Unit] = field(default_factory=dict)
    routers: dict[str, tuple[str, tuple[Decl, ...]]] = field(default_factory=dict)  # 变量 → (前缀, 依赖)
    endpoints: dict[str, tuple[tuple[str, tuple[str, ...], str, tuple[Decl, ...]], ...]] = field(default_factory=dict)
    body_depends: list[tuple[str, Decl]] = field(default_factory=list)  # 函数体里的 Depends(...)，如注册循环
    issues: list[Issue] = field(default_factory=list)  # 模块级问题（路由声明写法等）

    def declared_routes(self) -> tuple[DeclaredRoute, ...]:
        return tuple(DeclaredRoute(self.file, function, method, self.routers[router][0] + path, router, index)
                     for function, entries in self.endpoints.items()
                     for index, (router, methods, path, _) in enumerate(entries) for method in methods)

    def gate_definition(self, qualname: str) -> str | None:
        """``qualname`` 属于哪个登记门禁自身的实现（含其内部闭包）；不属于返回 None。"""
        name = qualname.split(".<locals>", 1)[0].rsplit(".", 1)[-1]
        spec = self.registry.get(name)
        return name if spec is not None and spec.home == self.module else None
