"""统一公式引擎 — 企业级版本（L1 内核）

所有报表公式计算的唯一执行器。

设计原则：
- 纯函数，不依赖 async/db session
- 插件式函数注册（新增函数只需注册 handler）
- 返回 FormulaResult（含 value + errors + trace）
- 多列支持（TB 第二参数指定列名）
- 上年数据支持（PREV 函数）
- 公式解析缓存（同一公式不重复解析）

parse 层（Task 3 升级）：
- 递归下降 AST 解析（从 formula_parse_utils 并入）替换脆弱 regex token 替换
- 并行 diff 验证：新 AST 求值 vs 旧 regex 求值一致后才切换
- 保留 regex 路径一个版本周期作降级（_PARSE_MODE 控制）
- 对嵌套 PREV(TB(...)) / IF(TB>0, ROW, 0) 等更严谨

支持的函数：
- TB('1002','期末余额') — 单科目取值
- SUM_TB('1400~1499','期末余额') — 范围科目求和
- ROW('BS-002') — 引用其他行的值
- SUM_ROW('BS-002','BS-008') — 范围行次求和
- REPORT('BS-002','current') — 跨报表引用
- PREV('1002','期末余额') — 上年同期值
- AUX('1002','客户','期末余额') — 辅助核算取值
- ABS/ROUND/MAX/MIN/IF — 内置函数
"""

from __future__ import annotations

import ast
import logging
import operator
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any, Callable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Parse 模式控制（Task 3：递归下降替换 regex）
# ═══════════════════════════════════════════════════════════════════════════════
# "ast"   = 新递归下降 AST 求值（**生产默认**，并行 diff 验证已通过 + Decimal 全程精确）
# "regex" = 旧 regex token 替换（降级/调试路径，env-var 可切换）
# "parallel" = 并行跑两路径做 diff 对照（调试用，env-var 可切换）
_PARSE_MODE: str = os.environ.get("FORMULA_PARSE_MODE", "ast")


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类型定义
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FormulaResult:
    """公式执行结果"""
    value: Decimal = Decimal("0")
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)  # 取数轨迹（审计用）

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


@dataclass
class FormulaContext:
    """公式执行上下文（L2 编排层预载、传给 L1 内核的同步数据快照）。

    L1 内核纯函数所需的全部数据都在此对象内（无 DB/async 耦合）。各业务域由
    L2 编排层经 L3 AmountResolver 批量取数后填充对应字段，再调 ``execute``。
    """
    # 科目编码 → {列名: 金额}（试算表 TB / SUM_TB，支持多列取数）
    tb_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 行次编码 → 已计算值（供 ROW/SUM_ROW/REPORT 引用）
    row_cache: dict[str, Decimal] = field(default_factory=dict)
    # 上年科目数据（供 PREV 引用）
    prior_tb_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 附注数据源（供 NOTE 函数）：section_code → {field_name: 金额}
    note_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 底稿数据源（供 WP 函数）：wp_code → {column: 金额}
    wp_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 辅助核算数据源（供 AUX 函数）：account_code → {辅助项: 金额}
    aux_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 默认列名
    default_column: str = "期末余额"

    # ── 便捷构造方法 ──
    @classmethod
    def from_simple_map(
        cls,
        tb_map: dict[str, Decimal],
        row_cache: dict[str, Any] | None = None,
        prior_map: dict[str, Decimal] | None = None,
    ) -> "FormulaContext":
        """从简单的 科目→金额 字典构建上下文（向后兼容）"""
        tb_data = {code: {"期末余额": val, "审定数": val, "未审数": val} for code, val in tb_map.items()}
        prior_data = {}
        if prior_map:
            prior_data = {code: {"期末余额": val} for code, val in prior_map.items()}
        rc = {k: Decimal(str(v)) for k, v in (row_cache or {}).items()}
        return cls(tb_data=tb_data, row_cache=rc, prior_tb_data=prior_data)


# ── 列名映射（中文 → 标准字段名） ──
COLUMN_ALIASES: dict[str, str] = {
    "期末余额": "期末余额",
    "审定数": "期末余额",
    "年初余额": "年初余额",
    "期初余额": "年初余额",
    "未审数": "期末余额",
    "本期发生额": "本期发生额",
    "RJE调整": "RJE调整",
    "AJE调整": "AJE调整",
}


# ═══════════════════════════════════════════════════════════════════════════════
# AddressValidator Protocol（Task 17：validate_formula 接 address_registry）
# ═══════════════════════════════════════════════════════════════════════════════
# 同步 Protocol：L1 内核纯函数不依赖 async/DB，由 L2 编排层预载后注入。
# 实现方可以是 AddressRegistryService 的同步适配器（预载地址集合后传入）。


@runtime_checkable
class AddressValidator(Protocol):
    """地址有效性校验器 Protocol（需求 7.5）。

    validate_formula 可选注入：当提供时，校验公式中引用的科目编码/行次编码
    是否在当前项目地址注册表中存在；悬空引用产生 validation error。

    实现者只需提供 validate_codes 方法：
    - 输入：一组待校验的编码（account codes / row codes）
    - 输出：其中无效（不存在）的编码子集
    """

    def validate_codes(self, codes: set[str]) -> set[str]:
        """返回 codes 中无效（不存在于注册表）的编码子集。"""
        ...


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


def parse_to_ast(formula: str) -> Any:
    """解析公式字符串为 AST（内核 parse 层入口）。

    解析结果可缓存（同公式不重复解析）。
    """
    tokens = _tokenize(formula)
    if not tokens:
        raise FormulaParseError("Empty formula")
    parser = _RecursiveDescentParser(tokens)
    return parser.parse()


# ─── AST 求值（纯函数，基于 FormulaContext） ─────────────────────────────────

