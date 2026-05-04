"""公式表达式解析器 — 将公式字符串解析为 AST 并执行

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
    ('NUMBER',   r'-?\d+\.?\d*'),
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


# ─── AST 求值器 ──────────────────────────────────────────────────────────────

class FormulaEvaluator:
    """AST 求值器 — 连接 FormulaEngine 执行器

    支持：
    - 算术运算（+, -, *, /）
    - 函数调用（TB, WP, AUX, PREV, SUM_TB）
    - 行引用（ROW）
    - 范围求和（SUM）
    - 数字和字符串字面量
    """

    def __init__(self, db: AsyncSession, project_id: UUID, year: int, engine=None):
        self.db = db
        self.project_id = project_id
        self.year = year
        self.engine = engine  # FormulaEngine instance
        self._row_cache: dict[str, Decimal] = {}  # 行引用缓存
        self._memo: dict[str, Decimal] = {}  # 公式结果缓存（同一批次内）
        self.trace: list[dict] = []  # 执行追踪

    def set_row_values(self, row_values: dict[str, Decimal]):
        """设置行引用值（供 ROW() 和 SUM() 使用）"""
        self._row_cache = row_values

    async def evaluate(self, node: Any) -> Decimal:
        """递归求值 AST 节点"""
        if isinstance(node, NumberNode):
            return node.value

        if isinstance(node, StringNode):
            try:
                return Decimal(node.value)
            except Exception:
                return Decimal(0)

        if isinstance(node, BinOpNode):
            left = await self.evaluate(node.left)
            right = await self.evaluate(node.right)
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
            operand = await self.evaluate(node.operand)
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
        """执行函数调用节点"""
        name = node.name
        args = node.args

        # 提取字符串参数
        str_args = []
        for a in args:
            if isinstance(a, StringNode):
                str_args.append(a.value)
            elif isinstance(a, NumberNode):
                str_args.append(str(a.value))
            elif isinstance(a, RowRefNode):
                str_args.append(a.row_code)
            else:
                val = await self.evaluate(a)
                str_args.append(str(val))

        # ── 跨模块引用函数（直接查数据库） ──
        if name == 'REPORT':
            return await self._exec_report(str_args)
        if name == 'NOTE':
            return await self._exec_note(str_args)
        if name == 'CONSOL':
            return await self._exec_consol(str_args)

        # ── 内置函数（通过 FormulaEngine） ──
        if self.engine:
            params = self._build_params(name, str_args)
            result = await self.engine.execute(
                db=self.db, project_id=self.project_id, year=self.year,
                formula_type=name, params=params,
            )
            val = result.get('value')
            if val is not None:
                try:
                    dec_val = Decimal(str(val))
                    self.trace.append({'type': 'FUNC', 'name': name, 'args': str_args, 'value': str(dec_val)})
                    return dec_val
                except Exception:
                    pass
            error = result.get('error')
            if error:
                self.trace.append({'type': 'FUNC', 'name': name, 'args': str_args, 'error': error})
            return Decimal(0)

        self.trace.append({'type': 'FUNC', 'name': name, 'args': str_args, 'error': 'No engine'})
        return Decimal(0)

    async def _exec_report(self, args: list[str]) -> Decimal:
        """REPORT('BS-002','期末') — 从 report_config 取报表行金额"""
        from sqlalchemy import text as sa_text
        row_code = args[0] if args else ''
        col = args[1] if len(args) > 1 else '期末'
        field = 'current_period_amount' if '期末' in col or '本期' in col else 'prior_period_amount'
        try:
            result = await self.db.execute(
                sa_text(f"SELECT {field} FROM report_config WHERE row_code = :rc AND is_deleted = false LIMIT 1"),
                {"rc": row_code},
            )
            row = result.fetchone()
            val = Decimal(str(row[0])) if row and row[0] is not None else Decimal(0)
            self.trace.append({'type': 'REPORT', 'code': row_code, 'col': col, 'value': str(val)})
            return val
        except Exception as e:
            self.trace.append({'type': 'REPORT', 'code': row_code, 'error': str(e)})
            return Decimal(0)

    async def _exec_note(self, args: list[str]) -> Decimal:
        """NOTE('货币资金','合计','期末') — 从附注数据取值（按行名+列名匹配）"""
        from sqlalchemy import text as sa_text
        import json as _json
        row_name = args[0] if args else ''
        col_name = args[1] if len(args) > 1 else '合计'
        period = args[2] if len(args) > 2 else '期末'
        try:
            # 查所有附注数据，按行名模糊匹配
            result = await self.db.execute(
                sa_text("SELECT section_id, data FROM consol_note_data WHERE project_id = :pid AND year = :y"),
                {"pid": str(self.project_id), "y": self.year},
            )
            for sec_row in result.fetchall():
                sec_data = sec_row[1] if isinstance(sec_row[1], dict) else {}
                headers = sec_data.get('headers', [])
                rows = sec_data.get('rows', [])
                # 找目标列
                col_idx = -1
                for hi, h in enumerate(headers):
                    if col_name in str(h) or (period and period in str(h)):
                        col_idx = hi
                        break
                if col_idx < 0:
                    continue
                # 找目标行
                for r in rows:
                    if r and len(r) > col_idx and row_name in str(r[0]):
                        try:
                            val = Decimal(str(r[col_idx]))
                            self.trace.append({'type': 'NOTE', 'row': row_name, 'col': col_name, 'value': str(val)})
                            return val
                        except (ValueError, TypeError):
                            continue
            self.trace.append({'type': 'NOTE', 'row': row_name, 'col': col_name, 'value': '0', 'msg': '未匹配'})
            return Decimal(0)
        except Exception as e:
            self.trace.append({'type': 'NOTE', 'row': row_name, 'error': str(e)})
            return Decimal(0)

    async def _exec_consol(self, args: list[str]) -> Decimal:
        """CONSOL('sheet_key','field') — 从合并工作底稿取值"""
        from sqlalchemy import text as sa_text
        sheet_key = args[0] if args else ''
        field_name = args[1] if len(args) > 1 else ''
        try:
            result = await self.db.execute(
                sa_text("SELECT data FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
                {"pid": str(self.project_id), "y": self.year, "sk": sheet_key},
            )
            row = result.fetchone()
            if row and isinstance(row[0], dict):
                data = row[0]
                # 支持 rows 数组中按字段名汇总
                if 'rows' in data and field_name:
                    total = Decimal(0)
                    for r in data['rows']:
                        v = r.get(field_name)
                        if v is not None:
                            try:
                                total += Decimal(str(v))
                            except (ValueError, TypeError):
                                pass
                    self.trace.append({'type': 'CONSOL', 'sheet': sheet_key, 'field': field_name, 'value': str(total)})
                    return total
            self.trace.append({'type': 'CONSOL', 'sheet': sheet_key, 'field': field_name, 'value': '0'})
            return Decimal(0)
        except Exception as e:
            self.trace.append({'type': 'CONSOL', 'sheet': sheet_key, 'error': str(e)})
            return Decimal(0)

    @staticmethod
    def _build_params(func_name: str, args: list[str]) -> dict:
        """将位置参数映射为命名参数"""
        if func_name == 'TB':
            return {'account_code': args[0] if args else '', 'column_name': args[1] if len(args) > 1 else '期末余额'}
        if func_name == 'WP':
            return {'wp_code': args[0] if args else '', 'cell_ref': args[1] if len(args) > 1 else ''}
        if func_name == 'AUX':
            return {
                'account_code': args[0] if args else '',
                'aux_type': args[1] if len(args) > 1 else '',
                'aux_name': args[2] if len(args) > 2 else '',
                'column_name': args[3] if len(args) > 3 else '期末余额',
            }
        if func_name == 'SUM_TB':
            return {'account_range': args[0] if args else '', 'column_name': args[1] if len(args) > 1 else '期末余额'}
        if func_name == 'PREV':
            return {'inner_type': args[0] if args else '', 'inner_params': {}}
        # 未知函数，传原始参数
        return {f'arg{i}': v for i, v in enumerate(args)}


# ─── 便捷函数 ────────────────────────────────────────────────────────────────

async def evaluate_formula(
    formula: str,
    db: AsyncSession,
    project_id: UUID,
    year: int,
    engine=None,
    row_values: dict[str, Decimal] | None = None,
) -> dict:
    """解析并执行公式，返回 { value, trace, error }"""
    try:
        ast = parse_formula(formula)
    except ParseError as e:
        return {'value': None, 'trace': [], 'error': f'解析错误: {e}'}

    evaluator = FormulaEvaluator(db, project_id, year, engine)
    if row_values:
        evaluator.set_row_values(row_values)

    try:
        value = await evaluator.evaluate(ast)
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
