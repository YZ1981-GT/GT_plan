"""差额表 POST 路由的 query/body 项目一致性 AST 守卫。

本守卫只检查三个指定的写/查询路由。它通过 Python AST 识别路由装饰器、
``body`` 与 ``project_id`` 参数，以及二者之间的 ``==``/``!=`` 比较，
不依赖源码字符串搜索，因此注释和 docstring 不会制造假阳性。

spec: consol-group-code-entry-consistency 任务 7.3 / R5.2
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess

import pytest
import sys
from pathlib import Path
from typing import Iterable

_ROOT = Path(__file__).resolve().parents[2]
_ROUTER = _ROOT / "backend" / "app" / "routers" / "consol_worksheet.py"
_TARGET_POST_ROUTES = frozenset({"/recalc", "/pivot", "/pivot/templates"})


def _route_path(decorator: ast.AST) -> str | None:
    """从 ``@router.post(…)`` AST 节点提取路径。"""
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if not isinstance(decorator.func.value, ast.Name):
        return None
    if decorator.func.value.id != "router" or decorator.func.attr != "post":
        return None
    if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
        return None
    path = decorator.args[0].value
    return path if isinstance(path, str) else None


def _function_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """返回函数所有显式参数名，供 AST 判据确认 query/body 参数存在。"""
    arguments = node.args
    return {
        argument.arg
        for argument in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        )
    }


def _is_body_project_attribute(node: ast.AST, body_name: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "project_id"
        and isinstance(node.value, ast.Name)
        and node.value.id == body_name
    )


def _is_query_project_name(node: ast.AST, query_name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == query_name


def _is_project_scope_comparison(
    node: ast.AST, *, body_name: str, query_name: str
) -> bool:
    """判断一个 Compare 是否比较 body.project_id 与 query project_id。"""
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return False
    if not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return False
    operands = (node.left, node.comparators[0])
    return (
        _is_body_project_attribute(operands[0], body_name)
        and _is_query_project_name(operands[1], query_name)
    ) or (
        _is_query_project_name(operands[0], query_name)
        and _is_body_project_attribute(operands[1], body_name)
    )


def _target_routes(source: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """按 POST 路由装饰器收集目标函数，不扫描注释或 docstring 文本。"""
    tree = ast.parse(source, filename=str(_ROUTER))
    routes: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            path = _route_path(decorator)
            if path in _TARGET_POST_ROUTES:
                routes[path] = node
    return routes


def _scope_comparison_violations(source: str) -> list[str]:
    """返回目标路由中缺少 body/query 项目比较的路由路径。"""
    routes = _target_routes(source)
    violations: list[str] = []
    for path in sorted(_TARGET_POST_ROUTES):
        function = routes.get(path)
        if function is None:
            violations.append(f"{path}: 未找到指定 POST 路由")
            continue

        parameters = _function_parameters(function)
        body_name = "body" if "body" in parameters else None
        query_name = "project_id" if "project_id" in parameters else None
        if body_name is None or query_name is None:
            violations.append(f"{path}: 缺少 body 或 query project_id 参数")
            continue

        has_comparison = any(
            _is_project_scope_comparison(
                candidate,
                body_name=body_name,
                query_name=query_name,
            )
            for candidate in ast.walk(function)
        )
        if not has_comparison:
            violations.append(f"{path}: 缺少 body.project_id 与 project_id 的比较")
    return violations


def _comparison_if_nodes(source: str) -> Iterable[ast.If]:
    """返回目标路由中承载项目比较的 if 节点，供真实磁盘变异删除。"""
    routes = _target_routes(source)
    for path in sorted(_TARGET_POST_ROUTES):
        function = routes[path]
        for candidate in ast.walk(function):
            if not isinstance(candidate, ast.If):
                continue
            if _is_project_scope_comparison(
                candidate.test,
                body_name="body",
                query_name="project_id",
            ):
                yield candidate


def _delete_one_production_comparison(original: bytes) -> bytes:
    """删除一个完整比较 if 块，保留生产文件其它字节不变。"""
    source = original.decode("utf-8")
    tree = ast.parse(source, filename=str(_ROUTER))
    target = next(iter(_comparison_if_nodes(source)), None)
    assert target is not None, "变异未找到生产比较，不能证明守卫有效"
    assert target.lineno is not None and target.end_lineno is not None

    lines = source.splitlines(keepends=True)
    start = target.lineno - 1
    end = target.end_lineno
    mutated = "".join((*lines[:start], *lines[end:]))
    mutated_tree = ast.parse(mutated, filename=str(_ROUTER))
    assert mutated_tree is not None
    assert ast.dump(tree) != ast.dump(mutated_tree)
    return mutated.encode("utf-8")


def test_target_routes_have_project_scope_comparison() -> None:
    """三个指定 POST 路由全部必须比较请求体与 query 项目。"""
    source = _ROUTER.read_text(encoding="utf-8")
    routes = _target_routes(source)
    assert set(routes) == set(_TARGET_POST_ROUTES)
    violations = _scope_comparison_violations(source)
    assert violations == [], "\n".join(violations)


def test_ast_guard_ignores_comments_and_docstrings() -> None:
    """注释/docstring 中出现相同文字不能让缺失比较的路由通过。"""
    source = '''
@router.post("/recalc")
async def recalc(body, project_id):
    """body.project_id != project_id"""
    # if body.project_id != project_id:
    return None
'''
    violations = _scope_comparison_violations(source)
    assert "/recalc: 缺少 body.project_id 与 project_id 的比较" in violations


def test_mutation_deleting_one_production_comparison_is_red() -> None:
    """真实磁盘变异删除一个比较后，守卫子进程必须失败，并逐字节恢复。"""
    original = _ROUTER.read_bytes()
    original_digest = hashlib.sha256(original).hexdigest()
    mutated = _delete_one_production_comparison(original)
    assert mutated != original

    _ROUTER.write_bytes(mutated)
    try:
        env = os.environ.copy()
        env.pop("DATABASE_URL", None)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "backend/tests/test_route_body_project_id_consistency.py::"
                "test_target_routes_have_project_scope_comparison",
                "-q",
                "-p",
                "no:playwright",
            ],
            cwd=_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        evidence = ((result.stdout or "") + (result.stderr or ""))[-4000:]
        print(f"[task-7.3-mutation][RED] 删除一个生产比较后的守卫输出:\n{evidence}")
        assert result.returncode != 0, (
            "删除生产比较后 AST 守卫仍通过，说明守卫未覆盖缺陷。\n" + evidence
        )
        assert "FAILED" in evidence or "AssertionError" in evidence
    finally:
        _ROUTER.write_bytes(original)
        restored = _ROUTER.read_bytes()
        restored_digest = hashlib.sha256(restored).hexdigest()
        print(
            f"[task-7.3-mutation][RESTORE] bytes_equal={restored == original} "
            f"sha256={restored_digest} expected={original_digest}"
        )
        assert restored_digest == original_digest
        assert restored == original


_MUTATION_ROUTE_CASES = (
    ("/recalc", "recalc_worksheet"),
    ("/pivot", "pivot_query"),
    ("/pivot/templates", "create_template"),
)


def _delete_route_production_comparison(original: bytes, route_path: str) -> bytes:
    """删除指定生产端点的项目比较，供 7.4 每端点独立变异使用。"""
    source = original.decode("utf-8")
    tree = ast.parse(source, filename=str(_ROUTER))
    routes = _target_routes(source)
    function = routes.get(route_path)
    assert function is not None, f"变异未找到生产路由: {route_path}"

    candidates = [
        candidate
        for candidate in ast.walk(function)
        if isinstance(candidate, ast.If)
        and _is_project_scope_comparison(
            candidate.test,
            body_name="body",
            query_name="project_id",
        )
    ]
    assert len(candidates) == 1, (
        f"{route_path} 的生产项目比较数量应为 1，实际为 {len(candidates)}"
    )
    target = candidates[0]
    assert target.lineno is not None and target.end_lineno is not None

    lines = source.splitlines(keepends=True)
    mutated = "".join(
        (*lines[: target.lineno - 1], *lines[target.end_lineno :])
    )
    ast.parse(mutated, filename=str(_ROUTER))
    assert ast.dump(tree) != ast.dump(ast.parse(mutated, filename=str(_ROUTER)))
    return mutated.encode("utf-8")


def _run_guard_or_behavior_test(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-q", "-p", "no:playwright"],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(("route_path", "route_function"), _MUTATION_ROUTE_CASES)
def test_each_production_comparison_mutation_is_red(
    route_path: str, route_function: str
) -> None:
    """每个差额表端点独立删比较，AST 与真实端点测试都必须打红。"""
    original = _ROUTER.read_bytes()
    original_digest = hashlib.sha256(original).hexdigest()
    mutated = _delete_route_production_comparison(original, route_path)
    assert mutated != original

    _ROUTER.write_bytes(mutated)
    try:
        guard_result = _run_guard_or_behavior_test(
            [
                "backend/tests/test_route_body_project_id_consistency.py::"
                "test_target_routes_have_project_scope_comparison"
            ]
        )
        guard_evidence = ((guard_result.stdout or "") + (guard_result.stderr or ""))[-4000:]
        print(
            f"[task-7.4][{route_path}][AST RED] returncode={guard_result.returncode}\n"
            f"{guard_evidence}"
        )
        assert guard_result.returncode != 0, (
            f"{route_path} 删除比较后 AST 守卫仍通过:\n{guard_evidence}"
        )
        assert "FAILED" in guard_evidence or "AssertionError" in guard_evidence

        behavior_result = _run_guard_or_behavior_test(
            [
                "backend/tests/test_consol_worksheet_project_scope.py",
                "-k",
                "test_mismatched_body_project_is_rejected_before_service "
                f"and {route_function}",
            ]
        )
        behavior_evidence = (
            (behavior_result.stdout or "") + (behavior_result.stderr or "")
        )[-4000:]
        print(
            f"[task-7.4][{route_path}][BEHAVIOR RED] "
            f"returncode={behavior_result.returncode}\n{behavior_evidence}"
        )
        assert behavior_result.returncode != 0, (
            f"{route_path} 删除比较后端点行为测试仍通过:\n{behavior_evidence}"
        )
        assert "FAILED" in behavior_evidence or "AssertionError" in behavior_evidence
    finally:
        _ROUTER.write_bytes(original)
        restored = _ROUTER.read_bytes()
        restored_digest = hashlib.sha256(restored).hexdigest()
        print(
            f"[task-7.4][{route_path}][RESTORE] bytes_equal={restored == original} "
            f"sha256={restored_digest} expected={original_digest}"
        )
        assert restored_digest == original_digest
        assert restored == original
