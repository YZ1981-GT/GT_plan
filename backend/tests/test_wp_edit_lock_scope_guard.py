"""底稿写接口的编辑锁范围守卫（spec workpaper-multi-window-lock-gaps R3.6）。

``dedicated_wp_gate`` 对路径带 ``{wp_id}`` 的写路由默认校验编辑锁，豁免集中在 ``_wp_edit_lock_scope``。本文件枚举
应用的全部 ``{wp_id}`` 写路由，钉住豁免名单不会悄悄放过写底稿的接口：

1. 每条豁免规则都命中路由（没有失效条目）；
2. 「不写底稿」类：处理函数与同模块被调函数里没有写库证据（``NON_CONTENT_WRITES`` 登记的除外，登记也都还命中）；
3. 计算后可选写回：处理函数（经同模块被调函数）调了 ``_maybe_apply_*``，模块里每个 ``_maybe_apply_*`` 都调写回点校验；
4. 不经门的 ``{wp_id}`` 写路由全部登记；登记为校验的处理函数里真有校验调用，登记为不校验的没有；
5. 底稿 id 在请求体里的三条编辑器内写入显式校验。

只看同模块被调函数：跨模块的写入（服务层）看不到，所以「不写底稿」类靠命名约定 + 本静态检查兜住处理函数里直接写库的情形。
"""
from __future__ import annotations

import ast
import inspect
import re
import sys
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

import app.routers._wp_gate as wp_gate
from app.routers._wp_edit_lock_scope import (
    BODY_CARRIED_CHECKED,
    NON_CONTENT_WRITES,
    SCOPE_RULES,
    UNGATED_WRITE_DECISIONS,
    EditLockScope,
    edit_lock_scope,
)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LOCK_CALLS = {"enforce_edit_lock_for_content_write", "raise_if_edit_locked", "_enforce_entry_edit_lock"}
_SESSION_WRITES = {"commit", "flush", "add", "add_all", "merge", "delete"}
_SESSION_NAMES = {"db", "session", "sess", "s"}
_FILE_WRITES = {
    "commit_bytes", "write_bytes", "save_structure_to_excel", "push_html_to_excel", "write_cells_to_xlsx",
    "write_cell_to_parsed_data", "write_projection_to_parsed_data", "touch_after_parsed_data_commit",
    "merge_snapshot_incremental", "fill_plan_docx", "fill_summary_docx", "flag_modified",
}
_SQL_WRITE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.I)


@lru_cache(maxsize=1)
def _routes() -> tuple[tuple[str, APIRoute], ...]:
    from app.main import app

    out = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods & WRITE_METHODS):
                out.append((method, route))
    return tuple(out)


def _wp_routes() -> list[tuple[str, APIRoute]]:
    return [(m, r) for m, r in _routes() if "{wp_id}" in r.path]


def _gated(dep) -> bool:
    return getattr(dep, "call", None) is wp_gate.dedicated_wp_gate or any(
        _gated(d) for d in getattr(dep, "dependencies", []) or []
    )


# ── 静态分析：处理函数 + 同模块被调函数 ─────────────────────────────────────────


@lru_cache(maxsize=None)
def _module_tree(path: str) -> tuple[ast.Module, dict[str, list[ast.AST]]]:
    tree = ast.parse(Path(path).read_bytes().decode("utf-8-sig"))  # 个别路由文件带 BOM
    defs: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.setdefault(node.name, []).append(node)
    return tree, defs


def _handler_node(fn) -> tuple[str, ast.AST]:
    fn = inspect.unwrap(fn)
    path = inspect.getsourcefile(fn)
    assert path, f"{fn} 取不到源文件"
    _tree, defs = _module_tree(path)
    candidates = defs.get(fn.__name__, [])
    first = fn.__code__.co_firstlineno
    for node in candidates:
        lines = {node.lineno, *(d.lineno for d in node.decorator_list)}
        if first in lines:
            return path, node
    assert len(candidates) == 1, f"{path} 里 {fn.__name__} 定位不唯一"
    return path, candidates[0]


