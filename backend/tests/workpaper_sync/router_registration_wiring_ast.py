"""`wp_sync_router` 注册接线的 AST 判据（多个 pilot / registrar 守卫共用，避免各写一份漂移）。

现行形态（spec writeback-followup-issue-closure P4 起）：

* 两个生产接线点 —— HTML→OO 的 `_registration` 与 callback 之后的 `_apply_durable_incoming` ——
  都 await **同一个**注册入口 `_attach_pilot_adapters`（callback 一侧原先自带一份不加锁、
  不写缓存、不隔离 pilot 的冷建）；
* `_attach_pilot_adapters` 把各 pilot 的 attach 作为关键字实参交给逐条隔离的
  `_isolated_pilot_attach`（2026-10-04 隔离修复），并 await `register_from_manifest`；
* `_isolated_pilot_attach` 逐个 await 交进来的 attach。

判据只认 AST 节点（调用 / await / 关键字实参），docstring 与注释不进 AST。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROUTER_PY = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_sync_router.py"

#: 两个生产接线点。
PRODUCTION_ENTRIES: tuple[str, ...] = ("_registration", "_apply_durable_incoming")


def router_functions(path: Path = ROUTER_PY) -> dict[str, ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _callee_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def awaited_names(fn: ast.AST) -> set[str]:
    """函数体内被 `await` 的调用名（`await f(...)` / `await x.f(...)`）。"""
    return {
        name
        for node in ast.walk(fn)
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
        for name in [_callee_name(node.value)]
        if name
    }


def attaches_handed_to_isolation(fn: ast.AST) -> set[str]:
    """`_isolated_pilot_attach(...)` 调用里作为关键字实参交出去的名字。"""
    return {
        kw.value.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and _callee_name(node) == "_isolated_pilot_attach"
        for kw in node.keywords
        if isinstance(kw.value, ast.Name)
    }


def assert_pilot_attach_wired(attach_name: str) -> None:
    """`attach_name` 经共享入口接到两个生产接线点上（任一环断开即抛）。"""
    fns = router_functions()
    shared = fns["_attach_pilot_adapters"]
    handed = attaches_handed_to_isolation(shared)
    assert attach_name in handed, (
        f"`_attach_pilot_adapters` 没把 {attach_name} 交给 `_isolated_pilot_attach`：{sorted(handed)}"
    )
    assert "fn" in awaited_names(fns["_isolated_pilot_attach"]), (
        "`_isolated_pilot_attach` 只收参数、不 await 交进来的 attach"
    )
    for entry in PRODUCTION_ENTRIES:
        assert "_attach_pilot_adapters" in awaited_names(fns[entry]), (
            f"{entry} 没 await 共享注册入口 `_attach_pilot_adapters` —— 半接线"
        )
