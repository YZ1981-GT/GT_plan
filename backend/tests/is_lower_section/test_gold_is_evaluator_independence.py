"""金标准求值器独立性（spec income-statement-lower-section-formulas 任务 4）。

``gold_is_evaluator`` 必须是独立实现：一旦它 import 生产的报表 / 取数 / 逐行计算模块，
「生产与金标准一致」就退化成「生产与自己一致」，对拍恒绿。判据用 AST（文本匹配会被
注释与 docstring 两头骗过，memory 方法论铁律㉖）。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

GOLD = Path(__file__).resolve().parent / "gold_is_evaluator.py"
#: 禁止 import 的生产模块（前缀匹配）：报表求值链上的每一层
FORBIDDEN = (
    "app.services.report_engine",
    "app.services.report_row_compute",
    "app.services.report_eval_order",
    "app.services.report_formula_service",
    "app.services.formula_engine",
    "app.services.formula_grammar",
    "app.services.formula_preloader",
    "app.services.amount_resolver",
    "app.services.tb_leaf_codes",
    "app.services.consol_report_values",
)
ALLOWED_ROOTS = {"re", "dataclasses", "decimal", "__future__", "typing", "collections"}


def imported_modules() -> list[str]:
    tree = ast.parse(GOLD.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_gold_evaluator_imports_no_production_module():
    hits = [name for name in imported_modules()
            if any(name == item or name.startswith(item + ".") for item in FORBIDDEN)]
    assert hits == [], f"金标准求值器 import 了生产模块，对拍会恒绿：{hits}"


def test_gold_evaluator_imports_only_stdlib():
    outside = [name for name in imported_modules() if name.split(".")[0] not in ALLOWED_ROOTS]
    assert outside == [], f"金标准求值器只许用标准库，多出：{outside}"


def test_independence_scanner_catches_injected_import():
    """反向变异：给源码注入一行生产 import，判据必须报出来（否则扫描器空转）。"""
    injected = GOLD.read_text(encoding="utf-8") + "\nfrom app.services.report_engine import evaluate_formula\n"
    tree = ast.parse(injected)
    names = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
    assert [name for name in names
            if any(name == item or name.startswith(item + ".") for item in FORBIDDEN)] == [
        "app.services.report_engine"]


def test_comment_mentioning_production_module_is_not_flagged():
    """注释 / docstring 里写生产模块名不算 import（文本匹配会误报，AST 不会）。"""
    tree = ast.parse("# from app.services.report_engine import x\n'''见 app.services.report_row_compute'''\n")
    assert [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))] == []


@pytest.mark.parametrize("formula", [
    "ROW('IS-001')+ROW('IS-002')",
    "SUM_ROW('IS-056','IS-061')",
    "-TB('6702','本期发生额')",
    "TB('6001','本期发生额')+TB('6051','本期发生额')",
    "ROW('IS-001')-ROW('IS-007')+ROW('IS-030')",
])
def test_gold_evaluator_parses_every_production_writing(formula):
    """四套种子实际出现的五种写法金标准都认得（未识别写法会被对拍用例断言为 0，这里先单测）。"""
    from tests.is_lower_section.gold_is_evaluator import GoldRow, evaluate

    result = evaluate([GoldRow("X-001", 1, formula)], {"6001": 1, "6051": 2, "6702": 3})
    assert result.unparsed == {}, result.unparsed
