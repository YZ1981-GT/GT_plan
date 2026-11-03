"""税审底稿公式引擎：按 Excel 口径解析、求值样表里的公式。

只覆盖样表实际用到的语法与函数（SUM / IF / IFERROR / MIN / MAX / SUMIF / AND / OR /
ISNUMBER / ABS / ROUND / LEFT / COUNTA 等，见 ``FUNCTIONS``）；用到未支持的函数时
结果为 ``#NAME?``，由测试保证模型里的函数全部受支持。

- 解析：openpyxl Tokenizer 分词 → 递归下降生成元组 AST。
- 值：``Decimal`` / ``str`` / ``bool`` / ``None``（空格）/ ``XlError``。
- 求值上下文只需实现 ``cell(sheet, row, col)``；区域按行列逐格取。
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation
from typing import Any, Callable, Protocol

from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string


class XlError(str):
    """Excel 错误值（#DIV/0! 等）；是 str 的子类，便于序列化。"""


DIV0 = XlError("#DIV/0!")
VALUE = XlError("#VALUE!")
REF = XlError("#REF!")
NAME = XlError("#NAME?")
NUM = XlError("#NUM!")
NA = XlError("#N/A")
CIRC = XlError("#CIRC!")
_ERRORS = {e: e for e in (DIV0, VALUE, REF, NAME, NUM, NA, XlError("#NULL!"))}

Value = Any  # Decimal | str | bool | None | XlError
Node = tuple


class FormulaSyntaxError(ValueError):
    pass


class Context(Protocol):
    def cell(self, sheet: str, row: int, col: int) -> Value: ...


# ───────────────────────────── 解析 ─────────────────────────────

_SHEET_RE = re.compile(r"^(?:'((?:[^']|'')+)'|([^'!]+))!(.+)$")
_EXTERNAL_RE = re.compile(r"\[\d+\]")
_BINARY_PRECEDENCE = {
    "=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1,
    "&": 2,
    "+": 3, "-": 3,
    "*": 4, "/": 4,
    "^": 5,
}


def _parse_ref(text: str, current_sheet: str) -> Node:
    """单元格 / 区域引用 → ('ref', sheet, r1, c1, r2, c2)。外部簿前缀 [1] 按本簿处理。"""
    text = _EXTERNAL_RE.sub("", text)
    sheet = current_sheet
    m = _SHEET_RE.match(text)
    if m:
        sheet = (m.group(1).replace("''", "'") if m.group(1) is not None else m.group(2))
        text = m.group(3)
    parts = text.replace("$", "").split(":")
    if len(parts) > 2:
        return ("err", REF)
    try:
        coords = []
        for p in parts:
            col_letters, row = coordinate_from_string(p)
            coords.append((row, column_index_from_string(col_letters)))
    except ValueError:
        return ("err", NAME)  # 命名区域 / 整列引用：样表未用到
    (r1, c1), (r2, c2) = coords[0], coords[-1]
    return ("ref", sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))


class _Parser:
    def __init__(self, tokens: list[Token], sheet: str) -> None:
        self.tokens = tokens
        self.pos = 0
        self.sheet = sheet

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> Token:
        tok = self.peek()
        if tok is None:
            raise FormulaSyntaxError("公式意外结束")
        self.pos += 1
        return tok

    def expression(self, min_prec: int = 1) -> Node:
        left = self.unary()
        while True:
            tok = self.peek()
            if tok is None or tok.type != Token.OP_IN or tok.value not in _BINARY_PRECEDENCE:
                break
            prec = _BINARY_PRECEDENCE[tok.value]
            if prec < min_prec:
                break
            self.take()
            # ^ 在 Excel 里左结合，其余也左结合
            right = self.expression(prec + 1)
            left = ("bin", tok.value, left, right)
        return left

    def unary(self) -> Node:
        tok = self.peek()
        if tok is not None and tok.type == Token.OP_PRE:
            self.take()
            operand = self.unary()
            return ("neg", operand) if tok.value == "-" else operand
        return self.postfix(self.primary())

    def postfix(self, node: Node) -> Node:
        while (tok := self.peek()) is not None and tok.type == Token.OP_POST and tok.value == "%":
            self.take()
            node = ("pct", node)
        return node

    def primary(self) -> Node:
        tok = self.take()
        if tok.type == Token.OPERAND:
            if tok.subtype == Token.NUMBER:
                return ("num", Decimal(tok.value))
            if tok.subtype == Token.TEXT:
                return ("str", tok.value[1:-1].replace('""', '"'))
            if tok.subtype == Token.LOGICAL:
                return ("bool", tok.value.upper() == "TRUE")
            if tok.subtype == Token.ERROR:
                return ("err", _ERRORS.get(tok.value.upper(), XlError(tok.value.upper())))
            return _parse_ref(tok.value, self.sheet)
        if tok.type == Token.FUNC and tok.subtype == Token.OPEN:
            return self.call(tok.value[:-1].upper())
        if tok.type == Token.PAREN and tok.subtype == Token.OPEN:
            node = self.expression()
            close = self.take()
            if close.type != Token.PAREN:
                raise FormulaSyntaxError("括号不匹配")
            return node
        raise FormulaSyntaxError(f"无法识别的记号 {tok.value!r}")

    def call(self, name: str) -> Node:
        args: list[Node] = []
        tok = self.peek()
        if tok is not None and tok.type == Token.FUNC and tok.subtype == Token.CLOSE:
            self.take()
            return ("call", name, args)
        while True:
            tok = self.peek()
            if tok is not None and (tok.type == Token.SEP or (tok.type == Token.FUNC and tok.subtype == Token.CLOSE)):
                args.append(("empty",))
            else:
                args.append(self.expression())
            tok = self.take()
            if tok.type == Token.FUNC and tok.subtype == Token.CLOSE:
                return ("call", name, args)
            if tok.type != Token.SEP:
                raise FormulaSyntaxError(f"函数 {name} 参数之后出现 {tok.value!r}")


