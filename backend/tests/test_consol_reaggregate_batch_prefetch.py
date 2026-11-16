"""C2：合并附注重汇总按章节批取叶子来源的接线守卫。"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "app" / "services" / "consol_note_subtree_reaggregate.py"
PREFETCH = ROOT / "app" / "services" / "consol_note_reaggregate_prefetch.py"
APPLY = ROOT / "app" / "services" / "consol_note_detail_apply_service.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _method(tree: ast.AST, name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"找不到 async 方法 {name}")


def _called_names(node: ast.AST) -> list[str]:
    return [
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    ]


def test_section_prefetch_exists_and_calls_load_source_tables_once_per_section():
    tree = _tree(PREFETCH)
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "prefetch_section_sources")
    calls = _called_names(method)
    assert "load_source_tables" in calls, (
        "章节预取方法没有调用 load_source_tables，来源仍可能按叶子重复读取"
    )
    assert calls.count("load_source_tables") == 1


def test_process_section_prefetches_before_node_loop():
    tree = _tree(RUNNER)
    method = _method(tree, "process_section")
    calls = [
        (child.lineno, child.func.attr if isinstance(child.func, ast.Attribute) else child.func.id)
        for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and (isinstance(child.func, ast.Name) or isinstance(child.func, ast.Attribute))
    ]
    prefetch = [line for line, name in calls if name == "prefetch_section_sources"]
    assert prefetch, "process_section 没有调用章节预取"
    loops = [child.lineno for child in ast.walk(method) if isinstance(child, ast.For)]
    assert loops and min(prefetch) < min(loops), (
        "章节预取必须发生在逐节点循环之前，否则仍是按叶子读取"
    )


def test_pull_passes_prefetched_sources_to_apply():
    tree = _tree(RUNNER)
    method = _method(tree, "_pull")
    calls = [
        child for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "apply_detail_refresh"
    ]
    assert len(calls) == 1
    keyword_names = {keyword.arg for keyword in calls[0].keywords}
    assert "prefetched_sources" in keyword_names, (
        "_pull 调用 apply_detail_refresh 时漏传 prefetched_sources，批取结果不会被消费"
    )


def test_apply_detail_refresh_accepts_prefetched_sources_and_skips_reload():
    tree = _tree(APPLY)
    function = _method(tree, "apply_detail_refresh")
    args = {arg.arg for arg in function.args.kwonlyargs}
    assert "prefetched_sources" in args

    # 读取 sources 的赋值必须是「有预取就复用，否则才 load_source_tables」，
    # 不能只加形参却仍然无条件重查。
    assigns = [
        child for child in ast.walk(function)
        if isinstance(child, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "sources" for target in child.targets)
    ]
    assert assigns, "apply_detail_refresh 没有 sources 赋值"
    source_code = ast.unparse(assigns[0].value)
    assert "prefetched_sources" in source_code
    assert "load_source_tables" in source_code


def test_batch_prefetch_is_not_per_node_source_query():
    """双向变异守卫：生产批取方法必须只有一个来源查询调用点。"""
    tree = _tree(RUNNER)
    method = _method(tree, "process_section")
    names = _called_names(method)
    assert "load_source_tables" not in names, (
        "process_section 自己又直接调用 load_source_tables，形成按章节 + 按叶子双重读取"
    )


def test_elimination_node_computes_cells_from_loaded_view_before_persist():
    """C3：差额节点使用已装载 ViewContext 的纯内存计算，不重新走 note_breakdown。"""
    tree = _tree(RUNNER)
    method = _method(tree, "_elim")
    names = _called_names(method)
    assert "note_cell_values" in names, "差额节点没有从已加载 ViewContext 计算公式单元格"
    assert "fill_by_formula" in names, "差额节点没有复用既有保护格/写入路径"

    calls = [
        child for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "fill_by_formula"
    ]
    assert len(calls) == 1
    keywords = {keyword.arg for keyword in calls[0].keywords}
    assert {"_precomputed_cells", "_precomputed_is_root_consol"} <= keywords, (
        "差额节点计算结果没有传给写入层，仍会重新调用完整 note_breakdown"
    )


def test_formula_fill_supports_precomputed_cells_without_note_breakdown():
    """C3：fill_by_formula 的预计算分支必须存在，且默认调用方语义不变。"""
    formula_tree = _tree(ROOT / "app" / "services" / "consol_note_formula_service.py")
    method = _method(formula_tree, "fill_by_formula")
    args = {arg.arg for arg in method.args.kwonlyargs}
    assert "_precomputed_cells" in args
    assert "_precomputed_is_root_consol" in args
    calls = _called_names(method)
    assert "note_breakdown" in calls, "默认路径丢失 note_breakdown，旧调用会失效"
