"""门禁登记表 + AST 识别器（design §4.12，需求 1.7 / 1.8 / 9.1）。

识别四处来源：① 签名参数默认值里的 ``Depends`` / ``Security``（不论参数名，含 ``_``；``Annotated`` 同；
不带参数的 ``Depends()`` 取参数注解）；② 装饰器与路由器的 ``dependencies=[...]``；③ 路由注册时附加的依赖
（只在运行时可见，取自 ``RouteRecord.registration_dependencies``）；④ 函数体内对登记门禁的调用（门禁工厂的
返回值可先赋给局部变量再 ``await`` 调用），含经同文件辅助函数的间接调用（逐层绑定实参，记录辅助函数链；
级别经辅助函数参数传入的按调用方逐个取值）。入口：``recognize_endpoint``（端点，含运行时对账）与
``recognize_function``（任一函数单元，供影响清单）。

只认 ``ast.Call`` 的 ``ast.Name`` / ``ast.Attribute`` 调用节点：注释不进 AST，docstring 与其他字符串是
``Constant``，都不会被当成门禁。函数体调用位于 if / try / 循环 / with / match / 布尔短路 / 条件表达式 /
推导式 / assert 之内的标「条件执行」。级别取字面量、同文件常量（模块级唯一绑定）或登记表里的默认值。

识别不了的一律记 ``Issue``（中文），不静默跳过：未识别依赖、级别无法静态确定、不支持的写法、登记表与实现
不一致；签名、路由器、装饰器三处依赖另与运行时路由表逐项对账。哪些问题致命由调用方决定（附注清册全部致命）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import astscan
from .astmodel import (LEVEL_UNDETERMINED, REGISTRY_MISMATCH, UNKNOWN_DEPENDENCY, UNSUPPORTED, Decl, Issue,
                       ModuleInfo, ParseFailure, Site, Unit, Val)
from .routes import DeclaredRoute, DependencyRef, RouteRecord

__all__ = ["CATEGORIES", "LEVELS", "LEVEL_RANK", "LEVELLED", "LEVEL_UNDETERMINED", "REGISTRY", "REGISTRY_MISMATCH",
           "UNKNOWN_DEPENDENCY", "UNSUPPORTED", "Arg", "EndpointGates", "GateSpec", "GateUse", "Issue", "ModuleInfo",
           "ParseFailure", "analyze_module", "max_level", "recognize_endpoint", "recognize_function"]

LEVELS = ("readonly", "review", "edit")
LEVEL_RANK = {level: rank for rank, level in enumerate(LEVELS, start=1)}
CATEGORIES = {
    "project": "项目级", "project_wp": "项目级（按底稿反查）", "project_object": "项目级（对象反查）",
    "note_edit": "附注编辑门禁", "design": "design 定级门禁", "deliverable": "交付中心门禁",
    "operation": "操作矩阵", "consol_lock": "合并锁", "global_role": "全局角色", "identity": "仅登录",
    "wp_visibility": "底稿可见性（注册附加）", "neutral": "中性依赖",
}
LEVELLED = frozenset({"project", "project_wp", "project_object", "note_edit", "design"})
_MISSING: Any = object()

@dataclass(frozen=True)
class Arg:
    """门禁的一个静态参数：位置 / 关键字 / 省略时的默认值 / 取值形态。"""

    key: str  # 输出键（level / operation / roles / action / consol_lock …）
    position: int | None
    keyword: str
    default: Any = _MISSING  # _MISSING = 必填
    form: str = "literal"  # literal / bool / member（取 A.b 的成员名）/ names（字符串集合，排序输出）


@dataclass(frozen=True)
class GateSpec:
    """登记表的一项。``local`` = 同文件具名门禁：必须定义在调用方同一文件，按辅助函数展开后核对登记级别。"""

    name: str
    category: str
    level: str | Arg | None = None  # 固定级别 / 由实参给出 / 无项目级级别
    args: tuple[Arg, ...] = ()
    factory: bool = False  # 调用返回依赖函数：Depends(f(...)) 或 f(...)(...)
    local: bool = False
    awaited: bool = True  # 函数体调用须直接 await（工厂型指它返回的依赖）
    home: str | None = None  # 定义所在模块（该模块内的定义即门禁实现本身）
    overlays: tuple[tuple[str, Any], ...] = ()  # 叠加信息：免查名单 / 能力 / EQCR 排除 / 操作点 …
    source: str = "design §4.12"


_D, _NG, _DN = "app.deps", "app.services.note_edit_gate", "app.routers.disclosure_notes"
_PERM = Arg("level", 3, "min_permission", "readonly")
_CONSOL = Arg("consol_lock", None, "consol_lock", form="bool")
_BYPASS = ("global_role_bypass", ("admin", "partner"))
_NOTE = (("eqcr_exclusion", True), ("operation", "note:edit"))
_DB = (("db_session", True),)
_SPECS = (
    GateSpec("require_project_access", "project", Arg("level", 0, "min_permission", "readonly"), factory=True, home=_D),
    GateSpec("assert_project_permission", "project", _PERM, home=_D),
    GateSpec("require_project_permission", "project", "review", (Arg("permission", 0, "permission"),),
             factory=True, home=_D),
    GateSpec("authorize_wp_edit", "project_wp", "edit", home=_D,
             overlays=(_BYPASS, ("global_capability", "WORKPAPER_WRITE"))),
    GateSpec("require_wp_edit_permission", "project_wp", "edit", factory=True, home=_D,
             overlays=(_BYPASS, ("global_capability", "WORKPAPER_WRITE"))),
    GateSpec("authorize_wp_read", "project_wp", "readonly", home=_D, overlays=(_BYPASS,)),
    GateSpec("assert_target_accessible", "project", "readonly", home="app.services.custom_query.ownership_guard",
             overlays=(_BYPASS, ("membership", "成员行 ∪ 现行委派")), source="现扫补全：disclosure_notes.trace_cell"),
    GateSpec("_assert_project_edit", "project_object", "edit", local=True, home=_DN),
    GateSpec("_assert_object_project_access", "project_object", Arg("level", None, "min_permission", "readonly"),
             local=True, home=_DN),
    GateSpec("_assert_note_project_access", "project_object", _PERM, local=True, home=_DN),
    GateSpec("_assert_validation_project_access", "project_object", Arg("level", 3, "min_permission", "edit"),
             local=True, home=_DN),
    GateSpec("require_note_edit_access", "note_edit", "review", (_CONSOL,), factory=True, home=_NG, overlays=_NOTE),
    GateSpec("assert_note_edit_access", "note_edit", "review", (_CONSOL,), home=_NG, overlays=_NOTE),
    GateSpec("assert_note_edit_access_for_object", "note_edit", "review", (_CONSOL,), home=_NG, overlays=_NOTE),
    GateSpec("assert_note_edit_access_on_projects", "design", "review", (_CONSOL,), home=_NG,
             overlays=_NOTE + (("multi_project", True),)),
    GateSpec("assert_note_role_access", "design", "review",
             (Arg("project_roles", None, "project_roles", form="names"), Arg("denied_message", None, "denied_message")),
             home=_NG, overlays=_NOTE),
    GateSpec("_guard_action", "deliverable", None, (Arg("action", 3, "action", form="member"),),
             home="app.routers.deliverable", overlays=(("eqcr_exclusion", True), ("level_by", "action"))),
    GateSpec("require_operation", "operation", None, (Arg("operation", 0, "operation"),), factory=True, home=_D),
    GateSpec("check_consol_lock", "consol_lock", home=_D),
    GateSpec("require_role", "global_role", None, (Arg("roles", 0, "allowed_roles", form="names"),),
             factory=True, home=_D),
    GateSpec("get_current_user", "identity", home=_D),
    GateSpec("get_current_user_sse", "identity", home=_D),
    GateSpec("dedicated_wp_gate", "wp_visibility", home="app.routers._wp_gate",
             source="D6：router_registry 在 include_router(dependencies=...) 时附加"),
    GateSpec("get_db", "neutral", awaited=False, home="app.core.database", overlays=_DB),
    GateSpec("get_sync_db", "neutral", awaited=False, home="app.core.database", overlays=_DB),
    GateSpec("get_redis", "neutral", awaited=False, home="app.core.redis"),
    GateSpec("get_container", "neutral", awaited=False, home="app.core.container", source="现扫补全（全仓）"),
    GateSpec("get_evidence_facade", "neutral", awaited=False, home="app.routers.evidence_governance",
             source="现扫补全（全仓）"),
    GateSpec("PaginationParams", "neutral", awaited=False, home="app.core.pagination",
             source="现扫补全（全仓）：请求参数类，经不带参数的 Depends() 取参数注解"),
)
REGISTRY: dict[str, GateSpec] = {spec.name: spec for spec in _SPECS}



def analyze_module(file: str, source: bytes | str) -> ModuleInfo:
    """按本登记表解析一个文件（``file`` 为相对仓库根的正斜杠路径）；无法解析时抛 ``ParseFailure``。"""
    return astscan.analyze_module(file, source, REGISTRY)

# ─── 端点识别 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateUse:
    """一处实际生效的登记门禁。同文件具名门禁按辅助函数展开，其名字记在 chain 里。"""

    name: str
    category: str
    via: str  # registration / router / route / signature / body
    conditional: bool
    chain: tuple[str, ...]  # 经过的同文件函数（辅助函数或本文件依赖函数），由外到内
    level: str | None
    level_origin: str | None  # fixed / literal / constant / default / closure
    params: tuple[tuple[str, Any], ...]
    param: str | None  # 签名参数名
    site: tuple[str, str, int]  # (文件, 所在函数或声明, 序号)；同一 site 被多个端点共用即同一调用点


@dataclass(frozen=True)
class EndpointGates:
    file: str
    function: str
    uses: tuple[GateUse, ...]
    markers: tuple[str, ...]  # 签名里的请求参数标记
    signature_kinds: frozenset[str]  # db_session / upload_file / background_tasks
    stub: tuple[str, ...] | None
    issues: tuple[Issue, ...]


def max_level(uses: tuple[GateUse, ...] | list[GateUse]) -> str | None:
    levels = [u.level for u in uses if u.category in LEVELLED and u.level]
    return max(levels, key=LEVEL_RANK.__getitem__) if levels else None


def _pick(rule: Arg, args: tuple[Val, ...], kwargs: tuple[tuple[str, Val], ...], star: bool) -> Val | None:
    for key, val in kwargs:
        if key == rule.keyword:
            return val
    if star:  # 有 *args / **kwargs 时位置实参可能错位，未以关键字写明的一律视为不能静态确定
        return Val("unknown", "*args / **kwargs")
    if rule.position is not None and rule.position < len(args):
        return args[rule.position]
    return None if rule.default is _MISSING else Val("literal", rule.default, "default")


def _form(rule: Arg, val: Val | None) -> tuple[bool, Any]:
    if val is None or val.kind not in ("literal", "member"):
        return False, None
    if rule.form == "member":
        return (True, val.value.rsplit(".", 1)[-1]) if val.kind == "member" else (isinstance(val.value, str), val.value)
    value = val.value if val.kind == "literal" else _MISSING
    if rule.form == "bool":
        return isinstance(value, bool), value
    if rule.form == "names":
        ok = isinstance(value, (tuple, frozenset)) and all(isinstance(x, str) for x in value)
        return ok, (tuple(sorted(value)) if ok else None)
    return isinstance(value, (str, int, bool)), value


def _rules(spec: GateSpec) -> tuple[Arg, ...]:
    return ((spec.level,) if isinstance(spec.level, Arg) else ()) + spec.args


def _bound(val: Val | None, bindings: dict[str, Val] | None) -> Val | None:
    if val is None or val.kind != "param":
        return val
    if bindings is not None and val.value in bindings:
        return bindings[val.value]
    return Val("unknown", f"参数 {val.value}（取值由请求或调用方决定）")


class _Resolver:
    """为一个端点展开门禁：挂载声明 + 函数体（逐层进入同文件辅助函数，按调用方绑定实参）。"""

    def __init__(self, info: ModuleInfo, function: str) -> None:
        self.info, self.function = info, function
        self.uses: list[GateUse] = []
        self.issues: list[Issue] = []

    def issue(self, kind: str, name: str, detail: str) -> None:
        self.issues.append(Issue(kind, self.info.file, self.function, name, detail))

    def gate(self, name: str, args: tuple[Val, ...], kwargs: tuple[tuple[str, Val], ...], star: bool,
             bind: Callable[[Val | None], Val | None], via: str, cond: bool, chain: tuple[str, ...],
             param: str | None, site: tuple[str, str, int]) -> None:
        spec = REGISTRY[name]
        where = f"（经 {' → '.join(chain)}）" if chain else ""
        level, origin = (spec.level, "fixed") if isinstance(spec.level, str) else (None, None)
        if isinstance(spec.level, Arg):
            val = bind(_pick(spec.level, args, kwargs, star))
            if val is not None and val.kind == "literal" and val.value in LEVEL_RANK:
                level, origin = val.value, val.origin
            elif val is not None and val.kind == "literal":
                self.issue(UNSUPPORTED, name, f"级别取值 {val.value!r} 不是 readonly / review / edit{where}")
            else:
                self.issue(LEVEL_UNDETERMINED, name, f"级别实参 {val.value if val else '缺失'}{where}")
        params = []
        for rule in spec.args:
            val = bind(_pick(rule, args, kwargs, star))
            ok, value = _form(rule, val)
            if not ok:
                self.issue(UNSUPPORTED, name, f"参数 {rule.keyword} 无法静态确定（{val.value if val else '缺失'}）{where}")
            params.append((rule.key, value if ok else None))
        self.uses.append(GateUse(name, spec.category, via, cond, chain, level, origin, tuple(params), param, site))

    def body(self, unit: Unit, bindings: dict[str, Val] | None, chain: tuple[str, ...], cond: bool,
             stack: frozenset[str]) -> None:
        self.issues.extend(unit.body_issues)
        for site in unit.sites:
            here = cond or site.conditional
            if site.kind == "gate":
                self.gate(site.name, site.args, site.kwargs, site.star, lambda v: _bound(v, bindings), "body", here,
                          chain, None, (self.info.file, unit.qualname, site.ordinal))
                continue
            target = self.info.units.get(site.name)
            if target is None or site.name in stack:
                continue
            if target.is_async and not site.awaited:  # 协程 / 异步生成器没在本处执行：其中有门禁才报
                if self.may_gate(target, stack | {site.name}):
                    self.issue(UNSUPPORTED, site.name, "异步辅助函数没有直接 await（其中的门禁不会执行）")
                continue
            inner = {} if site.star else {p: _bound(v, bindings) for p, v in zip(target.positional, site.args)}
            inner.update((k, _bound(v, bindings)) for k, v in site.kwargs)
            for p in target.params:
                if p not in inner:
                    inner[p] = Val("unknown", "*args / **kwargs") if site.star else \
                        target.defaults.get(p, Val("unknown", f"参数 {p} 未传入"))
            start = len(self.uses)
            self.body(target, inner, (*chain, site.name), here, stack | {site.name})  # type: ignore[arg-type]
            spec = REGISTRY.get(site.name)
            if spec is not None and spec.local:
                self.check_local(spec, site, bindings, self.uses[start:])

    def may_gate(self, unit: Unit, stack: frozenset[str]) -> bool:
        """``unit`` 或其逐层同文件辅助函数里有非中性门禁调用（或识别不了的写法）。"""
        if unit.body_issues:
            return True
        for site in unit.sites:
            if site.kind == "gate" and REGISTRY[site.name].category != "neutral":
                return True
            target = self.info.units.get(site.name)
            if site.kind == "helper" and target is not None and site.name not in stack \
                    and self.may_gate(target, stack | {site.name}):
                return True
        return False

    def check_local(self, spec: GateSpec, site: Site, bindings: dict[str, Val] | None, inner: list[GateUse]) -> None:
        expected = spec.level if isinstance(spec.level, str) else None
        if isinstance(spec.level, Arg):
            val = _bound(_pick(spec.level, site.args, site.kwargs, site.star), bindings)
            expected = val.value if val is not None and val.kind == "literal" else None
        levels = {u.level for u in inner if u.category in LEVELLED}
        if not levels:
            self.issue(REGISTRY_MISMATCH, spec.name, "展开后没有项目级判定")
        elif expected is not None and levels != {expected}:
            self.issue(REGISTRY_MISMATCH, spec.name, f"登记级别 {expected}，实现给出 {sorted(map(str, levels))}")


    def decls(self, decls: tuple[Decl, ...] | list[Decl], via: str, chain: tuple[str, ...], where: str) -> None:
        for index, decl in enumerate(decls, start=1):
            if decl.kind == "gate":
                self.gate(decl.name, decl.args, decl.kwargs, False, lambda v: v, via, False, chain, decl.param,
                          (self.info.file, where, index if decl.param is None else 0))
            elif decl.kind == "local":
                self.issue(UNKNOWN_DEPENDENCY, decl.name, "本文件定义的依赖函数，未登记")
                target = self.info.units.get(decl.name)
                if target is not None and decl.name not in chain:
                    self.issues.extend(target.signature_issues)
                    self.decls(target.decls, via, (*chain, decl.name), target.qualname)
                    self.body(target, None, (*chain, decl.name), False, frozenset({decl.name}))
            else:
                self.issue(UNKNOWN_DEPENDENCY if decl.kind == "unknown" else UNSUPPORTED, decl.name, decl.detail)

    def refs(self, route: RouteRecord) -> None:
        """注册时附加的依赖只在运行时可见：按登记名识别，级别与参数取工厂闭包里的字面量。"""
        site = (f"backend/app/router_registry/{route.group}.py", "include_router", 0)
        for ref in route.registration_dependencies:
            spec = REGISTRY.get(ref.name)
            if spec is None or spec.local or spec.factory != (ref.kind == "closure"):
                kind = UNKNOWN_DEPENDENCY if spec is None or spec.local else UNSUPPORTED
                self.issue(kind, f"{ref.module}.{ref.qualname}", "路由注册时附加的依赖")
                continue
            kwargs = tuple((r.keyword, Val("literal", ref.closure_value(r.keyword), "closure"))
                           for r in _rules(spec) if r.keyword in dict(ref.closure))
            self.gate(spec.name, (), kwargs, False, lambda v: v, "registration", False, (), None, site)

    @staticmethod
    def _level_of(name: str, value: Callable[[Arg], Any]) -> Any:
        spec = REGISTRY.get(name)
        return value(spec.level) if spec is not None and isinstance(spec.level, Arg) else None

    def _decl_key(self, decl: Decl) -> tuple[str, Any]:
        def literal(rule: Arg) -> Any:
            val = _pick(rule, decl.args, decl.kwargs, False)
            return val.value if val is not None and val.kind == "literal" else None
        return decl.name, (self._level_of(decl.name, literal) if decl.kind == "gate" else None)

    def _ref_key(self, ref: DependencyRef) -> tuple[str, Any]:
        return ref.name, self._level_of(ref.name, lambda rule: ref.closure_value(
            rule.keyword, None if rule.default is _MISSING else rule.default))

    def compare(self, label: str, decls: tuple[Decl, ...] | list[Decl], refs: tuple[DependencyRef, ...]) -> None:
        """源码声明与运行时路由表逐项对账（名称与级别；签名依赖按参数名对）。"""
        if label == "签名依赖":
            ours: Any = {d.param: self._decl_key(d) for d in decls}
            theirs: Any = {r.param: self._ref_key(r) for r in refs}
        else:
            ours, theirs = [self._decl_key(d) for d in decls], [self._ref_key(r) for r in refs]
        if ours != theirs:
            self.issue(UNSUPPORTED, label, f"源码声明 {ours} 与运行时路由表 {theirs} 不一致")


def recognize_endpoint(info: ModuleInfo, declared: DeclaredRoute, route: RouteRecord | None = None) -> EndpointGates:
    """识别一条声明路由的现门禁。``route`` 为路由表里对应的记录（未注册的端点传 None，不做运行时对账）。"""
    resolver = _Resolver(info, declared.function)
    unit = info.units.get(declared.function)
    entries = info.endpoints.get(declared.function, ())
    if unit is None or declared.decorator >= len(entries) or declared.router not in info.routers:
        resolver.issue(UNSUPPORTED, declared.function, "源码里找不到这条路由声明")
        return EndpointGates(info.file, declared.function, (), (), frozenset(), None, tuple(resolver.issues))
    router_decls, route_decls = info.routers[declared.router][1], entries[declared.decorator][3]
    if route is not None:
        resolver.refs(route)
    resolver.decls(router_decls, "router", (), f"APIRouter {declared.router}")
    resolver.decls(route_decls, "route", (), f"{declared.function} 的路由装饰器")
    resolver.issues.extend(unit.signature_issues)
    resolver.decls(unit.decls, "signature", (), declared.function)
    resolver.body(unit, None, (), False, frozenset({declared.function}))
    if route is not None:
        resolver.compare("路由器依赖", router_decls, route.router_dependencies)
        resolver.compare("装饰器依赖", route_decls, route.route_dependencies)
        resolver.compare("签名依赖", unit.decls, route.parameter_dependencies)
    return EndpointGates(info.file, declared.function, tuple(resolver.uses), tuple(unit.markers),
                         frozenset(unit.signature_kinds), unit.stub, tuple(dict.fromkeys(resolver.issues)))


def recognize_function(info: ModuleInfo, qualname: str) -> EndpointGates:
    """识别任一函数单元（不限端点；供影响清单扫描服务层与辅助函数）：签名依赖 + 函数体，逐层进入同文件辅助函数。

    没有调用方可绑定实参：级别取自本函数参数的记「级别无法静态确定」（经调用方逐个取值的，从调用方识别）。"""
    resolver = _Resolver(info, qualname)
    unit = info.units.get(qualname)
    if unit is None:
        resolver.issue(UNSUPPORTED, qualname, "源码里找不到这个函数")
        return EndpointGates(info.file, qualname, (), (), frozenset(), None, tuple(resolver.issues))
    resolver.issues.extend(unit.signature_issues)
    resolver.decls(unit.decls, "signature", (), qualname)
    resolver.body(unit, None, (), False, frozenset({qualname.rsplit(".", 1)[-1]}))
    return EndpointGates(info.file, qualname, tuple(resolver.uses), tuple(unit.markers),
                         frozenset(unit.signature_kinds), unit.stub, tuple(dict.fromkeys(resolver.issues)))
