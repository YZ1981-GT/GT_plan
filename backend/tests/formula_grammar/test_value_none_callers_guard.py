"""ADR-FGR-03: FormulaResult.value=None 调用方清单与 ok/None 守卫。"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).with_name("value_none_callers.json")


def _function_nodes(tree: ast.AST, function_name: str) -> list[ast.AST]:
    """按末段函数名找节点，兼容类方法和嵌套 handler。"""
    wanted = function_name.rsplit(".", 1)[-1]
    return [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == wanted
    ]


def _is_result_attr(node: ast.AST, result_name: str, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == result_name
    )


def _has_attr(tree: ast.AST, result_name: str, attr: str) -> bool:
    return any(_is_result_attr(node, result_name, attr) for node in ast.walk(tree))


def _has_result_ok(tree: ast.AST, result_name: str) -> bool:
    """返回 AST 中是否引用了指定结果的 ``ok`` 属性。"""
    return _has_attr(tree, result_name, "ok")


def _contains_result_value_none(node: ast.AST, result_name: str) -> bool:
    """判断一个条件表达式是否明确处理 ``result.value is None``。"""
    return _has_value_none_check(node, result_name)


def _guard_condition(node: ast.AST) -> ast.AST | None:
    """取出可能决定结果消费的条件表达式。"""
    if isinstance(node, (ast.If, ast.While)):
        return node.test
    if isinstance(node, ast.IfExp):
        return node.test
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        return node.value
    return None


def _has_combined_result_guard(tree: ast.AST, result_name: str) -> bool:
    """确认结果消费前同时存在 ``ok`` 与 ``value is None`` 守卫。

    两种合法写法都接受：同一条件中的短路判断，或先判 ``ok``、随后判
    ``value is None`` 的连续早退。后者是报表逐行计算器的既有写法。
    """
    ok_lines: list[int] = []
    value_lines: list[int] = []
    for node in ast.walk(tree):
        condition = _guard_condition(node)
        if condition is None:
            continue
        if _has_result_ok(condition, result_name):
            ok_lines.append(getattr(node, "lineno", -1))
        if _contains_result_value_none(condition, result_name):
            value_lines.append(getattr(node, "lineno", -1))
        if _has_result_ok(condition, result_name) and _contains_result_value_none(condition, result_name):
            return True
    return any(ok < value for ok in ok_lines for value in value_lines)


def _has_value_none_check(tree: ast.AST, result_name: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
            continue
        if not isinstance(node.ops[0], (ast.Is, ast.IsNot)):
            continue
        left, right = node.left, node.comparators[0]
        if _is_result_attr(left, result_name, "value") and isinstance(right, ast.Constant) and right.value is None:
            return True
        if _is_result_attr(right, result_name, "value") and isinstance(left, ast.Constant) and left.value is None:
            return True
    return False


def _has_variable_none_check(tree: ast.AST, variable: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
            continue
        if not isinstance(node.ops[0], (ast.Is, ast.IsNot)):
            continue
        left, right = node.left, node.comparators[0]
        if isinstance(left, ast.Name) and left.id == variable and isinstance(right, ast.Constant) and right.value is None:
            return True
        if isinstance(right, ast.Name) and right.id == variable and isinstance(left, ast.Constant) and left.value is None:
            return True
    return False


def _source_entry(entry: dict) -> tuple[str, ast.AST | None]:
    path = ROOT / entry["file"]
    assert path.is_file(), f"清单文件不存在：{entry['file']}"
    source = path.read_text(encoding="utf-8-sig")
    if entry["kind"] == "frontend":
        return source, None
    tree = ast.parse(source, filename=str(path))
    nodes = _function_nodes(tree, entry["function"])
    assert nodes, f"清单调用方函数不存在：{entry['file']}::{entry['function']}"
    return source, nodes[0]


def _guard_passes(entry: dict, source: str, node: ast.AST | None) -> bool:
    if entry["kind"] == "frontend":
        marker = entry.get("marker", "—")
        if marker not in source:
            return False
        if entry["file"].endswith("FormulaManagerDialog.vue"):
            return "formula-result-error" in source or "失败原因" in source
        return "result.errors" in source or "errors?.length" in source
    if entry["kind"] == "nullable":
        return _has_variable_none_check(node, entry["variable"])
    result_name = entry["result"]
    return _has_combined_result_guard(node, result_name)


def load_entries() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", load_entries(), ids=lambda e: f"{e['file']}::{e.get('function', e.get('test'))}")
def test_every_registered_value_none_caller_has_guard(entry: dict) -> None:
    source, node = _source_entry(entry)
    assert _guard_passes(entry, source, node), (
        f"{entry['file']}::{entry.get('function')} 缺少 ok + value=None/None 守卫"
    )


def test_manifest_has_unique_production_callers() -> None:
    entries = load_entries()
    keys = [(e["file"], e.get("function", e.get("test"))) for e in entries]
    assert len(keys) == len(set(keys)), "value_none_callers.json 有重复调用方登记"
    assert len(entries) >= 25, "任务 4 清单不能退化成只登记少数包装器"


@pytest.mark.parametrize(
    "entry",
    [e for e in load_entries() if e.get("kind") == "result"],
    ids=lambda e: f"{e['file']}::{e['function']}",
)
def test_guard_detects_removed_ok_check_for_every_result_caller(entry: dict) -> None:
    """变异：任一登记调用方去掉本结果的 ok 判断，守卫必须打红。"""
    path = ROOT / entry["file"]
    source = path.read_text(encoding="utf-8-sig")
    result_name = entry["result"]
    assert f"{result_name}.ok" in source, f"清单调用方没有可变异的 ok 判断：{path}"
    mutated = source.replace(f"{result_name}.ok", "True")
    tree = ast.parse(mutated, filename=str(path))
    nodes = _function_nodes(tree, entry["function"])
    assert nodes, f"变异后调用方函数不存在：{path}::{entry['function']}"
    assert not _guard_passes(entry, mutated, nodes[0]), (
        f"去掉 {result_name}.ok 判断后守卫仍通过：{path}::{entry['function']}"
    )
