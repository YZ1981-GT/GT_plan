"""守卫：formula_settings 执行层函数必须有生产调用方（spec formula-settings-wiring-closure T10）。

AST 扫描 ``backend/app``（排除 tests）确认每个关键函数至少被一处生产代码引用。
防止 mock/spy 测试全绿而真实接线断裂（adj-formula 教训 ①）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# 要检查的函数：(模块路径后缀, 函数名)
WIRED_FUNCTIONS: list[tuple[str, str]] = [
    ("formula_settings.cross_check_rules", "run_user_rules"),
    ("formula_settings.wp_effective", "init_prefill_overrides"),
    ("formula_settings.wp_effective", "overlay_prefill_formulas"),
    ("formula_settings.consol_note_settings", "effective_formulas"),
    ("formula_settings.note_settings", "save_section"),
    ("formula_settings.note_settings", "materialize"),
    ("formula_settings.note_settings", "materialize_quietly"),
    ("formula_settings.rollback", "rollback_from_log"),
    ("formula_settings.custom_presets", "upsert"),
    ("formula_settings.propagation", "publish_events"),
    ("formula_management.cross_check_history", "list_history"),
    ("formula_push.coverage", "load_coverage"),
    ("formula_push.coverage", "compute"),
    ("formula_settings.dependencies", "formula_dependencies"),
    ("formula_catalog", "build_catalog"),
    ("formula_catalog", "catalog_stats"),
    ("formula_catalog", "extract_function_names"),
]

# 域列表——确保 WIRED_FUNCTIONS 覆盖所有接线域
WIRED_DOMAINS = {"cross_check_rules", "wp_effective", "consol_note_settings", "note_settings",
                 "rollback", "custom_presets", "propagation", "cross_check_history",
                 "coverage", "dependencies", "formula_catalog"}


def _scan_production_refs() -> dict[str, set[str]]:
    """扫描 app/ 下所有 .py 里对各函数名的引用（import / 直接调用 / 属性访问）。

    返回 {函数名: {引用该名的文件路径集合}}。
    排除 tests/ 目录和 __pycache__。
    """
    targets = {fn for _, fn in WIRED_FUNCTIONS}
    # 也匹配 from ... import 形式
    refs: dict[str, set[str]] = {fn: set() for fn in targets}

    for py_file in APP_ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        rel = str(py_file.relative_to(APP_ROOT))
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # 快速文本预筛
        matched = {fn for fn in targets if fn in source}
        if not matched:
            continue
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # import X, from X import Y
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.astext if hasattr(alias, "astext") else alias.name
                    if name in matched:
                        refs[name].add(rel)
            # 函数调用 / 属性访问
            if isinstance(node, ast.Name) and node.id in matched:
                refs[node.id].add(rel)
            if isinstance(node, ast.Attribute) and node.attr in matched:
                refs[node.attr].add(rel)
    return refs


_REFS_CACHE: dict[str, set[str]] | None = None


def _get_refs() -> dict[str, set[str]]:
    global _REFS_CACHE
    if _REFS_CACHE is None:
        _REFS_CACHE = _scan_production_refs()
    return _REFS_CACHE


@pytest.mark.parametrize("module_suffix,func_name", WIRED_FUNCTIONS,
                         ids=[f"{m.rsplit('.', 1)[-1]}.{f}" for m, f in WIRED_FUNCTIONS])
def test_function_has_production_caller(module_suffix: str, func_name: str):
    """每个接线函数至少在一处非定义模块的生产代码里被引用。"""
    refs = _get_refs()
    callers = refs.get(func_name, set())
    # 排除自身定义所在文件（用 services/ 限定避免同名 router 被误排）
    defn_path_part = "services/" + module_suffix.replace(".", "/") + ".py"
    non_self = {r for r in callers if defn_path_part not in r}
    assert non_self, (
        f"{module_suffix}.{func_name} 没有生产调用方——"
        f"该函数只在测试里被调用，生产接线断裂"
    )


def test_wired_domains_coverage():
    """WIRED_FUNCTIONS 列表覆盖了所有接线域，不遗漏。"""
    covered = set()
    for module_suffix, _ in WIRED_FUNCTIONS:
        parts = module_suffix.split(".")
        covered.add(parts[-1])
    assert covered >= WIRED_DOMAINS, f"未覆盖：{WIRED_DOMAINS - covered}"