def parse_formula(formula: str, sheet: str) -> Node:
    """'=A1+B1' → AST。语法错误抛 FormulaSyntaxError。"""
    text = formula if formula.startswith("=") else "=" + formula
    tokens = [t for t in Tokenizer(text).items if t.type != Token.WSPACE]
    if not tokens:
        return ("empty",)
    parser = _Parser(tokens, sheet)
    node = parser.expression()
    if parser.peek() is not None:
        raise FormulaSyntaxError(f"多余的记号 {parser.peek().value!r}")
    return node


def iter_refs(node: Node):
    """遍历 AST 里的全部引用 ('ref', sheet, r1, c1, r2, c2)。"""
    kind = node[0]
    if kind == "ref":
        yield node
    elif kind in ("neg", "pct"):
        yield from iter_refs(node[1])
    elif kind == "bin":
        yield from iter_refs(node[2])
        yield from iter_refs(node[3])
    elif kind == "call":
        for arg in node[2]:
            yield from iter_refs(arg)


def iter_functions(node: Node):
    kind = node[0]
    if kind == "call":
        yield node[1]
        for arg in node[2]:
            yield from iter_functions(arg)
    elif kind in ("neg", "pct"):
        yield from iter_functions(node[1])
    elif kind == "bin":
        yield from iter_functions(node[2])
        yield from iter_functions(node[3])


# ───────────────────────────── 值转换 ─────────────────────────────

def is_error(v: Value) -> bool:
    return isinstance(v, XlError)


def to_number(v: Value) -> Value:
    if v is None:
        return Decimal(0)
    if isinstance(v, XlError):
        return v
    if isinstance(v, bool):
        return Decimal(int(v))
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    text = str(v).strip()
    if not text:
        return VALUE
    try:
        return Decimal(text)
    except InvalidOperation:
        return VALUE


def number_text(d: Decimal) -> str:
    """Decimal → Excel 风格文本（无科学计数、无多余尾零）。"""
    if d == d.to_integral_value():
        return str(d.quantize(Decimal(1)))
    return format(d.normalize(), "f")


def to_text(v: Value) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, Decimal):
        return number_text(v)
    return str(v)


def to_bool(v: Value) -> Value:
    if v is None:
        return False
    if isinstance(v, XlError) or isinstance(v, bool):
        return v
    if isinstance(v, Decimal):
        return v != 0
    text = str(v).strip().upper()
    if text in ("TRUE", "FALSE"):
        return text == "TRUE"
    return VALUE


def _type_rank(v: Value) -> int:
    if isinstance(v, bool):
        return 2
    if isinstance(v, str):
        return 1
    return 0


def compare(op: str, a: Value, b: Value) -> Value:
    if is_error(a):
        return a
    if is_error(b):
        return b
    if a is None:
        a = "" if isinstance(b, str) else (False if isinstance(b, bool) else Decimal(0))
    if b is None:
        b = "" if isinstance(a, str) else (False if isinstance(a, bool) else Decimal(0))
    ra, rb = _type_rank(a), _type_rank(b)
    if ra != rb:
        x, y = ra, rb
    elif isinstance(a, str):
        x, y = a.lower(), b.lower()
    else:
        x, y = a, b
    return {
        "=": x == y, "<>": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y,
    }[op]


def _arith(op: str, a: Value, b: Value) -> Value:
    a, b = to_number(a), to_number(b)
    if is_error(a):
        return a
    if is_error(b):
        return b
    try:
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return DIV0 if b == 0 else a / b
        return a ** b
    except (InvalidOperation, DivisionByZero, OverflowError):
        return NUM


