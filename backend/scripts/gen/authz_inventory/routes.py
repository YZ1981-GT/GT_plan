"""运行时路由表：端点注册信息取自目标树真实执行的路由注册（design D6）。

- ``collect_route_table(root)``：在子进程里把 ``<root>/backend`` 放到 ``sys.path[0]``，导入该树的
  ``app.router_registry``（断言 ``app.__file__`` 位于 ``<root>`` 之下），按 ``register_all_routers``
  实际调用的各个 ``register_*_routers`` 逐个建空 ``FastAPI()`` 注册一次，收集每条 ``APIRoute``：方法、
  完整路径（注册前缀 + 路由器前缀 + 装饰器路径）、端点函数所在文件（相对仓库根、正斜杠）与函数名、
  注册 / 路由器 / 路由 / 签名参数四处依赖、所属注册分组。一个函数多条路由、多个方法各记一条。
- ``note_router_files(root)``：附注写端点清册的扫描范围（需求 1.1）。
- ``match_declared_routes(...)``：源码声明的路由与路由表对账；声明了却不在表里的记「未注册」，
  表里有却对不上源码声明的单列（调用方按「不支持的写法」报错）。

子进程以 ``-I -B -X utf8`` 启动：不带入当前进程的 ``sys.path`` / ``PYTHON*`` 环境，不写 ``.pyc``；
环境变量里的数据库 / Redis 连接串不传给子进程；并装审计钩子，网络连接、数据库驱动连接、文件写入
（结果文件除外）、增删改目录与文件、起子进程一律拦下并记录 —— 收集路由不得连接开发库或共享 Redis，
也不得在被扫描的树里落任何文件。有任何一项被拦下即判收集失败（导入期的副作用被拦后，路由表可能与
生产注册不一致），不静默放过。

本文件会被子进程当脚本执行（``--child``），模块顶层只导入标准库。
"""

from __future__ import annotations

import ast
import fnmatch
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "authz_route_table/v1"
REGISTRY_MODULE = "app.router_registry"
NOTE_FILE_PATTERNS = ("note*", "*note*", "disclosure*")
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_ENTRY = "register_all_routers"
_ENTRY_EXTRA_CALLS = frozenset({"_validate_registry_completeness"})  # 只读校验，不注册路由


class RouteCollectionError(RuntimeError):
    """收集运行时路由表失败（信息为中文原因）。"""


def _freeze(value: Any) -> Any:
    """把 JSON 取回的值变成可哈希形式：list → tuple，dict → 按键排序的 (键, 值) 元组。"""
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    return value


@dataclass(frozen=True)
class DependencyRef:
    """运行时依赖对象（``Depends(x)`` 的 ``x``）的可序列化描述。"""

    name: str  # 识别名：函数取 __name__；工厂产出的闭包取工厂名；类 / 实例取类名
    module: str
    qualname: str
    kind: str  # function / closure / class / instance / partial / other
    file: str | None = None  # 定义所在文件（相对仓库根、正斜杠）；不在仓库内为 None
    closure: tuple[tuple[str, Any], ...] = ()  # 闭包自由变量的字面量取值（按变量名排序）
    param: str | None = None  # 签名参数依赖的参数名；``dependencies=`` 声明的为 None

    def closure_value(self, var: str, default: Any = None) -> Any:
        return dict(self.closure).get(var, default)

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "module": self.module, "qualname": self.qualname, "kind": self.kind,
                "file": self.file, "closure": [[k, v] for k, v in self.closure], "param": self.param}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DependencyRef:
        return cls(name=data["name"], module=data["module"], qualname=data["qualname"], kind=data["kind"],
                   file=data["file"], closure=tuple((k, _freeze(v)) for k, v in data["closure"]),
                   param=data["param"])


_DEP_FIELDS = ("registration_dependencies", "router_dependencies", "route_dependencies", "parameter_dependencies")


