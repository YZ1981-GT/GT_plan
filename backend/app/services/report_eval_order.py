"""报表公式依赖拓扑序（spec income-statement-lower-section-formulas，ADR-ISL-01）。

单体三路（``_generate_report`` / ``regenerate_affected`` / ``recalculate_stale_rows``）与合并路径
``consol_report_values.ordered_rows`` 共用本模块：按 ``ROW`` / ``SUM_ROW`` 建依赖图取拓扑序，解决
「小计行排在明细行之前」时按行号求值必然撞上「引用行未就绪」的问题（国企利润表 IS-007 营业总成本、
IS-053 其他综合收益两段）。环上的行进 :attr:`EvalOrder.cycles`，由 ``report_row_compute.compute_row``
按「循环引用」失败，不求值、不写假数。
"""
from __future__ import annotations

import heapq
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.services.formula_grammar import ROW_PATTERN, SUM_ROW_PATTERN

logger = logging.getLogger(__name__)

REPORT_TYPE_ORDER = (
    "balance_sheet", "income_statement", "cash_flow_statement", "equity_statement",
    "cash_flow_supplement", "impairment_provision",
)


@dataclass(frozen=True)
class EvalOrder:
    """拓扑顺序及真实循环成员；悬空引用留给公式执行层报告。"""

    order: tuple[Any, ...]
    cycles: tuple[str, ...]

    @property
    def positions(self) -> dict[str, int]:
        """行次 → 在拓扑序中的位置；调用方按它给同一张表内的行排序。"""
        return {str(row.row_code): index for index, row in enumerate(self.order)}


def _type(row: Any) -> str:
    raw = getattr(row, "report_type", "")
    return str(getattr(raw, "value", raw))


def _key(row: Any) -> tuple[int, str, int, str]:
    report_type = _type(row)
    try:
        row_number = int(getattr(row, "row_number", 0) or 0)
    except (TypeError, ValueError):
        row_number = 0
    rank = REPORT_TYPE_ORDER.index(report_type) if report_type in REPORT_TYPE_ORDER else len(REPORT_TYPE_ORDER)
    return rank, report_type, row_number, str(getattr(row, "row_code", ""))


def _dependencies(rows: list[Any]) -> dict[str, set[str]]:
    by_code = {str(row.row_code): row for row in rows}
    if len(by_code) != len(rows):
        raise ValueError("报表定义行次重复，无法建立公式依赖图")
    codes = sorted(by_code)
    deps: dict[str, set[str]] = {}
    for code, row in by_code.items():
        formula = str(getattr(row, "formula", "") or "")
        wanted = set(ROW_PATTERN.findall(formula))
        for start, end in SUM_ROW_PATTERN.findall(formula):
            wanted.update(item for item in codes if start <= item <= end)
        deps[code] = wanted & by_code.keys()
    return deps


def _cycle_members(deps: dict[str, set[str]]) -> set[str]:
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: set[str] = set()

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for dep in deps[node]:
            if dep not in indices:
                visit(dep)
                low[node] = min(low[node], low[dep])
            elif dep in on_stack:
                low[node] = min(low[node], indices[dep])
        if low[node] != indices[node]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1 or node in deps[node]:
            cycles.update(component)

    for node in deps:
        if node not in indices:
            visit(node)
    return cycles


def eval_order(rows: Iterable[Any]) -> EvalOrder:
    """按 ROW/SUM_ROW 依赖排序；同入度节点保持报表类型与行号稳定顺序。"""
    items = list(rows)
    by_code = {str(row.row_code): row for row in items}
    deps = _dependencies(items)
    dependents: dict[str, set[str]] = {code: set() for code in deps}
    indegree = {code: len(wanted) for code, wanted in deps.items()}
    for code, wanted in deps.items():
        for dep in wanted:
            dependents[dep].add(code)
    ready = [(_key(by_code[code]), code) for code, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        _, code = heapq.heappop(ready)
        ordered.append(code)
        for target in dependents[code]:
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, (_key(by_code[target]), target))
    remaining = sorted((code for code in deps if code not in ordered), key=lambda code: _key(by_code[code]))
    ordered.extend(remaining)
    cycles = tuple(sorted(_cycle_members(deps), key=lambda code: _key(by_code[code])))
    return EvalOrder(tuple(by_code[code] for code in ordered), cycles)


def plan_for_configs(configs: Iterable[Any]) -> EvalOrder:
    """生产侧入口：行次重复等结构问题不让报表生成整体失败，降级为行号序并记一条告警。

    降级后 ``cycles`` 为空（结构不可解析时不把行判成循环引用），逐行计算退回改动前的行号序语义。
    """
    items = list(configs)
    try:
        return eval_order(items)
    except ValueError as exc:
        logger.warning("报表公式依赖图不可解析（%s），本次按行号顺序求值", exc)
        return EvalOrder(tuple(sorted(items, key=_key)), ())


def order_within_type(rows: Iterable[Any], positions: Mapping[str, int] | None) -> list[Any]:
    """把一张表的行按全局拓扑位置排序；没有位置信息的行退回行号序（跨表顺序仍由调用方的报表类型序决定）。"""
    items = list(rows)
    if not positions:
        return sorted(items, key=_key)
    fallback = len(positions)
    return sorted(items, key=lambda row: (positions.get(str(row.row_code), fallback), _key(row)))
