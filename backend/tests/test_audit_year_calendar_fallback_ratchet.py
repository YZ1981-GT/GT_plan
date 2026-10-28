"""拿不到审计年度时用今年 / 写死年度 —— 后端棘轮（spec audit-year-calendar-fallback-ratchet 任务 1）。

审计年度应经单一来源 ``app.services.project_audit_year``（审计年度 → 审计期末 → 向导 → 项目名后缀）取，取不到
如实返回「未设置审计年度」。直接用今天的年份或写死的 2025 兜底，跨年审计、往年项目、新项目未填年度时会静默
取 / 写别的年度（如 ``routers/wp_prefill_preview.py`` 项目没有审计期末时按 2025 预填）。

口径（AST，注释与 docstring 天然不计），``backend/app`` 下：
1. 今天的年份：``datetime.now(...).year`` / ``datetime.utcnow().year`` / ``datetime.today().year`` / ``date.today().year``
   （含 ``datetime.datetime.now()``、``__import__("datetime").datetime.now()`` 等前缀写法，减不减 1 都算）；
2. 写死年度（2000~2099 的整数字面量）出现在：名字含 year 的参数默认值（含 ``Query(2025)`` / ``Field(2025)``）、
   名字含 year 的变量 / 属性赋值、``x or 2025``（``or`` 前面的操作数里有 year）、``x if … else 2025``（条件或取值里有 year）、
   ``.get("…year…", 2025)`` / ``getattr(x, "…year…", 2025)``。
盲区：先把 ``datetime.now()`` 存进变量再取 ``.year`` 不计（与日期计算同形）。

2026-10-25 现算按文件冻结在 ``BASELINE``：新增（基线外的文件、或文件里比基线多）⇒ 红；变少 ⇒ 红（把基线下调到
现算值，为 0 删掉条目 —— 基线只许变小；只是挪动代码时把条目一起挪过去，总数不得超过 ``FROZEN_TOTAL_CAP``）。
日历本身就该取今年的地方（独立性年度声明、趋势图年份上限等）同样冻结在表里，逐处判定见 spec 任务 2。
"""

from __future__ import annotations

import ast
import functools
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
_TODAY_FUNCS = frozenset({"now", "utcnow", "today"})
_PARAM_MARKERS = frozenset({"Query", "Field", "Form", "Body", "Path", "Header", "Cookie"})

#: 冻结时的总数（挪动可以，净增不行）。
#: 2026-10-25 冻结 130；任务 2.2 CALENDAR 日历用途 17 处移入豁免表 → 113。
#: 任务 5.2 全部 literal 命中清零 + 并发会话已修 → 22。
#: 任务 6.1：16 处审计年度兜底清零 + 4 处日历移入豁免 → 基线清空。
FROZEN_TOTAL_CAP = 0

#: 日历用途豁免表（spec 任务 2.2 + 6.1）：趋势图终点、EQCR 指标当年、导入年度探测默认值、
#: 独立性声明当年、递延税计算到期年等，本就该取今天的年份而非审计年度。
#: 豁免须可证伪：文件仍命中扫描口径。
CALENDAR_YEAR_EXEMPT: dict[str, tuple[int, str]] = {
    "routers/eqcr/independence.py": (1, "独立性声明端点年度默认当年"),
    "routers/eqcr/metrics.py": (1, "EQCR 指标默认年度（当年）"),
    "routers/eqcr_snapshot.py": (3, "EQCR 快照默认年度（审上年 ×3 端点）"),
    "routers/eqcr_trends.py": (1, "趋势图终点年度"),
    "routers/import_intelligence.py": (3, "导入智能分析端点 Query(2025)（年度探测）"),
    "routers/import_templates.py": (1, "导入模板端点 Query(2025)（年度探测）"),
    "routers/independence.py": (1, "独立性声明待签项目列表按当年过滤"),
    "routers/wp_render_strategies/_g10_disclosure_io.py": (2, "G10 披露 IO 空模板工作簿表头年度"),
    "services/client_quality_trend_service.py": (1, "客户质量趋势终点"),
    "services/dashboard_aggregator_service.py": (2, "看板审计年度兜底（无 audit_period_end 时）"),
    "services/eqcr_independence_service.py": (2, "年度独立性声明查询/提交按当年"),
    "services/ledger_import/pipeline.py": (1, "导入管线年度兜底"),
    "services/ledger_import/year_detector.py": (1, "导入年度探测 P5 默认值"),
    "services/n1_deferred_tax_assets_service.py": (1, "可弥补亏损到期计算须用真实当前年度"),
    "services/smart_import_engine.py": (2, "智能导入年度探测兜底（2 处）"),
}