@dataclass(frozen=True)
class RouteRecord:
    """路由表的一条记录：一个（方法，完整路径）。"""

    method: str
    path: str  # 完整路径（未注册的端点为 路由器前缀 + 装饰器路径）
    group: str | None  # 注册分组（router_registry 子模块名）；未注册为 None
    registered: bool
    file: str | None  # 端点函数所在文件（相对仓库根、正斜杠）
    function: str  # 端点函数 __qualname__
    module: str
    registration_prefix: str = ""
    registration_dependencies: tuple[DependencyRef, ...] = ()  # include_router(dependencies=...)
    router_dependencies: tuple[DependencyRef, ...] = ()  # APIRouter(dependencies=...)
    route_dependencies: tuple[DependencyRef, ...] = ()  # 装饰器 dependencies=（及嵌套路由器带入的）
    parameter_dependencies: tuple[DependencyRef, ...] = ()  # 签名参数上的 Depends

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.file or "", self.path, self.method)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {k: getattr(self, k) for k in ("method", "path", "group", "registered", "file",
                                                             "function", "module", "registration_prefix")}
        for name in _DEP_FIELDS:
            data[name] = [ref.to_json() for ref in getattr(self, name)]
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RouteRecord:
        deps = {name: tuple(DependencyRef.from_json(d) for d in data[name]) for name in _DEP_FIELDS}
        return cls(method=data["method"], path=data["path"], group=data["group"], registered=data["registered"],
                   file=data["file"], function=data["function"], module=data["module"],
                   registration_prefix=data["registration_prefix"], **deps)


@dataclass(frozen=True)
class RouteTable:
    """一棵树的运行时路由表。``elapsed_seconds`` 只供日志与验收记录，不进任何产物。"""

    groups: tuple[str, ...]  # 注册分组，按 register_all_routers 的调用顺序
    routes: tuple[RouteRecord, ...]
    api_route_counts: tuple[tuple[str, int], ...]  # 各分组的 APIRoute 对象数（未按方法展开）
    other_route_counts: tuple[tuple[str, int], ...]  # 各分组经 include_router 加入的非 APIRoute 路由数
    app_file: str  # 导入的 app/__init__.py（相对仓库根）
    blocked: tuple[str, ...] = ()  # 子进程里被拦下的副作用（应为空）
    elapsed_seconds: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "groups": list(self.groups), "routes": [r.to_json() for r in self.routes],
                "api_route_counts": dict(self.api_route_counts),
                "other_route_counts": dict(self.other_route_counts),
                "app_file": self.app_file, "blocked": list(self.blocked)}

    @classmethod
    def from_json(cls, data: dict[str, Any], *, elapsed_seconds: float = 0.0) -> RouteTable:
        if data.get("schema") != SCHEMA:
            raise RouteCollectionError(f"路由表格式不符：期望 {SCHEMA}，得到 {data.get('schema')!r}")
        return cls(groups=tuple(data["groups"]), routes=tuple(RouteRecord.from_json(r) for r in data["routes"]),
                   api_route_counts=tuple(data["api_route_counts"].items()),
                   other_route_counts=tuple(data["other_route_counts"].items()),
                   app_file=data["app_file"], blocked=tuple(data["blocked"]), elapsed_seconds=elapsed_seconds)


@dataclass(frozen=True)
class DeclaredRoute:
    """源码里声明的一条路由（由 gates.ModuleInfo.declared_routes 给出）。"""

    file: str
    function: str
    method: str
    path: str  # 路由器前缀 + 装饰器路径
    router: str  # 路由器变量名
    decorator: int  # 第几个路由装饰器（从 0 起，按源码自上而下）


@dataclass(frozen=True)
class RouteMatch:
    registered: tuple[tuple[DeclaredRoute, RouteRecord], ...]
    unregistered: tuple[tuple[DeclaredRoute, RouteRecord], ...]  # 记录 registered=False、group=None
    unmatched_runtime: tuple[RouteRecord, ...]  # 扫描文件里、对不上任何源码声明的运行时路由


def module_name(rel_file: str) -> str:
    """``backend/app/routers/x.py`` → ``app.routers.x``（``__init__.py`` 取包名）。"""
    parts = Path(rel_file).with_suffix("").parts
    if parts and parts[0] == "backend":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def note_router_files(root: Path) -> tuple[str, ...]:
    """附注清册的扫描文件：``backend/app/routers/`` 直接子文件中匹配三个模式的 ``.py``（去重、排序）。"""
    folder = Path(root) / "backend" / "app" / "routers"
    names = {p.name for p in folder.iterdir() if p.is_file() and p.suffix == ".py"
             and any(fnmatch.fnmatchcase(p.name, pattern) for pattern in NOTE_FILE_PATTERNS)}
    return tuple(f"backend/app/routers/{name}" for name in sorted(names))


