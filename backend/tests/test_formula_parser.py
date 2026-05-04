"""公式解析器单元测试 — 不需要数据库和后端服务

运行：python -m pytest backend/tests/test_formula_parser.py -v
"""

import pytest
import asyncio
from decimal import Decimal

from app.services.formula_parser import (
    parse_formula, tokenize, ParseError,
    NumberNode, StringNode, BinOpNode, UnaryNode,
    FuncCallNode, RowRefNode, RangeSumNode,
    FormulaEvaluator, evaluate_formula,
)


class TestTokenizer:
    def test_number(self):
        tokens = tokenize("123")
        assert len(tokens) == 1
        assert tokens[0].type == "NUMBER"
        assert tokens[0].value == "123"

    def test_decimal(self):
        tokens = tokenize("3.14")
        assert tokens[0].value == "3.14"

    def test_string(self):
        tokens = tokenize("'hello'")
        assert tokens[0].type == "STRING"

    def test_function(self):
        tokens = tokenize("TB('1001')")
        assert tokens[0].type == "FUNC"
        assert tokens[0].value == "TB"

    def test_operators(self):
        tokens = tokenize("1 + 2 - 3 * 4 / 5")
        ops = [t.value for t in tokens if t.type in ("PLUS", "MINUS", "STAR", "SLASH")]
        assert ops == ["+", "-", "*", "/"]

    def test_ident_with_dash(self):
        tokens = tokenize("BS-002")
        assert tokens[0].type == "IDENT"
        assert tokens[0].value == "BS-002"


class TestParser:
    def test_number(self):
        ast = parse_formula("42")
        assert isinstance(ast, NumberNode)
        assert ast.value == Decimal("42")

    def test_addition(self):
        ast = parse_formula("1 + 2")
        assert isinstance(ast, BinOpNode)
        assert ast.op == "+"

    def test_subtraction(self):
        ast = parse_formula("100 - 50")
        assert isinstance(ast, BinOpNode)
        assert ast.op == "-"
        assert isinstance(ast.left, NumberNode)
        assert ast.left.value == Decimal("100")
        assert isinstance(ast.right, NumberNode)
        assert ast.right.value == Decimal("50")

    def test_precedence(self):
        """乘法优先于加法"""
        ast = parse_formula("1 + 2 * 3")
        assert isinstance(ast, BinOpNode)
        assert ast.op == "+"
        assert isinstance(ast.right, BinOpNode)
        assert ast.right.op == "*"

    def test_parentheses(self):
        ast = parse_formula("(1 + 2) * 3")
        assert isinstance(ast, BinOpNode)
        assert ast.op == "*"
        assert isinstance(ast.left, BinOpNode)
        assert ast.left.op == "+"

    def test_unary_minus(self):
        ast = parse_formula("-100")
        assert isinstance(ast, UnaryNode)
        assert ast.op == "-"

    def test_function_call(self):
        ast = parse_formula("TB('1001','期末余额')")
        assert isinstance(ast, FuncCallNode)
        assert ast.name == "TB"
        assert len(ast.args) == 2

    def test_row_ref(self):
        ast = parse_formula("BS-002")
        assert isinstance(ast, RowRefNode)
        assert ast.row_code == "BS-002"

    def test_range_sum(self):
        ast = parse_formula("SUM(CN-001:CN-010)")
        assert isinstance(ast, RangeSumNode)
        assert ast.start_code == "CN-001"
        assert ast.end_code == "CN-010"

    def test_row_function(self):
        ast = parse_formula("ROW('BS-002')")
        assert isinstance(ast, RowRefNode)
        assert ast.row_code == "BS-002"

    def test_complex_expression(self):
        ast = parse_formula("CN-001 + CN-011 - CN-021")
        assert isinstance(ast, BinOpNode)

    def test_empty_formula(self):
        with pytest.raises(ParseError):
            parse_formula("")

    def test_nested_function(self):
        ast = parse_formula("SUM_TB('1001~1099','期末余额')")
        assert isinstance(ast, FuncCallNode)
        assert ast.name == "SUM_TB"


class TestEvaluator:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_arithmetic(self):
        result = self._run(evaluate_formula("100 + 200 * 3", db=None, project_id=None, year=2024))
        assert result["value"] == 700.0
        assert result["error"] is None

    def test_subtraction(self):
        result = self._run(evaluate_formula("100 - 50", db=None, project_id=None, year=2024))
        assert result["value"] == 50.0

    def test_division(self):
        result = self._run(evaluate_formula("100 / 4", db=None, project_id=None, year=2024))
        assert result["value"] == 25.0

    def test_division_by_zero(self):
        result = self._run(evaluate_formula("100 / 0", db=None, project_id=None, year=2024))
        assert result["value"] == 0.0  # 除零返回 0

    def test_row_reference(self):
        result = self._run(evaluate_formula(
            "BS-002 + 100", db=None, project_id=None, year=2024,
            row_values={"BS-002": Decimal("50000")},
        ))
        assert result["value"] == 50100.0

    def test_range_sum(self):
        result = self._run(evaluate_formula(
            "SUM(CN-001:CN-003)", db=None, project_id=None, year=2024,
            row_values={"CN-001": Decimal("100"), "CN-002": Decimal("200"), "CN-003": Decimal("300"), "CN-004": Decimal("999")},
        ))
        assert result["value"] == 600.0  # CN-004 不在范围内

    def test_unary_minus(self):
        result = self._run(evaluate_formula("-100 + 50", db=None, project_id=None, year=2024))
        assert result["value"] == -50.0

    def test_trace(self):
        result = self._run(evaluate_formula("100 + 200", db=None, project_id=None, year=2024))
        assert len(result["trace"]) > 0
        assert result["trace"][0]["op"] == "+"

    def test_parse_error(self):
        result = self._run(evaluate_formula("", db=None, project_id=None, year=2024))
        assert result["error"] is not None
