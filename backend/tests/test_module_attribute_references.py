"""守卫：读导入模块上不存在的属性 / 在类上直接调实例方法却没传实例。

这两类断引用只在运行到那一行时才炸（AttributeError / TypeError），导入期检查和函数体内 import 守卫
（``test_lazy_import_resolvability.py``）都看不到。实例（2026-10-21 起，到 10-29 才发现）：

- ``routers/ai_content.py`` 读 ``ai_content_log_service.get_by_id``，该函数不存在 ⇒ 确认 / 修订 / 拒绝
  AI 内容每次 500；
- 同一处写回调 ``DisclosureEngine.update_note(db=db, ...)``：实例方法当静态方法调 ⇒ TypeError。

判据（AST，不按文本匹配）：

1. 名字绑定到 app 模块（``from app.services import x`` / ``import app.services.x as x``，含函数体内导入），
   读 ``x.attr`` 时模块上必须有 ``attr``，或 ``attr`` 是它的子模块；模块自定义 ``__getattr__`` 的跳过。
2. ``X.m(...)`` 里 ``X`` 是从 app 导入的类、``m`` 是普通实例方法（首参 ``self``）、调用**没有位置参数**
   ⇒ 实例没有传进去。

两条判据各有自检用例：喂一段已知有问题的源码必须报出来，防扫描口径失效后恒绿。
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import types
from functools import lru_cache
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"


@lru_cache(maxsize=None)
def _load(name: str) -> types.ModuleType | None:
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001 — 导入失败归导入期 / lazy import 守卫，这里只看能导入的模块
        return None


@lru_cache(maxsize=None)
def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _package_of(rel: str) -> str:
    return ".".join(Path(rel).with_suffix("").parts[:-1])


def _resolve_from(node: ast.ImportFrom, pkg: str) -> str | None:
    """``from X import ...`` 的绝对模块名（相对导入按所在包展开）。"""
    if not node.level:
        return node.module
    parts = pkg.split(".")
    if node.level > len(parts):
        return None
    return ".".join(parts[: len(parts) - node.level + 1] + ([node.module] if node.module else []))


def _is_app(name: str | None) -> bool:
    return bool(name) and (name == "app" or name.startswith("app."))


def find_missing_module_attrs(source: str, rel: str) -> list[str]:
    """判据 1：``x.attr`` 读法里 x 绑定的 app 模块上没有 attr。"""
    tree = ast.parse(source)
    pkg = _package_of(rel)
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_app(alias.name) and alias.asname:
                    bound[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(node, pkg)
            if not _is_app(base):
                continue
            for alias in node.names:
                if _is_module(f"{base}.{alias.name}"):
                    bound[alias.asname or alias.name] = f"{base}.{alias.name}"
    out: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name) and node.value.id in bound):
            continue
        modname = bound[node.value.id]
        mod = _load(modname)
        if mod is None or hasattr(mod, "__getattr__") or hasattr(mod, node.attr):
            continue
        if _is_module(f"{modname}.{node.attr}"):
            continue
        out.append(f"{rel}:{node.lineno}  {modname}.{node.attr}")
    return out


def find_unbound_instance_method_calls(source: str, rel: str) -> list[str]:
    """判据 2：在从 app 导入的类上直接调实例方法、且没有位置参数（实例只能经第一个位置参数传入）。"""
    tree = ast.parse(source)
    pkg = _package_of(rel)
    names: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = _resolve_from(node, pkg)
            if _is_app(base):
                for alias in node.names:
                    names[alias.asname or alias.name] = (base, alias.name)
    out: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id in names):
            continue
        if node.args or any(k.arg is None for k in node.keywords):  # 有位置参数 / **kwargs 可能带实例
            continue
        base, attr = names[node.func.value.id]
        mod = _load(base)
        cls = getattr(mod, attr, None) if mod is not None else None
        if not inspect.isclass(cls):
            continue
        raw = inspect.getattr_static(cls, node.func.attr, None)
        if not inspect.isfunction(raw):  # staticmethod / classmethod / property / 不存在 都跳过
            continue
        params = list(inspect.signature(raw).parameters)
        if params and params[0] == "self" and "self" not in {k.arg for k in node.keywords}:
            out.append(f"{rel}:{node.lineno}  {attr}.{node.func.attr}(…) 没传实例")
    return out


def _app_sources() -> list[tuple[str, str]]:
    # utf-8-sig：有几个模块文件带 BOM（Python 认，ast.parse 收到带 BOM 的字符串会报 SyntaxError）
    return [
        (py.relative_to(BACKEND).as_posix(), py.read_text(encoding="utf-8-sig"))
        for py in sorted(APP.rglob("*.py"))
    ]


def test_no_missing_module_attribute() -> None:
    hits = [hit for rel, src in _app_sources() for hit in find_missing_module_attrs(src, rel)]
    assert not hits, "读了导入模块上不存在的属性（运行到这一行即 AttributeError）：\n  " + "\n  ".join(hits)


def test_no_unbound_instance_method_call() -> None:
    hits = [hit for rel, src in _app_sources() for hit in find_unbound_instance_method_calls(src, rel)]
    assert not hits, "在类上直接调实例方法却没传实例（运行到这一行即 TypeError）：\n  " + "\n  ".join(hits)


def test_scan_covers_app_tree() -> None:
    """防空转：扫描范围确实是 app 下的全部模块，且包含这次出过问题的两个文件。"""
    rels = {rel for rel, _ in _app_sources()}
    assert len(rels) > 500
    assert {"app/routers/ai_content.py", "app/services/ai_content_log_service.py"} <= rels


def test_self_check_missing_attribute_is_reported() -> None:
    src = (
        "from app.services import ai_content_log_service\n"
        "\n"
        "async def f(db, log_id):\n"
        "    return await ai_content_log_service.no_such_function(db=db, log_id=log_id)\n"
    )
    assert find_missing_module_attrs(src, "app/routers/_probe.py") == [
        "app/routers/_probe.py:4  app.services.ai_content_log_service.no_such_function"
    ]


def test_self_check_existing_attribute_and_submodule_pass() -> None:
    src = (
        "from app.services import ai_content_log_service\n"
        "from app import services\n"
        "a = ai_content_log_service.get_by_id\n"
        "b = services.ai_content_log_service\n"
    )
    assert find_missing_module_attrs(src, "app/routers/_probe.py") == []


def test_self_check_unbound_call_is_reported_and_bound_call_passes() -> None:
    src = (
        "from app.services.disclosure_engine import DisclosureEngine\n"
        "\n"
        "async def f(db, note_id):\n"
        "    await DisclosureEngine.update_note(db=db, note_id=note_id)\n"
        "    await DisclosureEngine(db).update_note(note_id)\n"
    )
    assert find_unbound_instance_method_calls(src, "app/routers/_probe.py") == [
        "app/routers/_probe.py:4  DisclosureEngine.update_note(…) 没传实例"
    ]