def _eval_ast(node: Any, ctx: FormulaContext, trace: list[str]) -> Decimal:
    """递归求值 AST 节点（纯函数，无 DB/async）。

    所有数据从 FormulaContext 取，与旧 regex 路径语义对齐。
    """
    if isinstance(node, ASTNumber):
        return node.value

    if isinstance(node, ASTString):
        # 字符串字面量尝试转 Decimal（兼容 formula_parser 行为）
        try:
            return Decimal(node.value)
        except (InvalidOperation, ValueError):
            return Decimal("0")

    if isinstance(node, ASTBinOp):
        left = _eval_ast(node.left, ctx, trace)
        right = _eval_ast(node.right, ctx, trace)
        if node.op == '+':
            return left + right
        elif node.op == '-':
            return left - right
        elif node.op == '*':
            return left * right
        elif node.op == '/':
            return left / right if right != 0 else Decimal("0")
        return Decimal("0")

    if isinstance(node, ASTUnary):
        operand = _eval_ast(node.operand, ctx, trace)
        return -operand if node.op == '-' else operand

    if isinstance(node, ASTCompare):
        left = _eval_ast(node.left, ctx, trace)
        right = _eval_ast(node.right, ctx, trace)
        op = node.op
        if op == '>':
            return Decimal("1") if left > right else Decimal("0")
        elif op == '<':
            return Decimal("1") if left < right else Decimal("0")
        elif op == '>=':
            return Decimal("1") if left >= right else Decimal("0")
        elif op == '<=':
            return Decimal("1") if left <= right else Decimal("0")
        elif op == '==':
            return Decimal("1") if left == right else Decimal("0")
        elif op == '!=':
            return Decimal("1") if left != right else Decimal("0")
        return Decimal("0")

    if isinstance(node, ASTRowRef):
        val = ctx.row_cache.get(node.row_code, Decimal("0"))
        trace.append(f"ROW('{node.row_code}') = {val}")
        return val

    if isinstance(node, ASTRangeSum):
        total = Decimal("0")
        for code, rv in ctx.row_cache.items():
            if node.start_code <= code <= node.end_code:
                total += rv
        trace.append(f"SUM({node.start_code}:{node.end_code}) = {total}")
        return total

    if isinstance(node, ASTFuncCall):
        return _eval_func_node(node, ctx, trace)

    logger.warning("Unknown AST node type in _eval_ast: %s", type(node))
    return Decimal("0")


def _eval_func_node(node: ASTFuncCall, ctx: FormulaContext, trace: list[str]) -> Decimal:
    """求值函数调用 AST 节点。

    优先从 FunctionRegistry 查找 handler（Task 4 插件式），
    未注册函数返回 0 并记录 trace。
    """
    name = node.name
    args = node.args

    # 从 registry 查找 handler
    handler = _REGISTRY.get(name)
    if handler is not None:
        return handler(args, ctx, trace)

    # 未注册函数 → 0
    trace.append(f"{name}(...) = 0 (unknown)")
    return Decimal("0")


def _extract_string_args(args: list[Any], ctx: FormulaContext, trace: list[str]) -> list[str]:
    """从 AST 参数列表中提取字符串值。"""
    str_args: list[str] = []
    for a in args:
        if isinstance(a, ASTString):
            str_args.append(a.value)
        elif isinstance(a, ASTNumber):
            str_args.append(str(a.value))
        elif isinstance(a, ASTRowRef):
            str_args.append(a.row_code)
        else:
            # 对复杂表达式求值后转字符串
            val = _eval_ast(a, ctx, trace)
            str_args.append(str(val))
    return str_args


# ═══════════════════════════════════════════════════════════════════════════════
# FunctionRegistry 插件式函数注册（Task 4）
# ═══════════════════════════════════════════════════════════════════════════════
# 所有 DSL 函数的单一注册表。新增函数 = 注册一个 handler，全域可用。
# handler 签名：(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal

# 函数 handler 签名
FunctionHandler = Callable[[list[Any], "FormulaContext", list[str]], Decimal]


