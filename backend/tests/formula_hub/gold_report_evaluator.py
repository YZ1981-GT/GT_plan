"""报表行独立金标准求值器（只在测试中用；spec formula-hub-integrity-closure 任务 17，需求 5.4，ADR-FHIC-24）。

输入 = 原始 SQL 行：``report_config`` 生效公式文本（准则行，``project:{项目}`` 行覆盖公式、独有行追加）与本项目本年度未删
的 ``trial_balance`` 行。词法、递归下降、叶子筛选、列名映射都在本文件里另写；只 import 标准库与 ``sqlalchemy``
（独立性守卫 ``test_gold_evaluator_independence.py`` 用 AST 与子进程核对）。

支持的语法 = 实施时扫描快照库 fh_snap_202610270028 全部未删 ``report_config`` 公式所得（4 个准则 1191 行，有公式 318 行，
``project:`` 行 0）：函数 ``TB`` 264 次、``SUM_ROW`` 65、``ROW`` 28、``SUM_TB`` 4；实参全是单引号字符串（694 个）、
逗号 333；括号 361 对全是函数调用的括号；二元 ``+`` 26、``-`` 17；``TB`` 列名「期末余额」208 /「本期发生额」56，
``SUM_TB`` 列名「期末余额」4、区间都写成「起~止」。没出现过的一律不支持、遇到即记为未识别（守卫断言总数为 0）：
数字、乘除、一元正负号、分组括号、空白、双引号与全角符号、其他函数名与列名。

口径：
- ``TB('码', 列)``：宽集合 = 标准码以「码」开头（字面前缀）的行；``SUM_TB('起~止', 列)``：宽集合 = 起 ≤ 码 ≤ 止、或码以「止」
  开头（字符串按码点比较）。宽集合里只计叶子 —— 集合内不存在以本码为前缀且更长的其他码；同码多行全部计入。
- 列名映射写死：「期末余额」= ``audited_amount``；「本期发生额」= ``audited_amount`` − ``opening_balance``（空值按 0）。
- 按（报表类型序, 行号, 行次）求值；无公式行一开始就按 0 可引用。``ROW('x')`` 取已算出的行：还没算到或不可算 ⇒ 本行不可算，
  定义里没有 ⇒ 悬空、不可算；``SUM_ROW('a','b')`` = 与本行同表、a ≤ 行次 ≤ b 的行之和，其中任一行没算出 ⇒ 本行不可算。
- 不可算的行 ``value`` 为 None 并写明原因：读取侧判「未过期」而金标准不可算、或金额与金标准差 > 0.005，即是 false-fresh。
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Union
from uuid import UUID

from sqlalchemy import text

#: 报表类型求值顺序（跨表 ``ROW`` 引用按此顺序可见，如权益变动表引用利润表行）
TYPE_ORDER = ("balance_sheet", "income_statement", "cash_flow_statement", "equity_statement",
              "cash_flow_supplement", "impairment_provision")
#: 函数名 → 实参个数（只收扫描出现过的四个）
ARITY = {"TB": 2, "SUM_TB": 2, "ROW": 1, "SUM_ROW": 2}
#: TB / SUM_TB 列名（只收扫描出现过的两个）
COLUMNS = ("期末余额", "本期发生额")
#: template_type + report_scope 组成的准则；组合不在其中按 enterprise（与需求所述的准则口径一致）
STANDARDS = ("soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone")
ZERO = Decimal("0")


class Unrecognized(Exception):
    """公式里出现了金标准不支持的语法。"""


class NotComputable(Exception):
    """引用的行悬空、尚未算到或本身不可算。"""


@dataclass(frozen=True)
class Token:
    kind: str  # name / string / ( / ) / , / + / - / end
    text: str
    pos: int


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class BinOp:
    op: str
    left: Node
    right: Node


Node = Union[Call, BinOp]


def tokenize(formula: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(formula):
        ch = formula[i]
        if ch in "(),+-":
            tokens.append(Token(ch, ch, i))
            i += 1
        elif ch == "'":
            end = formula.find("'", i + 1)
            if end < 0:
                raise Unrecognized(f"第 {i} 位起的单引号字符串没有结束")
            tokens.append(Token("string", formula[i + 1:end], i))
            i = end + 1
        elif ch.isascii() and (ch.isalpha() or ch == "_"):
            j = i + 1
            while j < len(formula) and formula[j].isascii() and (formula[j].isalnum() or formula[j] == "_"):
                j += 1
            tokens.append(Token("name", formula[i:j], i))
            i = j
        else:
            raise Unrecognized(f"第 {i} 位字符 {ch!r}")
    tokens.append(Token("end", "", len(formula)))
    return tokens


def _plain(value: str) -> bool:
    return bool(value) and not any(ch.isspace() for ch in value)


def _check_args(name: str, args: list[str]) -> None:
    if len(args) != ARITY[name]:
        raise Unrecognized(f"{name} 实参 {len(args)} 个（应为 {ARITY[name]} 个）")
    if name in ("TB", "SUM_TB") and args[1] not in COLUMNS:
        raise Unrecognized(f"{name} 列名 {args[1]!r}")
    if name == "TB" and not (_plain(args[0]) and "~" not in args[0]):
        raise Unrecognized(f"TB 科目码 {args[0]!r}")
    if name == "SUM_TB":
        bounds = args[0].split("~")
        if len(bounds) != 2 or not all(_plain(b) for b in bounds):
            raise Unrecognized(f"SUM_TB 区间 {args[0]!r}")
    if name in ("ROW", "SUM_ROW") and not all(_plain(a) for a in args):
        raise Unrecognized(f"{name} 行次 {args!r}")


class _Parser:
    """formula := expr end；expr := call (('+' | '-') call)*；call := name '(' string (',' string)* ')'。"""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens, self.i = tokens, 0

    def peek(self) -> Token:
        return self.tokens[self.i]

    def take(self, kind: str) -> Token:
        tok = self.peek()
        if tok.kind != kind:
            raise Unrecognized(f"第 {tok.pos} 位应为 {kind}，实为 {tok.kind} {tok.text!r}")
        self.i += 1
        return tok

    def formula(self) -> Node:
        node = self.expr()
        self.take("end")
        return node

    def expr(self) -> Node:
        node: Node = self.call()
        while self.peek().kind in ("+", "-"):
            op = self.take(self.peek().kind).kind
            node = BinOp(op, node, self.call())
        return node

    def call(self) -> Call:
        tok = self.peek()
        if tok.kind in ("+", "-"):
            raise Unrecognized(f"第 {tok.pos} 位一元 {tok.text}")
        if tok.kind == "(":
            raise Unrecognized(f"第 {tok.pos} 位分组括号")
        name = self.take("name").text
        if name not in ARITY:
            raise Unrecognized(f"函数 {name}")
        self.take("(")
        args = [self.take("string").text]
        while self.peek().kind == ",":
            self.take(",")
            args.append(self.take("string").text)
        self.take(")")
        _check_args(name, args)
        return Call(name, tuple(args))


def parse(formula: str) -> Node:
    return _Parser(tokenize(formula)).formula()


def calls_of(node: Node) -> list[Call]:
    if isinstance(node, Call):
        return [node]
    return [*calls_of(node.left), *calls_of(node.right)]


@dataclass(frozen=True)
class ConfigRow:
    report_type: str
    row_code: str
    row_number: int
    formula: str | None

    @property
    def has_formula(self) -> bool:
        return bool((self.formula or "").strip())


@dataclass(frozen=True)
class TbRow:
    code: str
    audited_amount: Decimal | None
    opening_balance: Decimal | None


@dataclass(frozen=True)
class GoldValue:
    value: Decimal | None
    reason: str | None = None


@dataclass
class GoldResult:
    standard: str
    formulas: dict[tuple[str, str], str | None] = field(default_factory=dict)
    values: dict[tuple[str, str], GoldValue] = field(default_factory=dict)
    unrecognized: list[str] = field(default_factory=list)


def leaf_codes(codes: Iterable[str]) -> set[str]:
    """集合内不存在「以本码为前缀且更长的其他码」的码（逐对比较，不排序）。"""
    distinct = set(codes)
    return {c for c in distinct if not any(len(o) > len(c) and o.startswith(c) for o in distinct)}


def tb_family(tb: Sequence[TbRow], call: Call) -> list[TbRow]:
    """``TB`` / ``SUM_TB`` 的宽集合（叶子筛选之前）。"""
    if call.name == "TB":
        return [r for r in tb if r.code.startswith(call.args[0])]
    start, end = call.args[0].split("~")
    return [r for r in tb if start <= r.code and (r.code <= end or r.code.startswith(end))]


def _amount(row: TbRow, column: str) -> Decimal:
    audited = row.audited_amount if row.audited_amount is not None else ZERO
    if column == "期末余额":
        return audited
    return audited - (row.opening_balance if row.opening_balance is not None else ZERO)


def tb_value(tb: Sequence[TbRow], call: Call, *, leaves_only: bool = True) -> Decimal:
    """``leaves_only=False`` = 宽集合全部相加（父行也计入），只供守卫证明「双计会改变结果」。"""
    family = tb_family(tb, call)
    keep = leaf_codes(r.code for r in family) if leaves_only else {r.code for r in family}
    return sum((_amount(r, call.args[1]) for r in family if r.code in keep), ZERO)


def mixed_family_refs(formula: str | None, tb: Sequence[TbRow]) -> list[str]:
    """公式里宽集合含父子并存科目（有码另有以它为前缀的更长码）的 ``TB`` / ``SUM_TB`` 引用。"""
    try:
        node = parse(formula or "")
    except Unrecognized:
        return []
    refs = []
    for call in calls_of(node):
        if call.name in ("TB", "SUM_TB"):
            codes = {r.code for r in tb_family(tb, call)}
            if codes - leaf_codes(codes):
                refs.append(f"{call.name}('{call.args[0]}')")
    return refs


class _Evaluator:
    def __init__(self, rows: list[ConfigRow], tb: Sequence[TbRow], leaves_only: bool) -> None:
        self.tb, self.leaves_only = tb, leaves_only
        self.defined = {r.row_code for r in rows}
        self.by_type: dict[str, list[ConfigRow]] = {}
        for r in rows:
            self.by_type.setdefault(r.report_type, []).append(r)
        self.ready: dict[str, Decimal] = {r.row_code: ZERO for r in rows if not r.has_formula}

    def value(self, node: Node, row: ConfigRow) -> Decimal:
        if isinstance(node, BinOp):
            left, right = self.value(node.left, row), self.value(node.right, row)
            return left + right if node.op == "+" else left - right
        if node.name in ("TB", "SUM_TB"):
            return tb_value(self.tb, node, leaves_only=self.leaves_only)
        if node.name == "ROW":
            return self._row(node.args[0])
        start, end = node.args
        members = [r.row_code for r in self.by_type[row.report_type] if start <= r.row_code <= end]
        return sum((self._row(code) for code in members), ZERO)

    def _row(self, code: str) -> Decimal:
        if code in self.ready:
            return self.ready[code]
        raise NotComputable(f"引用行 {code} {'未算出' if code in self.defined else '在定义里不存在'}")


def evaluate(configs: Iterable[ConfigRow], tb: Sequence[TbRow], *, standard: str = "",
             leaves_only: bool = True) -> GoldResult:
    result = GoldResult(standard=standard)
    rows: list[ConfigRow] = []
    seen_codes: dict[str, str] = {}
    for c in configs:
        key = (c.report_type, c.row_code)
        if c.report_type not in TYPE_ORDER:
            result.unrecognized.append(f"{c.report_type}/{c.row_code}：报表类型不在求值顺序里")
        elif key in result.formulas or c.row_code in seen_codes:
            result.unrecognized.append(f"{c.report_type}/{c.row_code}：行次重复定义（ROW 引用会有歧义）")
        else:
            result.formulas[key] = c.formula
            seen_codes[c.row_code] = c.report_type
            rows.append(c)
    rows.sort(key=lambda c: (TYPE_ORDER.index(c.report_type), c.row_number, c.row_code))
    ev = _Evaluator(rows, tb, leaves_only)
    for c in rows:
        key = (c.report_type, c.row_code)
        if not c.has_formula:
            result.values[key] = GoldValue(ZERO)
            continue
        try:
            node = parse(c.formula or "")
        except Unrecognized as exc:
            result.unrecognized.append(f"{c.report_type}/{c.row_code} {c.formula!r}：{exc}")
            result.values[key] = GoldValue(None, f"语法未识别：{exc}")
            continue
        try:
            value = ev.value(node, c)
        except NotComputable as exc:
            result.values[key] = GoldValue(None, str(exc))
            continue
        ev.ready[c.row_code] = value
        result.values[key] = GoldValue(value)
    return result


async def resolve_standard(db: Any, project_id: UUID) -> str:
    row = (await db.execute(text(
        "SELECT template_type, report_scope FROM projects WHERE id = :pid AND is_deleted = false"),
        {"pid": project_id})).one_or_none()
    if row is None:
        return "enterprise"
    standard = f"{row[0] or 'soe'}_{row[1] or 'standalone'}"
    return standard if standard in STANDARDS else "enterprise"


async def load_config_rows(db: Any, project_id: UUID, standard: str) -> list[ConfigRow]:
    """准则行 + 本项目行（同表同行次覆盖公式，结构取准则行；独有行追加；本项目行重复的原样追加，由求值报重复）。"""
    own_std = f"project:{project_id}"
    raw = (await db.execute(text(
        "SELECT applicable_standard, report_type::text, row_code, row_number, formula FROM report_config "
        "WHERE is_deleted = false AND applicable_standard IN (:std, :own)"),
        {"std": standard, "own": own_std})).all()
    base = [ConfigRow(rt, code, num or 0, formula) for std, rt, code, num, formula in raw if std == standard]
    own: dict[tuple[str, str], ConfigRow] = {}
    extra: list[ConfigRow] = []
    for std, rt, code, num, formula in raw:
        if std != own_std:
            continue
        row = ConfigRow(rt, code, num or 0, formula)
        if (rt, code) in own:
            extra.append(row)
        else:
            own[(rt, code)] = row
    merged = [ConfigRow(r.report_type, r.row_code, r.row_number, own[(r.report_type, r.row_code)].formula)
              if (r.report_type, r.row_code) in own else r for r in base]
    base_keys = {(r.report_type, r.row_code) for r in base}
    return [*merged, *(r for k, r in own.items() if k not in base_keys), *extra]


async def load_tb_rows(db: Any, project_id: UUID, year: int) -> list[TbRow]:
    rows = (await db.execute(text(
        "SELECT standard_account_code, audited_amount, opening_balance FROM trial_balance "
        "WHERE project_id = :pid AND year = :year AND is_deleted = false"),
        {"pid": project_id, "year": year})).all()
    return [TbRow(str(code), audited, opening) for code, audited, opening in rows]


async def evaluate_project(db: Any, project_id: UUID, year: int, *, leaves_only: bool = True) -> GoldResult:
    standard = await resolve_standard(db, project_id)
    configs = await load_config_rows(db, project_id, standard)
    return evaluate(configs, await load_tb_rows(db, project_id, year), standard=standard, leaves_only=leaves_only)


async def scan_all_formulas(db: Any) -> tuple[int, list[str]]:
    """全部未删 ``report_config`` 公式（各准则与 ``project:`` 行）逐条解析：返回（解析条数, 未识别项）。"""
    raw = (await db.execute(text(
        "SELECT applicable_standard, report_type::text, row_code, formula FROM report_config "
        "WHERE is_deleted = false"))).all()
    parsed, issues = 0, []
    for std, rt, code, formula in raw:
        if not (formula or "").strip():
            continue
        parsed += 1
        try:
            parse(formula)
        except Unrecognized as exc:
            issues.append(f"{std}/{rt}/{code} {formula!r}：{exc}")
    return parsed, issues
