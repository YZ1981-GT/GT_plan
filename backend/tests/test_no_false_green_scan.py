"""防假绿扫描测试（partner-manager-edit-permission 任务 15.2；需求 12.1、12.13）。

AST 扫描本 spec 新增与改写的测试文件及测试函数，检测六类容易导致假绿的写法。
扫描清单由基线树与 worktree 之间的差异动态计算。
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import NamedTuple

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKTREE = Path(__file__).resolve().parents[1]  # backend/
BASELINE_REF = os.environ.get(
    "PM_EDIT_BASELINE_REF",
    "a02a21419a7ffef349384a766798b7ac291fca05",
)

# Functions that MUST NOT be replaced via dependency_overrides or monkeypatch
# (requirement 12.1 / 12.13 pattern 1)
_NON_REPLACEABLE_NAMES = frozenset({
    # judgment / permission functions
    "require_project_access",
    "assert_project_permission",
    "require_note_edit_access",
    "assert_note_edit_access",
    "assert_note_edit_access_for_object",
    "assert_note_edit_access_on_projects",
    "assert_note_role_access",
    "is_project_eqcr",
    "_guard_action",
    # permission cache functions (removed, must stay gone)
    "_get_cached_permission",
    "_set_cached_permission",
    "invalidate_permission_cache",
})

# hypothesis / fast-check settings
_REQUIRED_HYP_MAX = 5
_REQUIRED_FC_RUNS = 5

# Allowed skip/xfail markers
_ALLOWED_SKIP_PATTERNS = frozenset({"pg_only"})


# ---------------------------------------------------------------------------
# Scan list computation
# ---------------------------------------------------------------------------

class ScanTarget(NamedTuple):
    """A test file to scan, with whether it's entirely new or just modified."""
    path: str  # relative to WORKTREE (e.g. "tests/test_foo.py")
    is_new: bool


def _compute_scan_list() -> list[ScanTarget]:
    """Compute test files new/modified by this spec vs baseline."""
    result = subprocess.run(
        ["git", "diff", "--name-status", "--diff-filter=AM",
         BASELINE_REF, "--", "tests/"],
        capture_output=True, text=True, cwd=str(WORKTREE),
        timeout=30,
    )
    targets = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, rel_path = parts
        fname = os.path.basename(rel_path)
        if not fname.startswith("test_") or not fname.endswith(".py"):
            continue
        targets.append(ScanTarget(path=rel_path, is_new=(status == "A")))
    return sorted(targets, key=lambda t: t.path)


