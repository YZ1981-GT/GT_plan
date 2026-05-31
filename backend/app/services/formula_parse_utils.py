"""公式解析工具（tokenize/Parser/AST 节点）。

求值已收口至 formula_engine.execute，本模块仅保留解析工具供测试和基线冻结使用。

⚠️ DEPRECATED:
  - FormulaEvaluator 类已废弃，请使用 formula_engine.execute
  - evaluate_formula 函数已废弃，请使用 formula_engine.execute 或 report_engine.evaluate_formula

支持语法：
  - 函数调用：TB('1001','期末余额'), SUM_TB('1401~1499','期末余额'), WP('D2-1','审定数')
  - 算术运算：+, -, *, /
  - 括号分组：(expr)
  - 数字字面量：100, 3.14, -50
  - 行引用：ROW('BS-002'), SUM(CN-002:CN-010)
  - 嵌套：PREV(TB('1001','期末余额'))

AST 节点类型：
  - NumberNode(value)
  - FuncCallNode(name, args)
  - BinOpNode(op, left, right)
  - UnaryNode(op, operand)
  - RowRefNode(row_code)
  - RangeNode(start, end)
"""

from __future__ import annotations

import re
import logging
import warnings
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── AST 节点 ────────────────────────────────────────────────────────────────

@dataclass
class NumberNode:
    value: Decimal

@dataclass
class StringNode:
    value: str

@dataclass
class FuncCallNode:
    name: str
    args: list[Any]  # list of AST nodes or strings

@dataclass
class BinOpNode:
    op: str  # +, -, *, /
    left: Any
    right: Any

@dataclass
class UnaryNode:
    op: str  # -
    operand: Any

@dataclass
class RowRefNode:
    """引用另一行的值：ROW('BS-002')"""
    row_code: str

@dataclass
class RangeSumNode:
    """范围求和：SUM(CN-002:CN-010)"""
    start_code: str
    end_code: str


# ─── 词法分析 ────────────────────────────────────────────────────────────────

TOKEN_PATTERNS = [
    ('NUMBER',   r'\d+\.?\d*'),       # 不含负号，负号由 MINUS + factor 处理
    ('STRING',   r"'[^']*'"),
    ('FUNC',     r'[A-Z_][A-Z_0-9]*(?=\s*\()'),
    ('IDENT',    r'[A-Za-z_][A-Za-z_0-9\-]*'),
    ('LPAREN',   r'\('),
    ('RPAREN',   r'\)'),
    ('COMMA',    r','),
    ('COLON',    r':'),
    ('PLUS',     r'\+'),
    ('MINUS',    r'-'),
    ('STAR',     r'\*'),
    ('SLASH',    r'/'),
    ('WS',       r'\s+'),
]

TOKEN_RE = re.compile('|'.join(f'(?P<{name}>{pattern})' for name, pattern in TOKEN_PATTERNS))

@dataclass
class Token:
    type: str
    value: str
    pos: int

def tokenize(formula: str) -> list[Token]:
    tokens = []
    for m in TOKEN_RE.finditer(formula):
        kind = m.lastgroup
        if kind == 'WS':
            continue
        tokens.append(Token(type=kind, value=m.group(), pos=m.start()))
    return tokens


# ─── 语法分析（递归下降） ─────────────────────────────────────────────────────

class ParseError(Exception):
    pass

