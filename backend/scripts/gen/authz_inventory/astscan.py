"""源码静态扫描（供 gates 识别端点门禁；design §4.12「函数级识别用 AST」）。

``analyze_module(file, source, registry)`` 把一个文件解析成 ``ModuleInfo``（数据模型见 ``astmodel``）：导入别名
（含函数体内的延迟导入）、模块级唯一绑定的字面量常量、全部函数单元（模块级 / 类方法 / 嵌套函数）的签名依赖声明与
函数体调用点、模块级 ``APIRouter`` 与路由装饰器。只认 ``ast.Call`` 的 ``ast.Name`` / ``ast.Attribute`` 节点，
注释、docstring 与字符串不计；调用点带「条件执行」标记与实参的静态取值。登记表由调用方传入（``gates.REGISTRY``），
本模块不认识任何具体门禁的语义。

支持的写法另含：路由器前缀与装饰器路径为同文件字符串常量及其 ``+`` 拼接；``Depends()`` 不带参数时按 FastAPI
取参数注解为依赖；门禁工厂的返回值赋给局部变量后 ``await 变量(...)``。其余写法记 ``Issue``，不静默跳过。
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Mapping
from typing import Any

from .astmodel import (DEPENDS_MARKERS, PARAM_MARKERS, ROUTE_VERBS, UNSUPPORTED, Decl, Issue, ModuleInfo,
                       ParseFailure, Site, Unit, Val)
from .routes import module_name


def _frozen(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_frozen(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _frozen(v)) for k, v in value.items()))
    return value


def _literal(node: ast.AST) -> tuple[bool, Any]:
    """字面量（含 frozenset / set / tuple / list 包一层字面量）→ (是否字面量, 可哈希的值)。"""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords \
            and node.func.id in ("frozenset", "set", "tuple", "list") and len(node.args) <= 1:
        ok, inner = _literal(node.args[0]) if node.args else (True, ())
        if not ok or not isinstance(inner, (tuple, frozenset)):
            return False, None
        return True, frozenset(inner) if node.func.id in ("frozenset", "set") else tuple(inner)
    try:
        return True, _frozen(ast.literal_eval(node))
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False, None


def _bindings(tree: ast.AST) -> Counter[str]:
    """全模块每个名字的绑定次数（赋值、del、形参、定义、导入、except、match、global / nonlocal）。"""
    counts: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            counts[node.id] += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            counts[node.name] += 1
        elif isinstance(node, ast.arg):
            counts[node.arg] += 1
        elif isinstance(node, ast.alias):
            counts[(node.asname or node.name).split(".")[0]] += 1
        elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
            counts[node.name] += 1
        elif isinstance(node, ast.MatchMapping) and node.rest:
            counts[node.rest] += 1
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            counts.update(node.names)
    return counts


def _assign_target(node: ast.AST) -> tuple[str | None, ast.expr | None]:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id, node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
        return node.target.id, node.value
    return None, None


def _dotted(node: ast.AST | None) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name) and parts:
        return ".".join([node.id, *reversed(parts)])
    return None


def _base_name(info: ModuleInfo, func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return info.imports.get(func.id, func.id)
    return func.attr if isinstance(func, ast.Attribute) else None


def _resolve(info: ModuleInfo, func: ast.AST) -> tuple[str, str | None]:
    """调用目标 → (gate / helper / bad_local / other, 名称)。本文件模块级函数即同文件辅助函数；
    门禁实现所在模块里对同名函数的调用仍算门禁（供影响清单识别「门禁内部」）。"""
    if isinstance(func, ast.Name):
        if func.id in info.toplevel:
            spec = info.registry.get(func.id)
            local_gate = spec is not None and not spec.local and spec.home == info.module
            return ("gate" if local_gate else "helper"), func.id
        name = info.imports.get(func.id, func.id)
    elif isinstance(func, ast.Attribute):
        name = func.attr
    else:
        return "other", None
    spec = info.registry.get(name)
    if spec is None:
        return "other", name
    return ("bad_local" if spec.local else "gate"), name


def _value(info: ModuleInfo, params: frozenset[str], expr: ast.AST) -> Val:
    if isinstance(expr, ast.Constant):
        return Val("literal", expr.value)
    if isinstance(expr, ast.Name):
        if expr.id in params:
            return Val("param", expr.id)
        if expr.id in info.constants:
            return Val("literal", info.constants[expr.id], "constant")
        return Val("unknown", expr.id)
    dotted = _dotted(expr)
    if dotted:
        return Val("member", dotted)
    ok, value = _literal(expr)
    return Val("literal", value) if ok else Val("unknown", ast.unparse(expr)[:80])


def _static_str(info: ModuleInfo, expr: ast.AST | None) -> str | None:
    """字符串字面量、同文件字符串常量及二者的 ``+`` 拼接 → 静态取值；其他写法（含 None）→ None。"""
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.Name) and isinstance(info.constants.get(expr.id), str):
        return info.constants[expr.id]
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        left, right = _static_str(info, expr.left), _static_str(info, expr.right)
        return None if left is None or right is None else left + right
    return None


def _call_values(info: ModuleInfo, params: frozenset[str], call: ast.Call) -> tuple[Any, Any, bool]:
    args = tuple(_value(info, params, a) for a in call.args if not isinstance(a, ast.Starred))
    kwargs = tuple((k.arg, _value(info, params, k.value)) for k in call.keywords if k.arg)
    star = any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords)
    return args, kwargs, star


def _decl(info: ModuleInfo, param: str | None, call: ast.Call, annotation: ast.expr | None = None) -> Decl:
    """``Depends(...)`` / ``Security(...)`` → 依赖声明；不带依赖参数时按 FastAPI 取参数注解（类型）为依赖。"""
    target = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "dependency"), None)
    if target is None:
        if not isinstance(annotation, (ast.Name, ast.Attribute)):
            return Decl(param, "Depends()", "unknown", detail="不带参数的 Depends()，参数注解不是名称")
        target = annotation
    if isinstance(target, ast.Call):
        kind, name = _resolve(info, target.func)
        args, kwargs, star = _call_values(info, frozenset(), target)
        if kind == "gate" and info.registry[name].factory and not star:  # type: ignore[index]
            return Decl(param, name, "gate", args, kwargs)  # type: ignore[arg-type]
        detail = "登记的门禁不是工厂" if kind == "gate" else "未登记的工厂调用"
        return Decl(param, name or ast.unparse(target.func), "bad" if kind == "gate" else "unknown", detail=detail)
    if isinstance(target, (ast.Name, ast.Attribute)):
        kind, name = _resolve(info, target)
        if kind == "gate" and info.registry[name].factory:  # type: ignore[index]
            return Decl(param, name, "bad", detail="门禁工厂没有调用就作为依赖")  # type: ignore[arg-type]
        return Decl(param, name, {"gate": "gate", "helper": "local"}.get(kind, "unknown"))  # type: ignore[arg-type]
    return Decl(param, ast.unparse(target)[:80], "bad", detail="依赖目标不是名称或调用")


def _depends_call(info: ModuleInfo, node: ast.AST | None) -> ast.Call | None:
    if isinstance(node, ast.Call) and _base_name(info, node.func) in DEPENDS_MARKERS:
        return node
    if isinstance(node, ast.Subscript) and _base_name(info, node.value) == "Annotated" \
            and isinstance(node.slice, ast.Tuple):
        return next((e for e in node.slice.elts[1:] if _depends_call(info, e) is not None), None)  # type: ignore[misc]
    return None


def _scan_param(info: ModuleInfo, unit: Unit, arg: ast.arg, default: ast.expr | None) -> None:
    ann = arg.annotation
    call = _depends_call(info, default) or _depends_call(info, ann)
    dep_type = ann  # Depends() 不带参数时的依赖：注解本身，或 Annotated[类型, ...] 的类型
    if isinstance(ann, ast.Subscript) and _base_name(info, ann.value) == "Annotated" and isinstance(ann.slice, ast.Tuple):
        dep_type = ann.slice.elts[0]
    names = {getattr(n, "id", None) or getattr(n, "attr", None) for n in ast.walk(ann)} if ann is not None else set()
    if "UploadFile" in names:
        unit.signature_kinds.add("upload_file")
    if "BackgroundTasks" in names:
        unit.signature_kinds.add("background_tasks")
    if call is not None:
        decl = _decl(info, arg.arg, call, dep_type)
        unit.decls.append(decl)
        spec = info.registry.get(decl.name) if decl.kind == "gate" else None
        if spec is not None and ("db_session", True) in spec.overlays:
            unit.signature_kinds.add("db_session")
    elif isinstance(default, ast.Call):
        marker = _base_name(info, default.func)
        if marker in PARAM_MARKERS:
            unit.markers.append(marker)  # type: ignore[arg-type]
            if marker == "File":
                unit.signature_kinds.add("upload_file")
        elif marker == "BackgroundTasks":
            unit.signature_kinds.add("background_tasks")
        elif not _literal(default)[0]:  # frozenset() 之类的字面量默认值不是依赖
            unit.signature_issues.append(Issue(UNSUPPORTED, info.file, unit.qualname, marker or "?",
                                               f"参数 {arg.arg} 的默认值是未登记的调用"))


def _children(node: ast.AST, cond: bool) -> list[tuple[ast.AST, bool]]:
    """子节点及其「条件执行」标记：分支体、异常处理、循环体、with 体、match、短路与推导式里的为条件执行。"""
    nested = lambda nodes: [(c, True) for c in nodes]  # noqa: E731
    if isinstance(node, (ast.If, ast.While)):
        return [(node.test, cond), *nested(node.body + node.orelse)]
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return [(node.target, cond), (node.iter, cond), *nested(node.body + node.orelse)]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [*((item, cond) for item in node.items), *nested(node.body)]
    if isinstance(node, ast.Match):
        return [(node.subject, cond), *nested(node.cases)]
    if isinstance(node, ast.IfExp):
        return [(node.test, cond), (node.body, True), (node.orelse, True)]
    if isinstance(node, ast.BoolOp):
        return [(node.values[0], cond), *nested(node.values[1:])]
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        first = node.generators[0]
        rest = [c for c in ast.iter_child_nodes(node) if c is not first]
        return [(first.iter, cond), *nested(c for c in ast.iter_child_nodes(first) if c is not first.iter),
                *nested(rest)]
    if isinstance(node, (ast.Try, ast.TryStar, ast.Assert)):
        return nested(ast.iter_child_nodes(node))
    return [(c, cond) for c in ast.iter_child_nodes(node)]


class _BodyState:
    """一个函数体扫描期间的状态：赋给局部变量、待调用的门禁工厂调用。"""

    def __init__(self, params: frozenset[str]) -> None:
        self.params = params
        self.pending: dict[str, tuple[str, ast.Call, bool]] = {}  # 变量 → (门禁名, 工厂调用, 工厂处是否条件执行)
        self.called: set[str] = set()


def _scan_body(info: ModuleInfo, unit: Unit, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
    state = _BodyState(frozenset(unit.params))

    def visit(current: ast.AST, cond: bool, parents: tuple[ast.AST, ...]) -> None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return  # 嵌套定义是独立单元，不随本函数执行
        if isinstance(current, ast.Call) and _base_name(info, current.func) in DEPENDS_MARKERS:
            info.body_depends.append((unit.qualname, _decl(info, None, current)))
            return  # 依赖声明（如注册循环里的 dependencies=），不是本函数的执行
        if isinstance(current, ast.Call):
            _record_call(info, unit, current, cond, parents, state)
        for child, child_cond in _children(current, cond):
            visit(child, child_cond, (*parents, current))

    for stmt in node.body:
        visit(stmt, False, (node,))
    for var in sorted(set(state.pending) - state.called):
        unit.body_issues.append(Issue(UNSUPPORTED, info.file, unit.qualname, state.pending[var][0],
                                      f"门禁工厂的返回值赋给局部变量 {var} 后，本函数里没有调用它"))


def _record_call(info: ModuleInfo, unit: Unit, call: ast.Call, cond: bool, parents: tuple[ast.AST, ...],
                 state: _BodyState) -> None:
    parent, via, source = parents[-1], None, call
    if isinstance(call.func, ast.Name) and call.func.id in state.pending:
        via = call.func.id  # 调用的是先前赋给局部变量的门禁工厂返回值
        name, source, factory_cond = state.pending[via]
        kind, cond = "gate", cond or factory_cond
        state.called.add(via)
    else:
        kind, name = _resolve(info, call.func)  # type: ignore[assignment]
    if kind == "bad_local":
        unit.body_issues.append(Issue(UNSUPPORTED, info.file, unit.qualname, name or "?",
                                      "同文件具名门禁不在本文件定义（跨文件调用）"))
        return
    if kind not in ("gate", "helper"):
        return
    awaited = isinstance(parent, ast.Await)
    if kind == "gate":
        spec = info.registry[name]  # type: ignore[index]
        if spec.factory and via is None:
            target, value = _assign_target(parent)
            if target is not None and value is call:
                state.pending[target] = (spec.name, call, cond)
                return
            if not (isinstance(parent, ast.Call) and parent.func is call):
                unit.body_issues.append(Issue(UNSUPPORTED, info.file, unit.qualname, spec.name,
                                              "门禁工厂的返回值没有在同一表达式里调用，也没有赋给局部变量"))
                return
            awaited = len(parents) > 1 and isinstance(parents[-2], ast.Await)
        if spec.awaited and not awaited:
            unit.body_issues.append(Issue(UNSUPPORTED, info.file, unit.qualname, spec.name,
                                          "门禁调用没有直接 await（协程不会执行）"))
            return
    args, kwargs, star = _call_values(info, state.params, source)
    unit.sites.append(Site(kind, name, len(unit.sites) + 1, cond, awaited, args, kwargs, star, via))  # type: ignore[arg-type]


def _stub(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...] | None:
    """函数体（去掉 docstring）只有 raise 时，各 raise 的错误；否则 None。"""
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body or not all(isinstance(s, ast.Raise) and s.exc is not None for s in body):
        return None
    labels = []
    for stmt in body:
        exc = stmt.exc  # type: ignore[attr-defined]
        func = exc.func if isinstance(exc, ast.Call) else exc
        name = (_dotted(func) or getattr(func, "id", None) or ast.unparse(func)).rsplit(".", 1)[-1]
        if name == "HTTPException" and isinstance(exc, ast.Call):
            status = exc.args[0] if exc.args else next((k.value for k in exc.keywords if k.arg == "status_code"), None)
            dotted = _dotted(status) or ""
            code = status.value if isinstance(status, ast.Constant) else \
                (dotted.rsplit("HTTP_", 1)[1].split("_", 1)[0] if "HTTP_" in dotted else "?")
            name = f"HTTP {code}"
        labels.append(name)
    return tuple(labels)


def _make_unit(info: ModuleInfo, node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> Unit:
    a = node.args
    positional = tuple(x.arg for x in a.posonlyargs + a.args)
    extra = tuple(x.arg for x in (a.vararg, a.kwarg) if x is not None)
    unit = Unit(qualname, isinstance(node, ast.AsyncFunctionDef), positional + tuple(x.arg for x in a.kwonlyargs) + extra,
                positional)
    pairs = list(zip(a.posonlyargs + a.args, [None] * (len(positional) - len(a.defaults)) + list(a.defaults)))
    pairs += list(zip(a.kwonlyargs, a.kw_defaults))
    for arg, default in pairs:
        _scan_param(info, unit, arg, default)
        if default is not None:
            value = _value(info, frozenset(), default)
            unit.defaults[arg.arg] = Val(value.kind, value.value, "default") if value.kind == "literal" else value
    _scan_body(info, unit, node)
    unit.stub = _stub(node)
    return unit


def _collect_units(info: ModuleInfo, body: list[ast.stmt], prefix: str) -> None:
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = prefix + node.name
            info.units[qualname] = _make_unit(info, node, qualname)  # 同名重定义以最后一个为准
            _collect_units(info, node.body, qualname + ".<locals>.")
        elif isinstance(node, ast.ClassDef):
            _collect_units(info, node.body, prefix + node.name + ".")
        else:
            for name in ("body", "orelse", "finalbody", "handlers", "cases"):
                for child in getattr(node, name, ()) or ():
                    _collect_units(info, getattr(child, "body", [child]) if name in ("handlers", "cases")
                                   else [child], prefix)


def _dependencies_kw(info: ModuleInfo, call: ast.Call, where: str) -> tuple[Decl, ...]:
    expr = next((k.value for k in call.keywords if k.arg == "dependencies"), None)
    if expr is None:
        return ()
    if not isinstance(expr, (ast.List, ast.Tuple)):
        info.issues.append(Issue(UNSUPPORTED, info.file, where, "dependencies", "不是 Depends(...) 的列表字面量"))
        return ()
    decls = []
    for element in expr.elts:
        if isinstance(element, ast.Call) and _base_name(info, element.func) in DEPENDS_MARKERS:
            decls.append(_decl(info, None, element))
        else:
            info.issues.append(Issue(UNSUPPORTED, info.file, where, ast.unparse(element)[:60], "dependencies 元素不是 Depends(...)"))
    return tuple(decls)


def _collect_routes(info: ModuleInfo, tree: ast.Module) -> None:
    for node in tree.body:
        target, value = _assign_target(node)
        if target and isinstance(value, ast.Call) and _base_name(info, value.func) == "APIRouter":
            expr = next((k.value for k in value.keywords if k.arg == "prefix"), None)
            prefix = "" if expr is None else _static_str(info, expr)
            if prefix is None:
                info.issues.append(Issue(UNSUPPORTED, info.file, f"APIRouter {target}", "prefix",
                                         "前缀不是字符串字面量、同文件字符串常量或其 + 拼接"))
                prefix = ""
            info.routers[target] = (prefix, _dependencies_kw(info, value, f"APIRouter {target}"))
    top = {id(n) for n in tree.body}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = [d for d in node.decorator_list if isinstance(d, ast.Call)
                      and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_VERBS]
        if not decorators:
            continue
        if id(node) not in top:
            info.issues.append(Issue(UNSUPPORTED, info.file, node.name, node.name, "路由函数不在模块顶层"))
            continue
        entries = []
        for deco in decorators:
            router = deco.func.value.id if isinstance(deco.func.value, ast.Name) else ast.unparse(deco.func.value)
            path = _static_str(info, deco.args[0] if deco.args else
                               next((k.value for k in deco.keywords if k.arg == "path"), None))
            methods_expr = next((k.value for k in deco.keywords if k.arg == "methods"), None)
            ok, methods = _literal(methods_expr) if methods_expr is not None else (True, ("GET",))
            if router not in info.routers or path is None \
                    or (deco.func.attr == "api_route" and not (ok and all(isinstance(m, str) for m in methods))):
                info.issues.append(Issue(UNSUPPORTED, info.file, node.name, ast.unparse(deco)[:80],
                                         "路由装饰器须挂在本文件模块级 APIRouter 上；路径须为字符串字面量、"
                                         "同文件字符串常量或其 + 拼接，方法须为字面量"))
                continue
            verbs = tuple(sorted({m.upper() for m in methods})) if deco.func.attr == "api_route" else (deco.func.attr.upper(),)
            entries.append((router, verbs, path, _dependencies_kw(info, deco, node.name)))
        info.endpoints[node.name] = tuple(entries)


def analyze_module(file: str, source: bytes | str, registry: Mapping[str, Any]) -> ModuleInfo:
    """解析一个文件（``file`` 为相对仓库根的正斜杠路径）。无法解析时抛 ``ParseFailure``。

    ``source`` 宜传文件原始字节（编码声明与 UTF-8 BOM 由解析器处理）；传 str 时去掉开头的 BOM。"""
    if isinstance(source, str):
        source = source.removeprefix("\ufeff")
    try:
        tree = ast.parse(source, filename=file)
    except (SyntaxError, ValueError) as exc:
        raise ParseFailure(f"{file}：无法解析（{exc}）") from exc
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                imports[local] = alias.name if (alias.asname or isinstance(node, ast.ImportFrom)) else local
    counts = _bindings(tree)
    constants = {}
    for node in tree.body:
        target, value = _assign_target(node)
        if target and counts[target] == 1:
            ok, literal = _literal(value)  # type: ignore[arg-type]
            if ok:
                constants[target] = literal
    info = ModuleInfo(file, module_name(file), imports, constants,
                      {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}, registry)
    _collect_units(info, tree.body, "")
    _collect_routes(info, tree)
    return info