def match_declared_routes(table: RouteTable, declared: Iterable[DeclaredRoute],
                          files: Iterable[str]) -> RouteMatch:
    """把源码声明与 ``files`` 内的运行时路由逐条对上：方法、函数相同，且 完整路径 = 注册前缀 + 声明路径。"""
    scope = set(files)
    runtime = [r for r in table.routes if r.file in scope]
    used: set[int] = set()
    registered: list[tuple[DeclaredRoute, RouteRecord]] = []
    unregistered: list[tuple[DeclaredRoute, RouteRecord]] = []
    for decl in declared:
        hits = [r for r in runtime if (r.file, r.function, r.method) == (decl.file, decl.function, decl.method)
                and r.path == r.registration_prefix + decl.path]
        if hits:
            registered.extend((decl, r) for r in hits)
            used.update(id(r) for r in hits)
        else:
            record = RouteRecord(method=decl.method, path=decl.path, group=None, registered=False, file=decl.file,
                                 function=decl.function, module=module_name(decl.file))
            unregistered.append((decl, record))
    leftovers = tuple(r for r in runtime if id(r) not in used)
    return RouteMatch(tuple(registered), tuple(unregistered), leftovers)


def collect_route_table(root: Path, *, timeout: float = 900.0) -> RouteTable:
    """在子进程里收集 ``root`` 这棵树的运行时路由表（父进程调用）。"""
    root = Path(root).resolve()
    if not (root / "backend" / "app" / "router_registry" / "__init__.py").is_file():
        raise RouteCollectionError(f"--root 指向的不是本仓库（缺少 backend/app/router_registry/__init__.py）：{root}")
    workdir = Path(tempfile.mkdtemp(prefix="authz_routes_"))
    try:
        out = workdir / "routes.json"
        cmd = [sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "--child", str(root), str(out)]
        env = {k: v for k, v in os.environ.items() if not _is_connection_env(k)}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RouteCollectionError(f"子进程收集路由超时（{timeout:.0f} 秒）") from exc
        elapsed = time.monotonic() - started
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0 or not out.is_file():
            tail = "\n".join(stderr.splitlines()[-25:])
            raise RouteCollectionError(f"子进程收集路由失败（退出码 {proc.returncode}）：\n{tail}")
        data = json.loads(out.read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    table = RouteTable.from_json(data, elapsed_seconds=elapsed)
    if table.blocked:
        raise RouteCollectionError("子进程收集路由时有副作用被拦下（路由表可能与生产注册不一致）：\n"
                                   + "\n".join(f"- {item}" for item in table.blocked))
    return table


def _is_connection_env(name: str) -> bool:
    """数据库 / Redis 连接串类环境变量（不传给子进程）。"""
    upper = name.upper()
    return any(token in upper for token in ("DATABASE_URL", "REDIS_URL", "_DSN")) or upper.startswith("PG")


def routes_by_function(table: RouteTable) -> dict[tuple[str, str], tuple[RouteRecord, ...]]:
    """（端点函数所在文件，``__qualname__``）→ 该函数的全部路由（按完整路径、方法排序）。

    供按函数归属端点的场景使用（影响清单的「所门禁的端点」）：嵌套路由器、工厂里建的路由器也能对上。"""
    grouped: dict[tuple[str, str], list[RouteRecord]] = {}
    for record in table.routes:
        if record.file is not None:
            grouped.setdefault((record.file, record.function), []).append(record)
    return {key: tuple(sorted(items, key=lambda r: (r.path, r.method))) for key, items in sorted(grouped.items())}


# ─── 以下只在子进程里执行 ─────────────────────────────────────────────────────

_NET_EVENTS = frozenset({"socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo",
                         "socket.gethostbyname", "socket.gethostbyaddr"})
_FS_EVENTS = frozenset({"os.mkdir", "os.rmdir", "os.remove", "os.rename", "os.replace", "os.truncate",
                        "os.symlink", "os.link", "os.chmod", "os.chown", "os.utime", "os.chflags",
                        "shutil.rmtree", "shutil.copyfile", "shutil.copytree", "shutil.move",
                        "shutil.copymode", "shutil.copystat", "shutil.chown"})
_PROC_EVENTS = frozenset({"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
                          "os.startfile", "os.fork", "os.forkpty", "pty.spawn"})
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


def _install_guard(blocked: list[str], allowed_write: Path) -> None:
    """审计钩子：拦下网络 / 文件写入 / 文件系统改动 / 子进程 / 磁盘 SQLite，并记录。"""
    allowed = os.path.normcase(str(allowed_write))

    def refuse(what: str) -> None:
        blocked.append(what)
        raise PermissionError(f"authz_inventory 收集路由时禁止：{what}")

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event == "open":
            path, mode, flags = args
            writes = any(c in mode for c in "wax+") if isinstance(mode, str) else bool((flags or 0) & _WRITE_FLAGS)
            if writes and not isinstance(path, int) and os.path.normcase(os.path.abspath(os.fsdecode(path))) != allowed:
                refuse(f"写文件 {os.fsdecode(path)}")
        elif event in _NET_EVENTS:  # connect / bind / sendto 的第 2 个参数是地址，其余是主机名
            refuse(f"{event} {args[1] if event.endswith(('connect', 'bind', 'sendto')) else args[:2]!r}")
        elif event in _FS_EVENTS or event in _PROC_EVENTS:
            refuse(f"{event} {args[:1]!r}")
        elif event == "sqlite3.connect" and str(args[0]) != ":memory:":
            refuse(f"sqlite3.connect {args[0]!r}")

    sys.addaudithook(hook)
    import importlib

    for module_name_, attr in (("asyncpg", "connect"), ("asyncpg.connection", "connect"), ("psycopg2", "connect")):
        try:
            module = importlib.import_module(module_name_)
        except Exception:  # 驱动不存在即无从连接
            continue
        if hasattr(module, attr):
            setattr(module, attr, lambda *a, _w=f"{module_name_}.{attr}", **k: refuse(f"数据库连接 {_w}"))


def _register_functions(registry: Any) -> list[Any]:
    """按 ``register_all_routers`` 的函数体取出它实际调用的各个 ``register_*_routers``（顺序不变）。"""
    tree = ast.parse(inspect.getsource(getattr(registry, _ENTRY)).lstrip())
    names: list[str] = []
    for stmt in tree.body[0].body:  # type: ignore[attr-defined]
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        call = stmt.value if isinstance(stmt, ast.Expr) else None
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and len(call.args) == 1
                and not call.keywords):
            raise RouteCollectionError(f"{_ENTRY} 里有无法识别的语句（不支持的写法）：{ast.unparse(stmt)}")
        name = call.func.id
        if name in _ENTRY_EXTRA_CALLS:
            continue
        if not (name.startswith("register_") and name.endswith("_routers")) or name in names:
            raise RouteCollectionError(f"{_ENTRY} 调用了无法识别的函数（不支持的写法）：{name}")
        names.append(name)
    if not names:
        raise RouteCollectionError(f"{_ENTRY} 没有调用任何 register_*_routers")
    return [getattr(registry, name) for name in names]


