"""合并报表行级计算（spec consol-elimination-single-source-push §四，ADR-CSP-002 / ADR-CSP-003）。

合并报表、合并试算平衡表页、报表差额表共用 ``report_values``：对 ``{模板}_consolidated`` 的 report_config
逐行调 ``report_engine.evaluate_formula``（与单体报表同一编排与 L1 内核），只把取数换成 ``BasisResolver`` ——
读计算口径（``consol_calc_basis.node_measures``）里某节点某度量的科目金额，按科目码前缀汇总。

- 取数列：期末余额 / 审定数 = 本年审定数；本期发生额只对损益类科目成立（损益类没有年初数，审定数即本年累计）；
  年初余额 / 期初余额 / 其他已注册列、非损益类科目的本期发生额 ⇒ 该行留空并给原因（P9，不静默为 0）——
  取数范围内全树都没有科目时除外（没有试算行就没有年初数，真为 0）；未注册列名一律留空。
- 取数调用先规范化并加括号（``canonical_formula``）：编排层把取数结果以文本拼回表达式，宽松写法漏替换、
  一元负号后紧跟负值（``--5.00``）都会让内核静默给 0。
- 线性：公式只含 ``+ −``、数值常量与「乘除常数」⇒ 行值对度量线性，差额表各列之和 = 合计（P3 / P4）。
  非线性（ABS/MAX/MIN/IF/ROUND、比较、取数相乘）的行在合并报表本身照常求值，按列分解时留空并说明。
- 不取数的函数（PREV/NOTE/WP/AUX/ADJ、未注册函数）⇒ 留空并说明：单体编排会把它们静默置 0。
- 行缓存：同一次调用内跨报表类型共享（资产负债表 → 利润表 → 现金流量表 → 权益变动表 → 补充资料 → 减值准备），
  支持跨表 ROW；留空行不进缓存，引用留空行 / 不存在的行 / 排在后面的行的行也留空并指出被引用行。

纯函数层（``analyze_formula`` / ``BasisResolver`` / ``report_values`` / ``node_report``）不连库；
``load_report_rows`` / ``resolve_consol_standard`` 是薄装载。
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consol_calc_basis import (
    MEASURE_CONSOLIDATED,
    MEASURES,
    ONE,
    ZERO,
    to_cents,
)
from app.services.formula_engine import (
    ASTBinOp,
    ASTCompare,
    ASTFuncCall,
    ASTNumber,
    ASTRangeSum,
    ASTRowRef,
    ASTString,
    ASTUnary,
    COLUMN_ALIASES,
    FormulaParseError,
    parse_to_ast,
)
from app.services.formula_grammar import SUM_TB_PATTERN, TB_PATTERN

REPORT_TYPE_ORDER: tuple[str, ...] = (
    "balance_sheet",
    "income_statement",
    "cash_flow_statement",
    "equity_statement",
    "cash_flow_supplement",
    "impairment_provision",
)
BALANCE_COLUMNS = frozenset({"期末余额", "审定数"})
PERIOD_COLUMN = "本期发生额"
OPENING_COLUMNS = frozenset({"年初余额", "期初余额"})
# REPORT('行次','期间') 的期间：只取本期（合并口径没有上期计算值）
CURRENT_PERIODS = frozenset({"", "期末", "本期", "本年", "期末余额", "本期发生额", "current"})
_ROW_FUNCS = frozenset({"ROW", "REPORT"})
# 非线性函数的参数个数（最少, 最多；None = 不限）：个数不对时 L1 内核静默返回 0，这里先拦下
_NONLINEAR_FUNCS: dict[str, tuple[int, int | None]] = {
    "ABS": (1, 1), "ROUND": (1, 2), "MAX": (2, None), "MIN": (2, None), "IF": (3, 3),
}
_NO_DATA_FUNCS = frozenset({"PREV", "NOTE", "WP", "AUX", "ADJ"})


# ─────────────────────────────── 公式形态分析 ───────────────────────────────


@dataclass(frozen=True)
class FormulaShape:
    """一条公式在合并口径下能否求值、能否按列分解，以及它引用了哪些行。"""

    formula: str                                   # 规范化后的公式（TB/SUM_TB 参数间空格已去）
    error: str | None                              # 不能求值的原因（非空 ⇒ 该行留空）
    nonlinear: str | None                          # 不能按列分解的原因（None 且 error 为空 ⇒ 线性）
    row_refs: tuple[str, ...] = ()
    row_ranges: tuple[tuple[str, str], ...] = ()
    terms: tuple[tuple[tuple, Decimal], ...] = ()  # 线性项：(("tb",码,列)|("sum_tb",起,止,列)|("row",行)|("rows",起,止), 系数)
    constant: Decimal = ZERO
    tb_codes: tuple[str, ...] = ()                 # 直接取数的科目前缀（TB）
    tb_ranges: tuple[tuple[str, str], ...] = ()    # 直接取数的科目区间（SUM_TB）

    @property
    def linear(self) -> bool:
        return self.error is None and self.nonlinear is None


class _Invalid(Exception):
    pass


class _NotLinear(Exception):
    pass


_RELAXED_TB_CALL = re.compile(r"(?<![A-Za-z0-9_])(SUM_TB|TB)\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")


def canonical_formula(formula: str) -> str:
    """取数调用改成严格形式并加括号：``-TB( '1602' , '期末余额' )`` ⇒ ``-(TB('1602','期末余额'))``。

    ``report_engine.evaluate_formula`` 按严格正则（参数间不许空格）把取数结果**以文本**拼回表达式：
    ① 宽松写法漏替换 ⇒ 进 L1 内核按空数据求值 = 静默 0；② 一元负号后紧跟负值成了 ``--5.00``，
    内核的一元负号后只许跟原子 ⇒ 解析失败 = 静默 0（抵销度量常为负）。加括号后是 ``-(-5.00)``。
    求值与形态分析用同一份文本。
    """

    def repl(m: re.Match[str]) -> str:
        name, arg, col = m.group(1), m.group(2).strip(), m.group(3).strip()
        if name == "SUM_TB":
            arg = "~".join(p.strip() for p in arg.split("~"))
        return f"({name}('{arg}','{col}'))"

    return _RELAXED_TB_CALL.sub(repl, formula.strip())


def _ref_name(node: Any) -> str | None:
    if isinstance(node, ASTString):
        return node.value.strip()
    if isinstance(node, ASTRowRef):
        return node.row_code
    return None


def _string_args(node: ASTFuncCall, count: int) -> list[str]:
    if len(node.args) != count or not all(isinstance(a, ASTString) for a in node.args):
        raise _Invalid(f"{node.name}() 需要 {count} 个带引号的文本参数")
    return [a.value.strip() for a in node.args]


def _string_number(text: str) -> Decimal:
    """与 L1 内核同口径：带引号的文本按数字取值，取不了按 0。"""
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return ZERO
    return value if value.is_finite() else ZERO


def _const_value(node: Any) -> Decimal | None:
    """纯常量子式的值（数字、文本数字、负号、常量四则）；含取数或函数 ⇒ None。"""
    if isinstance(node, ASTNumber):
        return node.value
    if isinstance(node, ASTString):
        return _string_number(node.value)
    if isinstance(node, ASTUnary):
        v = _const_value(node.operand)
        return None if v is None else (-v if node.op == "-" else v)
    if isinstance(node, ASTBinOp):
        left, right = _const_value(node.left), _const_value(node.right)
        if left is None or right is None:
            return None
        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            return left / right if right != 0 else None
    return None


@dataclass
class _Collected:
    refs: list[str]
    ranges: list[tuple[str, str]]
    funcs: dict[str, int]
    tb_codes: list[str]
    tb_ranges: list[tuple[str, str]]


def _validate(node: Any, seen: _Collected) -> None:
    """遍历 AST：函数是否在合并口径内取数、参数形态、除数为 0；顺带收集行引用、取数科目与函数计数。"""
    if isinstance(node, ASTRowRef):
        seen.refs.append(node.row_code)
        return
    if isinstance(node, ASTRangeSum):
        seen.ranges.append((node.start_code, node.end_code))
        return
    if isinstance(node, (ASTNumber, ASTString)):
        return
    if isinstance(node, ASTUnary):
        _validate(node.operand, seen)
        return
    if isinstance(node, (ASTBinOp, ASTCompare)):
        if isinstance(node, ASTBinOp) and node.op == "/" and _const_value(node.right) == 0:
            raise _Invalid("除数为 0")
        _validate(node.left, seen)
        _validate(node.right, seen)
        return
    if not isinstance(node, ASTFuncCall):
        raise _Invalid("公式结构无法识别")
    name = node.name
    seen.funcs[name] = seen.funcs.get(name, 0) + 1
    if name == "TB":
        code, _col = _string_args(node, 2)
        if not code or "~" in code:
            raise _Invalid("TB() 的科目编码不能为空或含「~」（区间请用 SUM_TB）")
        seen.tb_codes.append(code)
        return
    if name == "SUM_TB":
        rng, _col = _string_args(node, 2)
        parts = [p.strip() for p in rng.split("~")]
        if len(parts) != 2 or not all(parts):
            raise _Invalid(f"SUM_TB() 区间「{rng}」应写成「起始~结束」")
        seen.tb_ranges.append((parts[0], parts[1]))
        return
    if name in _ROW_FUNCS:
        if not node.args or len(node.args) > (2 if name == "REPORT" else 1):
            raise _Invalid(f"{name}() 参数个数不对")
        ref = _ref_name(node.args[0])
        if not ref:
            raise _Invalid(f"{name}() 的行次须为文本")
        if len(node.args) == 2:
            period = _ref_name(node.args[1])
            if period is None or period not in CURRENT_PERIODS:
                raise _Invalid(f"REPORT() 期间「{period}」不取数（合并口径只有本期值）")
        seen.refs.append(ref)
        return
    if name == "SUM_ROW":
        if len(node.args) != 2:
            raise _Invalid("SUM_ROW() 需要起止两个行次")
        start, end = _ref_name(node.args[0]), _ref_name(node.args[1])
        if not start or not end:
            raise _Invalid("SUM_ROW() 的行次须为文本")
        seen.ranges.append((start, end))
        return
    if name in _NONLINEAR_FUNCS:
        low, high = _NONLINEAR_FUNCS[name]
        if len(node.args) < low or (high is not None and len(node.args) > high):
            raise _Invalid(f"{name}() 参数个数不对")
        for arg in node.args:
            _validate(arg, seen)
        return
    from app.services.formula_engine import _REGISTRY

    if name in _NO_DATA_FUNCS or name in _REGISTRY.known_function_names():
        raise _Invalid(f"函数 {name}() 在合并报表中不取数")
    raise _Invalid(f"函数 {name}() 未注册")


def _merge(a: dict, b: dict, factor: Decimal = ONE) -> dict:
    out = dict(a)
    for key, coef in b.items():
        total = out.get(key, ZERO) + factor * coef
        if total:
            out[key] = total
        else:
            out.pop(key, None)
    return out


def _linear(node: Any) -> tuple[dict, Decimal]:
    """线性展开：返回 (项 → 系数, 常数)；非线性抛 ``_NotLinear``（调用前已过 ``_validate``）。"""
    if isinstance(node, ASTNumber):
        return {}, node.value
    if isinstance(node, ASTString):
        return {}, _string_number(node.value)
    if isinstance(node, ASTRowRef):
        return {("row", node.row_code): ONE}, ZERO
    if isinstance(node, ASTRangeSum):
        return {("rows", node.start_code, node.end_code): ONE}, ZERO
    if isinstance(node, ASTUnary):
        terms, const = _linear(node.operand)
        if node.op == "-":
            return {k: -v for k, v in terms.items()}, -const
        return terms, const
    if isinstance(node, ASTFuncCall):
        name = node.name
        if name == "TB":
            code, col = (a.value.strip() for a in node.args)
            return {("tb", code, col): ONE}, ZERO
        if name == "SUM_TB":
            rng, col = (a.value.strip() for a in node.args)
            start, end = (p.strip() for p in rng.split("~"))
            return {("sum_tb", start, end, col): ONE}, ZERO
        if name in _ROW_FUNCS:
            return {("row", _ref_name(node.args[0])): ONE}, ZERO
        if name == "SUM_ROW":
            return {("rows", _ref_name(node.args[0]), _ref_name(node.args[1])): ONE}, ZERO
        raise _NotLinear(f"含 {name}()")
    if isinstance(node, ASTCompare):
        raise _NotLinear("含比较运算")
    if isinstance(node, ASTBinOp):
        lt, lc = _linear(node.left)
        rt, rc = _linear(node.right)
        if node.op in ("+", "-"):
            factor = ONE if node.op == "+" else -ONE
            return _merge(lt, rt, factor), lc + factor * rc
        if node.op == "*":
            if not lt:
                return _merge({}, rt, lc), lc * rc
            if not rt:
                return _merge({}, lt, rc), lc * rc
            raise _NotLinear("两个取数项相乘")
        if node.op == "/":
            if rt:
                raise _NotLinear("除以取数项")
            return _merge({}, lt, ONE / rc), lc / rc
    raise _NotLinear("公式结构不能线性展开")


def _untokenized(text: str) -> str | None:
    """内核词法 ``finditer`` 会跳过认不出的字符（引号外的中文、全角符号）再解析剩下的部分：
    ``A－B``（全角减号）被跳成 ``A B`` 或 ``A+－B`` 被跳成 ``A+B`` ⇒ 变号却无报错；其余情形整条解析失败 = 静默 0。"""
    from app.services.formula_engine import _AST_TOKEN_RE

    pos = 0
    for m in _AST_TOKEN_RE.finditer(text):
        gap = text[pos:m.start()].strip()
        if gap:
            return gap
        pos = m.end()
    return text[pos:].strip() or None


@lru_cache(maxsize=4096)
def analyze_formula(formula: str) -> FormulaShape:
    """合并口径下的公式形态（纯函数，按文本缓存）。"""
    text = canonical_formula(formula)
    junk = _untokenized(text)
    if junk:
        return FormulaShape(text, f"公式含无法识别的内容「{junk[:20]}」", None)
    try:
        ast = parse_to_ast(text)
    except FormulaParseError as exc:
        return FormulaShape(text, f"公式无法解析：{exc}", None)
    if isinstance(ast, ASTCompare):
        return FormulaShape(text, "勾稽校验式（比较运算），不是取数公式", None)
    seen = _Collected([], [], {}, [], [])
    try:
        _validate(ast, seen)
    except _Invalid as exc:
        return FormulaShape(text, str(exc), None)
    # 编排层按严格正则预替换取数：AST 看到的 TB/SUM_TB 必须都被正则命中，否则那一处按 0 进内核（静默 0）。
    # TB 正则也会命中 SUM_TB 内部，故独立 TB 数 = TB 命中数 − SUM_TB 命中数。
    n_sum = len(SUM_TB_PATTERN.findall(text))
    n_tb = len(TB_PATTERN.findall(text)) - n_sum
    if (n_tb, n_sum) != (seen.funcs.get("TB", 0), seen.funcs.get("SUM_TB", 0)):
        return FormulaShape(text, "TB()/SUM_TB() 写法无法取数（参数须为带引号的文本，逗号分隔）", None)
    from app.services.formula_engine import _is_blocked_formula

    if _is_blocked_formula(text):
        return FormulaShape(text, "公式含非白名单内容，已拦截", None)
    common = {
        "row_refs": tuple(dict.fromkeys(seen.refs)),
        "row_ranges": tuple(dict.fromkeys(seen.ranges)),
        "tb_codes": tuple(dict.fromkeys(seen.tb_codes)),
        "tb_ranges": tuple(dict.fromkeys(seen.tb_ranges)),
    }
    try:
        terms, const = _linear(ast)
    except _NotLinear as exc:
        return FormulaShape(text, None, str(exc), **common)
    ordered_terms = tuple(sorted(terms.items(), key=lambda kv: tuple(str(x) for x in kv[0])))
    # 仿射不是线性：各列都会带上常数，列和 = 合计 + (列数 − 1) × 常数
    nonlinear = f"含常数项 {const}" if const else None
    return FormulaShape(text, None, nonlinear, terms=ordered_terms, constant=const, **common)


def validate_linear(formula: str) -> str | None:
    """线性（可按列分解）⇒ None；否则返回原因（不能求值或非线性）。"""
    shape = analyze_formula(formula)
    return shape.error or shape.nonlinear


# ─────────────────────────────── 取数 ───────────────────────────────


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def is_period_account(code: str, category: Any = None) -> bool:
    """损益类科目：本期发生额 = 本年审定数（没有年初数）。类别缺失按编码 / 名称推断。

    只认 5/6 开头的收入、费用类 —— 4 开头在新旧两套科目表里分别是权益类与成本类，都有年初数。
    """
    if category is None:
        from app.services.account_chart_service import _infer_category

        category = _infer_category(code, "")
    return _enum_text(category) in ("revenue", "expense") and code[:1] in ("5", "6")


def _prefix_keys(keys: list[str], prefix: str) -> list[str]:
    """``keys`` 已排序：以 ``prefix`` 开头的键在有序表里连续，从 ``bisect_left`` 起取到不再匹配。"""
    out: list[str] = []
    i = bisect_left(keys, prefix)
    while i < len(keys) and keys[i].startswith(prefix):
        out.append(keys[i])
        i += 1
    return out


def _range_keys(keys: Iterable[str], start: str, end: str) -> list[str]:
    """与 L1 内核 ``SUM_TB`` 同口径：``start <= code[:len(start)] <= end``（含区间终点科目的子级）。"""
    n = len(start)
    return [k for k in keys if start <= k[:n] <= end]


class BasisResolver:
    """合并口径取数（实现 ``AmountResolver``）：某节点某度量的 {科目: 金额}，按科目码前缀汇总。

    ``categories`` 给本棵树的全部科目类别（``CalcBasis.categories``）：列能否取数按全体科目判定，
    不随某个度量里恰好有哪些非零科目而变 —— 同一行在五个度量上的留空判定一致（比较度量时必须传）。
    取数范围内全树都没有科目 ⇒ 年初 / 期初余额真为 0（没有试算行就没有年初数），照常取 0。
    每行求值前调 ``begin_row``；``reasons`` 是本行不取数的原因（有序去重）。
    """

    def __init__(self, values: Mapping[str, Decimal], categories: Mapping[str, Any] | None = None):
        # 到分：编排层把取数结果 ``str()`` 后拼回表达式，科学计数（如 ``1E+3``）内核词法不认 ⇒ 静默 0
        self._values = {k: to_cents(v) for k, v in values.items() if k}
        self._keys = sorted(self._values)
        self._categories = dict(categories or {})
        self._universe = sorted(set(self._categories) | set(self._values))
        self.reasons: list[str] = []

    def begin_row(self) -> None:
        self.reasons = []

    def _flag(self, reason: str) -> None:
        if reason not in self.reasons:
            self.reasons.append(reason)

    def _column_ok(self, label: str, column: str, universe_codes: list[str]) -> bool:
        if column in BALANCE_COLUMNS:
            return True
        if column not in COLUMN_ALIASES:
            self._flag(f"{label}：列名「{column}」未注册")
            return False
        if column == PERIOD_COLUMN:
            bad = [c for c in universe_codes if not is_period_account(c, self._categories.get(c))]
            if not bad:
                return True
            self._flag(f"{label}：本期发生额只能取损益类科目（{bad[0]} 不是损益类，需年初数，合并口径暂无）")
            return False
        if column in OPENING_COLUMNS and not universe_codes:
            return True
        self._flag(f"{label}：取数列「{column}」不在合并口径内（合并数只有本年期末审定数）")
        return False

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        code = (account_code or "").strip()
        if "~" in code:
            # report_engine 在原公式上跑 TB 正则，会命中 SUM_TB('a~b',…) 内部；该处已由 resolve_sum 取数
            return ZERO
        column = (column_name or "").strip()
        if not code:
            self._flag("TB()：科目编码为空")
            return ZERO
        if not self._column_ok(f"TB('{code}')", column, _prefix_keys(self._universe, code)):
            return ZERO
        return sum((self._values[k] for k in _prefix_keys(self._keys, code)), ZERO)

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        parts = [p.strip() for p in (code_range or "").split("~")]
        if len(parts) != 2 or not all(parts):
            self._flag(f"SUM_TB('{code_range}')：区间格式错误")
            return ZERO
        start, end = parts
        column = (column_name or "").strip()
        label = f"SUM_TB('{start}~{end}')"
        if not self._column_ok(label, column, _range_keys(self._universe, start, end)):
            return ZERO
        return sum((self._values[k] for k in _range_keys(self._keys, start, end)), ZERO)


# ─────────────────────────────── 行求值 ───────────────────────────────


@dataclass(frozen=True)
class ReportRow:
    """报表行配置（与 ORM 解耦）。"""

    report_type: str
    row_code: str
    row_name: str
    row_number: int
    formula: str | None = None
    indent_level: int = 0
    is_total_row: bool = False

    @classmethod
    def from_config(cls, cfg: Any) -> ReportRow:
        return cls(
            report_type=_enum_text(cfg.report_type),
            row_code=cfg.row_code,
            row_name=cfg.row_name or "",
            row_number=int(cfg.row_number or 0),
            formula=cfg.formula,
            indent_level=int(cfg.indent_level or 0),
            is_total_row=bool(cfg.is_total_row),
        )


@dataclass(frozen=True)
class RowValue:
    """一行在某组科目金额上的求值结果；``amount is None`` ⇒ 留空，``reason`` 说明原因。"""

    amount: Decimal | None
    reason: str | None = None
    linear: bool = True
    has_formula: bool = True

    def to_dict(self) -> dict:
        return {
            "amount": None if self.amount is None else str(self.amount),
            "reason": self.reason,
            "linear": self.linear,
            "has_formula": self.has_formula,
        }


def ordered_rows(rows: Iterable[ReportRow]) -> list[ReportRow]:
    """求值顺序：报表类型按 ``REPORT_TYPE_ORDER``（与单体增量重算同序），类型内按行号。"""
    rank = {t: i for i, t in enumerate(REPORT_TYPE_ORDER)}
    return sorted(rows, key=lambda r: (rank.get(r.report_type, len(rank)), r.report_type, r.row_number, r.row_code))


class _Pass:
    """一次 ``report_values`` 调用的求值状态：行缓存、已算 / 留空集合在全部报表类型间共享。"""

    def __init__(self, rows: list[ReportRow], resolver: BasisResolver, require_linear: bool):
        self.rows = rows
        self.resolver = resolver
        self.require_linear = require_linear
        self.all_codes = sorted({r.row_code for r in rows})
        self.known = set(self.all_codes)
        self.cache: dict[str, Decimal] = {}
        self.blank: set[str] = set()
        self.done: set[str] = set()

    def inputs(self, shape: FormulaShape, own: str) -> tuple[dict[str, Decimal], str | None]:
        """本行公式用到的行值（只传被引用的行与 ``SUM_ROW`` 区间内的行）；引用有问题返回原因。

        只传用到的行：内核每次求值都复制整个行缓存，传全量会让一次调用变成 O(行数²)。
        ``SUM_ROW`` 在内核里是对传入缓存按行号字符串区间求和 ⇒ 传入区间内全部已算行，结果与传全量相同。
        """
        needed: dict[str, Decimal] = {}

        def take(code: str, where: str) -> str | None:
            if code == own:
                return f"{where}引用了本行（循环引用）"
            if code in self.blank:
                return f"{where}引用的行 {code} 留空"
            if code not in self.done:
                return f"{where}引用的行 {code} 排在本行之后，尚未计算"
            needed[code] = self.cache[code]
            return None

        for ref in shape.row_refs:
            reason = f"引用的行 {ref} 不存在" if ref not in self.known else take(ref, "")
            if reason:
                return needed, reason
        for start, end in shape.row_ranges:
            for code in self.all_codes[bisect_left(self.all_codes, start):]:
                if code > end:
                    break
                reason = take(code, f"区间 {start}~{end} ")
                if reason:
                    return needed, reason
        return needed, None

    async def value(self, row: ReportRow, evaluate_formula: Any) -> RowValue:
        text = (row.formula or "").strip()
        if not text:
            return RowValue(to_cents(ZERO), has_formula=False)
        shape = analyze_formula(text)
        if shape.error:
            return RowValue(None, shape.error, linear=False)
        if self.require_linear and shape.nonlinear:
            return RowValue(None, f"公式非线性（{shape.nonlinear}），不能按列分解", linear=False)
        needed, reason = self.inputs(shape, row.row_code)
        if reason:
            return RowValue(None, reason, linear=shape.linear)
        self.resolver.begin_row()
        amount = await evaluate_formula(shape.formula, resolver=self.resolver, row_cache=needed)
        if self.resolver.reasons:
            return RowValue(None, "；".join(self.resolver.reasons), linear=shape.linear)
        return RowValue(to_cents(amount), None, linear=shape.linear)

    async def run(self) -> dict[str, RowValue]:
        from app.services.report_engine import evaluate_formula

        out: dict[str, RowValue] = {}
        for row in self.rows:
            value = await self.value(row, evaluate_formula)
            out[row.row_code] = value
            self.done.add(row.row_code)
            if value.amount is None:
                self.blank.add(row.row_code)
            else:
                self.cache[row.row_code] = value.amount
        return out


async def report_values(
    rows: Iterable[ReportRow],
    values: Mapping[str, Decimal],
    *,
    categories: Mapping[str, Any] | None = None,
    require_linear: bool = False,
) -> dict[str, RowValue]:
    """对一组科目金额逐行求报表值（design §4.3），返回 {行次: RowValue}。

    ``require_linear``：按列分解（个别数 / 调整 / 抵销各度量）时为 True —— 非线性行留空并说明；
    合并报表本身（合并数度量）为 False，非线性行照常求值，``RowValue.linear`` 标出以便差额表注明。
    无公式的行（标题行、手工行）值为 0，``has_formula=False``。
    """
    return await _Pass(ordered_rows(rows), BasisResolver(values, categories=categories), require_linear).run()


def term_matches(term: tuple, account: str) -> bool:
    """科目取数项是否取到该科目：``("tb", 码, 列)`` 前缀；``("sum_tb", 起, 止, 列)`` 与 ``_range_keys`` 同口径。"""
    if term[0] == "tb":
        return account.startswith(term[1])
    if term[0] == "sum_tb":
        start, end = term[1], term[2]
        return start <= account[:len(start)] <= end
    return False


def row_account_terms(rows: Iterable[ReportRow]) -> dict[str, dict[tuple, Decimal] | None]:
    """每行公式展开到科目取数项（``ROW`` / ``SUM_ROW`` 按求值顺序递归代入）：{行次: {取数项: 系数}}。

    行值 = Σ 系数 × 该项取到的科目金额之和（线性行），所以一笔分录明细行对某行的贡献 =
    Σ 取到该科目的项的系数 × 归一后金额 —— 穿透明细之和恒等于该行的度量值。
    不能线性展开（公式错误 / 非线性 / 引用排在后面或不能展开的行）⇒ None；无公式的行 ⇒ 空字典（值恒 0）。
    """
    ordered = ordered_rows(rows)
    all_codes = sorted({r.row_code for r in ordered})
    out: dict[str, dict[tuple, Decimal] | None] = {}
    for row in ordered:
        text = (row.formula or "").strip()
        if not text:
            out[row.row_code] = {}
            continue
        shape = analyze_formula(text)
        expanded: dict[tuple, Decimal] | None = {} if shape.linear else None
        for term, coef in shape.terms if expanded is not None else ():
            if term[0] in ("tb", "sum_tb"):
                expanded = _merge(expanded, {term: coef})
                continue
            codes = [term[1]] if term[0] == "row" else [
                c for c in all_codes[bisect_left(all_codes, term[1]):] if c <= term[2]
            ]
            for code in codes:
                sub = out.get(code) if code != row.row_code else None
                if sub is None:
                    expanded = None
                    break
                expanded = _merge(expanded, sub, coef)
            if expanded is None:
                break
        out[row.row_code] = expanded
    return out


async def node_report(
    rows: Iterable[ReportRow],
    measures: Mapping[str, Mapping[str, Decimal]],
    *,
    categories: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, RowValue]]:
    """某节点五个度量的报表行值：合并数不要求线性，其余四个度量按列分解要求线性。"""
    rows = list(rows)
    out: dict[str, dict[str, RowValue]] = {}
    for measure in MEASURES:
        out[measure] = await report_values(
            rows, measures.get(measure, {}), categories=categories,
            require_linear=measure != MEASURE_CONSOLIDATED,
        )
    return out


# ─────────────────────────────── 口径与装载 ───────────────────────────────


CONSOL_STANDARDS = ("soe_consolidated", "listed_consolidated")


def consol_standard(template_type: str | None) -> str:
    """合并报表口径（design §4.4）：上市版 ⇒ ``listed_consolidated``，其余（含未设置）⇒ ``soe_consolidated``。"""
    return "listed_consolidated" if (template_type or "").strip().lower() == "listed" else "soe_consolidated"


async def resolve_consol_standard(db: AsyncSession, project_id: UUID) -> str:
    from app.models.core import Project

    template_type = (await db.execute(
        sa.select(Project.template_type).where(Project.id == project_id)
    )).scalar_one_or_none()
    return consol_standard(template_type)


async def load_report_rows(db: AsyncSession, standard: str) -> list[ReportRow]:
    from app.models.report_models import ReportConfig

    result = await db.execute(
        sa.select(ReportConfig).where(
            ReportConfig.applicable_standard == standard,
            ReportConfig.is_deleted == sa.false(),
        )
    )
    return ordered_rows(ReportRow.from_config(c) for c in result.scalars().all())


__all__ = [
    "BALANCE_COLUMNS",
    "CONSOL_STANDARDS",
    "PERIOD_COLUMN",
    "REPORT_TYPE_ORDER",
    "BasisResolver",
    "FormulaShape",
    "ReportRow",
    "RowValue",
    "analyze_formula",
    "canonical_formula",
    "consol_standard",
    "is_period_account",
    "load_report_rows",
    "node_report",
    "ordered_rows",
    "report_values",
    "resolve_consol_standard",
    "row_account_terms",
    "term_matches",
    "validate_linear",
]