def _receiver_name(node: ast.AST) -> str:
    while isinstance(node, ast.Attribute):
        if node.attr in _SESSION_NAMES:
            return node.attr
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def _direct_facts(node: ast.AST) -> tuple[set[str], set[str]]:
    """(写库证据, 调用到的裸名函数)。"""
    evidence: set[str] = set()
    calls: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Attribute):
                if func.attr in _SESSION_WRITES and _receiver_name(func.value) in _SESSION_NAMES:
                    evidence.add(f"session.{func.attr}")
                if func.attr in _FILE_WRITES:
                    evidence.add(func.attr)
            elif isinstance(func, ast.Name):
                if func.id in _FILE_WRITES:
                    evidence.add(func.id)
                calls.add(func.id)
        elif isinstance(sub, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
            if any(isinstance(t, ast.Attribute) and t.attr == "parsed_data" for t in targets):
                evidence.add("parsed_data=")
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _SQL_WRITE.search(sub.value):
            evidence.add("sql-write")
    return evidence, calls


def _reach(path: str, root: ast.AST) -> tuple[set[str], set[str]]:
    """从处理函数出发沿同模块裸名调用走一遍：(写库证据, 走到的函数名)。"""
    _tree, defs = _module_tree(path)
    evidence: set[str] = set()
    seen: set[int] = set()
    names: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        names.add(getattr(node, "name", ""))
        ev, calls = _direct_facts(node)
        evidence |= ev
        for name in calls:
            stack.extend(defs.get(name, []))
    return evidence, names


def _calls_any(path: str, root: ast.AST, wanted: set[str]) -> bool:
    """处理函数（含同模块被调函数）里有没有调用 wanted 里的名字（裸名或属性名都算）。"""
    _tree, defs = _module_tree(path)
    seen: set[int] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in wanted:
                    return True
                if isinstance(func, ast.Name):
                    stack.extend(defs.get(func.id, []))
    return False


# ── 1. 豁免规则都命中 ───────────────────────────────────────────────────────────


def test_scan_surface_is_sane():
    routes = _wp_routes()
    gated = [(m, r) for m, r in routes if _gated(r.dependant)]
    check = [(m, r) for m, r in gated if edit_lock_scope(r.path) is EditLockScope.CHECK]
    assert len(routes) >= 500 and len(gated) >= 500, f"扫描面异常：写路由 {len(routes)}，挂门 {len(gated)}"
    assert len(check) >= 200, f"校验类只剩 {len(check)} 条，豁免规则是不是写宽了"
    assert any(r.path.endswith("/checklist-responses") for _m, r in check)
    assert any(r.path.endswith("/save-adjudication") for _m, r in check)


def test_every_exempt_rule_matches_a_gated_route():
    paths = [r.path for _m, r in _wp_routes() if _gated(r.dependant)]
    stale = [rule.pattern.pattern for rule in SCOPE_RULES if not any(rule.pattern.search(p) for p in paths)]
    assert stale == [], f"这些豁免规则一条路由都不命中（失效条目，删掉）：{stale}"


# ── 2. 「不写底稿」类没有写库证据 ───────────────────────────────────────────────


def test_no_write_handlers_show_no_write_evidence():
    offenders = []
    allowed_hits: set[str] = set()
    for method, route in _wp_routes():
        if not _gated(route.dependant) or edit_lock_scope(route.path) is not EditLockScope.NO_WRITE:
            continue
        path, node = _handler_node(route.endpoint)
        evidence, _names = _reach(path, node)
        if not evidence:
            continue
        if route.path in NON_CONTENT_WRITES:
            allowed_hits.add(route.path)
            continue
        offenders.append(f"{method} {route.path} [{route.endpoint.__module__}.{route.endpoint.__name__}] {sorted(evidence)}")
    assert offenders == [], (
        "归为「不写底稿」却在处理函数里写库（改成校验类，或确认写的不是底稿内容后登记 NON_CONTENT_WRITES）：\n"
        + "\n".join(offenders)
    )
    stale = sorted(set(NON_CONTENT_WRITES) - allowed_hits)
    assert stale == [], f"NON_CONTENT_WRITES 里这些登记已不再命中（删掉）：{stale}"


# ── 3. 计算后可选写回都在写回点校验 ─────────────────────────────────────────────


def test_on_apply_routes_check_at_the_write_point():
    routes = [(m, r) for m, r in _wp_routes() if edit_lock_scope(r.path) is EditLockScope.ON_APPLY]
    assert len(routes) >= 15, f"计算写回路由只剩 {len(routes)} 条"
    problems = []
    for method, route in routes:
        if not _gated(route.dependant):
            problems.append(f"{method} {route.path} 没挂底稿门（写回点拿不到请求人）")
            continue
        path, node = _handler_node(route.endpoint)
        _evidence, names = _reach(path, node)
        appliers = sorted(n for n in names if n.startswith("_maybe_apply"))
        if not appliers:
            problems.append(f"{method} {route.path} 处理函数没调 _maybe_apply_*（写回走了别的路）")
            continue
        _tree, defs = _module_tree(path)
        for name in appliers:
            for fn in defs[name]:
                if not _calls_any(path, fn, {"enforce_edit_lock_at_write_point"}):
                    problems.append(f"{Path(path).name}:{fn.lineno} {name} 写回前没调 enforce_edit_lock_at_write_point")
    assert problems == [], "\n".join(problems)


def test_every_maybe_apply_function_checks_the_lock():
    """路由之外也兜一层：routers 下所有 `_maybe_apply_*`（含尚未挂路由的）都在写回前校验。"""
    root = Path(wp_gate.__file__).resolve().parent
    missing = []
    for path in sorted(root.rglob("*.py")):
        tree, defs = _module_tree(str(path))
        for name, nodes in defs.items():
            if name.startswith("_maybe_apply"):
                missing += [f"{path.name}:{n.lineno} {name}" for n in nodes
                            if not _calls_any(str(path), n, {"enforce_edit_lock_at_write_point"})]
    assert missing == [], f"这些计算写回函数没调写回点校验：{missing}"


# ── 4. 不经门的写路由都登记 ─────────────────────────────────────────────────────


def test_ungated_wp_write_routes_are_all_registered():
    seen: set[tuple[str, str]] = set()
    problems = []
    for method, route in _wp_routes():
        if _gated(route.dependant):
            continue
        key = (method, route.path)
        seen.add(key)
        decision = UNGATED_WRITE_DECISIONS.get(key)
        if decision is None:
            problems.append(f"未登记：{method} {route.path} [{route.endpoint.__module__}.{route.endpoint.__name__}]")
            continue
        path, node = _handler_node(route.endpoint)
        calls = _calls_any(path, node, LOCK_CALLS)
        if decision[0] and not calls:
            problems.append(f"登记为校验但处理函数里没有校验调用：{method} {route.path}")
        if not decision[0] and calls:
            problems.append(f"登记为不校验但处理函数里有校验调用（登记过期）：{method} {route.path}")
    stale = sorted(set(UNGATED_WRITE_DECISIONS) - seen)
    assert problems == [] and stale == [], "\n".join(problems + [f"失效登记：{k}" for k in stale])


def test_body_carried_editor_writes_check_the_lock():
    by_key = {(m, r.path): r for m, r in _routes()}
    problems = []
    for method, path_tpl, _reason in BODY_CARRIED_CHECKED:
        route = by_key.get((method, path_tpl))
        if route is None:
            problems.append(f"路由不存在：{method} {path_tpl}")
            continue
        path, node = _handler_node(route.endpoint)
        if not _calls_any(path, node, LOCK_CALLS):
            problems.append(f"没有校验调用：{method} {path_tpl}")
    assert problems == [], "\n".join(problems)


# ── 静态检查本身的阳性 / 阴性对照 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("async def f(db):\n    await db.commit()\n", {"session.commit"}),
        ("async def f(self):\n    self.db.add(x)\n", {"session.add"}),
        ("def f(wp):\n    wp.parsed_data = {}\n", {"parsed_data="}),
        ("def f():\n    q = 'UPDATE working_paper SET a = 1'\n", {"sql-write"}),
        ("def f(p):\n    p.write_bytes(b'')\n", {"write_bytes"}),
        ("def f(seen):\n    seen.add(1)\n    wb.save(buf)\n", set()),
        ("def f():\n    q = 'SELECT 1 FROM working_paper'\n", set()),
    ],
)
def test_write_evidence_detector(src, expected):
    evidence, _calls = _direct_facts(ast.parse(src))
    assert evidence == expected


def test_reach_follows_same_module_calls(tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text(
        "async def handler(db):\n    return await _helper(db)\n\nasync def _helper(db):\n    await db.flush()\n",
        encoding="utf-8",
    )
    _tree, defs = _module_tree(str(mod))
    evidence, names = _reach(str(mod), defs["handler"][0])
    assert evidence == {"session.flush"} and {"handler", "_helper"} <= names


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
