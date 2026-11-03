"""税审底稿计算模型：加载 ``backend/data/tax_workpaper_model.json``，建依赖图，按需求值。

模型由 ``backend/scripts/gen/gen_tax_workpaper_sheets.py`` 从样表生成（只读数据，禁止手改）。
单元格键是 ``(sheet 名, 行, 列)``。「计算格」= 公式格 + 取数规则目标格；后者的值由
``tax_workpaper_fetch`` 按项目账套取得，作为依赖图的叶子传进来。

每次请求只算请求表打印区依赖到的计算格（依赖闭包），按加载时排好的拓扑序逐格求值，
不递归，因而不受依赖链长度限制；处在环上（及依赖环）的格返回 ``#CIRC!``。
"""

from __future__ import annotations

import bisect
import json
import threading
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, get_column_letter

from app.services.tax_formula_engine import (
    CIRC,
    NAME,
    FormulaSyntaxError,
    Value,
    evaluate,
    iter_refs,
    parse_formula,
)

MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "tax_workpaper_model.json"

Key = tuple[str, int, int]


def parse_a1(ref: str) -> tuple[int, int]:
    col, row = coordinate_from_string(ref)
    return row, column_index_from_string(col)


def to_a1(row: int, col: int) -> str:
    return f"{get_column_letter(col)}{row}"


def json_to_value(raw: Any) -> Value:
    if raw is None or isinstance(raw, (str, bool)):
        return raw
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    return None


class TaxWorkbook:
    def __init__(self, model: dict) -> None:
        self.model = model
        self.codes: dict[str, list[str]] = model["codes"]
        self.print_areas: dict[str, tuple[int, int, int, int] | None] = {}
        self.consts: dict[Key, Value] = {}
        self.formulas: dict[Key, tuple] = {}
        self.formula_text: dict[Key, str] = {}
        self.parse_errors: dict[Key, str] = {}
        self.rules: dict[Key, dict] = {}

        for name, sheet in model["sheets"].items():
            area = sheet.get("print")
            self.print_areas[name] = tuple(area) if area else None
            for ref, raw in sheet["cells"].items():
                row, col = parse_a1(ref)
                key = (name, row, col)
                if isinstance(raw, dict) and "f" in raw:
                    self.formula_text[key] = raw["f"]
                    try:
                        self.formulas[key] = parse_formula(raw["f"], name)
                    except FormulaSyntaxError as exc:
                        self.parse_errors[key] = str(exc)
                        self.consts[key] = NAME
                else:
                    self.consts[key] = json_to_value(raw)
        for item in model.get("rules", []):
            row, col = parse_a1(item["ref"])
            self.rules[(item["sheet"], row, col)] = item

        computed = set(self.formulas) | set(self.rules)
        self._rows_by_col: dict[tuple[str, int], list[int]] = defaultdict(list)
        for sheet, row, col in computed:
            self._rows_by_col[(sheet, col)].append(row)
        for rows in self._rows_by_col.values():
            rows.sort()

        self.deps: dict[Key, list[Key]] = {k: self._refs_to_keys(ast) for k, ast in self.formulas.items()}
        self.order, self.cyclic = self._topological_order()

    # ── 依赖图 ──
    def _refs_to_keys(self, ast: tuple) -> list[Key]:
        out: list[Key] = []
        for _, sheet, r1, c1, r2, c2 in iter_refs(ast):
            for col in range(c1, c2 + 1):
                rows = self._rows_by_col.get((sheet, col))
                if not rows:
                    continue
                lo = bisect.bisect_left(rows, r1)
                hi = bisect.bisect_right(rows, r2)
                out.extend((sheet, r, col) for r in rows[lo:hi])
        return out

    def _topological_order(self) -> tuple[dict[Key, int], set[Key]]:
        indegree = {k: 0 for k in self.formulas}
        users: dict[Key, list[Key]] = defaultdict(list)
        for key, deps in self.deps.items():
            for dep in set(deps):
                if dep in self.formulas:
                    indegree[key] += 1
                    users[dep].append(key)
        queue = deque(k for k, n in indegree.items() if n == 0)
        order: dict[Key, int] = {}
        while queue:
            key = queue.popleft()
            order[key] = len(order)
            for user in users[key]:
                indegree[user] -= 1
                if indegree[user] == 0:
                    queue.append(user)
        cyclic = set(self.formulas) - set(order)
        return order, cyclic

    def sheets_of(self, code: str) -> list[str]:
        return self.codes.get(code, [])

    def print_keys(self, sheet: str) -> list[Key]:
        """打印区内的计算格（公式格 + 取数目标格）。"""
        area = self.print_areas.get(sheet)
        out: list[Key] = []
        for key in list(self.formulas) + list(self.rules):
            if key[0] != sheet:
                continue
            if area and not (area[0] <= key[1] <= area[2] and area[1] <= key[2] <= area[3]):
                continue
            out.append(key)
        return out

    def closure(self, seeds: list[Key]) -> set[Key]:
        seen: set[Key] = set()
        stack = list(seeds)
        while stack:
            key = stack.pop()
            if key in seen:
                continue
            seen.add(key)
            stack.extend(d for d in self.deps.get(key, ()) if d not in seen)
        return seen

    def evaluate(
        self,
        needed: set[Key],
        inputs: dict[Key, Value],
        rule_values: dict[Key, Value],
    ) -> dict[Key, Value]:
        """按拓扑序求 ``needed`` 里的公式格；取数格取 ``rule_values``，手工值优先于取数与常量。"""
        results: dict[Key, Value] = {}
        wb = self

        class _Ctx:
            current: tuple[int, int] | None = None

            def cell(self, sheet: str, row: int, col: int) -> Value:
                key = (sheet, row, col)
                if key in wb.formulas:
                    if key in results:
                        return results[key]
                    return CIRC if key in wb.cyclic else None
                if key in inputs:
                    return inputs[key]
                if key in rule_values:
                    return rule_values[key]
                return wb.consts.get(key)

        ctx = _Ctx()
        for key in needed:
            if key in self.cyclic:
                results[key] = CIRC
        pending = sorted((k for k in needed if k in self.order), key=self.order.__getitem__)
        for key in pending:
            ctx.current = (key[1], key[2])  # 隐式交集按公式所在格
            ast = self.formulas[key]
            value = evaluate(ast, ctx)
            # 只引用一个空格的公式（表头 ='填写参数'!B11 这类）保持空白，Excel 会显示 0、页面上显示 0 不合适；
            # 其余公式结果为空按 Excel 显示 0
            if value is None and ast[0] != "ref":
                value = Decimal(0)
            results[key] = value
        return results

    def cell_value(self, key: Key, inputs: dict[Key, Value], rule_values: dict[Key, Value], results: dict[Key, Value]) -> Value:
        if key in self.formulas:
            return results.get(key)
        if key in inputs:
            return inputs[key]
        if key in rule_values:
            return rule_values[key]
        return self.consts.get(key)


_lock = threading.Lock()
_cached: tuple[float, TaxWorkbook] | None = None


def load_workbook(path: Path = MODEL_PATH) -> TaxWorkbook:
    """进程内缓存，模型文件更新（mtime 变化）后自动重载。"""
    global _cached
    mtime = path.stat().st_mtime
    with _lock:
        if _cached is None or _cached[0] != mtime:
            model = json.loads(path.read_text(encoding="utf-8"))
            _cached = (mtime, TaxWorkbook(model))
        return _cached[1]
