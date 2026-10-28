"""附注公式：逐表目标、按表结构生成的预设公式、严格求值（spec note-pull-header-formula-closure R3 / ADR-4）。

公式目标带表维度：第 1 张表 ``行:列``（兼容旧数据），第 n+1 张 ``t{n}:行:列``；行、列从 0 起，列不含标签列
（与 ``values`` 下标一致）。多表章节读 ``_tables``（编辑器与 Word 实际读取的位置），单表章节读顶层。

预设公式按每张表**当前**结构现算、不落库（按行号指格的公式落库后，增删行会指错格）：

* 合计 / 小计：合计构成只在判得准时生成（``note_total_terms.total_terms``，单体 / 合并 / 前端共用的唯一判定：
  单个合计、「其中：」标记、「小计 / 减：X / 合计」、多段小计 + 合计、标题式小计；判不准的回原因给公式管理）。
  只加金额列（标题行库判为比例 / 说明的列不加）。
* 账面价值 = 账面余额 − 坏账 / 减值 / 跌价准备、累计折旧 / 摊销（同一期间各自认得出才生成）。

变动表「期末 = 期初 + 增加 − 减少」是审核勾稽，不当自动运算（期末是审定数，不由变动倒算）。

求值严格（``evaluate``）：引用的单元格都没有数 ⇒ 不写、回原因（原先写 0，会盖掉公式推送按审定数写入的合计）；
算式写法认不出 / 除数为 0 / 跨表引用取不到 ⇒ 不写、回原因。支持 ``cell(行,列)``、``SUM(起:止, 列)``、数字与
+ − × ÷ 括号；跨表引用（TB / REPORT / WP / NOTE / PRIOR / AGING）由调用方传入的取数函数代入。
"""
from __future__ import annotations

import ast
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable

from app.services.consol_note_table_totals import to_decimal
from app.services.note_total_terms import plan_description, row_kind, sum_terms, total_order, total_terms

__all__ = [
    "CROSS_REF_RE", "book_value_columns", "describe_target", "evaluate", "formula_key", "formula_targets",
    "iter_note_tables", "parse_formula_key", "row_kind", "section_preset_formulas", "table_order",
    "recalc_table_totals", "table_preset_formulas", "target_issues", "total_terms",
]

