"""利润表金标准求值器（spec income-statement-lower-section-formulas 任务 4）。

独立实现词法 + 递归下降求值，只认报表公式实际出现的写法：``TB``、``SUM_TB``、``ROW``、``SUM_ROW``、
数字、``+ - * /``、括号、一元正负号。**不得 import 任何生产报表 / 取数 / 逐行计算模块**
（独立性由 ``test_gold_is_evaluator_independence.py`` 的 AST 判据钉死）。

求值顺序在本文件独立实现一次拓扑排序（与生产 ``report_eval_order`` 互为对照）：
依赖 = 公式里 ``ROW`` / ``SUM_ROW`` 指到的本套行次；环上的行不求值，记进 :attr:`GoldResult.cycles`。
无公式行取 0（与生产 ``FORMULA_LESS_VALUE`` 同值，本文件写死，不 import）。
未识别写法收集进 :attr:`GoldResult.unparsed`，调用方断言为 0。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

FORMULA_LESS_VALUE = Decimal("0")
_CENT = Decimal("0.01")
_TOKEN = re.compile(
    r"\s*(?:(?P<func>TB|SUM_TB|ROW|SUM_ROW)\s*\(|(?P<str>'[^']*')|(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<op>[+\-*/(),]))"
)


class GoldParseError(Exception):
    """金标准求值器不认识的写法。"""


@dataclass
class GoldResult:
    values: dict[str, Decimal] = field(default_factory=dict)
    cycles: tuple[str, ...] = ()
    unparsed: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GoldRow:
    """一行报表定义（只用到这四个字段）。"""

    row_code: str
    row_number: int
    formula: str | None
    report_type: str = "income_statement"


def cents(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


# ─────────────────────────── 词法 ───────────────────────────


def tokenize(formula: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(formula):
        if formula[pos].isspace():
            pos += 1
            continue
        match = _TOKEN.match(formula, pos)
        if match is None:
            raise GoldParseError(f"位置 {pos} 无法识别：{formula[pos:]!r}")
        pos = match.end()
        for kind in ("func", "str", "num", "op"):
            text = match.group(kind)
            if text is not None:
                tokens.append((kind, text))
                break
    return tokens


# ─────────────────────── 递归下降求值 ───────────────────────


class _Evaluator:
    def __init__(self, tokens: list[tuple[str, str]], tb: dict[str, Decimal], rows: dict[str, Decimal]):
        self.tokens, self.pos, self.tb, self.rows = tokens, 0, tb, rows

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        if self.pos >= len(self.tokens):
            raise GoldParseError("公式提前结束")
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect_op(self, op: str) -> None:
        kind, text = self.take()
        if kind != "op" or text != op:
            raise GoldParseError(f"期望 {op!r}，实际 {text!r}")

    def expect_str(self) -> str:
        kind, text = self.take()
        if kind != "str":
            raise GoldParseError(f"期望带引号的文本，实际 {text!r}")
        return text[1:-1].strip()

    def parse(self) -> Decimal:
        value = self.expression()
        if self.peek() is not None:
            raise GoldParseError(f"公式尾部有多余内容：{self.tokens[self.pos:]!r}")
        return value

    def expression(self) -> Decimal:
        value = self.term()
        while (token := self.peek()) and token[0] == "op" and token[1] in "+-":
            self.take()
            right = self.term()
            value = value + right if token[1] == "+" else value - right
        return value

    def term(self) -> Decimal:
        value = self.unary()
        while (token := self.peek()) and token[0] == "op" and token[1] in "*/":
            self.take()
            right = self.unary()
            if token[1] == "*":
                value *= right
            else:
                if right == 0:
                    raise GoldParseError("除数为 0")
                value /= right
        return value

    def unary(self) -> Decimal:
        token = self.peek()
        if token and token[0] == "op" and token[1] in "+-":
            self.take()
            value = self.unary()
            return -value if token[1] == "-" else value
        return self.atom()

    def atom(self) -> Decimal:
        kind, text = self.take()
        if kind == "num":
            return Decimal(text)
        if kind == "op" and text == "(":
            value = self.expression()
            self.expect_op(")")
            return value
        if kind == "func":
            return self.call(text)
        raise GoldParseError(f"不是原子项：{text!r}")

    def call(self, name: str) -> Decimal:
        if name == "TB":
            code = self.expect_str()
            self.expect_op(",")
            column = self.expect_str()
            self.expect_op(")")
            return self.tb_amount(code, column)
        if name == "SUM_TB":
            code_range = self.expect_str()
            self.expect_op(",")
            column = self.expect_str()
            self.expect_op(")")
            start, _, end = code_range.partition("~")
            total = Decimal("0")
            for code, amount in self.tb.items():
                if start.strip() <= code[:len(start.strip())] <= end.strip():
                    total += amount
            _ = column
            return total
        if name == "ROW":
            code = self.expect_str()
            self.expect_op(")")
            return self.rows.get(code, FORMULA_LESS_VALUE)
        if name == "SUM_ROW":
            start = self.expect_str()
            self.expect_op(",")
            end = self.expect_str()
            self.expect_op(")")
            return sum((amount for code, amount in self.rows.items() if start <= code <= end), Decimal("0"))
        raise GoldParseError(f"未支持的函数 {name}")

    def tb_amount(self, code: str, column: str) -> Decimal:
        """按科目码前缀汇总（叶子筛选在夹具里做：夹具只给叶子科目）。"""
        _ = column
        return sum((amount for item, amount in self.tb.items() if item.startswith(code)), Decimal("0"))


# ───────────────────── 顺序与整表求值 ─────────────────────


def _dependencies(rows: list[GoldRow]) -> dict[str, set[str]]:
    known = {row.row_code for row in rows}
    ordered = sorted(known)
    deps: dict[str, set[str]] = {}
    for row in rows:
        formula = row.formula or ""
        wanted: set[str] = set(re.findall(r"(?<!SUM_)ROW\('([^']*)'\)", formula))
        for start, end in re.findall(r"SUM_ROW\('([^']*)','([^']*)'\)", formula):
            wanted |= {code for code in ordered if start <= code <= end}
        deps[row.row_code] = wanted & known
    return deps


def _cycles(deps: dict[str, set[str]]) -> set[str]:
    alive = set(deps)
    while True:
        out = {code: deps[code] & alive for code in alive}
        into = {code: {src for src in alive if code in out[src]} for code in alive}
        drop = {code for code in alive if not out[code] or not into[code]}
        if not drop:
            return alive
        alive -= drop


def evaluate(rows: list[GoldRow], tb: dict[str, Decimal]) -> GoldResult:
    """按依赖序求值整张表；返回每行的分位金额、环成员与未识别写法。"""
    deps = _dependencies(rows)
    cycles = _cycles(deps)
    by_code = {row.row_code: row for row in rows}
    result = GoldResult(cycles=tuple(sorted(cycles)))
    pending = {code for code in deps if code not in cycles}
    # 无公式行先置 0（与生产一致），再按依赖就绪逐轮求值
    for code in sorted(pending):
        if not (by_code[code].formula or "").strip():
            result.values[code] = FORMULA_LESS_VALUE
    done = set(result.values)
    while (todo := pending - done):
        progressed = False
        for code in sorted(todo, key=lambda item: (by_code[item].row_number, item)):
            if deps[code] - done:
                continue
            formula = by_code[code].formula or ""
            try:
                result.values[code] = cents(_Evaluator(tokenize(formula), tb, dict(result.values)).parse())
            except GoldParseError as exc:
                result.unparsed[code] = f"{formula} —— {exc}"
                result.values[code] = FORMULA_LESS_VALUE
            done.add(code)
            progressed = True
        if not progressed:  # 依赖落在环上或悬空：按 0 收尾，不死循环
            for code in sorted(todo):
                result.values[code] = FORMULA_LESS_VALUE
                done.add(code)
    return result