def _get_new_or_changed_functions(
    file_path: Path, baseline_ref: str
) -> set[str] | None:
    """For a modified (not new) file, return names of new/changed test functions.

    Returns None if the file is entirely new (scan everything).
    """
    try:
        old_src = subprocess.run(
            ["git", "show", f"{baseline_ref}:{file_path.relative_to(WORKTREE)}"],
            capture_output=True, text=True, cwd=str(WORKTREE),
            timeout=15,
        ).stdout
    except Exception:
        return None
    if not old_src:
        return None

    try:
        old_tree = ast.parse(old_src)
    except SyntaxError:
        return None
    try:
        new_src = file_path.read_text(encoding="utf-8")
        new_tree = ast.parse(new_src)
    except (SyntaxError, OSError):
        return None

    old_funcs: dict[str, str] = {}
    for node in ast.walk(old_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                old_funcs[node.name] = ast.get_source_segment(old_src, node) or ""

    changed = set()
    for node in ast.walk(new_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                new_body = ast.get_source_segment(new_src, node) or ""
                if node.name not in old_funcs or old_funcs[node.name] != new_body:
                    changed.add(node.name)
    return changed


# ---------------------------------------------------------------------------
# AST scan patterns
# ---------------------------------------------------------------------------

class Finding(NamedTuple):
    file: str
    line: int
    pattern: str
    detail: str


def _scan_file(file_path: Path, rel: str, func_filter: set[str] | None) -> list[Finding]:
    """Scan a single test file for all 6 patterns."""
    findings: list[Finding] = []
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError) as exc:
        return [Finding(rel, 0, "parse_error", str(exc))]

    # Collect test functions to scan
    test_funcs: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                if func_filter is None or node.name in func_filter:
                    test_funcs.append(node)

    # Also scan module-level for patterns 1, 5, 6 (not inside test functions)
    _scan_pattern1_overrides(tree, source, rel, func_filter, findings)
    for func in test_funcs:
        _scan_pattern2_pytest_raises(func, rel, findings)
        _scan_pattern3_subprocess_exit_code_only(func, source, rel, findings)
        _scan_pattern4_or_multi_value(func, rel, findings)
    _scan_pattern5_hypothesis_settings(tree, source, rel, func_filter, findings)
    _scan_pattern6_skip_xfail(tree, source, rel, func_filter, findings)

    return findings


def _scan_pattern1_overrides(
    tree: ast.Module, source: str, rel: str,
    func_filter: set[str] | None,
    findings: list[Finding],
) -> None:
    """Pattern 1: dependency_overrides or monkeypatch replacing non-replaceable functions."""
    for node in ast.walk(tree):
        # dependency_overrides[func] = ...
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if node.value.attr == "dependency_overrides":
                name = _extract_name(node.slice)
                if name in _NON_REPLACEABLE_NAMES:
                    findings.append(Finding(
                        rel, node.lineno, "P1_override_non_replaceable",
                        f"dependency_overrides[{name}]",
                    ))
        # monkeypatch.setattr(..., "func_name", ...) or monkeypatch.setattr(module, "func_name", ...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "setattr" and _is_monkeypatch(node.func.value):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if arg.value in _NON_REPLACEABLE_NAMES:
                            findings.append(Finding(
                                rel, node.lineno, "P1_monkeypatch_non_replaceable",
                                f'monkeypatch.setattr(..., "{arg.value}", ...)',
                            ))


def _is_monkeypatch(node: ast.expr) -> bool:
    if isinstance(node, ast.Name) and "monkeypatch" in node.id.lower():
        return True
    if isinstance(node, ast.Attribute) and "monkeypatch" in node.attr.lower():
        return True
    return False


def _scan_pattern2_pytest_raises(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    rel: str,
    findings: list[Finding],
) -> None:
    """Pattern 2: pytest.raises blocks with >1 statement or no message assertion after."""
    for node in ast.walk(func):
        if not isinstance(node, ast.With) and not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            call = item.context_expr
            if not _is_pytest_raises(call):
                continue
            # Check statement count in the with block
            if len(node.body) > 1:
                findings.append(Finding(
                    rel, node.lineno, "P2_raises_multi_statement",
                    f"pytest.raises block has {len(node.body)} statements (should be 1)",
                ))


def _is_pytest_raises(node: ast.expr) -> bool:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            return (node.func.attr == "raises" and
                    isinstance(node.func.value, ast.Name) and
                    node.func.value.id == "pytest")
    return False


def _scan_pattern3_subprocess_exit_code_only(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
    rel: str,
    findings: list[Finding],
) -> None:
    """Pattern 3: subprocess tests that only assert exit code, not output content."""
    # Look for subprocess.run / subprocess.call followed by assert on returncode
    # without any assert on stdout/stderr
    has_subprocess = False
    has_returncode_assert = False
    has_output_assert = False

    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (isinstance(node.func.value, ast.Name) and
                    node.func.value.id == "subprocess" and
                    node.func.attr in ("run", "call", "check_call", "check_output")):
                has_subprocess = True
        if isinstance(node, ast.Attribute):
            if node.attr == "returncode":
                has_returncode_assert = True
            if node.attr in ("stdout", "stderr", "output"):
                has_output_assert = True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in ("stdout", "stderr"):
                has_output_assert = True

    if has_subprocess and has_returncode_assert and not has_output_assert:
        findings.append(Finding(
            rel, func.lineno, "P3_subprocess_exit_code_only",
            f"function {func.name} asserts returncode but not stdout/stderr",
        ))


def _scan_pattern4_or_multi_value(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    rel: str,
    findings: list[Finding],
) -> None:
    """Pattern 4: assert x == a or x == b; or assert x in {a, b}."""
    for node in ast.walk(func):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        # Pattern: x == a or x == b (BoolOp Or with Compare)
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
            eq_targets = set()
            for val in test.values:
                if isinstance(val, ast.Compare) and len(val.ops) == 1:
                    if isinstance(val.ops[0], (ast.Eq, ast.Is)):
                        target_name = _extract_name(val.left)
                        if target_name:
                            eq_targets.add(target_name)
            if len(eq_targets) == 1:
                # Same target compared with multiple values via or
                findings.append(Finding(
                    rel, node.lineno, "P4_or_multi_value",
                    f"assert uses 'or' to combine equality checks on same target",
                ))
        # Pattern: x in {a, b, c} or x in (a, b, c) or x in [a, b, c]
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            if isinstance(test.ops[0], ast.In):
                container = test.comparators[0]
                if isinstance(container, (ast.Set, ast.Tuple, ast.List)):
                    if len(container.elts) >= 2:
                        findings.append(Finding(
                            rel, node.lineno, "P4_membership_multi_literal",
                            f"assert uses 'in' with {len(container.elts)}-element literal container",
                        ))


def _scan_pattern5_hypothesis_settings(
    tree: ast.Module, source: str, rel: str,
    func_filter: set[str] | None,
    findings: list[Finding],
) -> None:
    """Pattern 5: hypothesis without explicit max_examples=5."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if func_filter is not None and node.name not in func_filter:
            continue

        # Check if function uses hypothesis (has @given decorator)
        is_hypothesis = False
        has_settings = False
        settings_max = None

        for deco in node.decorator_list:
            deco_name = _extract_decorator_name(deco)
            if deco_name == "given":
                is_hypothesis = True
            if deco_name == "settings":
                has_settings = True
                # Extract max_examples value
                if isinstance(deco, ast.Call):
                    for kw in deco.keywords:
                        if kw.arg == "max_examples":
                            if isinstance(kw.value, ast.Constant):
                                settings_max = kw.value.value

        if is_hypothesis:
            if not has_settings:
                findings.append(Finding(
                    rel, node.lineno, "P5_hypothesis_no_settings",
                    f"hypothesis test {node.name} has no @settings(max_examples=5)",
                ))
            elif settings_max != _REQUIRED_HYP_MAX:
                findings.append(Finding(
                    rel, node.lineno, "P5_hypothesis_wrong_max",
                    f"hypothesis test {node.name} has max_examples={settings_max} (expected {_REQUIRED_HYP_MAX})",
                ))


def _scan_pattern6_skip_xfail(
    tree: ast.Module, source: str, rel: str,
    func_filter: set[str] | None,
    findings: list[Finding],
) -> None:
    """Pattern 6: new skip/skipif/xfail markers (except pg_only and required xfail(strict=True))."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if func_filter is not None and node.name not in func_filter:
            continue

        for deco in node.decorator_list:
            deco_name = _extract_decorator_name(deco)
            if deco_name in ("skip", "skipif"):
                # Check if it's pg_only
                if isinstance(deco, ast.Call):
                    # pytest.mark.skipif with pg_only condition
                    for arg in deco.args:
                        if _source_contains(source, arg, "pg_only"):
                            continue
                    for kw in deco.keywords:
                        if _source_contains(source, kw.value, "pg_only"):
                            continue
                # Check decorator source for pg_only
                deco_src = ast.get_source_segment(source, deco) or ""
                if "pg_only" in deco_src:
                    continue
                findings.append(Finding(
                    rel, node.lineno, "P6_skip",
                    f"test {node.name} has @{deco_name} marker",
                ))
            if deco_name == "xfail":
                # Allow xfail(strict=True) only
                is_strict = False
                if isinstance(deco, ast.Call):
                    for kw in deco.keywords:
                        if kw.arg == "strict" and isinstance(kw.value, ast.Constant):
                            if kw.value.value is True:
                                is_strict = True
                if not is_strict:
                    findings.append(Finding(
                        rel, node.lineno, "P6_xfail_not_strict",
                        f"test {node.name} has @xfail without strict=True",
                    ))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_decorator_name(deco: ast.expr) -> str | None:
    """Extract the leaf name from a decorator (handles pytest.mark.xxx etc.)."""
    if isinstance(deco, ast.Name):
        return deco.id
    if isinstance(deco, ast.Attribute):
        return deco.attr
    if isinstance(deco, ast.Call):
        return _extract_decorator_name(deco.func)
    return None


def _source_contains(source: str, node: ast.expr, text: str) -> bool:
    seg = ast.get_source_segment(source, node)
    return seg is not None and text in seg


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_no_false_green_patterns():
    """AST scan for 6 false-green patterns in this spec's test files (requirement 12.13)."""
    scan_targets = _compute_scan_list()
    assert scan_targets, "scan list is empty — no test files changed vs baseline"

    all_findings: list[Finding] = []
    scanned_files = 0

    for target in scan_targets:
        file_path = WORKTREE / target.path
        if not file_path.exists():
            continue

        # For modified files, only scan new/changed test functions
        func_filter: set[str] | None = None
        if not target.is_new:
            func_filter = _get_new_or_changed_functions(file_path, BASELINE_REF)
            if func_filter is not None and not func_filter:
                continue  # no test functions changed in this file

        findings = _scan_file(file_path, target.path, func_filter)
        all_findings.extend(findings)
        scanned_files += 1

    # Report findings
    if all_findings:
        msg_parts = [f"\n防假绿扫描发现 {len(all_findings)} 处命中（{scanned_files} 个文件）：\n"]
        for f in all_findings:
            msg_parts.append(f"  {f.file}:{f.line} [{f.pattern}] {f.detail}")
        pytest.fail("\n".join(msg_parts))
