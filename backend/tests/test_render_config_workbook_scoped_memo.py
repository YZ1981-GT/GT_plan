"""D 循环渲染器同请求 memo 的守卫（spec platform-perf-hotspots R2）。

memo 成立的前提：d1~d7 渲染器（以及它们把 ctx 传进去的取数函数）只读与页签无关的
ctx 字段；页签相关的只有 d1 / d2 写进 html_data 的 ``"sheet_name"`` 键，由
``_memo_hit_html_data`` 换成本页名字。以后谁在这些模块里读了 ``ctx.sheet_html_data`` /
``ctx.sheet_schema`` / ``ctx.classification.class_code`` 之类，或者把 ctx 传给了没被扫描的
函数，本守卫打红，逼着重新判断 memo 是否还成立。
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from pathlib import Path

import pytest

from app.routers import wp_render_config as rc
from app.routers.wp_render_strategies import RENDERER_DISPATCH

BACKEND = Path(__file__).resolve().parents[1]
_SHARED_PACKAGES = (
    BACKEND / "app" / "services" / "d_cycle_extraction",
    BACKEND / "app" / "services" / "d4_extraction",
)
#: 包外但收 ctx 的取数模块（resolve_report_line_accounts / to_original_codes_with_flag）
_SHARED_FILES = (
    BACKEND / "app" / "services" / "four_table" / "report_line_accounts.py",
)
#: 同一请求里所有页签都相同的 ctx 字段。
_SHEET_INVARIANT_CTX_ATTRS = frozenset({
    "db", "wp_id", "project_id", "year", "business_category", "wp_code",
    "working_paper", "user_id", "audit_cycle", "component_type",
})
#: 收 ctx 但不读页签字段的内置 / 标准库调用（getattr 与 dataclasses.replace 另有专门判定）
_CTX_SAFE_CALLEES = frozenset({"getattr", "hasattr", "replace"})


def test_workbook_scoped_set_is_exactly_the_registered_d_renderers() -> None:
    d_types = {ct for ct in RENDERER_DISPATCH if re.fullmatch(r"d[1-7]-[a-z-]+", ct)}
    assert rc._WORKBOOK_SCOPED_RENDERERS == d_types
    # 整册专属集合有自己的 memo 语义（同一对象），两者不得重叠
    assert not (rc._WORKBOOK_SCOPED_RENDERERS & rc._WHOLE_WP_MULTISHEET_DEDICATED)


def _scanned_files() -> list[Path]:
    files: set[Path] = set()
    for component_type in rc._WORKBOOK_SCOPED_RENDERERS:
        module = importlib.import_module(RENDERER_DISPATCH[component_type].__module__)
        files.add(Path(inspect.getsourcefile(module)))
    for package in _SHARED_PACKAGES:
        files.update(package.rglob("*.py"))
    files.update(_SHARED_FILES)
    return sorted(files)


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parent_of: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_of[child] = node
    return parent_of


def _is_ctx(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "ctx"


def _is_sheet_name_dict_value(node: ast.AST, parent_of: dict[ast.AST, ast.AST]) -> bool:
    """``{"sheet_name": ctx.classification.sheet_name if ctx.classification else ""}`` 形态。"""
    cur = node
    while isinstance(parent_of.get(cur), ast.IfExp) and parent_of[cur].body is cur:
        cur = parent_of[cur]
    holder = parent_of.get(cur)
    if not isinstance(holder, ast.Dict):
        return False
    for key, value in zip(holder.keys, holder.values):
        if value is cur:
            return isinstance(key, ast.Constant) and key.value == "sheet_name"
    return False


def _sheet_dependent_ctx_reads(tree: ast.AST) -> list[tuple[int, str]]:
    parent_of = _parents(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in {"getattr", "hasattr"} and node.args and _is_ctx(node.args[0]):
            attr = node.args[1] if len(node.args) > 1 else None
            if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                if attr.value not in _SHEET_INVARIANT_CTX_ATTRS:
                    found.append((node.lineno, f"{node.func.id}(ctx, {attr.value!r})"))
            else:
                found.append((node.lineno, f"{node.func.id}(ctx, <动态>)"))
            continue
        if not (isinstance(node, ast.Attribute) and _is_ctx(node.value)):
            continue
        if node.attr in _SHEET_INVARIANT_CTX_ATTRS:
            continue
        parent = parent_of.get(node)
        if node.attr == "classification":
            # 只许两种：作真值判断（`x if ctx.classification else ""`），
            # 或把 .sheet_name 原样放进 html_data 的 "sheet_name" 键（memo 命中时换成本页名字）
            if isinstance(parent, (ast.IfExp, ast.If, ast.While)) and parent.test is node:
                continue
            if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.Not):
                continue
            if isinstance(parent, ast.Attribute) and parent.attr == "sheet_name":
                if _is_sheet_name_dict_value(parent, parent_of):
                    continue
                found.append((node.lineno, "ctx.classification.sheet_name"))
                continue
        found.append((node.lineno, f"ctx.{node.attr}"))
    return sorted(found)


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    return {
        a.asname: a.name
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for a in node.names if a.asname
    }


def _ctx_escapes(tree: ast.AST) -> list[tuple[int, str, ast.Call]]:
    """把 ctx 整个传出去的调用：(行号, 被调函数真名, 调用节点)。"""
    alias = _import_aliases(tree)
    out: list[tuple[int, str, ast.Call]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not any(_is_ctx(a) for a in [*node.args, *(k.value for k in node.keywords)]):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            name = ast.unparse(func)
        out.append((node.lineno, alias.get(name, name), node))
    return sorted(out, key=lambda item: (item[0], item[1]))


@pytest.mark.parametrize("path", _scanned_files(), ids=lambda p: p.name)
def test_d_renderers_only_read_sheet_invariant_ctx_fields(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = _sheet_dependent_ctx_reads(tree)
    assert offenders == [], (
        f"{path.name} 读了与页签有关的 ctx 字段 {offenders}：D 循环渲染器同请求只跑一次"
        "（_WORKBOOK_SCOPED_RENDERERS）的前提不再成立，先移出该集合或改成页签无关"
    )


def test_ctx_only_flows_into_scanned_functions() -> None:
    """ctx 传进去的每个函数都必须在扫描范围内、且形参就叫 ctx（上面的逐文件扫描才看得见）。"""
    trees = {p: ast.parse(p.read_text(encoding="utf-8")) for p in _scanned_files()}
    params_by_name: dict[str, list[set[str]]] = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = {a.arg for a in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]}
                params_by_name.setdefault(node.name, []).append(names)
    problems: list[str] = []
    for path, tree in trees.items():
        for lineno, callee, call in _ctx_escapes(tree):
            if callee in _CTX_SAFE_CALLEES:
                if callee == "replace":
                    bad = [k.arg for k in call.keywords if k.arg not in _SHEET_INVARIANT_CTX_ATTRS]
                    if bad:
                        problems.append(f"{path.name}:{lineno} replace(ctx, {bad}) 改了页签相关字段")
                continue
            defs = params_by_name.get(callee)
            if not defs:
                problems.append(f"{path.name}:{lineno} ctx 传给了扫描范围外的 {callee}()")
            elif not all("ctx" in names for names in defs):
                problems.append(f"{path.name}:{lineno} {callee}() 的形参不叫 ctx，逐文件扫描看不见")
    assert problems == [], "\n".join(problems)


def test_scanner_flags_sheet_dependent_reads() -> None:
    """守卫自身的变异：页签相关读取必须被认出来，否则上面的用例恒绿。"""
    src = (
        "def render(ctx):\n"
        "    a = ctx.sheet_html_data\n"
        "    b = ctx.classification.class_code\n"
        "    c = {'sheet_name': ctx.classification.sheet_name if ctx.classification else ''}\n"
        "    d = ctx.project_id\n"
        "    if '明细' in ctx.classification.sheet_name:\n"
        "        pass\n"
        "    e = getattr(ctx, 'sheet_schema', None)\n"
        "    f = getattr(ctx, 'year', None)\n"
        "    g = getattr(ctx, name)\n"
        "    h = {'title': ctx.classification.sheet_name}\n"
    )
    assert _sheet_dependent_ctx_reads(ast.parse(src)) == [
        (2, "ctx.sheet_html_data"),
        (3, "ctx.classification"),
        (6, "ctx.classification.sheet_name"),
        (8, "getattr(ctx, 'sheet_schema')"),
        (10, "getattr(ctx, <动态>)"),
        (11, "ctx.classification.sheet_name"),
    ]


def test_escape_scanner_resolves_aliases_and_flags_unknown_callees() -> None:
    src = (
        "from x.y import fetch as _fetch\n"
        "from dataclasses import replace as _dc_replace\n"
        "async def render(ctx):\n"
        "    await _fetch(ctx, codes)\n"
        "    helper.run(ctx=ctx)\n"
        "    _dc_replace(ctx, year=1)\n"
        "    other(1, 2)\n"
    )
    got = [(ln, name) for ln, name, _ in _ctx_escapes(ast.parse(src))]
    assert got == [(4, "fetch"), (5, "run"), (6, "replace")]


def test_memo_hit_replaces_sheet_name_for_workbook_scoped_renderers() -> None:
    memo = {"sheet_name": "审定表D2-1", "project_context": {"a": 1}, "responses_snapshot": {"x": {}}}
    got = rc._memo_hit_html_data(memo, "d2-accounts-receivable", "明细表D2-2")
    assert got == {**memo, "sheet_name": "明细表D2-2"}
    assert got is not memo
    assert memo["sheet_name"] == "审定表D2-1"  # 不改第一页的结果
    # 大块载荷按引用复用（不复制）
    assert got["project_context"] is memo["project_context"]
    assert got["responses_snapshot"] is memo["responses_snapshot"]


def test_memo_hit_without_sheet_name_or_for_whole_dedicated_returns_memo_itself() -> None:
    memo_no_name = {"project_context": {}, "rows": []}
    assert rc._memo_hit_html_data(memo_no_name, "d3-prepaid-accounts", "X") is memo_no_name
    whole = {"sheet_name": "第一页", "data": {}}
    # 整册专属组件沿用原行为：同一对象（含第一页的 sheet_name）
    whole_type = sorted(rc._WHOLE_WP_MULTISHEET_DEDICATED)[0]
    assert rc._memo_hit_html_data(whole, whole_type, "第二页") is whole