_KEY_RE = re.compile(r"^\s*(?:[tT](\d+)\s*:\s*)?(\d+)\s*:\s*(\d+)\s*$")
_CELL_RE = re.compile(r"cell\(\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)
_SUM_RE = re.compile(r"SUM\(\s*(\d+)\s*:\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)
#: 跨表引用 token（与 ``note_formula_generator._exec_cross_table`` 同一组函数）
CROSS_REF_RE = re.compile(r"(?:TB|REPORT|WP|NOTE|PRIOR|AGING)\([^)]*\)")

#: 准备类计量（账面价值 = 账面余额 − 这些列）
_PROVISION_WORDS = ("坏账准备", "减值准备", "跌价准备", "累计折旧", "累计摊销")
#: 毛额计量的补充写法（词表 gross_measures 只登记了「账面余额」）
_EXTRA_GROSS = frozenset({("原值",), ("原价",), ("账面原值",)})


# ─── 目标键 ──────────────────────────────────────────────────────────────────


def formula_key(table_index: int, row: int, col: int) -> str:
    """第 1 张表 ``行:列``（兼容旧数据），其余 ``t{n}:行:列``。"""
    return f"{row}:{col}" if table_index == 0 else f"t{table_index}:{row}:{col}"


def parse_formula_key(key: Any) -> tuple[int, int, int] | None:
    """``行:列`` / ``t{n}:行:列`` → (表, 行, 列)；不是单元格目标 → None。"""
    m = _KEY_RE.match(str(key or ""))
    if not m:
        return None
    return int(m.group(1) or 0), int(m.group(2)), int(m.group(3))


def iter_note_tables(td: Any) -> list[tuple[int, dict]]:
    """章节的表格：有 ``_tables`` 用 ``_tables``（下标与存储一致），否则顶层就是唯一一张表。"""
    if not isinstance(td, dict):
        return []
    tables = td.get("_tables")
    if isinstance(tables, list) and tables:
        return [(i, t) for i, t in enumerate(tables) if isinstance(t, dict)]
    return [(0, td)]


# ─── 行 / 列分类 ──────────────────────────────────────────────────────────────


def _column_keys(table: dict) -> list[Any]:
    from app.services.note_table_header_library import column_keys

    try:
        return column_keys(table)
    except Exception:  # noqa: BLE001 —— 表头坏了不生成预设，不阻断执行
        return []


def amount_columns(table: dict) -> list[int]:
    """金额列（``values`` 下标）：标题行库判为比例 / 说明的列不加总。"""
    return [k.index - 1 for k in _column_keys(table)[1:] if k.kind == "amount"]


def book_value_columns(table: dict) -> list[tuple[int, int, tuple[int, ...]]]:
    """``(账面价值列, 账面余额列, 准备列…)``（``values`` 下标）：同一期间各自唯一才算。"""
    from app.services.note_table_header_library import load_vocabulary

    vocab = load_vocabulary()
    by_period: dict[Any, list[Any]] = {}
    for k in _column_keys(table)[1:]:
        if k.kind == "amount" and k.measure:
            by_period.setdefault(k.period, []).append(k)
    out: list[tuple[int, int, tuple[int, ...]]] = []
    for keys in by_period.values():
        nets = [k for k in keys if k.measure in vocab.net_measures]
        gross = [k for k in keys if k.measure in vocab.gross_measures or k.measure in _EXTRA_GROSS]
        provisions = [k for k in keys if any(w in "".join(k.measure) for w in _PROVISION_WORDS)]
        if len(nets) == 1 and len(gross) == 1 and provisions:
            out.append((nets[0].index - 1, gross[0].index - 1, tuple(p.index - 1 for p in provisions)))
    return out


# ─── 预设公式 ─────────────────────────────────────────────────────────────────


def _sum_expression(terms: list[tuple[int, int]], col: int) -> str:
    rows = [r for r, _s in terms]
    if all(s == 1 for _r, s in terms) and len(rows) > 1 and rows == list(range(rows[0], rows[-1] + 1)):
        return f"SUM({rows[0]}:{rows[-1]}, {col})"
    parts = []
    for i, (r, s) in enumerate(terms):
        op = "" if i == 0 and s == 1 else (" + " if s == 1 else (" - " if i else "-"))
        parts.append(f"{op}cell({r},{col})")
    return "".join(parts)


def _preset(table_index: int, ftype: str, expression: str, description: str, source: str) -> dict[str, Any]:
    return {"type": ftype, "expression": expression, "description": description, "category": "auto_calc",
            "source": source, "binding_id": None, "table_index": table_index}


def table_preset_formulas(table: dict, table_index: int) -> tuple[dict[str, dict], list[dict]]:
    """一张表的预设公式 + 没生成的说明（``[{table_index, row, reason}]``）。"""
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    formulas: dict[str, dict] = {}
    notes: list[dict] = []
    if not rows:
        return formulas, notes
    amounts = amount_columns(table)
    plans, reasons = total_terms(rows)
    for r, why in sorted(reasons.items()):
        notes.append({"table_index": table_index, "row": r, "reason": why})
    for r, terms in sorted(plans.items()):
        if not amounts:
            notes.append({"table_index": table_index, "row": r, "reason": "没有金额列"})
            continue
        label = str(rows[r].get("label") or "合计").strip()
        description = f"{label} = {plan_description(rows, terms)}"
        for col in amounts:
            formulas[formula_key(table_index, r, col)] = _preset(
                table_index, "vertical_sum", _sum_expression(terms, col), description, "preset.total")
    for value_col, gross_col, provisions in book_value_columns(table):
        expr_tail = "".join(f" - cell({{r}},{p})" for p in provisions)
        for r, row in enumerate(rows):
            if row_kind(row) not in ("data", "sub", "total", "subtotal"):
                continue
            key = formula_key(table_index, r, value_col)
            if key in formulas:
                continue  # 合计行已按明细之和算
            formulas[key] = _preset(table_index, "book_value", f"cell({r},{gross_col})" + expr_tail.format(r=r),
                                    "账面价值 = 账面余额 − 准备", "preset.book_value")
    return formulas, notes


def section_preset_formulas(td: Any) -> tuple[dict[str, dict], list[dict]]:
    """章节各表的预设公式（逐表、按当前结构）+ 没生成的说明。

    执行器（``execute_note_formulas``）、公式管理预览、覆盖率统计（``compute_formula_coverage``）共用这一套。旧生成器
    （``generate_formulas_for_table``）只补明细行取数公式（行上带 ``account_codes`` / ``report_row_code`` 时的 TB / REPORT），
    且同一目标以按结构生成的为准；不再把 ``_check_presets`` 的英文预设名传给它 —— 它的求和不分段、「其中」与减项都加，
    原先同目标覆盖按结构生成的合计（spec note-pull-followup-closure R8）。
    """
    from app.services.note_formula_generator import generate_formulas_for_table

    formulas: dict[str, dict] = {}
    notes: list[dict] = []
    for t, table in iter_note_tables(td):
        f, n = table_preset_formulas(table, t)
        formulas.update(f)
        notes.extend(n)
        try:
            legacy = generate_formulas_for_table(
                {"headers": table.get("headers") or [], "rows": table.get("rows") or []}, [])
        except Exception:  # noqa: BLE001 —— 旧生成器失败不影响按结构生成的预设
            legacy = {}
        amounts = set(amount_columns(table)) if legacy else set()
        for key, fdef in legacy.items():
            parsed = parse_formula_key(key)
            if parsed and parsed[2] in amounts:  # 旧生成器按「期末 / 期初」字样认列，比例 / 说明列不取数
                formulas.setdefault(formula_key(t, parsed[1], parsed[2]), {**fdef, "table_index": t})
    return formulas, notes


def recalc_table_totals(table: dict, *, value_columns: int | None = None) -> int:
    """按合计构成回填一张表的合计 / 小计行 → 改了几格。

    只写判得准的合计行、金额列、自动格（``_cell_modes`` 手工 / 锁定格不动）；构成里的格全空不写（不写 0）。没有表头的
    旧表（表头读时才投影）按 ``value_columns`` 列全算。
    """
    rows = table.get("rows") if isinstance(table, dict) else None
    if not isinstance(rows, list) or not rows:
        return 0
    plans, _reasons = total_terms(rows)
    if not plans:
        return 0
    if table.get("headers"):
        columns = amount_columns(table)
    else:
        width = value_columns if value_columns is not None else max(
            (len(r.get("values") or []) for r in rows if isinstance(r, dict)), default=0)
        columns = list(range(width))
    changed = 0
    for r in total_order(rows, plans):
        row = rows[r]
        values = row.get("values")
        if not isinstance(values, list):
            continue
        modes = row.get("_cell_modes") if isinstance(row.get("_cell_modes"), dict) else {}
        for c in columns:
            if c >= len(values) or str(modes.get(str(c), "auto")) != "auto":
                continue
            total = sum_terms(plans[r], lambda i, c=c: _cell(rows, i, c))
            if total is None:
                continue
            new = float(total)
            old = to_decimal(values[c])
            if old is not None and abs(old - total) < Decimal("0.005"):
                continue
            values[c] = new
            changed += 1
    return changed


# ─── 严格求值 ─────────────────────────────────────────────────────────────────


def _cell(rows: list[Any], r: int, c: int) -> Decimal | None:
    if not 0 <= r < len(rows) or not isinstance(rows[r], dict):
        return None
    values = rows[r].get("values")
    return to_decimal(values[c]) if isinstance(values, list) and 0 <= c < len(values) else None


def _arith(node: ast.AST, literals: list[Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _arith(node.body, literals)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Decimal(str(node.value))
    if isinstance(node, ast.Name) and node.id.startswith("__v") and node.id[3:].isdigit():
        return literals[int(node.id[3:])]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _arith(node.operand, literals)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left, right = _arith(node.left, literals), _arith(node.right, literals)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise ZeroDivisionError
        return left / right
    raise ValueError(type(node).__name__)


def evaluate(expression: Any, rows: list[Any],
             resolve_cross: Callable[[str], Any] | None = None) -> tuple[Decimal | None, str | None]:
    """求值 → ``(值, None)`` 或 ``(None, 原因)``。表内引用空格按 0 参与运算，但引用的格全空时不出值。"""
    text = str(expression or "").strip()
    if text.startswith("="):
        text = text[1:].strip()
    if not text:
        return None, "公式为空"
    literals: list[Decimal] = []
    missing: list[str] = []
    counts = {"refs": 0, "filled": 0}

    def lit(value: Decimal) -> str:
        literals.append(value)
        return f"__v{len(literals) - 1}"

    def cross(m: re.Match[str]) -> str:
        raw = resolve_cross(m.group(0)) if resolve_cross else None
        value = to_decimal(raw)
        if value is None:
            missing.append(m.group(0))
            return lit(Decimal(0))
        counts["filled"] += 1
        return lit(value)

    def summed(m: re.Match[str]) -> str:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        total = Decimal(0)
        for r in range(min(a, b), max(a, b) + 1):
            counts["refs"] += 1
            value = _cell(rows, r, c)
            if value is not None:
                total += value
                counts["filled"] += 1
        return lit(total)

    def cell(m: re.Match[str]) -> str:
        counts["refs"] += 1
        value = _cell(rows, int(m.group(1)), int(m.group(2)))
        if value is None:
            return lit(Decimal(0))
        counts["filled"] += 1
        return lit(value)

    text = CROSS_REF_RE.sub(cross, text)
    text = _SUM_RE.sub(summed, text)
    text = _CELL_RE.sub(cell, text)
    if missing:
        return None, f"取不到 {'、'.join(dict.fromkeys(missing))}"
    if counts["refs"] and not counts["filled"]:
        return None, "引用的单元格都没有数"
    try:
        return _arith(ast.parse(text, mode="eval"), literals), None
    except ZeroDivisionError:
        return None, "除数为 0"
    except (SyntaxError, ValueError, TypeError, InvalidOperation, IndexError, RecursionError):
        return None, "算式写法无法识别（支持 cell(行,列)、SUM(起:止, 列)、数字与 + - * / 括号及跨表取数）"


def _deps(expression: Any) -> set[tuple[int, int]]:
    text = str(expression or "")
    out = {(int(m.group(1)), int(m.group(2))) for m in _CELL_RE.finditer(text)}
    for m in _SUM_RE.finditer(text):
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        out.update((r, c) for r in range(min(a, b), max(a, b) + 1))
    return out


def table_order(cells: dict[tuple[int, int], Any]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """同一张表内的执行顺序（被引用的格先算）→ ``(顺序, 循环引用的格)``；``cells`` = {(行, 列): 表达式}。"""
    pending = {cell: _deps(expr) & set(cells) - {cell} for cell, expr in cells.items()}
    order: list[tuple[int, int]] = []
    while pending:
        ready = sorted(cell for cell, deps in pending.items() if not deps)
        if not ready:
            return order, sorted(pending)
        for cell in ready:
            order.append(cell)
            pending.pop(cell)
        for deps in pending.values():
            deps.difference_update(ready)
    return order, []


# ─── 可读目标 / 目标清单 / 保存校验 ────────────────────────────────────────────


def _table_name(table: dict, index: int) -> str:
    return str(table.get("name") or table.get("title") or "").strip() or f"第 {index + 1} 张表"


def _column_labels(table: dict) -> list[str]:
    """逐列表头路径（「账面余额/金额」）：标题行库口径，取不到用平表头。"""
    paths = [k.label for k in _column_keys(table)[1:]]
    headers = table.get("headers") if isinstance(table.get("headers"), list) else []
    flat = [str(h or "").strip() for h in headers[1:]]
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    width = max(len(flat), len(paths), max((len(r.get("values") or []) for r in rows if isinstance(r, dict)), default=0))
    return [(paths[c] if c < len(paths) and paths[c] else "") or (flat[c] if c < len(flat) else "") or f"第 {c + 1} 列"
            for c in range(width)]


def formula_targets(td: Any) -> list[dict[str, Any]]:
    """公式弹窗的目标清单：逐表 ``{index, name, rows: [行名], columns: [列名]}``（下标即目标串里的数字）。"""
    out: list[dict[str, Any]] = []
    for t, table in iter_note_tables(td):
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        out.append({
            "index": t,
            "name": _table_name(table, t),
            "rows": [(str(r.get("label") or "").strip() if isinstance(r, dict) else "") or f"第 {i + 1} 行"
                     for i, r in enumerate(rows)],
            "columns": _column_labels(table),
        })
    return out


def describe_target(td: Any, target: Any, catalog: list[dict[str, Any]] | None = None) -> str:
    """``t1:3:0`` → 「表名 · 行名 · 列名」；认不出 / 超出范围原样返回。``catalog`` = 已算好的 ``formula_targets``。"""
    parsed = parse_formula_key(target)
    tables = {t["index"]: t for t in (catalog if catalog is not None else formula_targets(td))}
    if parsed is None or parsed[0] not in tables:
        return str(target or "")
    t, r, c = parsed
    table = tables[t]
    if not (0 <= r < len(table["rows"]) and 0 <= c < len(table["columns"])):
        return str(target)
    return f"{table['name']} · {table['rows'][r]} · {table['columns'][c]}"


def target_issues(td: Any, records: Iterable[Any]) -> list[dict[str, str]]:
    """保存前校验目标单元格：有公式却没目标 / 目标不是单元格 / 超出表格 ⇒ ``[{target, message}]``。"""
    tables = {t["index"]: t for t in formula_targets(td)}
    issues: list[dict[str, str]] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        expr = rec.get("formula") if rec.get("formula") is not None else rec.get("expression")
        if not str(expr or "").strip():
            continue
        target = str(rec.get("target") or rec.get("target_cell") or "").strip()
        label = target or f"第 {i + 1} 条"
        parsed = parse_formula_key(target)
        if not target:
            issues.append({"target": label, "message": "没有选择目标单元格（表 / 行 / 列）"})
        elif parsed is None:
            issues.append({"target": label, "message": "目标不是单元格（应为「行:列」或「t表号:行:列」）"})
        elif parsed[0] not in tables:
            issues.append({"target": label, "message": f"章节没有第 {parsed[0] + 1} 张表"})
        else:
            table = tables[parsed[0]]
            if parsed[1] >= len(table["rows"]) or parsed[2] >= len(table["columns"]):
                issues.append({"target": label, "message": (
                    f"超出「{table['name']}」（{len(table['rows'])} 行 × {len(table['columns'])} 列）")})
    return issues