def _relative(target: Any, root: Path) -> str | None:
    try:
        source = inspect.getsourcefile(target) or inspect.getfile(target)
    except TypeError:
        return None
    try:
        return Path(source).resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _literal(value: Any) -> Any:
    """闭包取值 → JSON 可表示的确定性形式。"""
    import enum

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_literal(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_literal(v) for v in value), key=repr)
    if isinstance(value, enum.Enum):
        return {"枚举": f"{type(value).__qualname__}.{value.name}"}
    kind = "可调用" if callable(value) else "非字面量"
    owner = value if callable(value) and hasattr(value, "__qualname__") else type(value)
    return {kind: f"{getattr(owner, '__module__', '?')}.{getattr(owner, '__qualname__', '?')}"}


def _describe(obj: Any, root: Path, param: str | None = None) -> dict[str, Any]:
    import functools

    kind, target = "function", obj
    if isinstance(obj, functools.partial):
        kind, target = "partial", obj.func
    elif inspect.isclass(obj):
        kind = "class"
    elif inspect.ismethod(obj):
        target = obj.__func__
    elif not inspect.isfunction(obj):
        kind, target = ("instance", type(obj)) if callable(obj) else ("other", type(obj))
    if inspect.isfunction(target):
        target = inspect.unwrap(target)
    qualname = getattr(target, "__qualname__", type(target).__qualname__)
    closure: list[list[Any]] = []
    if inspect.isfunction(target) and "<locals>" in qualname:
        kind = "closure" if kind == "function" else kind
        for var, cell in zip(target.__code__.co_freevars, target.__closure__ or ()):
            try:
                closure.append([var, _literal(cell.cell_contents)])
            except ValueError:  # 尚未赋值的单元
                closure.append([var, {"非字面量": "空单元"}])
    return {"name": qualname.split(".<locals>", 1)[0].rsplit(".", 1)[-1], "qualname": qualname, "kind": kind,
            "module": getattr(target, "__module__", None) or "?", "file": _relative(target, root),
            "closure": sorted(closure), "param": param}