class FunctionRegistry:
    """插件式函数注册表（需求 3.1 · 属性 Q1）。

    所有 DSL 函数（TB/SUM_TB/ROW/SUM_ROW/REPORT/PREV/AUX/NOTE/WP + ABS/ROUND/MAX/MIN/IF）
    的单一注册表。新增函数仅在此处 register 即全域可用。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, FunctionHandler] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        handler: FunctionHandler,
        *,
        arity: int | None = None,
        description: str = "",
        syntax: str = "",
        category: str = "",
    ) -> None:
        """注册/覆盖一个 DSL 函数。

        Args:
            name: 函数名（大写，如 'TB'）
            handler: 函数处理器，签名 (args, ctx, trace) -> Decimal
            arity: 参数个数（None=不限）
            description: 函数描述
            syntax: 语法示例
            category: 分类（取数/引用/数学/逻辑/自定义）
        """
        self._handlers[name] = handler
        self._metadata[name] = {
            "name": name,
            "arity": arity,
            "description": description,
            "syntax": syntax,
            "category": category,
        }

    def get(self, name: str) -> FunctionHandler | None:
        """获取函数 handler，不存在返回 None。"""
        return self._handlers.get(name)

    def known_function_names(self) -> set[str]:
        """返回所有已注册函数名集合（供 validate_formula 校验未知函数）。"""
        return set(self._handlers.keys())

    def list_all(self) -> list[dict]:
        """列出所有已注册函数信息（供 /formula router 展示）。"""
        return [dict(meta) for meta in self._metadata.values()]

    def unregister(self, name: str) -> bool:
        """注销函数，返回是否成功。"""
        if name in self._handlers:
            del self._handlers[name]
            del self._metadata[name]
            return True
        return False


# ─── 内置函数 handler 定义 ────────────────────────────────────────────────────

def _handle_abs(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """ABS(value) — 绝对值"""
    if len(args) >= 1:
        val = _eval_ast(args[0], ctx, trace)
        return abs(val)
    return Decimal("0")


def _handle_round(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """ROUND(value, ndigits) — 四舍五入"""
    if len(args) >= 1:
        val = _eval_ast(args[0], ctx, trace)
        ndigits = int(_eval_ast(args[1], ctx, trace)) if len(args) > 1 else 2
        return round(val, ndigits)
    return Decimal("0")


def _handle_max(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """MAX(a, b, ...) — 最大值"""
    if len(args) >= 2:
        vals = [_eval_ast(a, ctx, trace) for a in args]
        return max(vals)
    return Decimal("0")


def _handle_min(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """MIN(a, b, ...) — 最小值"""
    if len(args) >= 2:
        vals = [_eval_ast(a, ctx, trace) for a in args]
        return min(vals)
    return Decimal("0")


def _handle_if(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """IF(cond, true_val, false_val) — 条件判断"""
    if len(args) == 3:
        cond = _eval_ast(args[0], ctx, trace)
        return _eval_ast(args[1], ctx, trace) if cond != 0 else _eval_ast(args[2], ctx, trace)
    return Decimal("0")


def _handle_tb(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """TB('code','column') — 单科目取值"""
    str_args = _extract_string_args(args, ctx, trace)
    code = str_args[0] if str_args else ''
    col_name = str_args[1] if len(str_args) > 1 else ctx.default_column
    resolved_col = COLUMN_ALIASES.get(col_name, col_name)
    account_data = ctx.tb_data.get(code, {})
    val = account_data.get(resolved_col, account_data.get("期末余额", Decimal("0")))
    trace.append(f"TB('{code}','{col_name}') = {val}")
    return val


def _handle_sum_tb(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """SUM_TB('range','column') — 范围科目求和"""
    str_args = _extract_string_args(args, ctx, trace)
    code_range = str_args[0] if str_args else ''
    col_name = str_args[1] if len(str_args) > 1 else ctx.default_column
    val = Decimal("0")
    parts = code_range.split("~")
    if len(parts) == 2:
        start, end = parts[0], parts[1]
        prefix_len = len(start)
        for code, data in ctx.tb_data.items():
            code_prefix = code[:prefix_len]
            if start <= code_prefix <= end:
                val += data.get("期末余额", Decimal("0"))
    trace.append(f"SUM_TB('{code_range}') = {val}")
    return val


def _handle_row(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """ROW('code') — 引用其他行次"""
    str_args = _extract_string_args(args, ctx, trace)
    row_code = str_args[0] if str_args else ''
    val = ctx.row_cache.get(row_code, Decimal("0"))
    trace.append(f"ROW('{row_code}') = {val}")
    return val


def _handle_sum_row(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """SUM_ROW('start','end') — 范围行次求和"""
    str_args = _extract_string_args(args, ctx, trace)
    start_code = str_args[0] if str_args else ''
    end_code = str_args[1] if len(str_args) > 1 else ''
    val = Decimal("0")
    for code, rv in ctx.row_cache.items():
        if start_code <= code <= end_code:
            val += rv
    trace.append(f"SUM_ROW('{start_code}','{end_code}') = {val}")
    return val


def _handle_report(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """REPORT('row_code','period') — 跨报表引用"""
    str_args = _extract_string_args(args, ctx, trace)
    row_code = str_args[0] if str_args else ''
    val = ctx.row_cache.get(row_code, Decimal("0"))
    trace.append(f"REPORT('{row_code}') = {val}")
    return val


def _handle_prev(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """PREV('code','column') 或 PREV(TB('code','column')) — 上年同期值"""
    # PREV 可以嵌套：PREV(TB('1002','期末余额')) 或 PREV('1002','期末余额')
    if len(args) >= 1 and isinstance(args[0], ASTFuncCall):
        # 嵌套模式：PREV(TB('1002','期末余额')) → 从 prior_tb_data 取
        inner = args[0]
        if inner.name == "TB":
            inner_str_args = _extract_string_args(inner.args, ctx, trace)
            code = inner_str_args[0] if inner_str_args else ''
            col_name = inner_str_args[1] if len(inner_str_args) > 1 else ctx.default_column
            prior_data = ctx.prior_tb_data.get(code, {})
            val = prior_data.get("期末余额", Decimal("0"))
            trace.append(f"PREV(TB('{code}','{col_name}')) = {val}")
            return val
    # 简单模式：PREV('1002','期末余额')
    str_args = _extract_string_args(args, ctx, trace)
    code = str_args[0] if str_args else ''
    col_name = str_args[1] if len(str_args) > 1 else ctx.default_column
    prior_data = ctx.prior_tb_data.get(code, {})
    val = prior_data.get("期末余额", Decimal("0"))
    trace.append(f"PREV('{code}','{col_name}') = {val}")
    return val


def _handle_aux(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """AUX('account','dimension','column') — 辅助核算取值"""
    str_args = _extract_string_args(args, ctx, trace)
    account = str_args[0] if str_args else ''
    dimension = str_args[1] if len(str_args) > 1 else ''
    col_name = str_args[2] if len(str_args) > 2 else ctx.default_column
    account_data = ctx.aux_data.get(account, {})
    val = account_data.get(dimension, Decimal("0"))
    trace.append(f"AUX('{account}','{dimension}','{col_name}') = {val}")
    return val


def _handle_note(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """NOTE('section','field','column') — 附注数据取值"""
    str_args = _extract_string_args(args, ctx, trace)
    section = str_args[0] if str_args else ''
    field_name = str_args[1] if len(str_args) > 1 else ''
    col_name = str_args[2] if len(str_args) > 2 else ctx.default_column
    section_data = ctx.note_data.get(section, {})
    val = section_data.get(field_name, Decimal("0"))
    trace.append(f"NOTE('{section}','{field_name}','{col_name}') = {val}")
    return val


def _handle_wp(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """WP('wp_code','column') — 底稿数据取值"""
    str_args = _extract_string_args(args, ctx, trace)
    wp_code = str_args[0] if str_args else ''
    col_name = str_args[1] if len(str_args) > 1 else ctx.default_column
    wp_data = ctx.wp_data.get(wp_code, {})
    val = wp_data.get(col_name, Decimal("0"))
    trace.append(f"WP('{wp_code}','{col_name}') = {val}")
    return val


# ─── 全局 FunctionRegistry 实例 + 内置函数注册 ────────────────────────────────

_REGISTRY = FunctionRegistry()

# 取数函数
_REGISTRY.register("TB", _handle_tb, arity=2, description="取科目余额", syntax="TB('科目编码','列名')", category="取数")
_REGISTRY.register("SUM_TB", _handle_sum_tb, arity=2, description="范围科目求和", syntax="SUM_TB('起始~结束','列名')", category="取数")
_REGISTRY.register("PREV", _handle_prev, arity=2, description="上年同期值", syntax="PREV('科目编码','列名')", category="取数")
_REGISTRY.register("AUX", _handle_aux, arity=3, description="辅助核算取值", syntax="AUX('科目','维度','列名')", category="取数")
_REGISTRY.register("NOTE", _handle_note, arity=3, description="附注数据取值", syntax="NOTE('章节','字段','列名')", category="取数")
_REGISTRY.register("WP", _handle_wp, arity=2, description="底稿数据取值", syntax="WP('底稿编码','列名')", category="取数")

# 引用函数
_REGISTRY.register("ROW", _handle_row, arity=1, description="引用其他行次", syntax="ROW('行次编码')", category="引用")
_REGISTRY.register("SUM_ROW", _handle_sum_row, arity=2, description="范围行次求和", syntax="SUM_ROW('起始','结束')", category="引用")
_REGISTRY.register("REPORT", _handle_report, arity=2, description="跨报表引用", syntax="REPORT('行次编码','期间')", category="引用")

# 数学/逻辑函数
_REGISTRY.register("ABS", _handle_abs, arity=1, description="绝对值", syntax="ABS(值)", category="数学")
_REGISTRY.register("ROUND", _handle_round, arity=2, description="四舍五入", syntax="ROUND(值, 位数)", category="数学")
_REGISTRY.register("MAX", _handle_max, arity=2, description="最大值", syntax="MAX(值1, 值2)", category="数学")
_REGISTRY.register("MIN", _handle_min, arity=2, description="最小值", syntax="MIN(值1, 值2)", category="数学")
_REGISTRY.register("IF", _handle_if, arity=3, description="条件判断", syntax="IF(条件, 真值, 假值)", category="逻辑")


# ═══════════════════════════════════════════════════════════════════════════════
# 公式 Token 解析（Regex）
# ═══════════════════════════════════════════════════════════════════════════════

_TOKEN_PATTERNS = [
    ("SUM_ROW", re.compile(r"SUM_ROW\('([^']+)','([^']+)'\)")),
    ("SUM_TB", re.compile(r"SUM_TB\('([^']+)','([^']+)'\)")),
    ("TB", re.compile(r"TB\('([^']+)','([^']+)'\)")),
    ("ROW", re.compile(r"ROW\('([^']+)'\)")),
    ("REPORT", re.compile(r"REPORT\('([^']+)','([^']+)'\)")),
    ("PREV", re.compile(r"PREV\('([^']+)','([^']+)'\)")),
    ("AUX", re.compile(r"AUX\('([^']+)','([^']*?)','([^']+)'\)")),
    ("NOTE", re.compile(r"NOTE\('([^']+)','([^']+)','([^']+)'\)")),
    ("WP", re.compile(r"WP\('([^']+)','([^']+)'\)")),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 安全算术求值器
# ═══════════════════════════════════════════════════════════════════════════════

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_expr(expr: str) -> Decimal:
    """安全求值纯算术表达式（+−×÷ 括号 + 内置函数），基于 AST 解析。"""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return Decimal("0")

    def _eval_node(node: ast.expr) -> Decimal:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.BinOp):
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            op_func = _SAFE_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            if isinstance(node.op, ast.Div) and right == 0:
                return Decimal("0")
            return op_func(left, right)
        if isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand)
            op_func = _SAFE_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError("Unsupported unary operator")
            return op_func(operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            args = [_eval_node(a) for a in node.args]
            if fn == "ABS" and len(args) == 1:
                return abs(args[0])
            if fn == "ROUND" and len(args) >= 1:
                ndigits = int(args[1]) if len(args) > 1 else 2
                return round(args[0], ndigits)
            if fn == "MAX" and len(args) >= 2:
                return max(args)
            if fn == "MIN" and len(args) >= 2:
                return min(args)
            if fn == "IF" and len(args) == 3:
                return args[1] if args[0] != 0 else args[2]
            raise ValueError(f"Unsupported function: {fn}")
        if isinstance(node, ast.Compare):
            left = _eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = _eval_node(comparator)
                if isinstance(op, ast.Eq) and left != right: return Decimal("0")
                if isinstance(op, ast.NotEq) and left == right: return Decimal("0")
                if isinstance(op, ast.Gt) and not (left > right): return Decimal("0")
                if isinstance(op, ast.GtE) and not (left >= right): return Decimal("0")
                if isinstance(op, ast.Lt) and not (left < right): return Decimal("0")
                if isinstance(op, ast.LtE) and not (left <= right): return Decimal("0")
                left = right
            return Decimal("1")
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    try:
        return _eval_node(tree)
    except (ValueError, InvalidOperation, ZeroDivisionError, TypeError):
        return Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════════
# 核心执行函数
# ═══════════════════════════════════════════════════════════════════════════════

def execute_formula(
    formula: str | None,
    tb_map: dict[str, Decimal],
    row_cache: dict[str, Any],
    column: str = "期末余额",
) -> Decimal:
    """简易版执行（向后兼容）。返回 Decimal 值。"""
    ctx = FormulaContext.from_simple_map(tb_map, row_cache)
    result = execute(formula, ctx)
    return result.value


def execute(formula: str | None, ctx: FormulaContext) -> FormulaResult:
    """L1 内核唯一求值入口（Single Kernel Entry Point）。

    契约（需求 3.3/3.4 · 属性 Q2）：
      - 纯函数：同 formula + 同 ctx → 同 FormulaResult（确定性，可单测可缓存）。
      - 无 DB/async 耦合：所有取数由 L2 编排层预载进 ctx，本函数只做求值。
      - 返回 FormulaResult（含 value + errors + warnings + trace）。

    parse 层（Task 3）：
      - _PARSE_MODE="ast"      → 纯递归下降 AST 求值
      - _PARSE_MODE="regex"    → 旧 regex token 替换（降级路径）
      - _PARSE_MODE="parallel" → 并行跑两路径，diff 一致用 AST 结果，不一致 warn 回退 regex
    """
    result = FormulaResult()

    if not formula or not formula.strip():
        return result

    mode = _PARSE_MODE

    if mode == "regex":
        return _execute_regex(formula, ctx)
    elif mode == "ast":
        return _execute_ast(formula, ctx)
    else:
        # parallel 模式：并行跑 diff，一致后用 AST 结果
        return _execute_parallel(formula, ctx)


def _execute_ast(formula: str, ctx: FormulaContext) -> FormulaResult:
    """新 AST 递归下降求值路径。"""
    result = FormulaResult()
    try:
        ast_node = parse_to_ast(formula)
        result.value = _eval_ast(ast_node, ctx, result.trace)
    except FormulaParseError as e:
        result.errors.append(f"AST 解析失败: {e}")
        logger.warning("AST parse error: %s (formula=%s)", e, formula)
    except Exception as e:
        result.errors.append(f"AST 求值失败: {e}")
        logger.warning("AST eval error: %s (formula=%s)", e, formula)
    # PREV 无上年数据 warning（与旧路径一致）
    if "PREV" in formula:
        _check_prev_warnings(formula, ctx, result)
    return result


def _execute_regex(formula: str, ctx: FormulaContext) -> FormulaResult:
    """旧 regex token 替换求值路径（保留一个版本周期作降级）。"""
    result = FormulaResult()
    expression = formula
    col = ctx.default_column

    # ── 逐 token 替换 ──
    for token_name, pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(formula):
            val = Decimal("0")
            trace_msg = ""

            if token_name == "TB":
                code, col_name = match.group(1), match.group(2)
                resolved_col = COLUMN_ALIASES.get(col_name, col_name)
                account_data = ctx.tb_data.get(code, {})
                val = account_data.get(resolved_col, account_data.get("期末余额", Decimal("0")))
                trace_msg = f"TB('{code}','{col_name}') = {val}"

            elif token_name == "SUM_TB":
                code_range, col_name = match.group(1), match.group(2)
                parts = code_range.split("~")
                if len(parts) == 2:
                    start, end = parts[0], parts[1]
                    prefix_len = len(start)
                    for code, data in ctx.tb_data.items():
                        code_prefix = code[:prefix_len]
                        if start <= code_prefix <= end:
                            val += data.get("期末余额", Decimal("0"))
                trace_msg = f"SUM_TB('{code_range}') = {val}"

            elif token_name == "ROW":
                row_code = match.group(1)
                val = ctx.row_cache.get(row_code, Decimal("0"))
                trace_msg = f"ROW('{row_code}') = {val}"

            elif token_name == "SUM_ROW":
                start_code, end_code = match.group(1), match.group(2)
                for code, rv in ctx.row_cache.items():
                    if start_code <= code <= end_code:
                        val += rv
                trace_msg = f"SUM_ROW('{start_code}','{end_code}') = {val}"

            elif token_name == "REPORT":
                row_code = match.group(1)
                val = ctx.row_cache.get(row_code, Decimal("0"))
                trace_msg = f"REPORT('{row_code}') = {val}"

            elif token_name == "PREV":
                code, col_name = match.group(1), match.group(2)
                prior_data = ctx.prior_tb_data.get(code, {})
                val = prior_data.get("期末余额", Decimal("0"))
                if val == 0:
                    result.warnings.append(f"PREV('{code}'): 无上年数据")
                trace_msg = f"PREV('{code}','{col_name}') = {val}"

            elif token_name in ("AUX", "NOTE", "WP"):
                if token_name == "AUX":
                    account = match.group(1)
                    dimension = match.group(2)
                    account_data = ctx.aux_data.get(account, {})
                    val = account_data.get(dimension, Decimal("0"))
                    trace_msg = f"AUX('{account}','{dimension}') = {val}"
                elif token_name == "NOTE":
                    section = match.group(1)
                    field_name = match.group(2)
                    section_data = ctx.note_data.get(section, {})
                    val = section_data.get(field_name, Decimal("0"))
                    trace_msg = f"NOTE('{section}','{field_name}') = {val}"
                elif token_name == "WP":
                    wp_code = match.group(1)
                    col_name = match.group(2)
                    wp_data = ctx.wp_data.get(wp_code, {})
                    val = wp_data.get(col_name, Decimal("0"))
                    trace_msg = f"WP('{wp_code}','{col_name}') = {val}"

            expression = expression.replace(match.group(0), str(val), 1)
            if trace_msg:
                result.trace.append(trace_msg)

    # ── 安全求值 ──
    try:
        result.value = safe_eval_expr(expression)
    except Exception as e:
        result.errors.append(f"算术求值失败: {e} (expr={expression})")
        logger.warning("Formula eval error: %s (expr=%s, formula=%s)", e, expression, formula)

    return result


def _execute_parallel(formula: str, ctx: FormulaContext) -> FormulaResult:
    """并行模式：同时跑 AST 和 regex 两路径，diff 一致用 AST 结果，不一致 warn 回退 regex。

    需求 2.3：并行跑 diff（新 AST 求值 vs 旧 regex 求值）一致后才切换。
    """
    regex_result = _execute_regex(formula, ctx)
    ast_result = _execute_ast(formula, ctx)

    # 如果 AST 解析/求值失败，直接回退 regex
    if not ast_result.ok:
        regex_result.warnings.append(
            f"[parallel] AST 路径失败({ast_result.errors[0] if ast_result.errors else '?'})，回退 regex"
        )
        return regex_result

    # diff 比较：value 逐位一致
    if ast_result.value == regex_result.value:
        # 一致 → 使用 AST 结果（更严谨的解析）
        return ast_result
    else:
        # 不一致 → warn 并回退 regex 结果
        diff_msg = (
            f"[parallel] AST={ast_result.value} vs regex={regex_result.value}，回退 regex"
        )
        logger.warning("Parse diff: %s (formula=%s)", diff_msg, formula)
        regex_result.warnings.append(diff_msg)
        return regex_result


def _check_prev_warnings(formula: str, ctx: FormulaContext, result: FormulaResult):
    """检查 PREV 函数是否有上年数据缺失的 warning。"""
    import re as _re
    for m in _re.finditer(r"PREV\('([^']+)'", formula):
        code = m.group(1)
        prior_data = ctx.prior_tb_data.get(code, {})
        if prior_data.get("期末余额", Decimal("0")) == 0:
            warning = f"PREV('{code}'): 无上年数据"
            if warning not in result.warnings:
                result.warnings.append(warning)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_formula_account_codes(formula: str | None) -> set[str]:
    """从公式中提取所有涉及的科目编码（用于汇总调整分录）。"""
    if not formula:
        return set()
    codes: set[str] = set()
    tb_pattern = _TOKEN_PATTERNS[2][1]  # TB pattern
    sum_tb_pattern = _TOKEN_PATTERNS[1][1]  # SUM_TB pattern
    for match in tb_pattern.finditer(formula):
        codes.add(match.group(1))
    for match in sum_tb_pattern.finditer(formula):
        code_range = match.group(1)
        parts = code_range.split("~")
        if len(parts) == 2:
            codes.add(f"__range__{parts[0]}~{parts[1]}")
    return codes


def validate_formula(formula: str, address_validator: AddressValidator | None = None) -> list[str]:
    """校验公式语法，返回错误列表（空=合法）。

    使用 FunctionRegistry.known_function_names 校验未知函数（Task 4）。
    当提供 address_validator 时，额外校验公式中引用的科目编码/行次编码
    是否存在于地址注册表（Task 17，需求 7.5：悬空引用即拒）。
    """
    if not formula or not formula.strip():
        return []
    errors = []
    # 检查括号匹配
    depth = 0
    for ch in formula:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if depth < 0:
            errors.append("括号不匹配：多余的右括号")
            break
    if depth > 0:
        errors.append("括号不匹配：缺少右括号")
    # 检查是否有未识别的函数（从 registry 获取已知函数名）
    import re as _re
    unknown = _re.findall(r"([A-Z_]+)\(", formula)
    known_funcs = _REGISTRY.known_function_names()
    for fn in unknown:
        if fn not in known_funcs:
            errors.append(f"未知函数: {fn}()")

    # ── 地址有效性校验（Task 17：address_validator 注入时启用） ──
    if address_validator is not None:
        codes = _extract_formula_codes(formula)
        if codes:
            invalid_codes = address_validator.validate_codes(codes)
            for code in sorted(invalid_codes):
                errors.append(f"悬空引用: '{code}' 在地址注册表中不存在")

    return errors


def _extract_formula_codes(formula: str) -> set[str]:
    """从公式中提取所有引用的编码（科目编码 + 行次编码）。

    用于 validate_formula 的地址有效性校验（Task 17）。
    提取范围：
    - TB('code', ...) → account code
    - SUM_TB('start~end', ...) → range start/end codes
    - ROW('code') → row code
    - SUM_ROW('start','end') → row codes
    - REPORT('code', ...) → row code
    - PREV('code', ...) → account code
    - AUX('code', ...) → account code
    - NOTE('section', ...) → section code
    - WP('code', ...) → wp code
    """
    import re as _re
    codes: set[str] = set()

    # TB / PREV — 科目编码（排除 SUM_TB 的匹配）
    for m in _re.finditer(r"(?<!SUM_)TB\(\s*'([^']+)'", formula):
        codes.add(m.group(1))
    for m in _re.finditer(r"PREV\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # SUM_TB — 范围编码（拆 start~end 为两个编码）
    for m in _re.finditer(r"SUM_TB\(\s*'([^']+)'", formula):
        range_str = m.group(1)
        parts = range_str.split("~")
        if len(parts) == 2:
            codes.add(parts[0])
            codes.add(parts[1])
        else:
            codes.add(range_str)

    # ROW — 行次编码（排除 SUM_ROW 的匹配）
    for m in _re.finditer(r"(?<!SUM_)ROW\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # SUM_ROW — 范围行次编码
    for m in _re.finditer(r"SUM_ROW\(\s*'([^']+)'\s*,\s*'([^']+)'", formula):
        codes.add(m.group(1))
        codes.add(m.group(2))

    # REPORT — 行次编码
    for m in _re.finditer(r"REPORT\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # AUX — 科目编码
    for m in _re.finditer(r"AUX\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # NOTE — 章节编码
    for m in _re.finditer(r"NOTE\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # WP — 底稿编码
    for m in _re.finditer(r"WP\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    return codes


# ═══════════════════════════════════════════════════════════════════════════════
# FormulaEngine 类（向后兼容 formula.py 路由）
# ═══════════════════════════════════════════════════════════════════════════════

class FormulaEngine:
    """公式引擎类（兼容旧 API 路由）。

    旧路由 formula.py 需要一个带 redis_client 的类实例，
    提供 execute/list_all_functions/register_custom_function 等方法。
    """

    # 内置函数列表
    _BUILTIN_FUNCTIONS = [
        {"name": "TB", "description": "取科目余额", "syntax": "TB('科目编码','列名')", "category": "取数"},
        {"name": "SUM_TB", "description": "范围科目求和", "syntax": "SUM_TB('起始~结束','列名')", "category": "取数"},
        {"name": "ROW", "description": "引用其他行次", "syntax": "ROW('行次编码')", "category": "引用"},
        {"name": "SUM_ROW", "description": "范围行次求和", "syntax": "SUM_ROW('起始','结束')", "category": "引用"},
        {"name": "PREV", "description": "上年同期值", "syntax": "PREV('科目编码','列名')", "category": "取数"},
        {"name": "REPORT", "description": "跨报表引用", "syntax": "REPORT('行次编码','期间')", "category": "引用"},
        {"name": "AUX", "description": "辅助核算取值", "syntax": "AUX('科目','维度','列名')", "category": "取数"},
        {"name": "ABS", "description": "绝对值", "syntax": "ABS(值)", "category": "数学"},
        {"name": "ROUND", "description": "四舍五入", "syntax": "ROUND(值, 位数)", "category": "数学"},
        {"name": "MAX", "description": "最大值", "syntax": "MAX(值1, 值2)", "category": "数学"},
        {"name": "MIN", "description": "最小值", "syntax": "MIN(值1, 值2)", "category": "数学"},
        {"name": "IF", "description": "条件判断", "syntax": "IF(条件, 真值, 假值)", "category": "逻辑"},
    ]

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._custom_functions: dict[str, dict] = {}

    def list_all_functions(self) -> list[dict]:
        """列出所有可用函数（从 FunctionRegistry 获取，含内置 + 自定义）"""
        return _REGISTRY.list_all()

    def list_custom_functions(self) -> list[dict]:
        """列出自定义函数"""
        return [{"name": k, **v} for k, v in self._custom_functions.items()]

    def register_custom_function(self, name: str, description: str = "", syntax: str = "", formula: str = "", expression: str = "") -> dict:
        """注册自定义函数（底层委托 FunctionRegistry.register，Task 4）。"""
        if not name or not name.strip():
            raise ValueError("函数名不能为空")
        # 检查是否与内置函数冲突
        builtin_names = {f["name"] for f in self._BUILTIN_FUNCTIONS}
        if name in builtin_names:
            raise ValueError(f"内置函数 {name} 不可覆盖")
        # 校验表达式
        expr = expression or formula
        if expr and not _validate_custom_expression(expr):
            raise ValueError(f"表达式语法不合法: {expr}")
        # 保存到实例级自定义函数列表（向后兼容 list_custom_functions）
        self._custom_functions[name] = {
            "description": description,
            "syntax": syntax,
            "formula": expr,
            "expression": expr,
        }
        # 委托 FunctionRegistry 注册 handler（使自定义函数在 execute 中可用）
        def _custom_handler(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
            """自定义函数 handler：对表达式求值。"""
            if not expr:
                return Decimal("0")
            # 自定义函数的表达式中可能引用参数，简单实现：直接求值表达式
            custom_result = execute(expr, ctx)
            trace.append(f"{name}(...) = {custom_result.value} (custom)")
            return custom_result.value

        _REGISTRY.register(name, _custom_handler, description=description, syntax=syntax, category="自定义")
        return {"registered": True, "name": name}

    def unregister_custom_function(self, name: str) -> bool:
        """注销自定义函数（同步从 FunctionRegistry 移除）"""
        removed = self._custom_functions.pop(name, None) is not None
        if removed:
            _REGISTRY.unregister(name)
        return removed

    async def invalidate_cache(self, project_id=None, year=None, account_codes=None):
        """清除公式缓存（Redis）"""
        if not self.redis:
            return
        try:
            # 简单实现：删除项目相关的缓存键
            pattern = f"formula:*:{project_id}:*" if project_id else "formula:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self.redis.delete(*keys)
        except Exception:
            pass  # Redis 不可用时静默

    async def execute(self, db, project_id, year, formula_type: str, params: dict, **kwargs) -> dict:
        """执行公式（兼容旧 API）"""
        from decimal import Decimal
        # 简单实现：构建 tb_map 并调用统一引擎
        formula_str = params.get("formula", "")
        if not formula_str:
            return {"value": 0, "formula": "", "error": None}

        # 从 trial_balance 加载数据
        import sqlalchemy as sa
        from app.models.audit_platform_models import TrialBalance
        tb_table = TrialBalance.__table__
        q = sa.select(tb_table.c.standard_account_code, tb_table.c.unadjusted_amount).where(
            tb_table.c.project_id == project_id,
            tb_table.c.year == year,
            tb_table.c.is_deleted == sa.false(),
        )
        result = await db.execute(q)
        tb_map: dict[str, Decimal] = {}
        for r in result.fetchall():
            if r.standard_account_code:
                tb_map[r.standard_account_code] = tb_map.get(r.standard_account_code, Decimal("0")) + (r.unadjusted_amount or Decimal("0"))

        val = execute_formula(formula_str, tb_map, {})
        return {"value": float(val), "formula": formula_str, "error": None}

    async def batch_execute(self, db, project_id, year, formulas: list[dict], **kwargs) -> list[dict]:
        """批量执行公式"""
        results = []
        for f in formulas:
            r = await self.execute(db, project_id, year, f.get("formula_type", ""), f.get("params", {}))
            results.append(r)
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容导出（旧测试和旧模块依赖的名称）
# ═══════════════════════════════════════════════════════════════════════════════

class FormulaError(Exception):
    """公式执行错误"""
    pass


# parse 层公开 API（Task 3 新增）
__all__ = [
    "FormulaResult", "FormulaContext", "execute", "execute_formula",
    "validate_formula", "safe_eval_expr", "get_formula_account_codes",
    "FormulaEngine", "FormulaError",
    # Task 3: parse 层
    "parse_to_ast", "FormulaParseError", "_PARSE_MODE",
    "ASTNumber", "ASTString", "ASTFuncCall", "ASTBinOp", "ASTUnary",
    "ASTRowRef", "ASTRangeSum", "ASTCompare",
    # Task 4: FunctionRegistry
    "FunctionRegistry", "FunctionHandler", "_REGISTRY",
    # Task 17: AddressValidator Protocol
    "AddressValidator", "_extract_formula_codes",
]


# 旧测试引用的 Executor 类（占位，实际逻辑在 execute 函数中）
class TBExecutor:
    """TB 函数执行器（兼容占位）"""
    pass


class SumTBExecutor:
    """SUM_TB 函数执行器（兼容占位）"""
    pass


class PREVExecutor:
    """PREV 函数执行器（兼容占位）"""
    pass


class WPExecutor:
    """WP 函数执行器：从底稿 parsed_data 取数

    语法: WP('E1','审定数')
    从 WorkingPaper 的 parsed_data 中按 wp_code 和列名取数。

    Requirements: 39.1
    """

    @staticmethod
    async def execute(db, project_id, wp_code: str, column: str = "审定数"):
        """Fetch value from workpaper parsed_data."""
        from decimal import Decimal as D

        try:
            from app.models.workpaper_models import WorkingPaper, WpIndex

            result = await db.execute(
                sa.select(WorkingPaper.parsed_data)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(
                    WorkingPaper.project_id == project_id,
                    WpIndex.wp_code == wp_code,
                    WorkingPaper.is_deleted == sa.false(),
                )
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return D("0")

            parsed_data = row or {}
            col_map = {
                "审定数": "audited_amount",
                "未审数": "unadjusted_amount",
                "期初余额": "opening_balance",
                "期末余额": "audited_amount",
            }
            key = col_map.get(column, column)
            value = parsed_data.get(key, 0)
            return D(str(value)) if value is not None else D("0")
        except Exception:
            return D("0")


class REPORTExecutor:
    """REPORT 函数执行器：从 financial_report 取数

    语法: REPORT('BS','BS-001')
    从已生成的报表数据中按报表类型和行次编码取数。

    Requirements: 39.1
    """

    @staticmethod
    async def execute(db, project_id, year: int, report_type: str, row_code: str):
        """Fetch value from financial_report."""
        from decimal import Decimal as D

        try:
            result = await db.execute(
                sa.text("""
                    SELECT current_period_amount
                    FROM financial_report
                    WHERE project_id = :pid
                      AND year = :year
                      AND report_type = :rtype
                      AND row_code = :rcode
                      AND is_deleted = false
                    LIMIT 1
                """),
                {
                    "pid": str(project_id),
                    "year": year,
                    "rtype": report_type,
                    "rcode": row_code,
                },
            )
            row = result.fetchone()
            if row and row[0] is not None:
                return D(str(row[0]))
            return D("0")
        except Exception:
            return D("0")


class NOTEExecutor:
    """NOTE 函数执行器：从其他附注章节取数（交叉引用）

    语法: NOTE('五、（一）1','合计')
    从已生成的附注数据中按章节编码取数。

    Requirements: 39.1
    """

    @staticmethod
    async def execute(db, project_id, year: int, section_code: str, field_name: str = "合计"):
        """Fetch value from another note section (cross-reference)."""
        from decimal import Decimal as D

        try:
            result = await db.execute(
                sa.text("""
                    SELECT table_data
                    FROM disclosure_notes
                    WHERE project_id = :pid
                      AND year = :year
                      AND note_section = :section
                      AND is_deleted = false
                    LIMIT 1
                """),
                {
                    "pid": str(project_id),
                    "year": year,
                    "section": section_code,
                },
            )
            row = result.fetchone()
            if row and row[0]:
                table_data = row[0]
                rows = table_data.get("rows", []) if isinstance(table_data, dict) else []
                for r in rows:
                    if isinstance(r, dict) and r.get("is_total"):
                        values = r.get("values", [])
                        if values and values[0] is not None:
                            return D(str(values[0]))
                if rows:
                    last_row = rows[-1]
                    if isinstance(last_row, dict):
                        values = last_row.get("values", [])
                        if values and values[0] is not None:
                            return D(str(values[0]))
            return D("0")
        except Exception:
            return D("0")


def _validate_custom_expression(expression: str) -> bool:
    """校验自定义公式表达式是否安全合法。

    规则：
    - 不能为空
    - 不能包含 import/exec/eval/__/open 等危险关键字
    - 必须能被 ast.parse 解析
    """
    if not expression or not expression.strip():
        return False
    dangerous = ['import ', 'exec(', 'eval(', '__', 'open(', 'os.', 'sys.', 'subprocess']
    for d in dangerous:
        if d in expression:
            return False
    # 先替换公式函数为数字占位符再验证语法
    import re
    cleaned = re.sub(r"[A-Z_]+\([^)]*\)", "0", expression)
    try:
        ast.parse(cleaned, mode="eval")
        return True
    except SyntaxError:
        return False