#: 现算冻结（相对 backend/app）：只许变小。CALENDAR 类已移入 CALENDAR_YEAR_EXEMPT。
#: 任务 5.2 清零全部 literal 命中；并发会话已清零的同步下调。
#: 任务 6.1：16 处审计年度兜底改单一来源（清零），4 处日历用途移入豁免表。基线清空。
BASELINE: dict[str, int] = {}


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
        parts.append("__import__")
    return ".".join(reversed(parts))


def _is_today_year(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Attribute) and node.attr == "year" and isinstance(node.value, ast.Call)):
        return False
    func = node.value.func
    if not (isinstance(func, ast.Attribute) and func.attr in _TODAY_FUNCS):
        return False
    return _dotted(func.value).rsplit(".", 1)[-1] in ("datetime", "date")


def _year_literal(node: ast.AST | None) -> ast.Constant | None:
    if isinstance(node, ast.Constant) and type(node.value) is int and 2000 <= node.value <= 2099:
        return node
    return None


def _default_literal(node: ast.AST | None) -> ast.Constant | None:
    """参数默认值 / 字段默认值里的写死年度：字面量本身，或 ``Query(2025)`` / ``Field(default=2025)``。"""
    hit = _year_literal(node)
    if hit is not None or not isinstance(node, ast.Call):
        return hit
    if _dotted(node.func).rsplit(".", 1)[-1] not in _PARAM_MARKERS:
        return None
    if node.args and (hit := _year_literal(node.args[0])) is not None:
        return hit
    return next((h for kw in node.keywords if kw.arg == "default" and (h := _year_literal(kw.value))), None)


def _mentions_year(node: ast.AST) -> bool:
    return "year" in ast.unparse(node).lower()


def _target_mentions_year(target: ast.AST) -> bool:
    if isinstance(target, ast.Name):  # 全大写常量（``_MIN_YEAR = 2000`` 这类校验边界）不是兜底
        return "year" in target.id.lower() and not target.id.isupper()
    if isinstance(target, ast.Attribute):
        return "year" in target.attr.lower()
    return False


def _param_defaults(args: ast.arguments) -> list[tuple[ast.arg, ast.AST | None]]:
    positional = [*args.posonlyargs, *args.args]
    pairs = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
    return pairs + list(zip(args.kwonlyargs, args.kw_defaults))


def scan_source(source: str) -> Counter[str]:
    """一个文件里两类写法的出现次数（同一个节点只计一次）。"""
    tree = ast.parse(source)
    today: set[int] = set()
    literal: set[int] = set()
    for node in ast.walk(tree):
        if _is_today_year(node):
            today.add(id(node))
        hits: list[ast.Constant | None] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            hits += [_default_literal(d) for a, d in _param_defaults(node.args) if "year" in a.arg.lower()]
        elif isinstance(node, ast.Assign):
            if any(_target_mentions_year(t) for t in node.targets):
                hits.append(_year_literal(node.value))
        elif isinstance(node, ast.AnnAssign):
            if _target_mentions_year(node.target):
                hits.append(_default_literal(node.value))
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for i, value in enumerate(node.values[1:], 1):
                if any(_mentions_year(v) for v in node.values[:i]):
                    hits.append(_year_literal(value))
        elif isinstance(node, ast.IfExp):
            if _mentions_year(node.test) or _mentions_year(node.body):
                hits.append(_year_literal(node.orelse))
        elif isinstance(node, ast.Call):
            name = _dotted(node.func)
            key_pos = 0 if name.endswith(".get") else 1 if name == "getattr" else None
            if key_pos is not None and len(node.args) > key_pos + 1:
                key = node.args[key_pos]
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and "year" in key.value.lower():
                    hits.append(_year_literal(node.args[key_pos + 1]))
        literal.update(id(h) for h in hits if h is not None)
    return Counter({k: v for k, v in (("today", len(today)), ("literal", len(literal))) if v})


@functools.cache
def scan_app() -> tuple[int, dict[str, Counter[str]]]:
    files = sorted(APP.rglob("*.py"))
    found: dict[str, Counter[str]] = {}
    for file in files:
        counts = scan_source(file.read_text(encoding="utf-8-sig"))  # 个别源码带 BOM
        if counts:
            found[file.relative_to(APP).as_posix()] = counts
    return len(files), found