def _route_entries(route: Any, group: str, kwargs: dict[str, Any], router: Any, root: Path) -> list[dict[str, Any]]:
    """一条 APIRoute → 每个方法一条记录；依赖按「注册 → 路由器 → 路由 → 签名参数」拆开。"""
    deps = list(route.dependencies)
    registration = list(kwargs.get("dependencies") or [])
    own = list(getattr(router, "dependencies", None) or [])
    head = registration + own
    if len(deps) < len(head) or any(a is not b for a, b in zip(deps, head)):
        raise RouteCollectionError(f"{group} {route.path}：路由依赖无法按「注册 → 路由器 → 路由」拆分（不支持的写法）")
    subs = list(route.dependant.dependencies)
    if len(subs) < len(deps) or any(s.name is not None or s.call is not d.dependency for s, d in zip(subs, deps)):
        raise RouteCollectionError(f"{group} {route.path}：FastAPI 依赖结构与预期不符（无参依赖应排在最前）")
    endpoint = inspect.unwrap(route.endpoint)
    base = {"path": route.path, "group": group, "registered": True, "file": _relative(endpoint, root),
            "function": endpoint.__qualname__, "module": endpoint.__module__,
            "registration_prefix": kwargs.get("prefix") or "",
            "registration_dependencies": [_describe(d.dependency, root) for d in registration],
            "router_dependencies": [_describe(d.dependency, root) for d in own],
            "route_dependencies": [_describe(d.dependency, root) for d in deps[len(head):]],
            "parameter_dependencies": [_describe(s.call, root, s.name) for s in subs[len(deps):]]}
    return [dict(base, method=method) for method in sorted(route.methods)]


def _child_collect(root: Path, blocked: list[str]) -> dict[str, Any]:
    backend = root / "backend"
    sys.path.insert(0, str(backend))
    import importlib

    registry = importlib.import_module(REGISTRY_MODULE)
    if not sys.modules["app"].__file__:
        raise RouteCollectionError(f"导入的 app 是命名空间包（{backend / 'app'} 下没有 __init__.py），不在 --root 之下")
    app_file = Path(sys.modules["app"].__file__).resolve()
    if not app_file.is_relative_to((backend / "app").resolve()):
        raise RouteCollectionError(f"导入的 app 不在 --root 之下：{app_file}（期望在 {backend / 'app'} 内）")
    from fastapi import FastAPI
    from fastapi.routing import APIRoute

    routes: list[dict[str, Any]] = []
    groups: list[str] = []
    api_counts: dict[str, int] = {}
    other_counts: dict[str, int] = {}
    for register in _register_functions(registry):
        group = register.__module__.rsplit(".", 1)[-1]
        api = FastAPI()
        calls: list[tuple[Any, dict[str, Any], list[Any]]] = []
        original = api.include_router

        def recording(router: Any, *args: Any, _calls: Any = calls, _api: Any = api, _orig: Any = original,
                      **kwargs: Any) -> None:
            if args:
                raise RouteCollectionError("include_router 使用了位置参数（不支持的写法）")
            before = len(_api.router.routes)
            _orig(router, **kwargs)
            _calls.append((router, kwargs, list(_api.router.routes[before:])))

        api.include_router = recording  # type: ignore[method-assign]
        initial = len(api.router.routes)
        register(api)
        added = sum(len(new) for _, _, new in calls)
        if len(api.router.routes) - initial != added:
            raise RouteCollectionError(f"注册分组 {group} 以 include_router 以外的方式添加了路由（不支持的写法）")
        groups.append(group)
        api_counts[group] = other_counts[group] = 0
        for router, kwargs, new in calls:
            for route in new:
                if isinstance(route, APIRoute):
                    api_counts[group] += 1
                    routes.extend(_route_entries(route, group, kwargs, router, root))
                else:
                    other_counts[group] += 1
    return {"schema": SCHEMA, "groups": groups, "routes": routes, "api_route_counts": api_counts,
            "other_route_counts": other_counts, "app_file": app_file.relative_to(root).as_posix(),
            "blocked": blocked}


def _child_main(argv: list[str]) -> int:
    root, out = Path(argv[0]).resolve(), Path(argv[1]).resolve()
    blocked: list[str] = []
    _install_guard(blocked, out)
    payload = _child_collect(root, blocked)
    payload["blocked"] = list(blocked)
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] != ["--child"] or len(sys.argv) != 4:
        sys.exit("用法：routes.py --child <仓库根> <结果文件>（由 collect_route_table 调用）")
    sys.exit(_child_main(sys.argv[2:]))