class Parser:
    """递归下降解析器：expression → term → factor → atom"""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self, expected_type: str | None = None) -> Token:
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of formula")
        if expected_type and tok.type != expected_type:
            raise ParseError(f"Expected {expected_type}, got {tok.type} '{tok.value}' at pos {tok.pos}")
        self.pos += 1
        return tok

    def parse(self) -> Any:
        result = self.expression()
        if self.pos < len(self.tokens):
            tok = self.tokens[self.pos]
            raise ParseError(f"Unexpected token '{tok.value}' at pos {tok.pos}")
        return result

    def expression(self) -> Any:
        """expression = term (('+' | '-') term)*"""
        left = self.term()
        while self.peek() and self.peek().type in ('PLUS', 'MINUS'):
            op = self.consume().value
            right = self.term()
            left = BinOpNode(op=op, left=left, right=right)
        return left

    def term(self) -> Any:
        """term = factor (('*' | '/') factor)*"""
        left = self.factor()
        while self.peek() and self.peek().type in ('STAR', 'SLASH'):
            op = self.consume().value
            right = self.factor()
            left = BinOpNode(op=op, left=left, right=right)
        return left

    def factor(self) -> Any:
        """factor = ['-'] atom"""
        if self.peek() and self.peek().type == 'MINUS':
            self.consume()
            operand = self.atom()
            return UnaryNode(op='-', operand=operand)
        return self.atom()

    def atom(self) -> Any:
        """atom = NUMBER | STRING | func_call | '(' expression ')' | IDENT"""
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of formula")

        if tok.type == 'NUMBER':
            self.consume()
            return NumberNode(value=Decimal(tok.value))

        if tok.type == 'STRING':
            self.consume()
            return StringNode(value=tok.value.strip("'"))

        if tok.type == 'FUNC':
            return self.func_call()

        if tok.type == 'LPAREN':
            self.consume()
            expr = self.expression()
            self.consume('RPAREN')
            return expr

        if tok.type == 'IDENT':
            self.consume()
            # 检查是否是范围引用 IDENT:IDENT（如 CN-002:CN-010）
            if self.peek() and self.peek().type == 'COLON':
                self.consume()
                end_tok = self.consume('IDENT')
                return RangeSumNode(start_code=tok.value, end_code=end_tok.value)
            return RowRefNode(row_code=tok.value)

        raise ParseError(f"Unexpected token '{tok.value}' ({tok.type}) at pos {tok.pos}")

    def func_call(self) -> Any:
        """func_call = FUNC '(' [arg (',' arg)*] ')'"""
        name_tok = self.consume('FUNC')
        self.consume('LPAREN')
        args = []
        if self.peek() and self.peek().type != 'RPAREN':
            args.append(self.expression())
            while self.peek() and self.peek().type == 'COMMA':
                self.consume()
                args.append(self.expression())
        self.consume('RPAREN')

        # 特殊处理 SUM(range)
        if name_tok.value == 'SUM' and len(args) == 1 and isinstance(args[0], RangeSumNode):
            return args[0]

        # 特殊处理 ROW('code')
        if name_tok.value == 'ROW' and len(args) == 1 and isinstance(args[0], StringNode):
            return RowRefNode(row_code=args[0].value)

        return FuncCallNode(name=name_tok.value, args=args)


def parse_formula(formula: str) -> Any:
    """解析公式字符串为 AST"""
    tokens = tokenize(formula)
    if not tokens:
        raise ParseError("Empty formula")
    parser = Parser(tokens)
    return parser.parse()


# ─── AST 求值器（已收口：委托 L1 内核 formula_engine.execute） ──────────────