# ───────────────────────────── 求值 ─────────────────────────────

class Range:
    """区域值：按行的二维列表；``origin`` = 左上角 (行, 列)，隐式交集用。"""

    __slots__ = ("rows", "origin")

    def __init__(self, rows: list[list[Value]], origin: tuple[int, int] = (1, 1)) -> None:
        self.rows = rows
        self.origin = origin

    def values(self):
        for row in self.rows:
            yield from row

    def single(self, current: tuple[int, int] | None = None) -> Value:
        """区域当标量用：单格取该格；单行区域取与公式所在列相同的那格、单列区域取同行（Excel 隐式交集）。"""
        if len(self.rows) == 1 and len(self.rows[0]) == 1:
            return self.rows[0][0]
        if current is not None:
            r0, c0 = self.origin
            row, col = current
            if len(self.rows) == 1 and 0 <= col - c0 < len(self.rows[0]):
                return self.rows[0][col - c0]
            if all(len(r) == 1 for r in self.rows) and 0 <= row - r0 < len(self.rows):
                return self.rows[row - r0][0]
        return VALUE


def _range(ctx: Context, sheet: str, r1: int, c1: int, r2: int, c2: int) -> Range:
    return Range([[ctx.cell(sheet, r, c) for c in range(c1, c2 + 1)] for r in range(r1, r2 + 1)], (r1, c1))


def _eval_ref(node: Node, ctx: Context) -> Value | Range:
    _, sheet, r1, c1, r2, c2 = node
    if r1 == r2 and c1 == c2:
        return ctx.cell(sheet, r1, c1)
    return _range(ctx, sheet, r1, c1, r2, c2)


def evaluate(node: Node, ctx: Context) -> Value:
    """AST 求值，结果是标量（区域只在函数参数里出现，其余位置按公式所在格做隐式交集）。"""
    result = _eval(node, ctx)
    if isinstance(result, Range):
        result = result.single(getattr(ctx, "current", None))
    return result


def _eval(node: Node, ctx: Context) -> Value | Range:
    kind = node[0]
    if kind in ("num", "str", "bool", "err"):
        return node[1]
    if kind == "empty":
        return None
    if kind == "ref":
        return _eval_ref(node, ctx)
    if kind == "neg":
        v = to_number(evaluate(node[1], ctx))
        return v if is_error(v) else -v
    if kind == "pct":
        v = to_number(evaluate(node[1], ctx))
        return v if is_error(v) else v / 100
    if kind == "bin":
        op = node[1]
        a, b = evaluate(node[2], ctx), evaluate(node[3], ctx)
        if op == "&":
            if is_error(a):
                return a
            if is_error(b):
                return b
            return to_text(a) + to_text(b)
        if op in ("=", "<>", "<", ">", "<=", ">="):
            return compare(op, a, b)
        return _arith(op, a, b)
    if kind == "call":
        fn = FUNCTIONS.get(node[1])
        if fn is None:
            return NAME
        return fn(node[2], ctx)
    raise FormulaSyntaxError(f"未知节点 {kind}")


def _arg(node: Node, ctx: Context) -> Value | Range:
    """函数参数求值：引用（含单格引用）一律当区域，与 Excel「引用参数忽略文本」一致。"""
    if node[0] == "ref":
        return _range(ctx, *node[1:])
    return _eval(node, ctx)


def _numbers(args: list[Node], ctx: Context) -> list[Decimal] | XlError:
    """SUM / MIN / MAX 的取数口径：引用里只认数值（文本、逻辑值、空格忽略），直接参数按数值转换。"""
    out: list[Decimal] = []
    for a in args:
        if a[0] == "empty":
            continue
        v = _arg(a, ctx)
        if isinstance(v, Range):
            for x in v.values():
                if is_error(x):
                    return x
                if isinstance(x, Decimal):
                    out.append(x)
        else:
            n = to_number(v)
            if is_error(n):
                return n
            out.append(n)
    return out


def _fn_sum(args, ctx):
    nums = _numbers(args, ctx)
    return nums if is_error(nums) else sum(nums, Decimal(0))


def _fn_min(args, ctx):
    nums = _numbers(args, ctx)
    return nums if is_error(nums) else (min(nums) if nums else Decimal(0))


def _fn_max(args, ctx):
    nums = _numbers(args, ctx)
    return nums if is_error(nums) else (max(nums) if nums else Decimal(0))


def _scalar(args: list[Node], i: int, ctx: Context, default: Value = None) -> Value:
    if i >= len(args) or args[i][0] == "empty":
        return default
    return evaluate(args[i], ctx)


