"""交付导出契约（Req 18）：公式解析为静态值 + RFC 5987 文件名编码。

交付产物（审计报告 / 财报 / 附注 / 报表 Excel）必须满足：

1. **公式解析为静态值再输出**（Req 18.1/18.2）：导出前把工作簿中残留的可重算
   公式（如模板 ``=SUM(...)`` 小计、逐行合计）就地求值成静态数值。
2. **产物不保留可重算表达式**（Req 18.3）：flatten 后单元格值不再以 ``=`` 开头。
3. **悬空引用降级导出 + 日志标注**（Req 18.4）：某公式无法求值（未知函数 /
   循环引用 / 引用越界）时，以最近一次成功计算值（若单元格已缓存数值）导出，
   否则清空该单元并在导出日志中标注该悬空引用（含 sheet!coord + 原公式）。
4. **中文文件名 RFC 5987 编码**（Req 18.5）：``filename*=UTF-8''`` 百分号编码，
   避免下载文件名乱码；同时保留纯 ASCII 回退名兼容老客户端。

设计取舍：openpyxl 本身不求值公式。财务报表模板 / 从零生成的小计单元几乎都是
``=SUM(区间)`` 或简单四则运算（引用同表已填入的静态数值），因此本模块实现一个
**受限的、同工作簿内的**公式求值器：仅支持 ``SUM()`` + 单元格引用 + 数字 + 四则
运算 + 括号，通过读取兄弟单元格的静态数值递归求值（带记忆化与环检测）。不支持的
函数一律按悬空处理（记录日志 + 降级），绝不执行任意表达式。
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import quote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RFC 5987 Content-Disposition（Req 18.5）
# ---------------------------------------------------------------------------

_DEFAULT_ASCII_FALLBACK = "download"


def content_disposition_attachment(
    filename: str, *, ascii_fallback: str | None = None
) -> str:
    """构造 RFC 5987 编码的 ``Content-Disposition`` 头值（Req 18.5）。

    平台铁律「StreamingResponse 中文文件名必须 RFC5987 编码」：HTTP 头按 latin-1
    传输，含中文的文件名若不编码会 ``UnicodeEncodeError`` 或被浏览器丢弃。返回形如::

        attachment; filename="report.xlsx"; filename*=UTF-8''%E6%8A%A5%E8%A1%A8.xlsx

    - ``filename="..."``：纯 ASCII 回退名，供不支持 ``filename*`` 的老客户端。
    - ``filename*=UTF-8''...``：RFC 5987 百分号编码的真实名（含中文可正确解码还原）。

    Args:
        filename: 原始（可能含中文）文件名。
        ascii_fallback: 显式 ASCII 回退名；缺省时从 filename 剥离非 ASCII 字符生成。
    """
    fn = (filename or "").strip() or _DEFAULT_ASCII_FALLBACK
    if ascii_fallback:
        ascii_name = ascii_fallback
    else:
        ascii_name = fn.encode("ascii", "ignore").decode().strip() or _DEFAULT_ASCII_FALLBACK
    # 去掉 ASCII 回退名中会破坏 quoted-string 的双引号
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    # quote(safe="") 对 attr-char 集合之外的所有字符（含空格 / 反斜杠 / 引号）编码
    fn_utf8 = quote(fn, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{fn_utf8}"


# ---------------------------------------------------------------------------
# 公式解析为静态值（Req 18.1/18.2/18.3/18.4）
# ---------------------------------------------------------------------------

# 单元格引用（可含 $ 绝对引用 + 可选 sheet 限定：Sheet1!A1 或 'My Sheet'!A1）
_SHEET_PREFIX = r"(?:'[^']+'|[A-Za-z0-9_\u4e00-\u9fff]+)!"
_CELL_REF_RE = re.compile(
    r"(?P<sheet>" + _SHEET_PREFIX + r")?\$?(?P<col>[A-Za-z]{1,3})\$?(?P<row>\d+)"
)
# 剩余的函数调用（SUM 展开后仍出现 => 不支持）
_FUNC_CALL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\(")


@dataclass
class DanglingRef:
    """一处无法求值的公式（悬空引用）。"""

    location: str  # "SheetName!C31"
    formula: str  # 原始公式字符串
    reason: str


@dataclass
class FlattenResult:
    """flatten 汇总结果。"""

    flattened: int = 0
    dangling: list[DanglingRef] = field(default_factory=list)

    @property
    def dangling_count(self) -> int:
        return len(self.dangling)


def flatten_workbook_formulas(wb, *, log: logging.Logger | None = None) -> FlattenResult:
    """把工作簿中所有残留公式就地解析为静态值（Req 18.1/18.2/18.3）。

    Args:
        wb: openpyxl ``Workbook``。
        log: 记录悬空引用的 logger（缺省用本模块 logger）。

    Returns:
        FlattenResult：成功 flatten 数 + 悬空引用清单。
    """
    _log = log or logger
    result = FlattenResult()
    evaluator = _WorkbookEvaluator(wb, result, _log)
    for ws in wb.worksheets:
        # 快照公式单元坐标（求值过程中会改写 value，避免边遍历边改）
        formula_cells: list = []
        for row in ws.iter_rows():
            for cell in row:
                if _is_formula_value(cell.value):
                    formula_cells.append(cell)
        for cell in formula_cells:
            original = cell.value
            if not _is_formula_value(cell.value):
                # 可能已被依赖求值链改写
                continue
            location = f"{ws.title}!{cell.coordinate}"
            value = evaluator.evaluate(ws, original, location)
            if value is None:
                # 悬空：优先用最近一次成功计算值（openpyxl 缓存值），否则清空
                cached = _cached_value(cell)
                cell.value = cached
                result.dangling.append(
                    DanglingRef(location=location, formula=str(original), reason="unresolved")
                )
                _log.warning(
                    "交付导出悬空引用：%s 公式 %r 无法求值，以最近计算值 %r 降级导出",
                    location,
                    original,
                    cached,
                )
            else:
                cell.value = value
                result.flattened += 1
    if result.dangling:
        _log.info(
            "交付导出 flatten 完成：解析 %d 个公式为静态值，%d 处悬空引用降级",
            result.flattened,
            result.dangling_count,
        )
    return result


def _is_formula_value(value) -> bool:
    """单元格是否承载可重算公式表达式。"""
    return isinstance(value, str) and value.startswith("=")


def _cached_value(cell):
    """读取 openpyxl 缓存的最近计算值（若无则 None）。

    openpyxl 以非 data_only 模式加载时 ``cell.value`` 为公式串；部分模板会在
    ``cell._value`` 之外携带缓存结果，但通常不可得——此时返回 None（清空）。
    """
    for attr in ("_cached_value",):
        cached = getattr(cell, attr, None)
        if isinstance(cached, (int, float)):
            return float(cached)
    return None


class _WorkbookEvaluator:
    """受限的同工作簿公式求值器（SUM + 引用 + 四则运算）。"""

    def __init__(self, wb, result: FlattenResult, log: logging.Logger):
        self.wb = wb
        self.result = result
        self.log = log
        self._memo: dict[tuple[str, str], float | None] = {}
        self._in_progress: set[tuple[str, str]] = set()

    # -- 公开入口：求值一个公式字符串 --------------------------------------
    def evaluate(self, ws, formula: str, location: str) -> float | None:
        try:
            return self._eval_formula(ws, formula)
        except _DanglingError as exc:
            self.log.debug("公式 %s 求值失败：%s", location, exc)
            return None
        except Exception as exc:  # pragma: no cover - 防御
            self.log.debug("公式 %s 求值异常：%s", location, exc)
            return None

    # -- 单元格取值（递归 + 记忆化 + 环检测）-------------------------------
    def _cell_value(self, ws, coord: str) -> float:
        key = (ws.title, coord.upper())
        if key in self._memo:
            cached = self._memo[key]
            return cached if cached is not None else 0.0
        if key in self._in_progress:
            raise _DanglingError(f"circular reference at {coord}")
        try:
            cell = ws[coord]
        except (ValueError, KeyError) as exc:
            raise _DanglingError(f"invalid ref {coord}: {exc}") from exc
        raw = cell.value
        if raw is None:
            self._memo[key] = 0.0
            return 0.0  # 空单元 Excel 语义视作 0
        if isinstance(raw, bool):
            val = 1.0 if raw else 0.0
            self._memo[key] = val
            return val
        if isinstance(raw, (int, float)):
            val = float(raw)
            self._memo[key] = val
            return val
        if _is_formula_value(raw):
            self._in_progress.add(key)
            try:
                val = self._eval_formula(ws, raw)
            finally:
                self._in_progress.discard(key)
            self._memo[key] = val
            return val if val is not None else 0.0
        # 文本单元：Excel 在算术上下文按 0 处理
        self._memo[key] = 0.0
        return 0.0

    def _resolve_ws(self, ws, sheet_token: str | None):
        if not sheet_token:
            return ws
        name = sheet_token.rstrip("!")
        if name.startswith("'") and name.endswith("'"):
            name = name[1:-1]
        if name in self.wb.sheetnames:
            return self.wb[name]
        raise _DanglingError(f"unknown sheet {name}")

    # -- 公式求值 ----------------------------------------------------------
    def _eval_formula(self, ws, formula: str) -> float | None:
        expr = formula[1:] if formula.startswith("=") else formula
        expr = expr.strip()
        if not expr:
            return None
        # 展开所有 SUM(...) 为数值
        expr = self._expand_sum(ws, expr)
        # 展开后若仍有函数调用 → 不支持
        if _FUNC_CALL_RE.search(expr):
            raise _DanglingError(f"unsupported function in {expr!r}")
        # 替换剩余单元格引用为数值
        expr = self._replace_refs(ws, expr)
        return _safe_arith_eval(expr)

    def _expand_sum(self, ws, expr: str) -> str:
        """把 ``SUM(...)`` 展开为数值字面量（支持区间 / 引用 / 数字 / 逗号分隔）。"""
        while True:
            m = re.search(r"SUM\s*\(", expr, flags=re.IGNORECASE)
            if not m:
                return expr
            open_idx = expr.index("(", m.start())
            close_idx = _matching_paren(expr, open_idx)
            if close_idx < 0:
                raise _DanglingError(f"unbalanced SUM parens in {expr!r}")
            inner = expr[open_idx + 1 : close_idx]
            total = self._sum_terms(ws, inner)
            expr = expr[: m.start()] + repr(total) + expr[close_idx + 1 :]

    def _sum_terms(self, ws, inner: str) -> float:
        total = 0.0
        for term in _split_top_level(inner, ","):
            term = term.strip()
            if not term:
                continue
            if ":" in term:  # 区间 A5:A10（可含 sheet 限定）
                total += self._sum_range(ws, term)
                continue
            m = _CELL_REF_RE.fullmatch(term)
            if m:
                target = self._resolve_ws(ws, m.group("sheet"))
                total += self._cell_value(target, f"{m.group('col')}{m.group('row')}")
                continue
            try:
                total += float(term)
            except ValueError as exc:
                raise _DanglingError(f"unsupported SUM term {term!r}") from exc
        return total

    def _sum_range(self, ws, range_token: str) -> float:
        sheet_token = None
        rng = range_token
        if "!" in range_token:
            sheet_token, rng = range_token.split("!", 1)
            sheet_token += "!"
        target = self._resolve_ws(ws, sheet_token)
        rng = rng.replace("$", "").strip()
        try:
            cells = target[rng]
        except (ValueError, KeyError, TypeError) as exc:
            raise _DanglingError(f"invalid range {range_token!r}: {exc}") from exc
        total = 0.0
        # target[rng] 可能是单元 / 一维元组 / 二维元组
        for cell in _iter_cells(cells):
            total += self._cell_value(target, cell.coordinate)
        return total

    def _replace_refs(self, ws, expr: str) -> str:
        def _sub(m: re.Match) -> str:
            target = self._resolve_ws(ws, m.group("sheet"))
            value = self._cell_value(target, f"{m.group('col')}{m.group('row')}")
            return repr(value)

        return _CELL_REF_RE.sub(_sub, expr)


class _DanglingError(Exception):
    """公式无法求值（悬空）。"""


def _iter_cells(cells):
    """把 openpyxl ``ws[range]`` 的返回（单元 / 一维 / 二维元组）拍平为单元序列。"""
    if isinstance(cells, tuple):
        for item in cells:
            if isinstance(item, tuple):
                yield from item
            else:
                yield item
    else:
        yield cells


def _matching_paren(s: str, open_idx: int) -> int:
    """返回与 ``s[open_idx]='('`` 匹配的右括号下标；无匹配返回 -1。"""
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top_level(s: str, sep: str) -> list[str]:
    """按顶层分隔符切分（忽略括号内的分隔符）。"""
    parts: list[str] = []
    depth = 0
    current = []
    for ch in s:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


# 允许的 AST 节点：数字常量 + 四则运算 + 一元正负 + 括号
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub)


def _safe_arith_eval(expr: str) -> float | None:
    """安全求值纯算术表达式（仅数字 + ``+ - * /`` + 括号）。

    引用与 SUM 已在上游替换为数值字面量。禁止名称 / 调用 / 属性等一切非算术节点。
    """
    expr = expr.strip()
    if not expr:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise _DanglingError(f"syntax error in {expr!r}") from exc

    def _eval(node) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise _DanglingError(f"non-numeric constant {node.value!r}")
            return float(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            # Div
            if right == 0:
                raise _DanglingError("division by zero")
            return left / right
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARYOPS):
            operand = _eval(node.operand)
            return operand if isinstance(node.op, ast.UAdd) else -operand
        raise _DanglingError(f"unsupported expression node {type(node).__name__}")

    return _eval(tree)