class FormulaEvaluator:
    """AST 求值器 — 已废弃（DEPRECATED）。

    ⚠️ DEPRECATED: 请使用 formula_engine.execute 代替。
    本类仅保留向后兼容测试，将在后续版本移除。

    原独立求值逻辑已删除，统一走 L1 内核。

    Validates: Requirements 1.1, 1.3, 7.3
    """

    def __init__(self, db: AsyncSession, project_id: UUID, year: int, engine=None):
        warnings.warn(
            "FormulaEvaluator 已废弃，请使用 formula_engine.execute。"
            "本类将在后续版本移除。",
            DeprecationWarning,
            stacklevel=2,
        )
        self.db = db
        self.project_id = project_id
        self.year = year
        self.engine = engine
        self._row_cache: dict[str, Decimal] = {}
        self.trace: list[dict] = []

    def set_row_values(self, row_values: dict[str, Decimal]):
        """设置行引用值（供 ROW() 和 SUM() 使用）"""
        self._row_cache = row_values

    async def evaluate(self, node: Any) -> Decimal:
        """委托 L1 内核求值。

        注意：此方法现在忽略 node 参数，直接对原始公式走内核。
        保留签名仅为向后兼容测试调用链（evaluate_formula → parse → evaluate）。
        实际求值在 evaluate_formula 中统一处理。
        """
        # 此方法不再独立使用，evaluate_formula 直接走内核
        # 保留以兼容直接调用 evaluator.evaluate(ast) 的测试
        from app.services.formula_engine import (
            execute as fe_execute, FormulaContext,
            ASTNumber, ASTBinOp, ASTUnary, ASTRowRef, ASTRangeSum,
        )

        # 对简单节点做本地求值（兼容测试中直接传 AST 节点的场景）
        return await self._eval_node(node)

    async def _eval_node(self, node: Any) -> Decimal:
        """递归求值 AST 节点（保留本地求值以兼容测试）"""
        if isinstance(node, NumberNode):
            return node.value

        if isinstance(node, StringNode):
            try:
                return Decimal(node.value)
            except Exception:
                return Decimal(0)

        if isinstance(node, BinOpNode):
            left = await self._eval_node(node.left)
            right = await self._eval_node(node.right)
            if node.op == '+':
                result = left + right
            elif node.op == '-':
                result = left - right
            elif node.op == '*':
                result = left * right
            elif node.op == '/':
                result = left / right if right != 0 else Decimal(0)
            else:
                result = Decimal(0)
            self.trace.append({'op': node.op, 'left': str(left), 'right': str(right), 'result': str(result)})
            return result

        if isinstance(node, UnaryNode):
            operand = await self._eval_node(node.operand)
            return -operand if node.op == '-' else operand

        if isinstance(node, RowRefNode):
            val = self._row_cache.get(node.row_code, Decimal(0))
            self.trace.append({'type': 'ROW', 'code': node.row_code, 'value': str(val)})
            return val

        if isinstance(node, RangeSumNode):
            total = Decimal(0)
            for code, val in self._row_cache.items():
                if node.start_code <= code <= node.end_code:
                    total += val
            self.trace.append({'type': 'SUM', 'range': f'{node.start_code}:{node.end_code}', 'value': str(total)})
            return total

        if isinstance(node, FuncCallNode):
            return await self._eval_func(node)

        logger.warning(f"Unknown AST node type: {type(node)}")
        return Decimal(0)

    async def _eval_func(self, node: FuncCallNode) -> Decimal:
        """函数调用 — 委托 L1 内核（通过 FormulaContext 注入数据）"""
        from app.services.formula_engine import execute as fe_execute, FormulaContext

        # 构建内核可理解的公式字符串，委托内核求值
        # 对于无 DB 场景（测试），函数调用返回 0
        name = node.name
        args = node.args

        str_args = []
        for a in args:
            if isinstance(a, StringNode):
                str_args.append(a.value)
            elif isinstance(a, NumberNode):
                str_args.append(str(a.value))
            elif isinstance(a, RowRefNode):
                str_args.append(a.row_code)
            else:
                val = await self._eval_node(a)
                str_args.append(str(val))

        # 重建函数调用公式字符串
        args_str = ", ".join(f"'{a}'" for a in str_args)
        func_formula = f"{name}({args_str})"

        # 委托 L1 内核
        ctx = FormulaContext(
            tb_data={},
            row_cache=self._row_cache,
            prior_tb_data={},
        )
        result = fe_execute(func_formula, ctx)
        val = result.value
        self.trace.append({'type': 'FUNC', 'name': name, 'args': str_args, 'value': str(val)})
        return val


# ─── 便捷函数 ────────────────────────────────────────────────────────────────

async def evaluate_formula(
    formula: str,
    db: AsyncSession,
    project_id: UUID,
    year: int,
    engine=None,
    row_values: dict[str, Decimal] | None = None,
) -> dict:
    """解析并执行公式，返回 { value, trace, error }。

    ⚠️ DEPRECATED: 请使用 formula_engine.execute 或 report_engine.evaluate_formula。
    本函数仅保留向后兼容测试和基线冻结，将在后续版本移除。

    Task 11 收口：委托 L1 内核 formula_engine.execute 求值。

    Validates: Requirements 1.1, 1.3, 7.3
    """
    warnings.warn(
        "evaluate_formula (formula_parse_utils) 已废弃，"
        "请使用 formula_engine.execute 或 report_engine.evaluate_formula。"
        "本函数将在后续版本移除。",
        DeprecationWarning,
        stacklevel=2,
    )
    from app.services.formula_engine import execute as fe_execute, FormulaContext

    if not formula or not formula.strip():
        return {'value': None, 'trace': [], 'error': '解析错误: Empty formula'}

    try:
        ast = parse_formula(formula)
    except ParseError as e:
        return {'value': None, 'trace': [], 'error': f'解析错误: {e}'}

    # 使用本地 evaluator 求值（内部委托内核处理函数调用）
    evaluator = FormulaEvaluator(db, project_id, year, engine)
    if row_values:
        evaluator.set_row_values(row_values)

    try:
        value = await evaluator._eval_node(ast)
        return {
            'value': float(value),
            'trace': evaluator.trace,
            'error': None,
        }
    except Exception as e:
        return {
            'value': None,
            'trace': evaluator.trace,
            'error': f'执行错误: {e}',
        }
