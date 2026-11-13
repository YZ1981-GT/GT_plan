"""公式 AST 层：节点定义 + 词法分析 + 递归下降解析（从 ``formula_engine`` 拆出，纯函数无 DB）。

``formula_engine`` 原样再导出这里的全部名字，既有 ``from app.services.formula_engine import …`` 不受影响。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# 递归下降 AST 解析层（Task 3：从 formula_parse_utils 并入）
# ═══════════════════════════════════════════════════════════════════════════════
# AST 节点定义 + 词法分析 + 递归下降 Parser
# 对嵌套 PREV(TB(...)) / IF(TB>0, ROW, 0) 等比 regex 更严谨

# ─── AST 节点 ────────────────────────────────────────────────────────────────

@dataclass
class ASTNumber:
    """数字字面量"""
    value: Decimal


@dataclass
class ASTString:
    """字符串字面量"""
    value: str


@dataclass
class ASTFuncCall:
    """函数调用节点"""
    name: str
    args: list[Any]  # list of AST nodes


@dataclass
class ASTBinOp:
    """二元运算节点"""
    op: str  # +, -, *, /
    left: Any
    right: Any


@dataclass
class ASTUnary:
    """一元运算节点"""
    op: str  # -
    operand: Any


@dataclass
class ASTRowRef:
    """行引用节点：ROW('BS-002')"""
    row_code: str


@dataclass
class ASTRangeSum:
    """范围求和节点：SUM(CN-002:CN-010)"""
    start_code: str
    end_code: str


@dataclass
class ASTCompare:
    """比较运算节点（用于 IF 条件）"""
    op: str  # >, <, >=, <=, ==, !=
    left: Any
    right: Any


# ─── 词法分析 ────────────────────────────────────────────────────────────────

_AST_TOKEN_PATTERNS = [
    ('NUMBER',   r'\d+\.?\d*'),
    ('STRING',   r"'[^']*'"),
    ('DSTRING',  r'"[^"]*"'),  # spec: formula-management-deep-optimization P2-8 双引号字符串
    ('FUNC',     r'[A-Z_][A-Z_0-9]*(?=\s*\()'),
    ('IDENT',    r'[A-Za-z_][A-Za-z_0-9\-]*'),
    ('LPAREN',   r'\('),
    ('RPAREN',   r'\)'),
    ('COMMA',    r','),
    ('COLON',    r':'),
    ('GTE',      r'>='),
    ('LTE',      r'<='),
    ('NEQ',      r'!='),
    ('EQ',       r'=='),
    ('GT',       r'>'),
    ('LT',       r'<'),
    ('PLUS',     r'\+'),
    ('MINUS',    r'-'),
    ('STAR',     r'\*'),
    ('SLASH',    r'/'),
    ('WS',       r'\s+'),
]

_AST_TOKEN_RE = re.compile('|'.join(f'(?P<{name}>{pattern})' for name, pattern in _AST_TOKEN_PATTERNS))


@dataclass
class _Token:
    type: str
    value: str
    pos: int


def _tokenize(formula: str) -> list[_Token]:
    """词法分析：将公式字符串拆分为 token 列表。"""
    tokens: list[_Token] = []
    for m in _AST_TOKEN_RE.finditer(formula):
        kind = m.lastgroup
        if kind == 'WS':
            continue
        tokens.append(_Token(type=kind, value=m.group(), pos=m.start()))
    return tokens


# ─── 语法分析（递归下降） ─────────────────────────────────────────────────────

class FormulaParseError(Exception):
    """公式解析错误"""
    pass


class FormulaBlockedError(Exception):
    """公式含非白名单内容（未注册函数 / eval/exec / URL / 外链）——被拦截（P0-项2）。

    与 ``FormulaParseError``（结构坏=damaged）区分：blocked 是**结构合法但语义越权/未授权**。
    引擎据此把 ``FormulaResult.blocked`` 置 True（不静默返 0 冒充正常）。
    """
    pass


class _RecursiveDescentParser:
    """递归下降解析器：expression → comparison → term → factor → atom

    相比旧 regex token 替换，能正确处理：
    - 嵌套函数调用 PREV(TB('1002','期末余额'))
    - IF 条件中的比较运算 IF(TB('1002','期末余额')>0, ...)
    - 任意深度括号嵌套
    """

    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> _Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self, expected_type: str | None = None) -> _Token:
        tok = self.peek()
        if tok is None:
            raise FormulaParseError("Unexpected end of formula")
        if expected_type and tok.type != expected_type:
            raise FormulaParseError(
                f"Expected {expected_type}, got {tok.type} '{tok.value}' at pos {tok.pos}"
            )
        self.pos += 1
        return tok

    def parse(self) -> Any:
        result = self.comparison()
        if self.pos < len(self.tokens):
            tok = self.tokens[self.pos]
            raise FormulaParseError(f"Unexpected token '{tok.value}' at pos {tok.pos}")
        return result

    def comparison(self) -> Any:
        """comparison = expression (('>' | '<' | '>=' | '<=' | '==' | '!=') expression)?"""
        left = self.expression()
        if self.peek() and self.peek().type in ('GT', 'LT', 'GTE', 'LTE', 'EQ', 'NEQ'):
            op_tok = self.consume()
            right = self.expression()
            return ASTCompare(op=op_tok.value, left=left, right=right)
        return left

    def expression(self) -> Any:
        """expression = term (('+' | '-') term)*"""
        left = self.term()
        while self.peek() and self.peek().type in ('PLUS', 'MINUS'):
            op = self.consume().value
            right = self.term()
            left = ASTBinOp(op=op, left=left, right=right)
        return left

    def term(self) -> Any:
        """term = factor (('*' | '/') factor)*"""
        left = self.factor()
        while self.peek() and self.peek().type in ('STAR', 'SLASH'):
            op = self.consume().value
            right = self.factor()
            left = ASTBinOp(op=op, left=left, right=right)
        return left

    def factor(self) -> Any:
        """factor = ['-'] atom"""
        if self.peek() and self.peek().type == 'MINUS':
            self.consume()
            operand = self.atom()
            return ASTUnary(op='-', operand=operand)
        return self.atom()

    def atom(self) -> Any:
        """atom = NUMBER | STRING | func_call | '(' comparison ')' | IDENT"""
        tok = self.peek()
        if tok is None:
            raise FormulaParseError("Unexpected end of formula")

        if tok.type == 'NUMBER':
            self.consume()
            return ASTNumber(value=Decimal(tok.value))

        if tok.type == 'STRING':
            self.consume()
            return ASTString(value=tok.value.strip("'"))

        if tok.type == 'DSTRING':
            self.consume()
            return ASTString(value=tok.value.strip('"'))

        if tok.type == 'FUNC':
            return self._func_call()

        if tok.type == 'LPAREN':
            self.consume()
            expr = self.comparison()
            self.consume('RPAREN')
            return expr

        if tok.type == 'IDENT':
            self.consume()
            # 检查是否是范围引用 IDENT:IDENT（如 CN-002:CN-010）
            if self.peek() and self.peek().type == 'COLON':
                self.consume()
                end_tok = self.consume('IDENT')
                return ASTRangeSum(start_code=tok.value, end_code=end_tok.value)
            return ASTRowRef(row_code=tok.value)

        raise FormulaParseError(f"Unexpected token '{tok.value}' ({tok.type}) at pos {tok.pos}")

    def _func_call(self) -> Any:
        """func_call = FUNC '(' [arg (',' arg)*] ')'"""
        name_tok = self.consume('FUNC')
        self.consume('LPAREN')
        args: list[Any] = []
        if self.peek() and self.peek().type != 'RPAREN':
            args.append(self.comparison())
            while self.peek() and self.peek().type == 'COMMA':
                self.consume()
                args.append(self.comparison())
        self.consume('RPAREN')

        # 特殊处理 SUM(range)
        if name_tok.value == 'SUM' and len(args) == 1 and isinstance(args[0], ASTRangeSum):
            return args[0]

        # 特殊处理 ROW('code')
        if name_tok.value == 'ROW' and len(args) == 1 and isinstance(args[0], ASTString):
            return ASTRowRef(row_code=args[0].value)

        return ASTFuncCall(name=name_tok.value, args=args)


@lru_cache(maxsize=2048)
def parse_to_ast(formula: str) -> Any:
    """解析公式字符串为 AST（内核 parse 层入口）。

    解析结果可缓存（同公式不重复解析）。
    AST 节点构造后从不修改字段，可安全共享。
    """
    tokens = _tokenize(formula)
    if not tokens:
        raise FormulaParseError("Empty formula")
    parser = _RecursiveDescentParser(tokens)
    return parser.parse()