_COUNTED = '''
from datetime import date, datetime, timezone
import datetime as dt
from fastapi import Query
from pydantic import BaseModel, Field

def a(year: int = 2025, *, audit_year=Query(2024), fiscal_year=Query(default=2023), limit=Query(2022)): ...
def b(): return datetime.now(timezone.utc).year - 1
def c(): return date.today().year
def d(): return dt.datetime.utcnow().year
def e(): return __import__("datetime").datetime.now().year
def f(row): return int(row.audit_year or 2025)
def g(wp): return getattr(wp, "year", None) or 2025
def h(body): return body.get("year", 2025)
def i(x): return getattr(x, "audit_year", 2022)
def j(year): return year if year else 2021
class M(BaseModel):
    year: int = Field(2020)
def k():
    year = 2025
    self_year = 2024
'''
_COUNTED_EXPECTED = Counter({"today": 4, "literal": 11})

_NOT_COUNTED = '''
"""示例：year = 2025、datetime.now().year 写在 docstring 里不计。"""
from datetime import datetime
# year = 2025  注释不计
def a(limit: int = 2025): ...
def b(): return datetime(2024, 1, 1).year
def c(): return range(2000, 2100)
def d(x): return x or 2025
def e(): years = sorted({2024, 2025})
def f(d): return d.get("month", 2025)
def g(row): return row.created_at.year
_MIN_YEAR = 2000
'''


class TestScannerRules:
    def test_counted_forms(self):
        assert scan_source(_COUNTED) == _COUNTED_EXPECTED

    def test_not_counted_forms(self):
        assert scan_source(_NOT_COUNTED) == Counter()

    def test_scan_covers_app(self):
        n_files, _found = scan_app()
        assert n_files > 1000, f"backend/app 只扫到 {n_files} 个 .py ⇒ 扫描根写错"


def _expected_count(rel: str) -> int:
    """文件的期望总数 = 基线 + 豁免。"""
    return BASELINE.get(rel, 0) + (CALENDAR_YEAR_EXEMPT.get(rel, (0,))[0])


class TestRatchet:
    def test_no_new_occurrences(self):
        _n, found = scan_app()
        grown = [
            f"{rel}：期望 {_expected_count(rel)}（基线 {BASELINE.get(rel, 0)} + 豁免 {CALENDAR_YEAR_EXEMPT.get(rel, (0,))[0]}）→ 现算 {sum(c.values())}（{dict(c)}）"
            for rel, c in sorted(found.items())
            if sum(c.values()) > _expected_count(rel)
        ]
        assert not grown, (
            "审计年度请经 app.services.project_audit_year 取，取不到如实报错，不要用今年 / 写死年度兜底；"
            "只是把代码挪到别的文件时，把基线条目一起挪过去：\n  " + "\n  ".join(grown)
        )

    def test_baseline_only_shrinks(self):
        _n, found = scan_app()
        stale = [
            f"{rel}：期望 {n + CALENDAR_YEAR_EXEMPT.get(rel, (0,))[0]} → 现算 {sum(found.get(rel, Counter()).values())}"
            for rel, n in sorted(BASELINE.items())
            if sum(found.get(rel, Counter()).values()) < n + CALENDAR_YEAR_EXEMPT.get(rel, (0,))[0]
        ]
        assert not stale, "已修掉的请把基线下调到现算值（为 0 删掉条目）：\n  " + "\n  ".join(stale)

    def test_baseline_well_formed(self):
        assert list(BASELINE) == sorted(BASELINE), "基线键须排序"
        assert all(isinstance(n, int) and n > 0 for n in BASELINE.values())
        assert sum(BASELINE.values()) <= FROZEN_TOTAL_CAP, "基线总数超过冻结值（挪动可以，净增不行）"

    def test_exempt_table_falsifiable(self):
        """豁免的文件仍命中扫描口径（可证伪）。"""
        _n, found = scan_app()
        missing = [
            f"{rel}：豁免了 {cnt} 处但扫描结果为 0（豁免失效）"
            for rel, (cnt, _reason) in sorted(CALENDAR_YEAR_EXEMPT.items())
            if not found.get(rel)
        ]
        assert not missing, "豁免的文件已不命中扫描口径，请从豁免表中删除：\n  " + "\n  ".join(missing)

    def test_exempt_table_well_formed(self):
        assert list(CALENDAR_YEAR_EXEMPT) == sorted(CALENDAR_YEAR_EXEMPT), "豁免表键须排序"
        assert all(isinstance(cnt, int) and cnt > 0 for cnt, _reason in CALENDAR_YEAR_EXEMPT.values())
