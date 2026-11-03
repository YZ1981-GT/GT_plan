"""跨 sheet 追溯的身份路径守卫（acnr-foundation-defect-closure T20，需求 8.2，design §9.2；纯 AST，不跑代码）。

- ``backend/app`` 里每个 ``CrossSheetResolver(...)`` 构造都显式传 ``resolve_identity=False``（含模块单例），即
  生产使用方要么由编排器经 exact_identity 拿身份、要么声明只取值；
- 同步桥接 ``_sync_resolve`` 只在 ``cross_sheet_resolver.py`` 里被引用，且只在 ``_bridge_identity`` 内；
  ``_bridge_identity`` 的调用都在 ``if self._resolve_identity`` 的 body 里（条件恰为该属性，取反 / 组合 / else 分支都红）
  ⇒ 生产路径上同步桥接（运行中的事件循环里恒降级为 None）不可达。tasks.md 原文写「生产不引用 _sync_resolve」，
  实现保留该函数，按需求 8.2「若保留须由守卫证明不可达」以本守卫证明（RV7.7-01）；
- 反向自检：扫描确实找到了已知的两处生产构造，避免扫描范围失效时判据空转。
"""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
RESOLVER = APP / "services" / "custom_query" / "cross_sheet_resolver.py"
#: 已知的生产构造（文件相对 app 的路径）；新增构造不必登记，但这两处必须被扫到
KNOWN_CONSTRUCTIONS = {"services/custom_query/cross_sheet_resolver.py", "services/wp_formula_eval_service.py"}


def _trees():
    for path in sorted(APP.rglob("*.py")):
        yield path, ast.parse(path.read_bytes().decode("utf-8-sig"), filename=str(path))


def _is_ctor(call: ast.Call) -> bool:
    func = call.func
    return (isinstance(func, ast.Name) and func.id == "CrossSheetResolver") or (
        isinstance(func, ast.Attribute) and func.attr == "CrossSheetResolver")


def _constructions() -> list[tuple[str, int, ast.Call]]:
    found = []
    for path, tree in _trees():
        rel = path.relative_to(APP).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_ctor(node):
                found.append((rel, node.lineno, node))
    return found


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _refs(tree: ast.AST, name: str) -> list[ast.AST]:
    out: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            out.append(node)
        elif isinstance(node, ast.Attribute) and node.attr == name:
            out.append(node)
        elif isinstance(node, ast.alias) and name in (node.name, node.asname):
            out.append(node)
    return out


def test_every_production_construction_passes_resolve_identity_false():
    found = _constructions()
    assert KNOWN_CONSTRUCTIONS <= {rel for rel, _, _ in found}, f"扫描没有找到已知构造：{found}"
    bad = []
    for rel, line, call in found:
        kw = {k.arg: k.value for k in call.keywords if k.arg}
        value = kw.get("resolve_identity")
        if not (isinstance(value, ast.Constant) and value.value is False):
            bad.append(f"{rel}:{line}")
    assert not bad, f"这些 CrossSheetResolver 构造没有显式传 resolve_identity=False：{bad}"


def test_sync_bridge_only_referenced_inside_guarded_helper():
    outside = []
    for path, tree in _trees():
        if path == RESOLVER:
            continue
        if _refs(tree, "_sync_resolve") or _refs(tree, "_bridge_identity"):
            outside.append(path.relative_to(APP).as_posix())
    assert not outside, f"生产代码在 cross_sheet_resolver.py 之外引用了同步桥接：{outside}"

    tree = ast.parse(RESOLVER.read_bytes().decode("utf-8-sig"))
    parents = _parents(tree)

    def enclosing(node, kinds):
        cur = parents.get(node)
        while cur is not None and not isinstance(cur, kinds):
            cur = parents.get(cur)
        return cur

    uses = [n for n in _refs(tree, "_sync_resolve") if isinstance(n, ast.Name)]
    assert uses, "反向自检：没有找到 _sync_resolve 的调用"
    for use in uses:
        fn = enclosing(use, (ast.FunctionDef, ast.AsyncFunctionDef))
        assert fn is not None and fn.name == "_bridge_identity", f"_sync_resolve 在第 {use.lineno} 行被 _bridge_identity 之外引用"

    calls = [n for n in _refs(tree, "_bridge_identity") if isinstance(n, ast.Attribute)]
    assert calls, "反向自检：没有找到 _bridge_identity 的调用"
    for call in calls:
        guard = enclosing(call, (ast.If,))
        assert guard is not None, f"第 {call.lineno} 行调用 _bridge_identity 不在任何 if 分支里"
        test = guard.test
        # 条件必须恰为 self._resolve_identity（取反、与其他条件组合都不算），调用必须在 body 而非 orelse
        assert (isinstance(test, ast.Attribute) and test.attr == "_resolve_identity"
                and isinstance(test.value, ast.Name) and test.value.id == "self"), (
            f"第 {call.lineno} 行调用 _bridge_identity 的 if 条件不是 self._resolve_identity：{ast.unparse(test)}")
        branch = call
        while parents.get(branch) is not guard:
            branch = parents[branch]
        assert branch in guard.body, f"第 {call.lineno} 行调用 _bridge_identity 在 if self._resolve_identity 的 else 分支里"