def _fn_if(args, ctx):
    cond = to_bool(_scalar(args, 0, ctx))
    if is_error(cond):
        return cond
    if cond:
        return _scalar(args, 1, ctx, Decimal(0)) if len(args) > 1 else True
    if len(args) < 3:
        return False
    return _scalar(args, 2, ctx, Decimal(0))


def _fn_iferror(args, ctx):
    v = _scalar(args, 0, ctx)
    if is_error(v):
        return _scalar(args, 1, ctx, Decimal(0))
    return Decimal(0) if v is None else v


def _logical(args, ctx, combine: Callable[[list[bool]], bool]):
    flags: list[bool] = []
    for a in args:
        v = _arg(a, ctx)
        items = list(v.values()) if isinstance(v, Range) else [v]
        for x in items:
            if is_error(x):
                return x
            if isinstance(v, Range) and (x is None or isinstance(x, str)):
                continue
            b = to_bool(x)
            if is_error(b):
                return b
            flags.append(b)
    return combine(flags) if flags else VALUE


def _fn_and(args, ctx):
    return _logical(args, ctx, all)


def _fn_or(args, ctx):
    return _logical(args, ctx, any)


def _fn_isnumber(args, ctx):
    v = _scalar(args, 0, ctx)
    return isinstance(v, Decimal)


def _fn_abs(args, ctx):
    v = to_number(_scalar(args, 0, ctx))
    return v if is_error(v) else abs(v)


def _fn_round(args, ctx):
    v = to_number(_scalar(args, 0, ctx))
    n = to_number(_scalar(args, 1, ctx))
    if is_error(v):
        return v
    if is_error(n):
        return n
    digits = int(n)
    return v.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP) if digits >= 0 else (
        (v.scaleb(digits).quantize(Decimal(1), rounding=ROUND_HALF_UP)).scaleb(-digits)
    )


def _fn_left(args, ctx):
    v = _scalar(args, 0, ctx)
    if is_error(v):
        return v
    n = to_number(_scalar(args, 1, ctx, Decimal(1)))
    if is_error(n):
        return n
    return to_text(v)[: max(int(n), 0)]


def _fn_counta(args, ctx):
    count = 0
    for a in args:
        if a[0] == "empty":
            continue
        v = _arg(a, ctx)
        items = v.values() if isinstance(v, Range) else [v]
        count += sum(1 for x in items if x is not None)
    return Decimal(count)


_CRITERIA_RE = re.compile(r"^(<=|>=|<>|<|>|=)?(.*)$", re.S)


def _criteria(crit: Value) -> Callable[[Value], bool]:
    """SUMIF 条件：数值相等、比较运算符、文本（大小写不敏感，支持 * ? 通配）。"""
    if isinstance(crit, Decimal) or isinstance(crit, bool):
        return lambda x: x is not None and not isinstance(x, str) and compare("=", x, crit) is True
    m = _CRITERIA_RE.match(to_text(crit))
    op, operand = (m.group(1) or "="), m.group(2)
    num = to_number(operand) if operand.strip() else VALUE
    if not is_error(num):
        def check_num(x: Value) -> bool:
            if not isinstance(x, Decimal):
                return op == "<>"
            return compare(op, x, num) is True
        return check_num
    pattern = re.compile(
        "^" + re.escape(operand).replace(r"\*", ".*").replace(r"\?", ".") + "$", re.I | re.S,
    )

    def check_text(x: Value) -> bool:
        hit = bool(pattern.match(to_text(x))) if operand else (x is None or x == "")
        return hit if op == "=" else (not hit if op == "<>" else False)
    return check_text


def _fn_sumif(args, ctx):
    rng = _arg(args[0], ctx)
    crit = _scalar(args, 1, ctx)
    if is_error(crit):
        return crit
    if not isinstance(rng, Range):
        rng = Range([[rng]])
    sum_rng = _arg(args[2], ctx) if len(args) > 2 and args[2][0] != "empty" else rng
    if not isinstance(sum_rng, Range):
        sum_rng = Range([[sum_rng]])
    match = _criteria(crit)
    total = Decimal(0)
    for i, row in enumerate(rng.rows):
        for j, x in enumerate(row):
            if not match(x):
                continue
            try:
                y = sum_rng.rows[i][j]
            except IndexError:
                continue
            if is_error(y):
                return y
            if isinstance(y, Decimal):
                total += y
    return total


FUNCTIONS: dict[str, Callable[[list[Node], Context], Value]] = {
    "SUM": _fn_sum,
    "MIN": _fn_min,
    "MAX": _fn_max,
    "IF": _fn_if,
    "IFERROR": _fn_iferror,
    "AND": _fn_and,
    "OR": _fn_or,
    "ISNUMBER": _fn_isnumber,
    "ABS": _fn_abs,
    "ROUND": _fn_round,
    "LEFT": _fn_left,
    "COUNTA": _fn_counta,
    "SUMIF": _fn_sumif,
}
